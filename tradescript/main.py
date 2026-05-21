#!/usr/bin/env python3
# main.py — TradeScript entry point
import sys, os
from lexer import tokenize
from parser import parse
from errors import LexerError, ParseError, TypeError_

def main():
    if len(sys.argv) < 2:
        print("Usage: python main.py <file.trade> [--dump-ast] [--run] [--type-only]")
        sys.exit(1)
    filepath = sys.argv[1]
    dump_ast  = "--dump-ast" in sys.argv
    run_flag  = "--run" in sys.argv
    type_only = "--type-only" in sys.argv
    if not os.path.exists(filepath):
        print(f"Error: File not found: {filepath}")
        sys.exit(1)
    with open(filepath, "r", encoding="utf-8") as f:
        source = f.read()
    try:
        tokens = tokenize(source)
        ast = parse(tokens)
        if dump_ast:
            print("=== AST ===")
            print(ast)
            return
        from type_checker import type_check
        type_check(ast)
        if type_only:
            print(f"OK — {filepath} type check passed.")
            return
        if run_flag:
            try:
                from interpreter import interpret
                interpret(ast)
            except ImportError:
                print("Interpreter not yet implemented.")
                sys.exit(1)
        else:
            print(f"OK — {filepath} parsed and type checked successfully.")
    except LexerError as e:
        print(str(e)); sys.exit(1)
    except ParseError as e:
        print(str(e)); sys.exit(1)
    except TypeError_ as e:
        print(str(e)); sys.exit(1)

if __name__ == "__main__":
    main()
