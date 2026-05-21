# type_checker.py — TradeScript Static Type Checker
# Walks the AST and enforces:
#   - Strong typing with limited coercion (int→float, float*percent→float)
#   - Name equivalence for structured types
#   - Static scoping (variable lookup in lexical scope chain)
#   - Return type consistency in func/indicator
#   - Built-in function signature checking

from ast_nodes import *
from errors import TypeError_


# ─── Type representations ──────────────────────────────────────────────────

# Primitive types are strings: "int", "float", "bool", "string", "percent"
# Array types: "int[]", "float[]", etc.
# Named struct types: "position", "portfolio", "order"
# Void (for statements): "void"

PRIMITIVES = {"int", "float", "bool", "string", "percent"}

# Structured type field definitions (name equivalence — type name matters)
STRUCT_FIELDS = {
    "position": {
        "symbol": "string",
        "shares": "int",
        "entry_price": "float",
        "current_price": "float",
        "dividend": "percent",
        "sector": "string",
    },
    "portfolio": {
        "positions": "position[]",
        "budget": "float",
        "currency": "string",
        "exchange": "string",
    },
    "order": {
        "type": "string",
        "symbol": "string",
        "shares": "int",
        "price": "float",
    },
}

# Built-in function signatures: name -> (param_types, return_type)
BUILTINS = {
    # Trading actions
    "buy":      (["string", "int"], "order"),
    "sell":     (["string", "int"], "order"),
    "sell_all": (["string"], "order"),

    # Technical indicators
    "SMA":           (["string", "int"], "float"),
    "EMA":           (["string", "int"], "float"),
    "RSI":           (["string", "int"], "float"),
    "MACD":          (["string"], "float"),
    "ATR":           (["string", "int"], "float"),
    "BollingerBand": (["string", "int", "string"], "float"),

    # Data retrieval
    "history": (["string", "int"], "float[]"),
    "price":   (["string"], "float"),
    "volume":  (["string", "int"], "float[]"),

    # Risk
    "stopLoss":     (["percent"], "order"),
    "takeProfit":   (["percent"], "order"),
    "valueAtRisk":  (["portfolio", "percent", "int"], "float"),
    "maxDrawdown":  (["portfolio"], "percent"),
    "positionSize": (["float", "percent", "float"], "int"),

    # Helpers
    "avg":    (["float[]"], "float"),
    "sum":    (["float[]"], "float"),
    "max":    (["float[]"], "float"),
    "min":    (["float[]"], "float"),
    "stddev": (["float[]"], "float"),
    "abs":    (["float"], "float"),
}


# ─── Scope (symbol table with lexical chaining) ───────────────────────────

class Scope:
    def __init__(self, parent=None, name="global"):
        self.parent = parent
        self.name = name
        self.symbols = {}  # name -> type_string

    def define(self, name, type_, line=None):
        if name in self.symbols:
            raise TypeError_(f"Redefinition of '{name}' in {self.name} scope", line or 0)
        self.symbols[name] = type_

    def lookup(self, name, line=None):
        if name in self.symbols:
            return self.symbols[name]
        if self.parent:
            return self.parent.lookup(name, line)
        return None  # not found (caller decides how to handle)

    def child(self, name="block"):
        return Scope(parent=self, name=name)


# ─── Coercion rules ───────────────────────────────────────────────────────

def is_array(t):
    return t is not None and t.endswith("[]")

def base_of_array(t):
    return t[:-2] if is_array(t) else t

def coerce_arithmetic(left, right, op, line):
    """
    Apply TradeScript coercion rules for arithmetic operators.
    Returns the result type or raises TypeError_.
    """
    # Identical types
    if left == right:
        if left in ("int", "float"):
            return left
        if left == "percent" and op in ("+", "-"):
            return "percent"
        if left == "percent" and op in ("*", "/"):
            raise TypeError_(f"Cannot {op} two percent values", line)
        raise TypeError_(f"Operator '{op}' not defined for type '{left}'", line)

    # int ↔ float coercion
    if {left, right} == {"int", "float"}:
        return "float"

    # float * percent or percent * float → float
    if op in ("*", "/") and "percent" in (left, right):
        other = right if left == "percent" else left
        if other in ("int", "float"):
            return "float"
        raise TypeError_(f"Cannot {op} '{left}' and '{right}'", line)

    # int * percent or percent * int → float
    if op in ("+", "-") and "percent" in (left, right):
        other = right if left == "percent" else left
        if other in ("int", "float"):
            raise TypeError_(
                f"Cannot {op} '{left}' and '{right}' — percent and numeric types are incompatible for addition/subtraction", line)

    raise TypeError_(f"Operator '{op}' not defined for types '{left}' and '{right}'", line)


def coerce_comparison(left, right, op, line):
    """Check that comparison operands are compatible."""
    if left == right:
        if left in ("int", "float", "percent", "string", "bool"):
            return "bool"
    if {left, right} == {"int", "float"}:
        return "bool"
    if op in ("crosses_above", "crosses_below"):
        if left in ("int", "float") and right in ("int", "float"):
            return "bool"
        raise TypeError_(f"'{op}' requires numeric operands, got '{left}' and '{right}'", line)
    raise TypeError_(f"Cannot compare '{left}' and '{right}' with '{op}'", line)


# ─── Type Checker ──────────────────────────────────────────────────────────

class TypeChecker:
    def __init__(self):
        self.global_scope = Scope(name="global")
        self.errors = []
        # User-defined function/indicator signatures
        self.user_funcs = {}   # name -> (param_types, return_type)
        self.portfolios = {}   # name -> PortfolioDecl
        self.strategies = {}   # name -> StrategyDecl
        self.current_return_type = None  # expected return type during func check

    def check(self, program):
        """Run the type checker on a Program AST. Raises TypeError_ on first error."""
        # Phase 1: Collect all declarations (forward reference support)
        self._collect_declarations(program)
        # Phase 2: Type check each declaration body
        self._check_declarations(program)
        return True  # no errors

    # ─── Phase 1: collect signatures ──────────────────────────────────────

    def _collect_declarations(self, program):
        for decl in program.declarations:
            if isinstance(decl, PortfolioDecl):
                self.portfolios[decl.name] = decl
                self.global_scope.define(decl.name, "portfolio", decl.line)

            elif isinstance(decl, StrategyDecl):
                self.strategies[decl.name] = decl
                # Strategy is a named entity but not a typed value
                self.global_scope.define(decl.name, "strategy", decl.line)

            elif isinstance(decl, (FuncDecl, IndicatorDecl)):
                param_types = [p.type_ for p in decl.params]
                self.user_funcs[decl.name] = (param_types, decl.return_type)
                self.global_scope.define(decl.name, "func", decl.line)

            elif isinstance(decl, SimulateDecl):
                pass  # checked in phase 2
            elif isinstance(decl, ForecastDecl):
                pass
            elif isinstance(decl, RecommendDecl):
                pass
            elif isinstance(decl, BacktestDecl):
                pass
            elif isinstance(decl, RunStmt):
                pass
            elif isinstance(decl, LetStmt):
                # Global let
                val_type = self._check_expr(decl.value, self.global_scope)
                if decl.type_annotation:
                    self._check_type_compat(decl.type_annotation, val_type, decl.line)
                    self.global_scope.define(decl.name, decl.type_annotation, decl.line)
                else:
                    self.global_scope.define(decl.name, val_type, decl.line)
            elif isinstance(decl, ExprStmt):
                pass  # checked in phase 2

    # ─── Phase 2: check bodies ────────────────────────────────────────────

    def _check_declarations(self, program):
        for decl in program.declarations:
            if isinstance(decl, PortfolioDecl):
                self._check_portfolio(decl)
            elif isinstance(decl, StrategyDecl):
                self._check_strategy(decl)
            elif isinstance(decl, (FuncDecl, IndicatorDecl)):
                self._check_func(decl)
            elif isinstance(decl, SimulateDecl):
                self._check_simulate(decl)
            elif isinstance(decl, ForecastDecl):
                self._check_forecast(decl)
            elif isinstance(decl, RecommendDecl):
                self._check_recommend(decl)
            elif isinstance(decl, BacktestDecl):
                self._check_backtest(decl)
            elif isinstance(decl, RunStmt):
                self._check_run(decl)
            elif isinstance(decl, ExprStmt):
                self._check_expr(decl.expr, self.global_scope)

    # ─── Portfolio ────────────────────────────────────────────────────────

    def _check_portfolio(self, decl):
        symbols_seen = set()
        for pos in decl.positions:
            if pos.symbol in symbols_seen:
                raise TypeError_(f"Duplicate position '{pos.symbol}' in portfolio '{decl.name}'", pos.line)
            symbols_seen.add(pos.symbol)
            # Shares must be positive
            if pos.shares <= 0:
                raise TypeError_(f"Shares must be positive, got {pos.shares}", pos.line)
            if pos.entry_price < 0:
                raise TypeError_(f"Entry price cannot be negative", pos.line)

    # ─── Strategy ─────────────────────────────────────────────────────────

    def _check_strategy(self, decl):
        # Verify referenced portfolio exists
        if decl.portfolio_name not in self.portfolios:
            raise TypeError_(f"Portfolio '{decl.portfolio_name}' not defined", decl.line)

        scope = self.global_scope.child(f"strategy:{decl.name}")
        for param in decl.params:
            scope.define(param.name, param.type_, param.line)

        for stmt in decl.body:
            self._check_strategy_stmt(stmt, scope)

    def _check_strategy_stmt(self, stmt, scope):
        if isinstance(stmt, WhenStmt):
            cond_type = self._check_expr(stmt.condition, scope)
            if cond_type != "bool":
                raise TypeError_(f"when condition must be bool, got '{cond_type}'", stmt.line)
            if isinstance(stmt.action, list):
                inner = scope.child("when-block")
                for s in stmt.action:
                    self._check_strategy_stmt(s, inner)
            else:
                self._check_expr(stmt.action, scope)
        elif isinstance(stmt, ApplyStmt):
            self._check_expr(stmt.call, scope)
        elif isinstance(stmt, IfStmt):
            self._check_if(stmt, scope)
        elif isinstance(stmt, ForStmt):
            self._check_for(stmt, scope)
        elif isinstance(stmt, LetStmt):
            self._check_let(stmt, scope)
        elif isinstance(stmt, ExprStmt):
            self._check_expr(stmt.expr, scope)

    # ─── Func / Indicator ─────────────────────────────────────────────────

    def _check_func(self, decl):
        scope = self.global_scope.child(f"func:{decl.name}")
        for param in decl.params:
            scope.define(param.name, param.type_, param.line)

        self.current_return_type = decl.return_type
        for stmt in decl.body:
            self._check_stmt(stmt, scope)
        self.current_return_type = None

    # ─── Simulate / Forecast / Recommend / Backtest ───────────────────────

    def _check_simulate(self, decl):
        if decl.portfolio_name not in self.portfolios:
            raise TypeError_(f"Portfolio '{decl.portfolio_name}' not defined", decl.line)
        if decl.strategy_name and decl.strategy_name not in self.strategies:
            raise TypeError_(f"Strategy '{decl.strategy_name}' not defined", decl.line)

    def _check_forecast(self, decl):
        # Just validate that the symbol is mentioned in some portfolio
        pass  # runtime check

    def _check_recommend(self, decl):
        if decl.portfolio_name not in self.portfolios:
            raise TypeError_(f"Portfolio '{decl.portfolio_name}' not defined", decl.line)

    def _check_backtest(self, decl):
        if decl.strategy_name not in self.strategies:
            raise TypeError_(f"Strategy '{decl.strategy_name}' not defined", decl.line)

    def _check_run(self, decl):
        if decl.portfolio_name not in self.portfolios:
            raise TypeError_(f"Portfolio '{decl.portfolio_name}' not defined", decl.line)
        self._check_expr(decl.call, self.global_scope)

    # ─── Statements ───────────────────────────────────────────────────────

    def _check_stmt(self, stmt, scope):
        if isinstance(stmt, LetStmt):
            self._check_let(stmt, scope)
        elif isinstance(stmt, IfStmt):
            self._check_if(stmt, scope)
        elif isinstance(stmt, ForStmt):
            self._check_for(stmt, scope)
        elif isinstance(stmt, ReturnStmt):
            self._check_return(stmt, scope)
        elif isinstance(stmt, ExprStmt):
            self._check_expr(stmt.expr, scope)
        elif isinstance(stmt, WhenStmt):
            self._check_strategy_stmt(stmt, scope)
        elif isinstance(stmt, ApplyStmt):
            self._check_expr(stmt.call, scope)

    def _check_let(self, stmt, scope):
        val_type = self._check_expr(stmt.value, scope)
        if stmt.type_annotation:
            self._check_type_compat(stmt.type_annotation, val_type, stmt.line)
            scope.define(stmt.name, stmt.type_annotation, stmt.line)
        else:
            if val_type is None:
                raise TypeError_(f"Cannot infer type for '{stmt.name}'", stmt.line)
            scope.define(stmt.name, val_type, stmt.line)

    def _check_if(self, stmt, scope):
        cond_type = self._check_expr(stmt.condition, scope)
        if cond_type != "bool":
            raise TypeError_(f"if condition must be bool, got '{cond_type}'", stmt.line)
        then_scope = scope.child("if-then")
        for s in stmt.then_body:
            self._check_stmt(s, then_scope)
        if stmt.else_body:
            else_scope = scope.child("if-else")
            for s in stmt.else_body:
                self._check_stmt(s, else_scope)

    def _check_for(self, stmt, scope):
        iter_type = scope.lookup(stmt.iterable_name, stmt.line)
        if iter_type is None:
            raise TypeError_(f"Undefined iterable '{stmt.iterable_name}'", stmt.line)

        # For portfolio iteration: each item is a position
        if iter_type == "portfolio":
            elem_type = "position"
        elif is_array(iter_type):
            elem_type = base_of_array(iter_type)
        else:
            raise TypeError_(f"Cannot iterate over '{iter_type}'", stmt.line)

        body_scope = scope.child("for-each")
        body_scope.define(stmt.var_name, elem_type, stmt.line)
        for s in stmt.body:
            self._check_stmt(s, body_scope)

    def _check_return(self, stmt, scope):
        val_type = self._check_expr(stmt.value, scope)
        if self.current_return_type:
            self._check_type_compat(self.current_return_type, val_type, stmt.line)

    # ─── Expressions ──────────────────────────────────────────────────────

    def _check_expr(self, expr, scope):
        """Returns the type string of the expression."""
        if isinstance(expr, IntLiteral):
            return "int"
        if isinstance(expr, FloatLiteral):
            return "float"
        if isinstance(expr, PercentLiteral):
            return "percent"
        if isinstance(expr, StringLiteral):
            return "string"
        if isinstance(expr, BoolLiteral):
            return "bool"

        if isinstance(expr, Identifier):
            t = scope.lookup(expr.name, expr.line)
            if t is None:
                raise TypeError_(f"Undefined variable '{expr.name}'", expr.line)
            return t

        if isinstance(expr, Ticker):
            # Ticker in expression context — treated as string (symbol)
            return "string"

        if isinstance(expr, AssignExpr):
            val_type = self._check_expr(expr.value, scope)
            existing = scope.lookup(expr.name, expr.line)
            if existing is None:
                raise TypeError_(f"Cannot assign to undefined variable '{expr.name}'", expr.line)
            self._check_type_compat(existing, val_type, expr.line)
            return existing

        if isinstance(expr, BinOp):
            return self._check_binop(expr, scope)

        if isinstance(expr, UnaryOp):
            return self._check_unaryop(expr, scope)

        if isinstance(expr, FuncCall):
            return self._check_funccall(expr, scope)

        if isinstance(expr, FieldAccess):
            return self._check_field_access(expr, scope)

        if isinstance(expr, ArrayLiteral):
            return self._check_array_literal(expr, scope)

        raise TypeError_(f"Unknown expression type: {type(expr).__name__}", getattr(expr, 'line', 0))

    def _check_binop(self, expr, scope):
        if expr.op == "[]":
            # Array indexing
            arr_type = self._check_expr(expr.left, scope)
            idx_type = self._check_expr(expr.right, scope)
            if not is_array(arr_type):
                raise TypeError_(f"Cannot index into non-array type '{arr_type}'", expr.line)
            if idx_type != "int":
                raise TypeError_(f"Array index must be int, got '{idx_type}'", expr.line)
            return base_of_array(arr_type)

        left = self._check_expr(expr.left, scope)
        right = self._check_expr(expr.right, scope)

        if expr.op in ("+", "-", "*", "/"):
            return coerce_arithmetic(left, right, expr.op, expr.line)

        if expr.op in (">", "<", ">=", "<=", "==", "!=", "crosses_above", "crosses_below"):
            return coerce_comparison(left, right, expr.op, expr.line)

        if expr.op in ("and", "or"):
            if left != "bool":
                raise TypeError_(f"'{expr.op}' requires bool operands, got '{left}'", expr.line)
            if right != "bool":
                raise TypeError_(f"'{expr.op}' requires bool operands, got '{right}'", expr.line)
            return "bool"

        raise TypeError_(f"Unknown operator '{expr.op}'", expr.line)

    def _check_unaryop(self, expr, scope):
        operand_type = self._check_expr(expr.operand, scope)
        if expr.op == "-":
            if operand_type in ("int", "float", "percent"):
                return operand_type
            raise TypeError_(f"Unary '-' not defined for type '{operand_type}'", expr.line)
        if expr.op == "not":
            if operand_type != "bool":
                raise TypeError_(f"'not' requires bool, got '{operand_type}'", expr.line)
            return "bool"
        raise TypeError_(f"Unknown unary operator '{expr.op}'", expr.line)

    def _check_funccall(self, expr, scope):
        name = expr.name

        # Check built-in first
        if name in BUILTINS:
            param_types, ret_type = BUILTINS[name]
            self._check_call_args(name, param_types, expr.args, scope, expr.line)
            return ret_type

        # Check user-defined func/indicator
        if name in self.user_funcs:
            param_types, ret_type = self.user_funcs[name]
            self._check_call_args(name, param_types, expr.args, scope, expr.line)
            return ret_type

        # Check strategy call (from run)
        if name in self.strategies:
            strat = self.strategies[name]
            param_types = [p.type_ for p in strat.params]
            self._check_call_args(name, param_types, expr.args, scope, expr.line)
            return "void"

        raise TypeError_(f"Undefined function '{name}'", expr.line)

    def _check_call_args(self, name, param_types, args, scope, line):
        if len(args) != len(param_types):
            raise TypeError_(
                f"'{name}' expects {len(param_types)} arguments, got {len(args)}", line)
        for i, (arg, expected) in enumerate(zip(args, param_types)):
            actual = self._check_expr(arg, scope)
            self._check_type_compat(expected, actual, line,
                                     ctx=f"argument {i+1} of '{name}'")

    def _check_field_access(self, expr, scope):
        # Resolve the object type
        if isinstance(expr.obj, str):
            obj_type = scope.lookup(expr.obj, expr.line)
            if obj_type is None:
                raise TypeError_(f"Undefined variable '{expr.obj}'", expr.line)
        elif isinstance(expr.obj, Node):
            obj_type = self._check_expr(expr.obj, scope)
        else:
            raise TypeError_(f"Invalid field access target", expr.line)

        field = expr.field

        # Check struct fields
        if obj_type in STRUCT_FIELDS:
            if field in STRUCT_FIELDS[obj_type]:
                return STRUCT_FIELDS[obj_type][field]
            raise TypeError_(
                f"Type '{obj_type}' has no field '{field}'", expr.line)

        raise TypeError_(f"Cannot access field '{field}' on type '{obj_type}'", expr.line)

    def _check_array_literal(self, expr, scope):
        if not expr.elements:
            return "void[]"  # empty array — type inferred later
        types = [self._check_expr(e, scope) for e in expr.elements]
        # All elements must be the same type (with coercion)
        base = types[0]
        for t in types[1:]:
            if t != base:
                if {t, base} == {"int", "float"}:
                    base = "float"  # coerce
                else:
                    raise TypeError_(
                        f"Mixed types in array literal: '{base}' and '{t}'", expr.line)
        return base + "[]"

    # ─── Type compatibility ───────────────────────────────────────────────

    def _check_type_compat(self, expected, actual, line, ctx=""):
        """Check if actual is compatible with expected (with coercion)."""
        if expected == actual:
            return
        # int → float coercion
        if expected == "float" and actual == "int":
            return
        # Ticker as string
        if expected == "string" and actual == "string":
            return

        prefix = f"In {ctx}: " if ctx else ""
        raise TypeError_(
            f"{prefix}Expected '{expected}', got '{actual}'", line)


# ─── Public API ────────────────────────────────────────────────────────────

def type_check(ast):
    """Run the type checker. Raises TypeError_ on first error."""
    checker = TypeChecker()
    checker.check(ast)
    return True
