# Agentic Python-to-Rust Converter

Converts a constrained Python program to Rust by first establishing a **verified
behavioral baseline** from tests, then translating, compiling, and running every
baseline input through the Rust code. On any compile error or outcome mismatch,
structured feedback goes back to the LLM in a bounded repair loop.

This is Phase 1: pure functions, basic types, minimal stdlib, no C-extension
dependencies. The project is intentionally organized so each concern has one
module and the two test paths converge on one verification pipeline.

---

## Quick start

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp .env.example .env            # add LLM_API_KEY

# Preferred sandbox (Docker-first):
docker build -f docker/Dockerfile.sandbox -t converter-sandbox:latest .

# Run the API:
.venv/bin/uvicorn converter.api.main:app --reload

# Run the React frontend (separate terminal; http://localhost:5173):
cd frontend && npm install && npm run dev

# Run unit tests:
.venv/bin/pytest

# Run the eval suite (needs a real LLM key):
.venv/bin/converter-eval --json
```

If Docker is unavailable, set `SANDBOX_MODE=subprocess` (or leave
`SANDBOX_FALLBACK_TO_SUBPROCESS=true`). The fallback is less isolated; see
[Security](#security). Because Rust builds are offline in every sandbox, the
subprocess fallback also needs the harness dependencies cached once on the host:

```bash
cargo fetch --manifest-path src/converter/sandbox/rust_harness/Cargo.toml
```

The Docker image performs this prefetch during `docker build`.

---

## Architecture

All packages live under `src/converter/`.

```text
api/            FastAPI submit endpoint
agent/          LangGraph state machine (state, routing, graph, nodes, runner)
testing/        Normalized tests, pytest AST ingestion, generation, validation, baseline
errors_map/     Python-exception -> Rust-variant convention (one source of truth)
sandbox/        Docker-first isolated execution for Python and Rust
translation/    Translate/repair prompts and LLM-facing translator
verification/   Differential comparison, per-category scores, pass criteria
observability/  Optional local MLflow tracing
evals/          Benchmark programs and metrics
core/           Config, logging, errors, LLM client, usage tracking, value comparison
tests/          Unit tests for routing, mapping, ingestion, differ, transitions
```

### The cyclic graph

```text
START
  |
  v
route_test_mode
  |-- user/augment --> ingest_tests --+
  |                                   |
  `-- generate -----> generate_tests -+--> validate_tests
                                              |
                                   route_after_validate
                         +--------------------+--------------------+
                  gaps & rounds left                      no gaps / capped
                         |                                        |
                  generate_tests                                  |
                         |                                        |
                  validate_tests                                  |
                         +--------------> capture_baseline <------+
                                                |
                                                v
                                            translate
                                                |
                                                v
                                             compile
                                                |
                                     route_after_compile
                                +---------------+---------------+
                          compile ok                     failed
                                |                            |
                                v                            v
                              verify ---------fail-------> repair
                                |                            |
                                |<------- compile <----------+
                                |
                        route_after_verify
                     +----------+-----------+
              criteria met          failed & attempts left
                     |                       |
                     v                       v
                   report                 repair
                     |
                    END
```

Loop invariants:

- `generate_tests` increments `generation_round`; regeneration stops at
  `max_generation_rounds` or when coverage gaps are empty.
- `repair` increments `attempt`; compile failures and verification mismatches
  both return through `repair -> compile`, capped by `max_attempts`.
- `report` is terminal and records why the run stopped.

### Deep-agent translator

The `translate` and `repair` nodes are backed by a **deep agent** (LangChain
`deepagents`, built on LangGraph) whenever `DEEP_AGENT_ENABLED=true` (default).
Instead of a single prompt, the agent gets an inner autonomous loop with:

- filesystem tools rooted at a temporary crate (`src/user_code.rs` only),
- `build_rust` (cargo through the sandbox executor),
- `run_differential` (the verified baseline through the built binary),
- `read_python_source` and `read_baseline`.

The agent iterates until the build and the baseline pass, then returns the final
`src/user_code.rs`. The outer graph still recompiles and re-verifies that file
deterministically, so the agent never certifies itself. Set
`DEEP_AGENT_ENABLED=false` to fall back to the original single-shot prompters.

The agent's model is an OpenAI-compatible `ChatOpenAI` pointed at
`LLM_BASE_URL`, so DeepSeek needs no code change. Token/latency/cost usage is
collected via a LangChain callback into the same per-run tracker.

---

## The two test paths

### PATH A — user provides pytest tests

1. **ingest_tests** parses a constrained pytest subset with Python's AST into
   `NormalizedTest` objects (function, args, kwargs, category, expected outcome).
2. **validate_tests** runs each normalized test against the **original Python**.
   - Tests that pass become the baseline.
   - Tests that fail are not silently dropped. They are reported in
     `invalid_user_tests` as "fails on original code" and excluded from the
     baseline. This usually means the test is stale or the code has a bug.
3. **augment mode** additionally generates tests for uncovered behavior, then
   validates them with the same rules.

Supported pytest shapes:

```python
assert f(1, 2) == 3
assert 3 == f(1, 2)
assert f(1) == pytest.approx(2.5)
with pytest.raises(ValueError):
    f("bad")
with pytest.raises(ValueError, match="positive"):
    f("-1")
pytest.raises(ValueError, f, "bad")
@pytest.mark.parametrize("x,y,expected", [(1, 2, 3), (3, 4, 7)])
def test_pair(x, y, expected):
    assert add(x, y) == expected
```

Anything else (fixtures, helper calls, classes, unparseable literals,
`assert f(...) is None`, etc.) becomes an `InvalidUserTest` with a reason. It is
never silently skipped.

### PATH B — no tests provided

1. **generate_tests** asks the LLM for structured JSON cases in three categories:
   - `happy_path`: normal expected behavior
   - `edge_case`: empty inputs, zero/negative numbers, large values,
     single-element collections, unicode, etc.
   - `error_condition`: invalid inputs that should raise; records the exact
     Python exception type and an optional message pattern.
2. **validate_tests** runs the generated guesses against Python. Only cases whose
   recorded expectation matches actual Python behavior are kept. Mismatches are
   rejected and the generator is asked to fill remaining gaps, up to
   `max_generation_rounds`.

### Shared pipeline

`capture_baseline` stores the confirmed `input -> value | error` oracle, tagged
with category and source (`user` or `generated`). Translation receives this
baseline as ground truth. Verification runs the same inputs through Rust.

---

## Error-mapping convention

Defined once in `errors_map/mapping.py`, used by both the translation prompt and
the verifier.

| Python exception | Rust `ConvError` variant |
|---|---|
| `ValueError` | `ConvError::ValueError(String)` |
| `TypeError` | `ConvError::TypeError(String)` |
| `KeyError` | `ConvError::KeyError(String)` |
| `IndexError` | `ConvError::IndexError(String)` |
| `ZeroDivisionError` | `ConvError::ZeroDivisionError(String)` |
| `OverflowError` | `ConvError::OverflowError(String)` |
| `ArithmeticError` | `ConvError::ArithmeticError(String)` |
| `AssertionError` | `ConvError::AssertionError(String)` |
| `RuntimeError` | `ConvError::RuntimeError(String)` |
| anything else | `ConvError::Other { python_type, message }` |

Rules:

- Exact class name maps first; then the Python exception MRO is consulted, so
  `UnicodeDecodeError` maps to `ValueError`.
- Verification compares the **variant name** first. The message is checked only
  when a test provides `message_pattern`.
- A Rust **panic always fails**, even when Python raised an exception. Generated
  Rust must return `Err(ConvError::...)`, never panic.
- Timeout and crash outcomes always fail.

---

## Fixed Rust harness

The LLM only writes `src/user_code.rs`. The converter owns everything else:

```text
Cargo.toml
Cargo.lock
src/main.rs           # reads cases.json, calls dispatch, catches panics, writes results.json
src/harness.rs        # Case type plus arg/req_arg/opt_named_arg/ensure_kwargs/json helpers
src/error_prelude.rs  # ConvError enum (injected from errors_map/rust_prelude.rs)
src/user_code.rs      # LLM output
```

Required entry point:

```rust
pub fn dispatch(
    case: &crate::harness::Case,
) -> Result<serde_json::Value, crate::error_prelude::ConvError>
```

The harness catches panics, so a panic is distinguishable from an `Err`. JSON is
the wire format between Python and Rust:

```json
{"test_id":"t1","function":"add","args":[1,2],"kwargs":{}}
```

Value outcomes serialize as `{"kind":"value","value":...}`; errors as
`{"kind":"error","error_variant":"ValueError","message":"..."}`; panics as
`{"kind":"panic"}`.

---

## Supported Python subset (Phase 1)

- Pure module-level functions, no classes, no async, no generators.
- Types: `None`, `bool`, `int`, `float`, `str`, `list`, `tuple` (as JSON arrays),
  `dict[str, T]`.
- Control flow, comprehensions, basic builtins: `len`, `sum`, `min`, `max`,
  `sorted`, `range`, `enumerate`, `zip`, common string/list/dict methods.
- Explicit `raise`, integer arithmetic, floor division/modulo semantics,
  negative indexing, unicode strings.
- No I/O, network, randomness, time, threads, external packages, or C extensions.
- Values must be JSON-serializable; dict keys must be strings; non-finite floats
  are not supported.
- Source limit: 500 lines (enforced in the API and nodes).

---

## Security

Every piece of Python and Rust is untrusted.

**Docker executor (default).** Each command runs in a fresh container with:

- `--network none`
- read-only root filesystem
- writable tmpfs at `/tmp` only
- all capabilities dropped and `no-new-privileges`
- CPU, memory, and PID limits
- hard wall-clock timeout, then `docker rm -f` by unique container name
- host uid/gid so the bind-mounted work directory is writable

Cargo dependencies are fetched once at image build time (`Cargo.lock` included),
then runtime builds run with `CARGO_NET_OFFLINE=true` into a writable copy of the
image's cargo cache.

**Subprocess fallback.** Used only if Docker is unavailable and
`SANDBOX_FALLBACK_TO_SUBPROCESS=true`. It applies CPU and file-size rlimits, a
sanitized environment, a separate process group, and timeouts, but it has **no
network namespace and no memory/PID cap**. Memory and PID isolation are
Docker-only because `RLIMIT_NPROC` is per-user and `RLIMIT_AS` breaks
LLVM/rustc. Do not use the fallback for adversarial input.

Secrets stay out of the sandbox: only `PATH`, locale, Rust toolchain variables,
`HOME`, and explicit env vars are passed.

---

## Configuration

All settings are environment variables (or `.env`). No keys are hard-coded.

| Variable | Default | Purpose |
|---|---|---|
| `LLM_API_KEY` | — | provider key |
| `LLM_BASE_URL` | `https://api.deepseek.com/v1` | OpenAI-compatible endpoint |
| `LLM_MODEL` | `deepseek-chat` | model name |
| `LLM_MAX_RETRIES` | `3` | boundary retries |
| `DEEP_AGENT_ENABLED` | `true` | use the deep-agent translate/repair loop |
| `DEEP_AGENT_MAX_STEPS` | `60` | inner agent recursion (model/tool turns) |
| `SANDBOX_MODE` | `docker` | `docker` or `subprocess` |
| `SANDBOX_IMAGE` | `converter-sandbox:latest` | sandbox image |
| `SANDBOX_FALLBACK_TO_SUBPROCESS` | `true` | fallback when Docker is missing |
| `TEST_TIMEOUT_S` | `5` | per Python test case |
| `COMPILE_TIMEOUT_S` | `60` | cargo build |
| `RUN_TIMEOUT_S` | `120` | Rust differential run |
| `MAX_SOURCE_LINES` | `500` | input limit |
| `MAX_ATTEMPTS` | `3` | repair cap |
| `MAX_GENERATION_ROUNDS` | `2` | regeneration cap |
| `MLFLOW_ENABLED` | `true` | local tracing toggle |
| `MLFLOW_TRACKING_URI` | `sqlite:///mlflow.db` | local trace store |
| `MLFLOW_EXPERIMENT_NAME` | `python-to-rust` | experiment name |
| `PROMPT_COST_PER_1K` / `COMPLETION_COST_PER_1K` | `0` | USD price table |
| `STRICT_THRESHOLD` / `EDGE_CASE_THRESHOLD` | `1.0` / `0.95` | pass criteria |

---

## Tracing

Tracing uses **MLflow** and runs entirely locally: no account, no hosted
service, no collector. Install the optional dependency and inspect traces with
the local MLflow UI:

```bash
.venv/bin/pip install -e '.[tracing]'      # or '.[dev]'
.venv/bin/mlflow ui --backend-store-uri sqlite:///mlflow.db
```

Defaults: `MLFLOW_ENABLED=true`, `MLFLOW_TRACKING_URI=sqlite:///mlflow.db`,
`MLFLOW_EXPERIMENT_NAME=python-to-rust`. SQLite keeps everything in one local
file; MLflow 3.x no longer accepts the legacy file-store backend by default.
Every graph node gets a span with the
run id, attempt/generation-round metadata, and a compact output summary. If
MLflow is not installed or configuration fails, tracing degrades to a no-op and
the conversion still runs. Disable it with `MLFLOW_ENABLED=false`.

---

## API

```bash
curl -s http://localhost:8000/convert \
  -H 'Content-Type: application/json' \
  -d '{
    "python_code": "def add(a, b):\n    return a + b\n",
    "tests": "def test_add():\n    assert add(1, 2) == 3\n",
    "test_mode": "user"
  }'
```

Response contains `run_id`, `status` (`passed` / `failed` / `error`), the final
`rust_code`, and the full `report`:

- per-category pass rates
- source breakdown (user vs generated)
- user tests that failed on the original Python
- repair iterations and generation rounds
- failed differential cases with expected/actual/reason
- compile status and diagnostics
- token/latency/cost usage
- final status and pass-criteria failures

`test_mode` may be omitted: no tests -> `generate`, tests -> `user`. Explicit
`user`/`augment` without tests returns HTTP 400. Oversized input also returns
400. Infrastructure failures (LLM/sandbox) return 502.

---

## Frontend

`frontend/` is a Vite + React + TypeScript app with a VS Code-style workspace:
an explorer for `main.py` / `tests.py`, Monaco editor tabs (Python syntax
highlighting), a bottom Output/Report panel, and the generated Rust opened as a
read-only `user_code.rs` tab.

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173, proxies /convert to :8000
npm run build      # emits frontend/dist, served by FastAPI at /
```

Source files persist in browser storage. `Ctrl/⌘ + Enter` runs a conversion;
test mode and the repair-attempt cap are configurable in the sidebar. Set
`VITE_API_BASE_URL` to point at a non-local API.

---

## Evals

```bash
.venv/bin/converter-eval
.venv/bin/converter-eval --program strings --max-attempts 2 --json
```

Five benchmark programs live in `src/converter/evals/programs/` (some ship user
tests). Metrics: compile rate, per-category match rate, average repair
iterations, generation rounds, test-validation rejection rate, cost per run, and
latency.

---

## Development

```bash
.venv/bin/pytest
.venv/bin/ruff check src tests
.venv/bin/mypy src
```

The unit tests do not call an LLM or Docker. They cover:

- both routing branches and both loop caps
- error mapping, including MRO fallback and unknown exceptions
- differential comparison (values, floats, dict order, bool/int, panic, message
  patterns)
- pytest AST ingestion (asserts, raises, match, approx, parametrize, unsupported
  shapes)
- state transitions and report construction

The end-to-end paths can be smoke-tested with a fake LLM and the subprocess
executor; both were used during development to validate generation, user tests,
augment mode, the repair loop, and Docker execution.

---

## Known limitations / next steps

- Phase 1 is single-file, pure functions, no classes or I/O.
- The pytest subset is deliberately narrow; complex tests are reported, not
  guessed at.
- Coverage is heuristic (category/function presence), not line/branch coverage.
- The API is synchronous; move long runs to a job queue for production.
- Message-pattern checks depend on the Rust message text and are opt-in.
- Large Python integers beyond `i64` must map to `OverflowError`; translation is
  instructed to use checked arithmetic, but this is a common failure mode worth
  testing.
- The subprocess fallback is not a security boundary.
