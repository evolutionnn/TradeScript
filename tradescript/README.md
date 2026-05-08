# TradeScript — Part 1 Implementation

## Requirements
- Python 3.8+
- No external libraries required

## Project Structure
```
tradescript/
├── main.py        # Entry point
├── lexer.py       # Tokeniser
├── parser.py      # Recursive descent parser
├── ast_nodes.py   # AST node classes
├── errors.py      # Error classes
└── tests/
    ├── test1_valid.trade   # Portfolio + Strategy + Simulate
    ├── test2_valid.trade   # func + indicator + for loop + forecast + recommend
    ├── test3_valid.trade   # backtest + complex expressions + let
    ├── error1.trade        # Missing closing brace
    ├── error2.trade        # Lowercase ticker (invalid)
    ├── error3.trade        # Missing -> in when statement
    ├── error4.trade        # Missing return type in func
    └── error5.trade        # Invalid character @
```

## Usage

### Parse a program (check for errors):
```bash
python3 main.py <file.trade>
```

### Parse and dump AST:
```bash
python3 main.py <file.trade> --dump-ast
```

## Examples

### Valid program:
```bash
python3 main.py tests/test1_valid.trade --dump-ast
# Output: === AST === followed by the full AST

python3 main.py tests/test2_valid.trade
# Output: OK — tests/test2_valid.trade parsed successfully.
```

### Invalid programs (with error messages):
```bash
python3 main.py tests/error1.trade
# [Line 6] Parse Error: Unexpected token None inside portfolio block

python3 main.py tests/error2.trade
# [Line 3] Parse Error: Expected 'TICKER' but got 'IDENT' ('aksa')

python3 main.py tests/error3.trade
# [Line 3] Parse Error: Expected '->' after when condition, got 'sell'

python3 main.py tests/error4.trade
# [Line 2] Parse Error: Expected 'OP' but got 'SEP' ('{')

python3 main.py tests/error5.trade
# [Line 3] Lexer Error: Unexpected character '@'
```

## Design Notes

- **Lexer**: Hand-written, single-pass, regex-based tokeniser.
  TICKER ([A-Z]{2,5}) vs IDENT disambiguation is deferred to the parser
  (a TICKER followed by '(' is a function call).

- **Parser**: Hand-written recursive descent. Each EBNF production rule
  maps directly to a parser method. Operator precedence is encoded in the
  grammar hierarchy (parse_or → parse_and → ... → parse_primary).

- **AST**: Each node class in ast_nodes.py corresponds to one grammar rule.
  The __repr__ method produces an indented tree dump for --dump-ast.
