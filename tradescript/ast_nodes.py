# ast_nodes.py — TradeScript AST Node Definitions
# Every grammar rule maps to one or more node classes here.

class Node:
    """Base class for all AST nodes."""
    def __repr__(self):
        return self._pretty(0)

    def _pretty(self, indent):
        name = self.__class__.__name__
        fields = vars(self)
        if not fields:
            return " " * indent + name
        lines = [" " * indent + name]
        for k, v in fields.items():
            if k == "line":
                continue
            prefix = " " * (indent + 2) + f"{k}: "
            if isinstance(v, list):
                if not v:
                    lines.append(prefix + "[]")
                else:
                    lines.append(prefix)
                    for item in v:
                        if isinstance(item, Node):
                            lines.append(item._pretty(indent + 4))
                        else:
                            lines.append(" " * (indent + 4) + repr(item))
            elif isinstance(v, Node):
                lines.append(prefix)
                lines.append(v._pretty(indent + 4))
            else:
                lines.append(prefix + repr(v))
        return "\n".join(lines)


# ─── Program ───────────────────────────────────────────────────────────────

class Program(Node):
    def __init__(self, declarations):
        self.declarations = declarations  # list of declaration nodes


# ─── Portfolio ─────────────────────────────────────────────────────────────

class PortfolioDecl(Node):
    def __init__(self, name, positions, budget, currency, exchange, line=None):
        self.name = name          # str
        self.positions = positions  # list of PositionDecl
        self.budget = budget      # float | None
        self.currency = currency  # str | None  (TICKER)
        self.exchange = exchange  # str | None  (TICKER)
        self.line = line

class PositionDecl(Node):
    def __init__(self, symbol, shares, entry_price, dividend, sector, line=None):
        self.symbol = symbol          # str (TICKER)
        self.shares = shares          # int
        self.entry_price = entry_price  # float
        self.dividend = dividend      # float | None  (percent value)
        self.sector = sector          # str | None
        self.line = line


# ─── Strategy ──────────────────────────────────────────────────────────────

class StrategyDecl(Node):
    def __init__(self, name, params, portfolio_name, body, line=None):
        self.name = name                  # str
        self.params = params              # list of Param
        self.portfolio_name = portfolio_name  # str
        self.body = body                  # list of strategy stmts
        self.line = line

class Param(Node):
    def __init__(self, name, type_, line=None):
        self.name = name    # str
        self.type_ = type_  # str  e.g. "int", "float", "float[]"
        self.line = line

class WhenStmt(Node):
    def __init__(self, condition, action, line=None):
        self.condition = condition  # expr node
        self.action = action        # expr | list of stmts
        self.line = line

class ApplyStmt(Node):
    def __init__(self, call, line=None):
        self.call = call  # FuncCall node
        self.line = line

class RunStmt(Node):
    def __init__(self, call, portfolio_name, line=None):
        self.call = call                  # FuncCall
        self.portfolio_name = portfolio_name  # str
        self.line = line


# ─── Func & Indicator ──────────────────────────────────────────────────────

class FuncDecl(Node):
    def __init__(self, name, params, return_type, body, line=None):
        self.name = name              # str
        self.params = params          # list of Param
        self.return_type = return_type  # str
        self.body = body              # list of stmts
        self.line = line

class IndicatorDecl(Node):
    def __init__(self, name, params, return_type, body, line=None):
        self.name = name
        self.params = params
        self.return_type = return_type
        self.body = body
        self.line = line


# ─── Simulate / Forecast / Recommend / Backtest ────────────────────────────

class SimulateDecl(Node):
    def __init__(self, portfolio_name, strategy_name, params, line=None):
        self.portfolio_name = portfolio_name  # str
        self.strategy_name = strategy_name    # str | None
        self.params = params                  # dict of sim parameters
        self.line = line

class ForecastDecl(Node):
    def __init__(self, symbol, params, line=None):
        self.symbol = symbol  # str (TICKER)
        self.params = params  # dict
        self.line = line

class RecommendDecl(Node):
    def __init__(self, portfolio_name, params, line=None):
        self.portfolio_name = portfolio_name
        self.params = params  # dict
        self.line = line

class BacktestDecl(Node):
    def __init__(self, strategy_name, params, line=None):
        self.strategy_name = strategy_name
        self.params = params  # dict
        self.line = line


# ─── Statements ────────────────────────────────────────────────────────────

class LetStmt(Node):
    def __init__(self, name, type_annotation, value, line=None):
        self.name = name                    # str
        self.type_annotation = type_annotation  # str | None
        self.value = value                  # expr node
        self.line = line

class IfStmt(Node):
    def __init__(self, condition, then_body, else_body, line=None):
        self.condition = condition    # expr node
        self.then_body = then_body    # list of stmts
        self.else_body = else_body    # list of stmts | None
        self.line = line

class ForStmt(Node):
    def __init__(self, var_name, iterable_name, body, line=None):
        self.var_name = var_name          # str
        self.iterable_name = iterable_name  # str
        self.body = body                  # list of stmts
        self.line = line

class ReturnStmt(Node):
    def __init__(self, value, line=None):
        self.value = value  # expr node
        self.line = line

class ExprStmt(Node):
    def __init__(self, expr, line=None):
        self.expr = expr
        self.line = line


# ─── Expressions ───────────────────────────────────────────────────────────

class AssignExpr(Node):
    """IDENT = expr  (right-associative)"""
    def __init__(self, name, value, line=None):
        self.name = name    # str
        self.value = value  # expr node
        self.line = line

class BinOp(Node):
    """Binary operation: left op right"""
    def __init__(self, op, left, right, line=None):
        self.op = op      # str e.g. "+", "crosses_above", "and"
        self.left = left
        self.right = right
        self.line = line

class UnaryOp(Node):
    """Unary operation: op operand"""
    def __init__(self, op, operand, line=None):
        self.op = op          # "-" or "not"
        self.operand = operand
        self.line = line

class FuncCall(Node):
    """function_name(arg1, arg2, ...)"""
    def __init__(self, name, args, line=None):
        self.name = name  # str
        self.args = args  # list of expr nodes
        self.line = line

class FieldAccess(Node):
    """object.field"""
    def __init__(self, obj, field, line=None):
        self.obj = obj      # str or Node (for chained access)
        self.field = field  # str
        self.line = line

class ArrayLiteral(Node):
    """[expr, expr, ...]"""
    def __init__(self, elements, line=None):
        self.elements = elements  # list of expr nodes
        self.line = line

class IntLiteral(Node):
    def __init__(self, value, line=None):
        self.value = value  # int
        self.line = line

class FloatLiteral(Node):
    def __init__(self, value, line=None):
        self.value = value  # float
        self.line = line

class PercentLiteral(Node):
    def __init__(self, value, line=None):
        self.value = value  # float (e.g. 5.0 for 5%)
        self.line = line

class StringLiteral(Node):
    def __init__(self, value, line=None):
        self.value = value  # str (without quotes)
        self.line = line

class BoolLiteral(Node):
    def __init__(self, value, line=None):
        self.value = value  # bool
        self.line = line

class Identifier(Node):
    def __init__(self, name, line=None):
        self.name = name  # str
        self.line = line

class Ticker(Node):
    def __init__(self, name, line=None):
        self.name = name  # str (e.g. "AKSA")
        self.line = line
