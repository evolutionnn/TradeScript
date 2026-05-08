#!/usr/bin/env python3
# main.py — TradeScript entry point
# Usage:
#   python main.py program.trade           # parse and check
#   python main.py program.trade --dump-ast  # parse and print AST

import sys
import os
from lexer import tokenize
from parser import parse
from errors import LexerError, ParseError


def main():
    if len(sys.argv) < 2:
        print("Usage: python main.py <file.trade> [--dump-ast]")
        sys.exit(1)

    filepath = sys.argv[1]
    dump_ast = "--dump-ast" in sys.argv

    if not os.path.exists(filepath):
        print(f"Error: File not found: {filepath}")
        sys.exit(1)

    with open(filepath, "r", encoding="utf-8") as f:
        source = f.read()

    try:
        tokens = tokenize(source)
        ast    = parse(tokens)

        if dump_ast:
            print("=== AST ===")
            print(ast)
        else:
            print(f"OK — {filepath} parsed successfully.")

    except LexerError as e:
        print(str(e))
        sys.exit(1)

    except ParseError as e:
        print(str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
