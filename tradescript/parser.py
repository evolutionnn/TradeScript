# parser.py — TradeScript Recursive Descent Parser
# Each grammar rule is a method. Returns an AST rooted at Program.

from lexer import (Token, TT_KEYWORD, TT_TICKER, TT_IDENT,
                   TT_INT, TT_FLOAT, TT_PERCENT, TT_STRING,
                   TT_BOOL, TT_OP, TT_SEP, TT_EOF)
from ast_nodes import *
from errors import ParseError


class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos    = 0

    # ─── Token helpers ─────────────────────────────────────────────────────

    def current(self):
        return self.tokens[self.pos]

    def peek(self, offset=1):
        idx = self.pos + offset
        if idx < len(self.tokens):
            return self.tokens[idx]
        return self.tokens[-1]  # EOF

    def advance(self):
        tok = self.tokens[self.pos]
        if self.pos < len(self.tokens) - 1:
            self.pos += 1
        return tok

    def expect(self, type_, value=None):
        tok = self.current()
        if tok.type_ != type_:
            raise ParseError(
                f"Expected {type_!r} but got {tok.type_!r} ({tok.value!r})",
                tok.line
            )
        if value is not None and tok.value != value:
            raise ParseError(
                f"Expected {value!r} but got {tok.value!r}",
                tok.line
            )
        return self.advance()

    def match(self, type_, value=None):
        tok = self.current()
        if tok.type_ != type_:
            return False
        if value is not None and tok.value != value:
            return False
        return True

    def match_any(self, *pairs):
        """Match (type, value) pairs — returns True if any match."""
        tok = self.current()
        for type_, value in pairs:
            if tok.type_ == type_ and (value is None or tok.value == value):
                return True
        return False

    def line(self):
        return self.current().line

    # ─── Program ───────────────────────────────────────────────────────────

    def parse(self):
        decls = []
        while not self.match(TT_EOF):
            decls.append(self.parse_declaration())
        return Program(decls)

    def parse_declaration(self):
        tok = self.current()
        if tok.type_ == TT_KEYWORD:
            if tok.value == "portfolio":
                return self.parse_portfolio()
            if tok.value == "strategy":
                return self.parse_strategy()
            if tok.value == "func":
                return self.parse_func()
            if tok.value == "indicator":
                return self.parse_indicator()
            if tok.value == "simulate":
                return self.parse_simulate()
            if tok.value == "forecast":
                return self.parse_forecast()
            if tok.value == "recommend":
                return self.parse_recommend()
            if tok.value == "backtest":
                return self.parse_backtest()
            if tok.value == "run":
                return self.parse_run_stmt()
        # fallthrough — treat as statement
        return self.parse_stmt()

    # ─── Portfolio ─────────────────────────────────────────────────────────

    def parse_portfolio(self):
        ln = self.line()
        self.expect(TT_KEYWORD, "portfolio")
        name = self.expect(TT_IDENT).value
        self.expect(TT_SEP, "{")

        positions = []
        budget = currency = exchange = None

        while not self.match(TT_SEP, "}"):
            if self.match(TT_KEYWORD, "position"):
                positions.append(self.parse_position())
            elif self.match(TT_KEYWORD, "budget"):
                self.advance()
                self.expect(TT_SEP, ":")
                budget = self.expect(TT_FLOAT).value
            elif self.match(TT_KEYWORD, "currency"):
                self.advance()
                self.expect(TT_SEP, ":")
                currency = self.expect(TT_TICKER).value
            elif self.match(TT_KEYWORD, "exchange"):
                self.advance()
                self.expect(TT_SEP, ":")
                exchange = self.expect(TT_TICKER).value
            else:
                tok = self.current()
                raise ParseError(
                    f"Unexpected token {tok.value!r} inside portfolio block",
                    tok.line
                )

        self.expect(TT_SEP, "}")
        return PortfolioDecl(name, positions, budget, currency, exchange, line=ln)

    def parse_position(self):
        ln = self.line()
        self.expect(TT_KEYWORD, "position")
        symbol = self.expect(TT_TICKER).value
        self.expect(TT_SEP, ":")
        shares = self.expect(TT_INT).value
        self.expect(TT_KEYWORD, "shares")
        self.expect(TT_KEYWORD, "at")
        entry_price = self.expect(TT_FLOAT).value

        dividend = sector = None
        if self.match(TT_KEYWORD, "dividend"):
            self.advance()
            self.expect(TT_SEP, ":")
            dividend = self.expect(TT_PERCENT).value
        if self.match(TT_KEYWORD, "sector"):
            self.advance()
            self.expect(TT_SEP, ":")
            sector = self.expect(TT_STRING).value

        return PositionDecl(symbol, shares, entry_price, dividend, sector, line=ln)

    # ─── Strategy ──────────────────────────────────────────────────────────

    def parse_strategy(self):
        ln = self.line()
        self.expect(TT_KEYWORD, "strategy")
        name = self.expect(TT_IDENT).value
        params = []
        if self.match(TT_SEP, "("):
            self.advance()
            params = self.parse_param_list()
            self.expect(TT_SEP, ")")
        self.expect(TT_KEYWORD, "for")
        portfolio_name = self.expect(TT_IDENT).value
        self.expect(TT_SEP, "{")
        body = self.parse_strategy_body()
        self.expect(TT_SEP, "}")
        return StrategyDecl(name, params, portfolio_name, body, line=ln)

    def parse_strategy_body(self):
        stmts = []
        while not self.match(TT_SEP, "}"):
            if self.match(TT_KEYWORD, "when"):
                stmts.append(self.parse_when())
            elif self.match(TT_KEYWORD, "apply"):
                stmts.append(self.parse_apply())
            else:
                stmts.append(self.parse_stmt())
        return stmts

    def parse_when(self):
        ln = self.line()
        self.expect(TT_KEYWORD, "when")
        condition = self.parse_expr()
        if not self.match(TT_OP, "->"):
            tok = self.current()
            raise ParseError(
                f"Expected '->' after when condition, got {tok.value!r}", tok.line)
        self.advance()
        # action: single func call, if-stmt, or block
        if self.match(TT_SEP, "{"):
            self.advance()
            action = self.parse_strategy_body()
            self.expect(TT_SEP, "}")
        elif self.match(TT_KEYWORD, "if"):
            action = self.parse_if()
        else:
            action = self.parse_expr()
        return WhenStmt(condition, action, line=ln)

    def parse_apply(self):
        ln = self.line()
        self.expect(TT_KEYWORD, "apply")
        call = self.parse_func_call_expr()
        return ApplyStmt(call, line=ln)

    def parse_run_stmt(self):
        ln = self.line()
        self.expect(TT_KEYWORD, "run")
        call = self.parse_func_call_expr()
        self.expect(TT_KEYWORD, "on")
        portfolio_name = self.expect(TT_IDENT).value
        return RunStmt(call, portfolio_name, line=ln)

    # ─── Func & Indicator ──────────────────────────────────────────────────

    def parse_func(self):
        ln = self.line()
        self.expect(TT_KEYWORD, "func")
        name = self.expect(TT_IDENT).value
        self.expect(TT_SEP, "(")
        params = self.parse_param_list()
        self.expect(TT_SEP, ")")
        self.expect(TT_OP, "->")
        return_type = self.parse_type()
        self.expect(TT_SEP, "{")
        body = self.parse_stmt_list()
        self.expect(TT_SEP, "}")
        return FuncDecl(name, params, return_type, body, line=ln)

    def parse_indicator(self):
        ln = self.line()
        self.expect(TT_KEYWORD, "indicator")
        name = self.expect(TT_IDENT).value
        self.expect(TT_SEP, "(")
        params = self.parse_param_list()
        self.expect(TT_SEP, ")")
        self.expect(TT_OP, "->")
        return_type = self.parse_type()
        self.expect(TT_SEP, "{")
        body = self.parse_stmt_list()
        self.expect(TT_SEP, "}")
        return IndicatorDecl(name, params, return_type, body, line=ln)

    def parse_param_list(self):
        params = []
        if self.match(TT_SEP, ")"):
            return params
        params.append(self.parse_param())
        while self.match(TT_SEP, ","):
            self.advance()
            params.append(self.parse_param())
        return params

    def parse_param(self):
        ln = self.line()
        tok = self.current()
        if tok.type_ not in (TT_IDENT, TT_KEYWORD):
            raise ParseError(f"Expected parameter name, got {tok.value!r}", tok.line)
        name = self.advance().value
        self.expect(TT_SEP, ":")
        type_ = self.parse_type()
        return Param(name, type_, line=ln)

    def parse_type(self):
        tok = self.current()
        # base type: int | float | bool | string | percent | IDENT
        if tok.type_ == TT_IDENT and tok.value in ("int", "float", "bool", "string", "percent"):
            base = tok.value
            self.advance()
        elif tok.type_ == TT_KEYWORD and tok.value in ("int", "float", "bool", "string", "percent"):
            base = tok.value
            self.advance()
        elif tok.type_ == TT_IDENT:
            base = tok.value
            self.advance()
        else:
            raise ParseError(f"Expected type name, got {tok.value!r}", tok.line)
        # array suffix
        if self.match(TT_SEP, "["):
            self.advance()
            self.expect(TT_SEP, "]")
            return base + "[]"
        return base

    # ─── Simulate / Forecast / Recommend / Backtest ────────────────────────

    def parse_simulate(self):
        ln = self.line()
        self.expect(TT_KEYWORD, "simulate")
        portfolio_name = self.expect(TT_IDENT).value
        strategy_name = None
        if self.match(TT_KEYWORD, "with"):
            self.advance()
            strategy_name = self.expect(TT_IDENT).value
        self.expect(TT_SEP, "{")
        params = self.parse_sim_params()
        self.expect(TT_SEP, "}")
        return SimulateDecl(portfolio_name, strategy_name, params, line=ln)

    def parse_sim_params(self):
        params = {}
        SIM_KEYS = {"from", "horizon", "scenarios", "method",
                    "inflation", "show", "to", "goal", "risk",
                    "min_dividend"}
        while not self.match(TT_SEP, "}"):
            tok = self.current()
            key = tok.value
            if tok.type_ not in (TT_KEYWORD, TT_IDENT) or key not in SIM_KEYS:
                raise ParseError(f"Unknown simulation parameter {key!r}", tok.line)
            self.advance()
            self.expect(TT_SEP, ":")

            if key == "horizon":
                value = self.expect(TT_INT).value
                unit_tok = self.current()
                if unit_tok.type_ in (TT_KEYWORD, TT_IDENT) and unit_tok.value in ("days", "years"):
                    unit = self.advance().value
                else:
                    unit = "days"
                params[key] = (value, unit)
            elif key == "scenarios":
                params[key] = self.expect(TT_INT).value
            elif key == "inflation":
                params[key] = self.expect(TT_PERCENT).value
            elif key == "method":
                tok = self.current()
                if tok.type_ == TT_KEYWORD and tok.value in ("montecarlo", "geometric", "historical"):
                    params[key] = self.advance().value
                elif tok.type_ == TT_STRING:
                    params[key] = self.advance().value
                else:
                    raise ParseError(f"Expected method name, got {tok.value!r}", tok.line)
            elif key == "show":
                params[key] = self.parse_show_list()
            elif key == "min_dividend":
                params[key] = self.expect(TT_PERCENT).value
            else:
                # from, to, goal, risk — string values
                params[key] = self.expect(TT_STRING).value
        return params

    def parse_show_list(self):
        items = []
        tok = self.current()
        # show items are keywords or idents
        while tok.type_ in (TT_KEYWORD, TT_IDENT) and tok.value not in (
                "from", "horizon", "scenarios", "method", "inflation",
                "to", "goal", "risk", "min_dividend", "show"):
            items.append(self.advance().value)
            if self.match(TT_SEP, ","):
                self.advance()
                tok = self.current()
            else:
                break
        return items

    def parse_forecast(self):
        ln = self.line()
        self.expect(TT_KEYWORD, "forecast")
        symbol = self.expect(TT_TICKER).value
        self.expect(TT_SEP, "{")
        params = self.parse_sim_params()
        self.expect(TT_SEP, "}")
        return ForecastDecl(symbol, params, line=ln)

    def parse_recommend(self):
        ln = self.line()
        self.expect(TT_KEYWORD, "recommend")
        self.expect(TT_KEYWORD, "for")
        portfolio_name = self.expect(TT_IDENT).value
        self.expect(TT_SEP, "{")
        params = self.parse_sim_params()
        self.expect(TT_SEP, "}")
        return RecommendDecl(portfolio_name, params, line=ln)

    def parse_backtest(self):
        ln = self.line()
        self.expect(TT_KEYWORD, "backtest")
        strategy_name = self.expect(TT_IDENT).value
        self.expect(TT_SEP, "{")
        params = self.parse_sim_params()
        self.expect(TT_SEP, "}")
        return BacktestDecl(strategy_name, params, line=ln)

    # ─── Statements ────────────────────────────────────────────────────────

    def parse_stmt_list(self):
        stmts = []
        while not self.match(TT_SEP, "}"):
            stmts.append(self.parse_stmt())
        return stmts

    def parse_stmt(self):
        tok = self.current()
        if tok.type_ == TT_KEYWORD:
            if tok.value == "let":
                return self.parse_let()
            if tok.value == "if":
                return self.parse_if()
            if tok.value == "for":
                return self.parse_for()
            if tok.value == "return":
                return self.parse_return()
        return ExprStmt(self.parse_expr(), line=tok.line)

    def parse_let(self):
        ln = self.line()
        self.expect(TT_KEYWORD, "let")
        name = self.expect(TT_IDENT).value
        type_annotation = None
        if self.match(TT_SEP, ":"):
            self.advance()
            type_annotation = self.parse_type()
        self.expect(TT_OP, "=")
        value = self.parse_expr()
        return LetStmt(name, type_annotation, value, line=ln)

    def parse_if(self):
        ln = self.line()
        self.expect(TT_KEYWORD, "if")
        condition = self.parse_expr()
        self.expect(TT_SEP, "{")
        then_body = self.parse_stmt_list()
        self.expect(TT_SEP, "}")
        else_body = None
        if self.match(TT_KEYWORD, "else"):
            self.advance()
            if self.match(TT_KEYWORD, "if"):
                else_body = [self.parse_if()]
            else:
                self.expect(TT_SEP, "{")
                else_body = self.parse_stmt_list()
                self.expect(TT_SEP, "}")
        return IfStmt(condition, then_body, else_body, line=ln)

    def parse_for(self):
        ln = self.line()
        self.expect(TT_KEYWORD, "for")
        self.expect(TT_KEYWORD, "each")
        var_name = self.expect(TT_IDENT).value
        self.expect(TT_KEYWORD, "in")
        iterable_name = self.expect(TT_IDENT).value
        self.expect(TT_SEP, "{")
        body = self.parse_stmt_list()
        self.expect(TT_SEP, "}")
        return ForStmt(var_name, iterable_name, body, line=ln)

    def parse_return(self):
        ln = self.line()
        self.expect(TT_KEYWORD, "return")
        value = self.parse_expr()
        return ReturnStmt(value, line=ln)

    # ─── Expressions ───────────────────────────────────────────────────────
    # Precedence (low → high):
    # assignment (=, right-assoc) → or → and → not → compare → add → mul → unary → primary

    def parse_expr(self):
        """Assignment: IDENT = expr  (right-associative)"""
        # Check if this looks like an assignment: IDENT followed by =
        if (self.match(TT_IDENT) and
                self.peek().type_ == TT_OP and self.peek().value == "="):
            ln = self.line()
            name = self.advance().value   # consume IDENT
            self.advance()               # consume =
            value = self.parse_expr()    # right-recursive for right-assoc
            return AssignExpr(name, value, line=ln)
        return self.parse_or()

    def parse_or(self):
        left = self.parse_and()
        while self.match(TT_KEYWORD, "or"):
            ln = self.line()
            self.advance()
            right = self.parse_and()
            left = BinOp("or", left, right, line=ln)
        return left

    def parse_and(self):
        left = self.parse_not()
        while self.match(TT_KEYWORD, "and"):
            ln = self.line()
            self.advance()
            right = self.parse_not()
            left = BinOp("and", left, right, line=ln)
        return left

    def parse_not(self):
        if self.match(TT_KEYWORD, "not"):
            ln = self.line()
            self.advance()
            return UnaryOp("not", self.parse_not(), line=ln)
        return self.parse_compare()

    def parse_compare(self):
        left = self.parse_add()
        COMPARE_OPS = {">", "<", ">=", "<=", "==", "!=",
                       "crosses_above", "crosses_below"}
        while self.match(TT_OP) and self.current().value in COMPARE_OPS:
            ln = self.line()
            op = self.advance().value
            right = self.parse_add()
            left = BinOp(op, left, right, line=ln)
        return left

    def parse_add(self):
        left = self.parse_mul()
        while self.match(TT_OP) and self.current().value in ("+", "-"):
            ln = self.line()
            op = self.advance().value
            right = self.parse_mul()
            left = BinOp(op, left, right, line=ln)
        return left

    def parse_mul(self):
        left = self.parse_unary()
        while self.match(TT_OP) and self.current().value in ("*", "/"):
            ln = self.line()
            op = self.advance().value
            right = self.parse_unary()
            left = BinOp(op, left, right, line=ln)
        return left

    def parse_unary(self):
        if self.match(TT_OP, "-"):
            ln = self.line()
            self.advance()
            return UnaryOp("-", self.parse_unary(), line=ln)
        return self.parse_primary()

    def parse_primary(self):
        tok = self.current()
        ln  = tok.line

        # Integer literal
        if tok.type_ == TT_INT:
            self.advance()
            return IntLiteral(tok.value, line=ln)

        # Float literal
        if tok.type_ == TT_FLOAT:
            self.advance()
            return FloatLiteral(tok.value, line=ln)

        # Percent literal
        if tok.type_ == TT_PERCENT:
            self.advance()
            return PercentLiteral(tok.value, line=ln)

        # String literal
        if tok.type_ == TT_STRING:
            self.advance()
            return StringLiteral(tok.value, line=ln)

        # Bool literal
        if tok.type_ == TT_BOOL:
            self.advance()
            return BoolLiteral(tok.value, line=ln)

        # Parenthesised expression
        if tok.type_ == TT_SEP and tok.value == "(":
            self.advance()
            expr = self.parse_expr()
            self.expect(TT_SEP, ")")
            return expr

        # Array literal
        if tok.type_ == TT_SEP and tok.value == "[":
            self.advance()
            elements = []
            if not self.match(TT_SEP, "]"):
                elements.append(self.parse_expr())
                while self.match(TT_SEP, ","):
                    self.advance()
                    elements.append(self.parse_expr())
            self.expect(TT_SEP, "]")
            return ArrayLiteral(elements, line=ln)

        # TICKER or IDENT — could be func call or field access
        if tok.type_ in (TT_TICKER, TT_IDENT):
            name = self.advance().value
            node_cls = Ticker if tok.type_ == TT_TICKER else Identifier

            # Function call: name(...)
            if self.match(TT_SEP, "("):
                self.advance()
                args = []
                if not self.match(TT_SEP, ")"):
                    args.append(self.parse_expr())
                    while self.match(TT_SEP, ","):
                        self.advance()
                        args.append(self.parse_expr())
                self.expect(TT_SEP, ")")
                result = FuncCall(name, args, line=ln)
            elif self.match(TT_SEP, "["):
                self.advance()
                index = self.parse_expr()
                self.expect(TT_SEP, "]")
                result = BinOp("[]", node_cls(name, line=ln), index, line=ln)
            elif self.match(TT_SEP, "."):
                self.advance()
                fld = self.expect(TT_IDENT).value
                result = FieldAccess(name, fld, line=ln)
            else:
                result = node_cls(name, line=ln)

            # Chained postfix: .field, [index] after any primary
            while True:
                if self.match(TT_SEP, "."):
                    self.advance()
                    fld = self.expect(TT_IDENT).value
                    result = FieldAccess(result, fld, line=self.line())
                elif self.match(TT_SEP, "["):
                    self.advance()
                    index = self.parse_expr()
                    self.expect(TT_SEP, "]")
                    result = BinOp("[]", result, index, line=self.line())
                else:
                    break
            return result

        # Keyword used as value (e.g. method: montecarlo, or param names like 'shares', 'days')
        if tok.type_ == TT_KEYWORD:
            self.advance()
            if tok.value in ("true", "false"):
                return BoolLiteral(tok.value == "true", line=ln)
            return Identifier(tok.value, line=ln)

        raise ParseError(
            f"Unexpected token {tok.value!r} in expression", tok.line
        )

    def parse_func_call_expr(self):
        """Parse a standalone function call (used by apply and run)."""
        tok = self.current()
        if tok.type_ not in (TT_IDENT, TT_TICKER):
            raise ParseError(f"Expected function name, got {tok.value!r}", tok.line)
        name = self.advance().value
        self.expect(TT_SEP, "(")
        args = []
        if not self.match(TT_SEP, ")"):
            args.append(self.parse_expr())
            while self.match(TT_SEP, ","):
                self.advance()
                args.append(self.parse_expr())
        self.expect(TT_SEP, ")")
        return FuncCall(name, args, line=tok.line)


# ─── Public API ────────────────────────────────────────────────────────────

def parse(tokens):
    return Parser(tokens).parse()
