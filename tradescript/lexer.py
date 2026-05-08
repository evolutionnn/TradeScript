# lexer.py — TradeScript Lexer
# Converts source text into a flat list of (type, value, line) tokens.

import re
from errors import LexerError

# ─── Token types ───────────────────────────────────────────────────────────

KEYWORDS = {
    "portfolio", "strategy", "func", "indicator", "simulate", "forecast",
    "recommend", "backtest", "position", "shares", "at", "dividend",
    "budget", "horizon", "scenarios", "method", "goal", "risk",
    "inflation", "show", "if", "else", "for", "each", "in", "when",
    "run", "apply", "return", "let", "and", "or", "not", "true", "false",
    "over", "montecarlo", "geometric", "historical",
    "with", "on", "currency", "exchange", "sector",
    "from", "to",
}

# Token type constants
TT_KEYWORD    = "KEYWORD"
TT_TICKER     = "TICKER"
TT_IDENT      = "IDENT"
TT_INT        = "INT_LIT"
TT_FLOAT      = "FLOAT_LIT"
TT_PERCENT    = "PERCENT_LIT"
TT_STRING     = "STRING_LIT"
TT_BOOL       = "BOOL_LIT"
TT_OP         = "OP"
TT_SEP        = "SEP"
TT_EOF        = "EOF"


class Token:
    def __init__(self, type_, value, line):
        self.type_  = type_
        self.value  = value
        self.line   = line

    def __repr__(self):
        return f"Token({self.type_}, {self.value!r}, line={self.line})"


# ─── Lexer ─────────────────────────────────────────────────────────────────

# Rules: (compiled_regex, token_type or handler_name)
# Order matters — first match wins.
TOKEN_RULES = [
    # Whitespace — skip
    (re.compile(r'[ \t\r]+'),                   None),
    # Newline — just advance line counter
    (re.compile(r'\n'),                          '__newline__'),
    # Single-line comment
    (re.compile(r'#[^\n]*'),                     None),
    # Multi-line comment
    (re.compile(r'/\*.*?\*/', re.DOTALL),        '__multiline__'),
    # Domain operators (must come before identifiers)
    (re.compile(r'crosses_above'),               TT_OP),
    (re.compile(r'crosses_below'),               TT_OP),
    # Two-char operators
    (re.compile(r'>=|<=|==|!=|->'),              TT_OP),
    # Single-char operators
    (re.compile(r'[+\-*/><!=]'),                 TT_OP),
    # Assignment
    (re.compile(r'='),                           TT_OP),
    # Separators
    (re.compile(r'[(){}\[\],:.]'),               TT_SEP),
    # Percent literal (before float and int)
    (re.compile(r'[0-9]+(?:\.[0-9]+)?%'),        TT_PERCENT),
    # Float literal (before int)
    (re.compile(r'[0-9]+\.[0-9]+'),              TT_FLOAT),
    # Int literal
    (re.compile(r'[0-9]+'),                      TT_INT),
    # String literal
    (re.compile(r'"[^"]*"'),                     TT_STRING),
    # TICKER: 2-5 uppercase letters — checked before IDENT
    (re.compile(r'[A-Z]{2,5}\b'),                TT_TICKER),
    # IDENT / KEYWORD: starts with letter or _
    (re.compile(r'[a-zA-Z_][a-zA-Z0-9_]*'),      '__ident__'),
]


def tokenize(source: str) -> list:
    """
    Convert source string to list of Token objects.
    Raises LexerError on unrecognised characters.
    """
    tokens = []
    pos    = 0
    line   = 1
    length = len(source)

    while pos < length:
        matched = False

        for pattern, tt in TOKEN_RULES:
            m = pattern.match(source, pos)
            if not m:
                continue

            matched = True
            text = m.group(0)
            end  = m.end()

            if tt is None:
                # Whitespace or single-line comment — skip
                pass

            elif tt == '__newline__':
                line += 1

            elif tt == '__multiline__':
                # Count newlines inside block comment
                line += text.count('\n')

            elif tt == '__ident__':
                # Decide: keyword, bool literal, or identifier
                if text in ('true', 'false'):
                    tokens.append(Token(TT_BOOL, text == 'true', line))
                elif text in KEYWORDS:
                    tokens.append(Token(TT_KEYWORD, text, line))
                else:
                    tokens.append(Token(TT_IDENT, text, line))

            elif tt == TT_TICKER:
                # A TICKER that is also a keyword wins as keyword
                if text in KEYWORDS:
                    tokens.append(Token(TT_KEYWORD, text, line))
                else:
                    tokens.append(Token(TT_TICKER, text, line))

            elif tt == TT_PERCENT:
                val = float(text[:-1])  # strip '%'
                tokens.append(Token(TT_PERCENT, val, line))

            elif tt == TT_FLOAT:
                tokens.append(Token(TT_FLOAT, float(text), line))

            elif tt == TT_INT:
                tokens.append(Token(TT_INT, int(text), line))

            elif tt == TT_STRING:
                tokens.append(Token(TT_STRING, text[1:-1], line))  # strip quotes

            else:
                tokens.append(Token(tt, text, line))

            pos = end
            break  # restart from next position

        if not matched:
            raise LexerError(f"Unexpected character {source[pos]!r}", line)

    tokens.append(Token(TT_EOF, None, line))
    return tokens


# ─── Quick test ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    sample = """
# Sample TradeScript program
portfolio myPort {
    position AKSA:  1305 shares at 7.95  dividend: 3.2%  sector: "chemicals"
    position AKSEN: 125  shares at 30.66
    budget:   50000.0
    currency: TRY
    exchange: BIST
}

strategy Crossover(fast: int, slow: int) for myPort {
    when SMA(AKSA, fast) crosses_above SMA(AKSA, slow) -> buy(AKSA, 10)
    when RSI(AKSEN, 14) > 70.0 -> {
        sell(AKSEN, 50)
        apply stopLoss(5%)
    }
    apply takeProfit(15%)
}

simulate myPort with Crossover {
    from:      "2026-05-04"
    horizon:   30 days
    scenarios: 1000
    method:    montecarlo
    show:      expected_value, worst_case, var_95
}
"""
    toks = tokenize(sample)
    for t in toks:
        print(t)
