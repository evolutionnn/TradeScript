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
