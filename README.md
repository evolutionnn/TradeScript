# TradeScript

A custom DSL for trading strategies with a hand-written lexer, recursive descent parser, and AST. (Python)

## Overview

TradeScript is a Domain Specific Language (DSL) designed for describing and executing trading strategies. It features:
- A hand-written lexer
- A recursive descent parser
- An abstract syntax tree (AST)
- 100% Python codebase

## Features

- Define trading strategies in an intuitive, high-level syntax
- Parse strategy code using a robust, hand-built parsing pipeline
- Extensible Python architecture for backtesting and simulation

## Getting Started

1. Clone this repository:

   ```bash
   git clone https://github.com/evolutionnn/TradeScript.git
   cd TradeScript
   ```

2. (Optional) Create a virtual environment:

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Run the parser or lexer (example):

   ```bash
   python main.py
   ```

## Example

```python
# Example strategy in TradeScript DSL
BUY WHEN SMA(CLOSE, 20) CROSSES ABOVE SMA(CLOSE, 50)
SELL WHEN RSI(14) > 70
```

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Please open issues and submit pull requests for bug fixes or new features.

## Author

[evolutionnn](https://github.com/evolutionnn)
