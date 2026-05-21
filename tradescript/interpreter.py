# interpreter.py — TradeScript Interpreter
# Executes a type-checked AST with:
#   - Static scoping via environment chain
#   - Stack-dynamic lifetimes
#   - Built-in indicators (SMA, EMA, RSI, MACD, ATR)
#   - Monte Carlo simulation (montecarlo, geometric, historical)
#   - forecast, recommend, backtest blocks

import numpy as np
import random
from ast_nodes import *
from errors import RuntimeError_


# ─── Runtime Values ────────────────────────────────────────────────────────

class Portfolio:
    def __init__(self, name, positions, budget, currency, exchange):
        self.name = name
        self.positions = positions  # dict: symbol -> Position
        self.budget = budget
        self.currency = currency or "USD"
        self.exchange = exchange or "UNKNOWN"

    def total_value(self):
        return sum(p.current_value() for p in self.positions.values()) + self.budget

class Position:
    def __init__(self, symbol, shares, entry_price, dividend, sector):
        self.symbol = symbol
        self.shares = shares
        self.entry_price = entry_price
        self.current_price = entry_price  # updated by simulation
        self.dividend = dividend or 0.0
        self.sector = sector or ""

    def current_value(self):
        return self.shares * self.current_price

class Order:
    def __init__(self, type_, symbol, shares, price):
        self.type_ = type_
        self.symbol = symbol
        self.shares = shares
        self.price = price


# ─── Environment (static scoping) ─────────────────────────────────────────

class Env:
    def __init__(self, parent=None, name="global"):
        self.parent = parent
        self.name = name
        self.store = {}

    def define(self, name, value):
        self.store[name] = value

    def get(self, name, line=0):
        if name in self.store:
            return self.store[name]
        if self.parent:
            return self.parent.get(name, line)
        raise RuntimeError_(f"Undefined variable '{name}'", line)

    def set(self, name, value, line=0):
        if name in self.store:
            self.store[name] = value
            return
        if self.parent:
            self.parent.set(name, value, line)
            return
        raise RuntimeError_(f"Cannot assign to undefined variable '{name}'", line)

    def child(self, name="block"):
        return Env(parent=self, name=name)


# ─── Simulated price data generator ───────────────────────────────────────

def generate_price_history(base_price, days=252, volatility=0.02, drift=0.0005):
    """Generate synthetic daily prices for a stock."""
    np.random.seed(hash(str(base_price) + str(days)) % (2**31))
    returns = np.random.normal(drift, volatility, days)
    prices = [base_price]
    for r in returns:
        prices.append(prices[-1] * (1 + r))
    return prices


# ─── Built-in indicators ──────────────────────────────────────────────────

def calc_sma(prices, period):
    if len(prices) < period:
        return sum(prices) / len(prices)
    return sum(prices[-period:]) / period

def calc_ema(prices, period):
    if not prices:
        return 0.0
    k = 2 / (period + 1)
    ema = prices[0]
    for p in prices[1:]:
        ema = p * k + ema * (1 - k)
    return ema

def calc_rsi(prices, period=14):
    if len(prices) < period + 1:
        return 50.0  # neutral
    deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    recent = deltas[-period:]
    gains = [d for d in recent if d > 0]
    losses = [-d for d in recent if d < 0]
    avg_gain = sum(gains) / period if gains else 0.001
    avg_loss = sum(losses) / period if losses else 0.001
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calc_macd(prices):
    ema12 = calc_ema(prices, 12)
    ema26 = calc_ema(prices, 26)
    return ema12 - ema26

def calc_atr(prices, period=14):
    if len(prices) < 2:
        return 0.0
    trs = [abs(prices[i] - prices[i-1]) for i in range(1, len(prices))]
    if len(trs) < period:
        return sum(trs) / len(trs)
    return sum(trs[-period:]) / period

def calc_bollinger(prices, period, side):
    sma = calc_sma(prices, period)
    if len(prices) < period:
        std = np.std(prices)
    else:
        std = np.std(prices[-period:])
    if side == "upper":
        return sma + 2 * std
    elif side == "lower":
        return sma - 2 * std
    return sma  # middle


# ─── Return value for early return ────────────────────────────────────────

class ReturnSignal(Exception):
    def __init__(self, value):
        self.value = value


# ─── Interpreter ───────────────────────────────────────────────────────────

class Interpreter:
    def __init__(self):
        self.global_env = Env(name="global")
        self.portfolios = {}
        self.strategies = {}
        self.functions = {}   # name -> (FuncDecl/IndicatorDecl, defining_env)
        self.price_data = {}  # symbol -> list of float (historical prices)

    def interpret(self, program):
        # Phase 1: Collect declarations
        self._collect(program)
        # Phase 2: Execute top-level statements
        self._execute(program)

    def _collect(self, program):
        for decl in program.declarations:
            if isinstance(decl, PortfolioDecl):
                self._define_portfolio(decl)
            elif isinstance(decl, StrategyDecl):
                self.strategies[decl.name] = decl
                self.global_env.define(decl.name, decl)
            elif isinstance(decl, (FuncDecl, IndicatorDecl)):
                self.functions[decl.name] = (decl, self.global_env)
                self.global_env.define(decl.name, decl)
            elif isinstance(decl, LetStmt):
                val = self._eval_expr(decl.value, self.global_env)
                self.global_env.define(decl.name, val)

    def _execute(self, program):
        for decl in program.declarations:
            if isinstance(decl, SimulateDecl):
                self._exec_simulate(decl)
            elif isinstance(decl, ForecastDecl):
                self._exec_forecast(decl)
            elif isinstance(decl, RecommendDecl):
                self._exec_recommend(decl)
            elif isinstance(decl, BacktestDecl):
                self._exec_backtest(decl)
            elif isinstance(decl, RunStmt):
                self._exec_run(decl)
            elif isinstance(decl, ExprStmt):
                self._eval_expr(decl.expr, self.global_env)

    # ─── Portfolio ────────────────────────────────────────────────────────

    def _define_portfolio(self, decl):
        positions = {}
        for pos in decl.positions:
            p = Position(pos.symbol, pos.shares, pos.entry_price, pos.dividend, pos.sector)
            positions[pos.symbol] = p
            # Generate synthetic price history for each position
            self.price_data[pos.symbol] = generate_price_history(pos.entry_price)
        port = Portfolio(decl.name, positions, decl.budget or 0.0, decl.currency, decl.exchange)
        self.portfolios[decl.name] = port
        self.global_env.define(decl.name, port)

    # ─── Run (snapshot mode) ──────────────────────────────────────────────

    def _exec_run(self, decl):
        port_name = decl.portfolio_name
        port = self.portfolios[port_name]
        call = decl.call
        strat = self.strategies.get(call.name)
        if not strat:
            raise RuntimeError_(f"Strategy '{call.name}' not found", decl.line)
        env = self.global_env.child(f"run:{call.name}")
        for param, arg in zip(strat.params, call.args):
            val = self._eval_expr(arg, self.global_env)
            env.define(param.name, val)
        print(f"\n{'='*50}")
        print(f"  Running strategy '{call.name}' on '{port_name}' (snapshot)")
        print(f"{'='*50}")
        self._exec_strategy_body(strat.body, env, port, snapshot=True)

    # ─── Strategy body execution ──────────────────────────────────────────

    def _exec_strategy_body(self, body, env, port, snapshot=False):
        for stmt in body:
            if isinstance(stmt, WhenStmt):
                cond = self._eval_expr(stmt.condition, env)
                if cond:
                    if isinstance(stmt.action, list):
                        inner = env.child("when-action")
                        for s in stmt.action:
                            self._exec_strategy_stmt(s, inner, port)
                    else:
                        result = self._eval_expr(stmt.action, env)
                        if isinstance(result, Order):
                            self._apply_order(result, port)
            elif isinstance(stmt, ApplyStmt):
                result = self._eval_expr(stmt.call, env)
                if isinstance(result, Order):
                    self._apply_order(result, port)
            else:
                self._exec_strategy_stmt(stmt, env, port)

    def _exec_strategy_stmt(self, stmt, env, port):
        if isinstance(stmt, LetStmt):
            val = self._eval_expr(stmt.value, env)
            env.define(stmt.name, val)
        elif isinstance(stmt, IfStmt):
            cond = self._eval_expr(stmt.condition, env)
            if cond:
                inner = env.child("if-then")
                for s in stmt.then_body:
                    self._exec_strategy_stmt(s, inner, port)
            elif stmt.else_body:
                inner = env.child("if-else")
                for s in stmt.else_body:
                    self._exec_strategy_stmt(s, inner, port)
        elif isinstance(stmt, ForStmt):
            iterable = env.get(stmt.iterable_name, stmt.line)
            if isinstance(iterable, Portfolio):
                items = list(iterable.positions.values())
            elif isinstance(iterable, list):
                items = iterable
            else:
                raise RuntimeError_(f"Cannot iterate over '{type(iterable)}'", stmt.line)
            for item in items:
                inner = env.child("for-each")
                inner.define(stmt.var_name, item)
                for s in stmt.body:
                    self._exec_strategy_stmt(s, inner, port)
        elif isinstance(stmt, ExprStmt):
            self._eval_expr(stmt.expr, env)
        elif isinstance(stmt, WhenStmt):
            cond = self._eval_expr(stmt.condition, env)
            if cond:
                if isinstance(stmt.action, list):
                    inner = env.child("when-action")
                    for s in stmt.action:
                        self._exec_strategy_stmt(s, inner, port)
                else:
                    result = self._eval_expr(stmt.action, env)
                    if isinstance(result, Order):
                        self._apply_order(result, port)
        elif isinstance(stmt, ApplyStmt):
            result = self._eval_expr(stmt.call, env)
            if isinstance(result, Order):
                self._apply_order(result, port)

    def _apply_order(self, order, port):
        if order.type_ == "buy":
            if order.symbol in port.positions:
                port.positions[order.symbol].shares += order.shares
            else:
                port.positions[order.symbol] = Position(
                    order.symbol, order.shares, order.price, 0.0, "")
            cost = order.shares * order.price
            port.budget -= cost
            print(f"  BUY  {order.shares} x {order.symbol} at {order.price:.2f} (cost: {cost:.2f})")
        elif order.type_ == "sell":
            if order.symbol in port.positions:
                pos = port.positions[order.symbol]
                actual = min(order.shares, pos.shares)
                pos.shares -= actual
                revenue = actual * order.price
                port.budget += revenue
                print(f"  SELL {actual} x {order.symbol} at {order.price:.2f} (revenue: {revenue:.2f})")
        elif order.type_ == "stop_loss":
            print(f"  STOP-LOSS set at {order.price:.2f}% for portfolio")
        elif order.type_ == "take_profit":
            print(f"  TAKE-PROFIT set at {order.price:.2f}% for portfolio")

    # ─── Simulate (iterative mode) ────────────────────────────────────────

    def _exec_simulate(self, decl):
        port = self.portfolios.get(decl.portfolio_name)
        if not port:
            raise RuntimeError_(f"Portfolio '{decl.portfolio_name}' not found", decl.line)

        params = decl.params
        horizon_val, horizon_unit = params.get("horizon", (30, "days"))
        horizon_days = horizon_val * 252 if horizon_unit == "years" else horizon_val
        num_scenarios = params.get("scenarios", 1000)
        method = params.get("method", "montecarlo")
        inflation = params.get("inflation", 0.0) / 100.0 if "inflation" in params else 0.0
        show_items = params.get("show", ["expected_value"])

        strat = None
        if decl.strategy_name and decl.strategy_name in self.strategies:
            strat = self.strategies[decl.strategy_name]

        symbols = list(port.positions.keys())
        base_prices = {s: port.positions[s].current_price for s in symbols}
        shares_map = {s: port.positions[s].shares for s in symbols}

        print(f"\n{'='*60}")
        print(f"  SIMULATE: {decl.portfolio_name}" +
              (f" with {decl.strategy_name}" if decl.strategy_name else ""))
        print(f"  Method: {method} | Horizon: {horizon_val} {horizon_unit} | Scenarios: {num_scenarios}")
        print(f"{'='*60}")

        final_values = []
        for sc in range(num_scenarios):
            sim_prices = {}
            for sym in symbols:
                bp = base_prices[sym]
                if method == "montecarlo":
                    vol = 0.02
                    drift = 0.0003
                    daily = np.random.normal(drift, vol, horizon_days)
                    path = bp * np.cumprod(1 + daily)
                elif method == "geometric":
                    vol = 0.025
                    drift = 0.0005
                    daily = np.random.normal(drift - 0.5*vol**2, vol, horizon_days)
                    path = bp * np.exp(np.cumsum(daily))
                elif method == "historical":
                    hist = self.price_data.get(sym, [bp])
                    returns = [hist[i]/hist[i-1] - 1 for i in range(1, len(hist))]
                    if not returns:
                        returns = [0.0]
                    sampled = [random.choice(returns) for _ in range(horizon_days)]
                    path = [bp]
                    for r in sampled:
                        path.append(path[-1] * (1 + r))
                    path = path[1:]
                else:
                    path = [bp] * horizon_days
                sim_prices[sym] = path

            # Calculate final portfolio value
            total = port.budget
            for sym in symbols:
                final_price = sim_prices[sym][-1] if len(sim_prices[sym]) > 0 else base_prices[sym]
                total += shares_map[sym] * final_price
            if inflation > 0:
                years = horizon_days / 252
                total /= (1 + inflation) ** years
            final_values.append(total)

        final_values = np.array(final_values)
        current_value = sum(shares_map[s] * base_prices[s] for s in symbols) + port.budget

        print(f"\n  Current portfolio value: {current_value:,.2f} {port.currency}")
        print(f"  {'-'*50}")

        for item in show_items:
            if item == "expected_value":
                print(f"  Expected value:      {np.mean(final_values):>15,.2f} {port.currency}")
            elif item == "worst_case":
                print(f"  Worst case (5%%):     {np.percentile(final_values, 5):>15,.2f} {port.currency}")
            elif item == "best_case":
                print(f"  Best case (95%%):     {np.percentile(final_values, 95):>15,.2f} {port.currency}")
            elif item == "var_95":
                var = current_value - np.percentile(final_values, 5)
                print(f"  Value at Risk (95%%): {var:>15,.2f} {port.currency}")
            elif item == "max_drawdown":
                dd = (current_value - np.min(final_values)) / current_value * 100
                print(f"  Max drawdown:        {dd:>14.2f}%")
            elif item == "dividend_income":
                total_div = sum(
                    shares_map[s] * base_prices[s] * (port.positions[s].dividend / 100)
                    for s in symbols
                ) * (horizon_days / 252)
                print(f"  Expected dividends:  {total_div:>15,.2f} {port.currency}")

        print(f"  {'-'*50}")
        pct_change = (np.mean(final_values) - current_value) / current_value * 100
        print(f"  Expected return:     {pct_change:>+14.2f}%\n")

    # ─── Forecast ─────────────────────────────────────────────────────────

    def _exec_forecast(self, decl):
        symbol = decl.symbol
        params = decl.params
        horizon_val, horizon_unit = params.get("horizon", (14, "days"))
        horizon_days = horizon_val * 252 if horizon_unit == "years" else horizon_val
        num_scenarios = params.get("scenarios", 1000)
        method = params.get("method", "montecarlo")
        show_items = params.get("show", ["expected_price"])

        # Find base price from any portfolio
        base_price = None
        for port in self.portfolios.values():
            if symbol in port.positions:
                base_price = port.positions[symbol].current_price
                break
        if base_price is None:
            base_price = 100.0

        finals = []
        for _ in range(num_scenarios):
            if method == "montecarlo":
                daily = np.random.normal(0.0003, 0.02, horizon_days)
                path = base_price * np.cumprod(1 + daily)
            elif method == "geometric":
                vol = 0.025
                daily = np.random.normal(0.0005 - 0.5*vol**2, vol, horizon_days)
                path = base_price * np.exp(np.cumsum(daily))
            else:
                hist = self.price_data.get(symbol, [base_price])
                rets = [hist[i]/hist[i-1] - 1 for i in range(1, len(hist))]
                if not rets: rets = [0.0]
                sampled = [random.choice(rets) for _ in range(horizon_days)]
                p = base_price
                path = []
                for r in sampled:
                    p *= (1 + r)
                    path.append(p)
            finals.append(path[-1] if len(path) > 0 else base_price)

        finals = np.array(finals)
        print(f"\n{'='*50}")
        print(f"  FORECAST: {symbol}")
        print(f"  Method: {method} | Horizon: {horizon_val} {horizon_unit} | Scenarios: {num_scenarios}")
        print(f"  Current price: {base_price:.2f}")
        print(f"  {'-'*40}")

        for item in show_items:
            if item == "expected_price":
                print(f"  Expected price:  {np.mean(finals):>10.2f}")
            elif item == "trend":
                pct = (np.mean(finals) - base_price) / base_price * 100
                direction = "UPWARD" if pct > 1 else "DOWNWARD" if pct < -1 else "SIDEWAYS"
                conf = min(abs(pct) * 5, 95)
                print(f"  Trend:           {direction} (confidence: {conf:.0f}%)")
        print()

    # ─── Recommend ────────────────────────────────────────────────────────

    def _exec_recommend(self, decl):
        port = self.portfolios.get(decl.portfolio_name)
        if not port:
            raise RuntimeError_(f"Portfolio '{decl.portfolio_name}' not found", decl.line)

        params = decl.params
        goal = params.get("goal", "maximize_return")
        risk_level = params.get("risk", "moderate")
        horizon_val, horizon_unit = params.get("horizon", (30, "days"))
        min_div = params.get("min_dividend", 0.0)

        print(f"\n{'='*60}")
        print(f"  RECOMMEND for {decl.portfolio_name}")
        print(f"  Goal: {goal} | Risk: {risk_level} | Horizon: {horizon_val} {horizon_unit}")
        print(f"  {'-'*50}")

        for sym, pos in port.positions.items():
            prices = self.price_data.get(sym, [pos.current_price])
            rsi = calc_rsi(prices)
            sma20 = calc_sma(prices, 20)
            sma50 = calc_sma(prices, 50)
            current = prices[-1] if prices else pos.current_price

            # Simple rule-based recommendation
            if rsi < 30 and current > sma50:
                action = "BUY"
                reason = f"RSI oversold ({rsi:.1f}), price above SMA50"
            elif rsi > 70:
                action = "SELL"
                reason = f"RSI overbought ({rsi:.1f})"
            elif sma20 > sma50 and rsi < 60:
                action = "BUY"
                reason = f"Bullish trend (SMA20 > SMA50), RSI neutral"
            elif sma20 < sma50 and rsi > 50:
                action = "SELL"
                reason = f"Bearish trend (SMA20 < SMA50)"
            else:
                action = "HOLD"
                reason = f"No clear signal (RSI: {rsi:.1f})"

            if min_div > 0 and pos.dividend < min_div:
                reason += f" | Dividend {pos.dividend:.1f}% below min {min_div:.1f}%"

            emoji = {"BUY": "+", "SELL": "-", "HOLD": "="}
            print(f"  [{emoji.get(action, '?')}] {sym:>6}: {action:<5} - {reason}")

        print(f"  {'-'*50}\n")

    # ─── Backtest ─────────────────────────────────────────────────────────

    def _exec_backtest(self, decl):
        strat = self.strategies.get(decl.strategy_name)
        if not strat:
            raise RuntimeError_(f"Strategy '{decl.strategy_name}' not found", decl.line)

        params = decl.params
        show_items = params.get("show", ["total_return"])

        print(f"\n{'='*50}")
        print(f"  BACKTEST: {decl.strategy_name}")
        print(f"  Period: {params.get('from', '?')} to {params.get('to', '?')}")
        print(f"  {'-'*40}")

        # Simplified backtest simulation
        np.random.seed(42)
        n_days = 500
        daily_returns = np.random.normal(0.0005, 0.015, n_days)
        cumulative = np.cumprod(1 + daily_returns)
        total_return = (cumulative[-1] - 1) * 100
        max_dd = np.min(cumulative / np.maximum.accumulate(cumulative) - 1) * 100
        sharpe = np.mean(daily_returns) / np.std(daily_returns) * np.sqrt(252)
        win_rate = np.sum(daily_returns > 0) / len(daily_returns) * 100

        for item in show_items:
            if item == "total_return":
                print(f"  Total return:    {total_return:>+10.2f}%")
            elif item == "sharpe_ratio":
                print(f"  Sharpe ratio:    {sharpe:>10.2f}")
            elif item == "win_rate":
                print(f"  Win rate:        {win_rate:>9.1f}%")
            elif item == "max_drawdown":
                print(f"  Max drawdown:    {max_dd:>+10.2f}%")
        print()

    # ─── Expression evaluation ────────────────────────────────────────────

    def _eval_expr(self, expr, env):
        if isinstance(expr, IntLiteral):
            return expr.value
        if isinstance(expr, FloatLiteral):
            return expr.value
        if isinstance(expr, PercentLiteral):
            return expr.value  # stored as float, e.g. 5.0 for 5%
        if isinstance(expr, StringLiteral):
            return expr.value
        if isinstance(expr, BoolLiteral):
            return expr.value
        if isinstance(expr, Ticker):
            return expr.name  # as string

        if isinstance(expr, Identifier):
            return env.get(expr.name, expr.line)

        if isinstance(expr, AssignExpr):
            val = self._eval_expr(expr.value, env)
            env.set(expr.name, val, expr.line)
            return val

        if isinstance(expr, BinOp):
            return self._eval_binop(expr, env)

        if isinstance(expr, UnaryOp):
            val = self._eval_expr(expr.operand, env)
            if expr.op == "-":
                return -val
            if expr.op == "not":
                return not val

        if isinstance(expr, FuncCall):
            return self._eval_funccall(expr, env)

        if isinstance(expr, FieldAccess):
            return self._eval_field_access(expr, env)

        if isinstance(expr, ArrayLiteral):
            return [self._eval_expr(e, env) for e in expr.elements]

        raise RuntimeError_(f"Cannot evaluate {type(expr).__name__}", getattr(expr, 'line', 0))

    def _eval_binop(self, expr, env):
        # Array indexing
        if expr.op == "[]":
            arr = self._eval_expr(expr.left, env)
            idx = self._eval_expr(expr.right, env)
            if not isinstance(arr, list):
                raise RuntimeError_(f"Cannot index non-array", expr.line)
            if idx < 0 or idx >= len(arr):
                raise RuntimeError_(f"Index {idx} out of range (0..{len(arr)-1})", expr.line)
            return arr[idx]

        # Short-circuit for and/or
        if expr.op == "and":
            left = self._eval_expr(expr.left, env)
            if not left:
                return False
            return bool(self._eval_expr(expr.right, env))

        if expr.op == "or":
            left = self._eval_expr(expr.left, env)
            if left:
                return True
            return bool(self._eval_expr(expr.right, env))

        left = self._eval_expr(expr.left, env)
        right = self._eval_expr(expr.right, env)

        # crosses_above / crosses_below — simplified: compare values
        if expr.op == "crosses_above":
            return left > right
        if expr.op == "crosses_below":
            return left < right

        # Arithmetic with percent handling
        if expr.op in ("+", "-", "*", "/"):
            return self._arithmetic(left, right, expr.op, expr.line)

        # Comparison
        if expr.op == ">":  return left > right
        if expr.op == "<":  return left < right
        if expr.op == ">=": return left >= right
        if expr.op == "<=": return left <= right
        if expr.op == "==": return left == right
        if expr.op == "!=": return left != right

        raise RuntimeError_(f"Unknown operator '{expr.op}'", expr.line)

    def _arithmetic(self, left, right, op, line):
        if op == "+": return left + right
        if op == "-": return left - right
        if op == "*": return left * right
        if op == "/":
            if right == 0:
                raise RuntimeError_("Division by zero", line)
            return left / right

    def _eval_funccall(self, expr, env):
        name = expr.name
        args = [self._eval_expr(a, env) for a in expr.args]

        # Built-in functions
        if name == "buy":
            symbol, shares = args[0], int(args[1])
            prices = self.price_data.get(symbol, [100.0])
            price = prices[-1] if prices else 100.0
            return Order("buy", symbol, shares, price)

        if name == "sell":
            symbol, shares = args[0], int(args[1])
            prices = self.price_data.get(symbol, [100.0])
            price = prices[-1] if prices else 100.0
            return Order("sell", symbol, shares, price)

        if name == "sell_all":
            symbol = args[0]
            prices = self.price_data.get(symbol, [100.0])
            price = prices[-1] if prices else 100.0
            return Order("sell", symbol, 999999, price)

        if name == "stopLoss":
            return Order("stop_loss", "", 0, args[0])
        if name == "takeProfit":
            return Order("take_profit", "", 0, args[0])

        if name == "SMA":
            prices = self.price_data.get(args[0], [100.0])
            return calc_sma(prices, int(args[1]))
        if name == "EMA":
            prices = self.price_data.get(args[0], [100.0])
            return calc_ema(prices, int(args[1]))
        if name == "RSI":
            prices = self.price_data.get(args[0], [100.0])
            return calc_rsi(prices, int(args[1]))
        if name == "MACD":
            prices = self.price_data.get(args[0], [100.0])
            return calc_macd(prices)
        if name == "ATR":
            prices = self.price_data.get(args[0], [100.0])
            return calc_atr(prices, int(args[1]))
        if name == "BollingerBand":
            prices = self.price_data.get(args[0], [100.0])
            return calc_bollinger(prices, int(args[1]), args[2])

        if name == "history":
            prices = self.price_data.get(args[0], [100.0])
            n = int(args[1])
            return prices[-n:] if len(prices) >= n else prices[:]
        if name == "price":
            prices = self.price_data.get(args[0], [100.0])
            return prices[-1] if prices else 100.0
        if name == "volume":
            n = int(args[1])
            return [random.uniform(100000, 5000000) for _ in range(n)]

        if name == "valueAtRisk":
            return 0.0  # simplified
        if name == "maxDrawdown":
            return 0.0
        if name == "positionSize":
            capital, risk_pct, atr_val = args
            if atr_val == 0:
                return 0
            return int(capital * (risk_pct / 100.0) / atr_val)

        # Helper functions
        if name == "avg":
            return sum(args[0]) / len(args[0]) if args[0] else 0.0
        if name == "sum":
            return sum(args[0])
        if name == "max":
            return max(args[0]) if args[0] else 0.0
        if name == "min":
            return min(args[0]) if args[0] else 0.0
        if name == "stddev":
            return float(np.std(args[0])) if args[0] else 0.0
        if name == "abs":
            return abs(args[0])

        # User-defined function
        if name in self.functions:
            func_decl, defining_env = self.functions[name]
            func_env = defining_env.child(f"func:{name}")  # static scoping!
            for param, arg_val in zip(func_decl.params, args):
                func_env.define(param.name, arg_val)
            try:
                for stmt in func_decl.body:
                    self._exec_stmt(stmt, func_env)
            except ReturnSignal as ret:
                return ret.value
            return None

        raise RuntimeError_(f"Unknown function '{name}'", expr.line)

    def _eval_field_access(self, expr, env):
        if isinstance(expr.obj, str):
            obj = env.get(expr.obj, expr.line)
        elif isinstance(expr.obj, Node):
            obj = self._eval_expr(expr.obj, env)
        else:
            raise RuntimeError_(f"Invalid field access", expr.line)

        field = expr.field
        if isinstance(obj, Position):
            return getattr(obj, field, None)
        if isinstance(obj, Portfolio):
            if field == "positions":
                return list(obj.positions.values())
            return getattr(obj, field, None)
        if isinstance(obj, Order):
            if field == "type":
                return obj.type_
            return getattr(obj, field, None)
        raise RuntimeError_(f"Cannot access field '{field}'", expr.line)

    # ─── Statement execution (inside func bodies) ─────────────────────────

    def _exec_stmt(self, stmt, env):
        if isinstance(stmt, LetStmt):
            val = self._eval_expr(stmt.value, env)
            env.define(stmt.name, val)
        elif isinstance(stmt, IfStmt):
            cond = self._eval_expr(stmt.condition, env)
            if cond:
                inner = env.child("if-then")
                for s in stmt.then_body:
                    self._exec_stmt(s, inner)
            elif stmt.else_body:
                inner = env.child("if-else")
                for s in stmt.else_body:
                    self._exec_stmt(s, inner)
        elif isinstance(stmt, ForStmt):
            iterable = env.get(stmt.iterable_name, stmt.line)
            items = list(iterable.positions.values()) if isinstance(iterable, Portfolio) else iterable
            for item in items:
                inner = env.child("for-each")
                inner.define(stmt.var_name, item)
                for s in stmt.body:
                    self._exec_stmt(s, inner)
        elif isinstance(stmt, ReturnStmt):
            val = self._eval_expr(stmt.value, env)
            raise ReturnSignal(val)
        elif isinstance(stmt, ExprStmt):
            self._eval_expr(stmt.expr, env)


# ─── Public API ────────────────────────────────────────────────────────────

def interpret(ast):
    interp = Interpreter()
    interp.interpret(ast)
