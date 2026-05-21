# errors.py — TradeScript Error Classes

class TradeScriptError(Exception):
    """Base error class."""
    pass

class LexerError(TradeScriptError):
    def __init__(self, message, line):
        self.line = line
        super().__init__(f"[Line {line}] Lexer Error: {message}")

class ParseError(TradeScriptError):
    def __init__(self, message, line):
        self.line = line
        super().__init__(f"[Line {line}] Parse Error: {message}")

class TypeError_(TradeScriptError):
    def __init__(self, message, line):
        self.line = line
        super().__init__(f"[Line {line}] Type Error: {message}")

class RuntimeError_(TradeScriptError):
    def __init__(self, message, line=0):
        self.line = line
        super().__init__(f"[Line {line}] Runtime Error: {message}")
