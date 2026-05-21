# TradeScript — Complete DSL Compiler & Interpreter (Part 1 & 2)

TradeScript is a domain-specific language (DSL) designed for stock market portfolio analysis, trading strategy definition, and Monte Carlo-based risk simulation. This repository contains the complete compiler front-end (lexer, parser, type checker) and the back-end runtime execution engine (interpreter).

## Key Features

- **Robust Front-End:** Hand-written, single-pass lexical analyzer and recursive descent parser.
- **Strong Static Type Checker:** 
  - Resolves forward references between top-level declarations in two passes.
  - Implements static scoping with environment chains.
  - Enforces strict type compatibility rules, including implicit conversions (e.g., `int` → `float`, `float * percent` → `float`) and custom primitive/record type equivalence.
  - Implements **Name Equivalence** for structured record types (`portfolio`, `position`, `order`) to prevent semantic bugs.
- **Dynamic Interpreter & Back-End:**
  - Standard variables (`let` statements) and static scoping binding environments.
  - Snapshot execution mode (`run` statement) to evaluate strategies at a single point in time.
  - Iterative execution mode (`simulate`, `backtest`) to evaluate rules step-by-step over historical or simulated price histories.
- **Advanced Monte Carlo Engine (NumPy Vectorized):**
  - **`montecarlo`**: Price simulation based on randomized daily normal returns.
  - **`geometric`**: Geometric Brownian Motion (GBM) producing mathematically rigorous log-normal price paths.
  - **`historical`**: Resampling/bootstrap simulation from actual historical returns of the portfolio assets.
- **Rich Technical Analysis Toolkit:**
  - Built-in indicators: `SMA` (Simple Moving Average), `EMA` (Exponential Moving Average), `RSI` (Relative Strength Index), `MACD` (Moving Average Convergence Divergence), `ATR` (Average True Range), and `BollingerBand`.
  - Math helpers: `avg`, `sum`, `max`, `min`, `stddev`, `abs`.
  - Core trading actions: `buy()`, `sell()`, `sell_all()`, `stopLoss()`, `takeProfit()`.

---

## Requirements

- **Python 3.9+**
- **NumPy** (for vectorized Monte Carlo computations)

To install dependencies:
```bash
pip install numpy
```

---

## Project Structure

```
tradescript/
├── main.py              # Unified entry point
├── lexer.py             # Hand-written tokeniser
├── parser.py            # Recursive descent parser
├── ast_nodes.py         # Abstract Syntax Tree node classes
├── type_checker.py      # Two-phase static type checker
├── interpreter.py       # Execution runtime & Monte Carlo engine
├── errors.py            # Custom compiler and runtime error classes
├── README.md            # Project documentation
└── tests/               # Test suites
    ├── test1_valid.trade     # Valid: Portfolio + Strategy (Crossover) + Simulate
    ├── test2_valid.trade     # Valid: func + indicator + for loops + forecast + recommend
    ├── test3_valid.trade     # Valid: backtest + let + simulate (historical)
    ├── error1.trade          # Syntax Error: Missing closing brace
    ├── error2.trade          # Syntax Error: Lowercase ticker (invalid)
    ├── error3.trade          # Syntax Error: Missing -> in when statement
    ├── error4.trade          # Syntax Error: Missing return type in func
    ├── error5.trade          # Lexical Error: Invalid character @
    ├── type_error1.trade     # Type Error: Implicit coercion violation (percent + float)
    ├── type_error2.trade     # Type Error: Return type mismatch in user-defined indicator
    └── type_error3.trade     # Type Error: Record type name equivalence violation
```

---

## Usage & Commands

All compiler stages are unified in `main.py`.

### 1. Type-Check and Parse Only
Verify syntactic and type correctness of a TradeScript program:
```bash
python main.py tests/test1_valid.trade --type-only
# Output: OK — tests/test1_valid.trade type check passed.
```

### 2. View Abstract Syntax Tree (AST)
Dump the parsed AST structure:
```bash
python main.py tests/test1_valid.trade --dump-ast
```

### 3. Run Interpreter
Execute the full runtime engine (evaluates all commands such as `run`, `simulate`, `forecast`, `recommend`, and `backtest`):
```bash
python main.py tests/test1_valid.trade --run
```

---

## Output Examples

### 1. Monte Carlo Portfolio Simulation (`--run` on `test1_valid.trade`)
```
============================================================
  SIMULATE: myPort with Crossover
  Method: montecarlo | Horizon: 30 days | Scenarios: 1000
============================================================

  Current portfolio value: 73,587.25 TRY
  --------------------------------------------------
  Expected value:            70,571.59 TRY
  Worst case (5%):           68,163.89 TRY
  Value at Risk (95%):        5,423.36 TRY
  --------------------------------------------------
  Expected return:              -4.10%
```

### 2. Technical Recommendation Engine (`--run` on `test2_valid.trade`)
```
============================================================
  RECOMMEND for techPort
  Goal: maximize_return | Risk: moderate | Horizon: 90 days
  --------------------------------------------------
  [+]  ASELS: BUY   - Bullish trend (SMA20 > SMA50), RSI neutral | Dividend 1.5% below min 2.0%
  [=]  KCHOL: HOLD  - No clear signal (RSI: 29.8)
  --------------------------------------------------
```

### 3. Static Type Error Detection (`main.py` on `type_error1.trade`)
```bash
python main.py tests/type_error1.trade
# Output: [Line 6] Type Error: Cannot add percent and float. Coercion rules reject this.
```

---

## Technical Design & Architecture

### Two-Phase Type Checking
To support flexible coding without rigid ordering requirements, the type checker uses a **two-phase symbol resolution** strategy:
1. **Signature Gathering (Phase 1):** Scans the AST to collect signatures of all top-level elements (`portfolio`, `strategy`, `func`, `indicator`) and populates the global symbol table.
2. **Body Verification (Phase 2):** Performs visitor-pattern-based type checking on all statements, local let-bindings, and expressions using static scoping rules.

### Name Equivalence Semantics
TradeScript strictly adheres to **Name Equivalence** for record types. Even if two structures define identical field lists, they are treated as fundamentally distinct types if their declared names differ:
- A variable of type `position` cannot be assigned to or used in place of an `order` record, protecting against critical domain-logic bugs in strategy execution.

### Vectorized Simulation Back-End
The simulation engine runs at high performance by vectorizing prices over all scenarios using **NumPy arrays** (`scenarios` × `horizon` dimension broadcasting), bringing execution times under ~700ms for large-scale portfolios and 1000+ scenarios.
