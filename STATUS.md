# Project Status — Agentic Python-to-Rust Converter

Last updated: 2026-11-09
Phase: **Phase 1 complete + deep-agent translator** (implementation, tests,
Docker sandbox, README, LangChain deep agent)

Use this file as the resume point for the next session. It records what exists,
what was verified, the design decisions that must not be undone accidentally,
and the known gaps.

---

## 1. Confirmed decisions

These were explicitly chosen and are now implemented:

| Decision | Choice |
|---|---|
| Package layout | `src/` layout (`src/converter/...`) |
| Sandbox | Docker-first, subprocess fallback when Docker is unavailable |
| User test ingestion | Constrained Python AST parser (not executing pytest) |
| Rust harness | Fixed converter-owned harness; LLM writes only `src/user_code.rs` |
| State model | Pydantic `ConverterState` inside LangGraph `StateGraph` |
| LLM provider | OpenAI-compatible client, DeepSeek defaults |
| Translator | LangChain **deep agent** for translate/repair by default; single-shot prompters retained behind `DEEP_AGENT_ENABLED=false` |
| Deep-agent tool boundary | `FilesystemBackend` rooted at the temp crate; agent writes only `src/user_code.rs`; cargo/run go through `SandboxExecutor` |
| Deep-agent certification | Outer graph always recompiles/re-verifies the agent's file; the agent never certifies itself |
| Tracing | Optional local MLflow; no hosting/account; no-op if disabled |

---

## 2. Current verification snapshot

Run from the project root:

```bash
.venv/bin/pytest -q
.venv/bin/ruff check src tests
.venv/bin/mypy src
```

Last results:

- `pytest`: **57 passed**
- `ruff`: clean
- `mypy`: clean (63 source files)
- Docker image `converter-sandbox:latest`: **built and present**
- Wheel packaging: verified that `rust_harness/src/*.rs`, `Cargo.lock`,
  `rust_prelude.rs`, and eval programs are included

Manual and live end-to-end checks already performed:

- Docker sandbox: Python validation works; Rust build/run works.
- Subprocess fallback: Python validation works; offline Rust build/run works
  after dependencies were fetched on this machine.
- Fake-LLM graph run: generate → validate → translate → compile → verify passed.
- Fake-LLM repair run: bad translation → verification failure → repair → passed
  at attempt 1.
- User-test path: stale user test reported as invalid and excluded; run passed.
- Augment path: user tests + generated edge test; run passed.
- **Live DeepSeek API call:** success (key loaded from `.env`, `deepseek-chat`
  endpoint reachable).
- **Live user-test conversion** (`add`, 3 tests): passed, compile ok, 3/3,
  0 repairs, 1 LLM call.
- **Live generated-test conversion** (`safe_divide`, 12 tests incl. error):
  passed, compile ok, 12/12, 0 repairs, 1 generation round, 2 LLM calls.
- **FastAPI `POST /convert`:** HTTP 200, status `passed`, correct report.
- **MLflow tracing:** traces persisted to `sqlite:///mlflow.db`; all node span
  names present (`ingest_tests`, `generate_tests`, `validate_tests`,
  `capture_baseline`, `translate`, `compile`, `verify`, `report`).
- **Eval CLI** (`strings`, `validators`): 2/2 passed, compile rate 1.0,
  overall match 1.0, 0 repairs. The only invalid user test is the intentional
  stale test in `strings_tests.py`.
- **Deep-agent integration (scripted model, no network):** the agent wrote
  `/src/user_code.rs` through the filesystem backend, then `run_deep_agent`
  read it back, validated `fn dispatch`, and cleaned up the temp workdir.
- **Deep-agent usage accounting:** a scripted two-call run recorded
  `llm_calls=2` with prompt/completion tokens into `UsageTracker` through the
  LangChain callback handler.
- **Deep-agent dependency build:** `create_deep_agent` accepted the
  `FilesystemBackend`, custom tools, and a `ChatOpenAI`-style model; path
  traversal is rejected and absolute-looking paths stay inside the temp crate.
- **Not yet done:** a live provider end-to-end run through the deep-agent path
  (see Known gaps).

Eval fixture bugs were found and fixed during live verification: three
`count_vowels` expectations were wrong (non-ASCII `é` is not counted by the
implementation). The remaining invalid test is intentional.

---

## 3. Source tree

```text
src/converter/
├── agent/
│   ├── state.py            # ConverterState, Report, Diagnostic
│   ├── services.py         # Services container / dependency injection
│   ├── routing.py          # conditional edges
│   ├── graph.py            # StateGraph wiring + tracing wrapper
│   ├── deepagent.py        # deep-agent translator: filesystem backend, tools,
│   │                       #   ChatOpenAI bridge, usage callback, invoke/cleanup
│   ├── runner.py           # ConversionRequest, run_conversion orchestration
│   └── nodes/
│       ├── ingest_tests.py
│       ├── generate_tests.py
│       ├── validate_tests.py
│       ├── capture_baseline.py
│       ├── translate.py
│       ├── compile.py
│       ├── verify.py
│       ├── repair.py
│       └── report.py
├── testing/
│   ├── models.py           # NormalizedTest, BaselineCase, PythonOutcome, enums
│   ├── analysis.py         # public function signatures, source line limit
│   ├── pytest_ingest.py    # constrained AST pytest parser
│   ├── generation.py       # structured categorized generation
│   ├── validation.py       # validate tests against original Python
│   ├── baseline.py         # confirmed input -> outcome snapshot
│   └── coverage.py         # heuristic regeneration gaps
├── errors_map/
│   ├── mapping.py          # single Python-exception -> Rust-variant source of truth
│   └── rust_prelude.rs     # injected ConvError enum + methods
├── sandbox/
│   ├── executor.py         # Docker executor + subprocess fallback
│   ├── python_runner.py    # sandboxed Python validation batch
│   ├── rust_runner.py      # cargo build + differential run; prepare_workdir
│   │                       #   and build_existing support the deep agent
│   └── rust_harness/
│       ├── Cargo.toml
│       ├── Cargo.lock
│       └── src/{main.rs,harness.rs}
├── translation/
│   ├── prompts.py          # translate + repair prompts
│   └── translator.py       # LLM-facing translate/repair + code validation
├── verification/
│   ├── models.py           # RustActual, MatchResult, FailureCase
│   ├── differ.py           # value/error/panic comparison
│   └── scoring.py          # category scoring + PassCriteria
├── observability/tracing.py
├── evals/
│   ├── programs/           # 5 benchmark programs, 2 with user tests
│   ├── metrics.py
│   └── runner.py
├── core/
│   ├── config.py
│   ├── logging.py
│   ├── errors.py
│   ├── llm.py
│   ├── usage.py
│   ├── values.py
│   └── parsing.py
└── api/
    ├── main.py
    └── schemas.py
```

Other files:

- `pyproject.toml`, `.env.example`, `.gitignore`, `README.md`, `STATUS.md`
- `docker/Dockerfile.sandbox`, `docker/sandbox-entrypoint.sh`
- `tests/` (57 tests)
- `agents.md` (original requirements)

---

## 4. Implemented requirements checklist

### Pipeline and paths

- [x] User tests normalized into a shared normalized test-case model.
- [x] User tests validated against original Python.
- [x] User tests that fail on original Python reported as invalid, not dropped.
- [x] Generated tests for no-test mode, categorized as happy/edge/error.
- [x] Generated test validation against Python; mismatches rejected.
- [x] Regeneration loop capped by `max_generation_rounds`.
- [x] Augment mode: user tests + generated gap fillers.
- [x] Baseline capture with category + source tags.
- [x] Translation to Rust.
- [x] Sandboxed compile.
- [x] Differential verification with value and error outcomes.
- [x] Repair loop on compile errors and mismatches, capped by `max_attempts`.
- [x] Deep-agent translator/repairer with filesystem, build, and differential
      tools; enabled by default with a single-shot fallback.
- [x] Configurable pass criteria (overall + per category).
- [x] Final report with per-category rates, source breakdown, invalid user tests,
      repair iterations, final Rust code, usage/cost/latency.

### Architecture

- [x] `agent/` LangGraph state machine with cycles and test-mode branch.
- [x] `testing/` normalized model, AST ingestion, generation, validation, baseline.
- [x] `errors_map/` single source of truth used by prompt and verifier.
- [x] `sandbox/` Docker-first untrusted execution for Python and Rust.
- [x] `translation/` translate + repair prompts with structured feedback,
      including the deep-agent system/task prompts.
- [x] `agent/deepagent.py` LangChain deep agent for translate/repair: sandboxed
      filesystem backend, `build_rust`/`run_differential` tools, DeepSeek
      `ChatOpenAI` bridge, and callback-based usage accounting.
- [x] `verification/` differential comparison and scoring.
- [x] `observability/` local MLflow tracing wrapper (Langfuse replaced by
      request; local `mlflow.db` + MLflow UI).
- [x] `evals/` 5 benchmark programs + metrics.
- [x] `core/` config, logging, errors, LLM retries, usage tracking.
- [x] `api/` FastAPI submit endpoint.
- [x] `tests/` routing, transitions, error mapping, ingestion, differ, tracing.
- [x] README with architecture, paths, mapping, subset, security, run guide.

---

## 5. Important contracts (do not change casually)

### Python runner JSON output

```json
{"test_id":"t1","kind":"value","value":3}
{"test_id":"t2","kind":"error","exception_type":"ZeroDivisionError",
 "exception_mro":["ZeroDivisionError","ArithmeticError","Exception","BaseException","object"],
 "message":"division by zero"}
{"test_id":"t3","kind":"timeout"}
{"test_id":"t4","kind":"unsupported","message":"..."}
```

### Rust harness input/output

Input cases:

```json
{"test_id":"t1","function":"add","args":[1,2],"kwargs":{}}
```

Rust output rows:

```json
{"test_id":"t1","kind":"value","value":3}
{"test_id":"t2","kind":"error","error_variant":"ValueError","message":"..."}
{"test_id":"t3","kind":"panic"}
```

### LLM Rust entry point

The LLM must provide `src/user_code.rs` containing:

```rust
pub fn dispatch(
    case: &crate::harness::Case,
) -> Result<serde_json::Value, crate::error_prelude::ConvError>
```

Helpers available: `arg`, `opt_arg`, `req_arg`, `opt_named_arg`, `kwarg`,
`opt_kwarg`, `ensure_kwargs`, `json`.

### Error mapping

Python exception names map to same-named `ConvError` variants. MRO fallback is
used for subclasses. Unknown exceptions map to
`ConvError::Other { python_type, message }`. Panics always fail, even when an
error was expected.

### Deep-agent boundary

- The agent owns only `src/user_code.rs`. Harness files and the error prelude
  stay converter-owned.
- Its filesystem backend is `FilesystemBackend(root_dir=<temp crate>,
  virtual_mode=True)`: `/` maps to the temp crate and `..` traversal is
  rejected, so paths like `/etc/passwd` resolve inside the crate, not the host.
- All command execution goes through `SandboxExecutor`; the agent has no direct
  shell. `build_rust` compiles in place; `run_differential` reuses the verified
  baseline and scoring.
- `run_deep_agent` seeds prior code for repair, reads the final file, rejects the
  placeholder or a file lacking `fn dispatch`, and deletes the workdir.
- The outer `compile`/`verify` nodes rebuild a fresh crate and re-run the
  baseline, so the agent's internal result is advisory only.

---

## 6. Configuration defaults

| Setting | Default |
|---|---|
| `SANDBOX_MODE` | `docker` |
| `SANDBOX_IMAGE` | `converter-sandbox:latest` |
| `SANDBOX_FALLBACK_TO_SUBPROCESS` | `true` |
| `TEST_TIMEOUT_S` | `5` |
| `COMPILE_TIMEOUT_S` | `60` |
| `RUN_TIMEOUT_S` | `120` |
| `MAX_SOURCE_LINES` | `500` |
| `MAX_ATTEMPTS` | `3` |
| `MAX_GENERATION_ROUNDS` | `2` |
| `DEEP_AGENT_ENABLED` | `true` |
| `DEEP_AGENT_MAX_STEPS` | `60` (inner-agent recursion limit) |
| Pass criteria | overall 1.0; happy 1.0; error 1.0; edge 0.95 |
| `LLM_BASE_URL` | `https://api.deepseek.com/v1` |
| `LLM_MODEL` | `deepseek-chat` |
| `MLFLOW_ENABLED` | `true` |
| `MLFLOW_TRACKING_URI` | `sqlite:///mlflow.db` |
| `MLFLOW_EXPERIMENT_NAME` | `python-to-rust` |

---

## 7. Commands

```bash
# Setup
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp .env.example .env            # set LLM_API_KEY

# Docker sandbox (preferred)
docker build -f docker/Dockerfile.sandbox -t converter-sandbox:latest .

# Optional: subprocess fallback dependency cache (already done on this machine)
cargo fetch --manifest-path src/converter/sandbox/rust_harness/Cargo.toml

# Checks
.venv/bin/pytest -q
.venv/bin/ruff check src tests
.venv/bin/mypy src

# API
.venv/bin/uvicorn converter.api.main:app --reload

# Local tracing UI (traces write to ./mlflow.db by default)
.venv/bin/mlflow ui --backend-store-uri sqlite:///mlflow.db

# Evals (needs a real LLM key)
.venv/bin/converter-eval --json
.venv/bin/converter-eval --program strings --max-attempts 2 --json
```

---

## 8. Environment notes from this session

- `.venv/` exists and has all dependencies installed (`.[dev]`, including
  `mlflow`, plus `deepagents` and `langchain-openai` added for the deep agent).
- Installing `deepagents` upgraded `langgraph` to `1.2.20` and added `langchain`;
  all existing tests still pass against it.
- Tracing backend is local MLflow; traces go to `./mlflow.db` (ignored by git).
- Docker daemon is accessible; `converter-sandbox:latest` is built.
- Host Rust toolchain is available; harness dependencies were fetched into the
  host cargo cache.
- `Cargo.lock` is committed in the harness directory and used by the Docker
  image prefetch. Runtime builds are offline.
- `src/agentic_py2rust.egg-info/` and `__pycache__` directories exist locally;
  they are ignored by `.gitignore`.
- A live `LLM_API_KEY` was configured in `.env` and real DeepSeek calls/evals
  succeeded (see section 2). The deep-agent path itself has only been exercised
  with scripted models so far.

---

## 9. Gotchas encountered (already handled)

1. **`RLIMIT_NPROC` is per-user**, not per-process. Applying the Docker PID cap
   in the subprocess fallback throttled cargo's thread pool. It was removed from
   the fallback; PID isolation is Docker-only.
2. **`RLIMIT_AS` breaks LLVM/rustc** by preventing pthread stack reservation.
   It was removed from the subprocess fallback; memory isolation is Docker-only.
3. **Rustup needs `RUSTUP_HOME`/`CARGO_HOME`**, not just `HOME`. The fallback
   sanitizer now points them at the real host directories.
4. **Docker build order:** offline mode must be enabled *after* `cargo fetch`,
   otherwise the image build cannot resolve serde.
5. **Wheel package data** needs explicit patterns for nested files:
   `rust_harness/src/*.rs`, not just `rust_harness/*.rs`.
6. **Eval programs must be a package** (`__init__.py`) to be included in the
   wheel; the discovery logic skips `__init__.py`.
7. **Tracing was switched from Langfuse to local MLflow** at the user's request.
   This supersedes the Langfuse references still present in the original
   `agents.md` requirements. MLflow is optional at runtime; if absent, tracing
   is a no-op.
8. **`FilesystemBackend(virtual_mode=True)` is what keeps deep-agent paths
   contained.** A path like `/etc/passwd` is rewritten under the temp crate;
   `..` raises `Path traversal not allowed`. Do not switch to a non-virtual
   backend for untrusted generated code.
9. **Deep agents bypass `TrackedLLM`,** so token/latency/cost tracking is done by
   `UsageCallbackHandler` (`on_chat_model_start`/`on_llm_end`) instead of the
   custom LLM wrapper.
10. **`ChatOpenAI` must use chat completions, not the Responses API.** The model
    is built with `use_responses_api=False` so DeepSeek stays OpenAI-compatible.
11. **The deep agent must not self-certify.** `translate`/`repair` return its file,
    but the outer graph still compiles and differentially verifies it.

---

## 10. Known gaps / limitations

- Phase 1 subset only: pure module-level functions, basic JSON-compatible types,
  no classes, async, generators, I/O, network, randomness, or external packages.
- Non-finite floats, non-string dict keys, and Python tuples as distinct types
  are unsupported; tuples are treated as JSON arrays.
- User-test parser is intentionally narrow. Unsupported shapes are reported, not
  executed as pytest.
- Coverage gaps are heuristic (function/category presence), not line/branch.
- Message-pattern checks can be strict because Rust message text may differ.
- API is synchronous; long conversions should move to a job queue.
- LLM/sandbox errors raised inside the graph become a report with
  `status="error"` (HTTP 200). Only pre-graph input errors are 400 and service
  construction failures are 502. Consider mapping infrastructure failures to 502
  with an attached report in a future pass.
- Subprocess fallback is not a security boundary.
- The deep-agent path has not yet been run end-to-end against a live provider
  (only scripted-model integration tests). Its quality/cost vs. the single-shot
  translator is unmeasured.
- The deep agent's inner loop is bounded only by `DEEP_AGENT_MAX_STEPS`; there
  is no separate overall wall-clock budget for the inner loop.
- Deep-agent internals are not individually spanned in MLflow yet; only the
  enclosing `translate`/`repair` node span is recorded.
- `deepagents` pulls additional provider packages (Anthropic/Google) even though
  only the OpenAI-compatible path is used.
- No authentication/rate limiting on the API.
- No CI configuration yet.

---

## 11. Suggested next-session priorities

1. Run the deep-agent path against the live provider (`DEEP_AGENT_ENABLED=true`)
   and compare compile rate, match rate, repair iterations, and cost against the
   single-shot baseline (`DEEP_AGENT_ENABLED=false`).
2. Turn the fake-LLM smoke scripts into repeatable integration tests (subprocess
   executor, no real provider) for both paths and the repair loop.
3. Decide whether infrastructure failures inside the graph should surface as
   HTTP 502 while still returning the partial report.
4. Add `pytest-asyncio`-style/class-based test support or broaden the ingester
   deliberately.
5. Improve coverage heuristics (per-function edge/error requirements, branch
   awareness).
6. Add a job queue + polling endpoint for long-running conversions.
7. Add CI (ruff, mypy, pytest, optional Docker build).
8. Add a pricing table for DeepSeek so cost reporting is meaningful.

---

## 12. Where to start reading

For a fast orientation:

1. `README.md` — architecture and usage.
2. `src/converter/agent/state.py` — all state fields.
3. `src/converter/agent/graph.py` — graph shape and loops.
4. `src/converter/agent/routing.py` — branch/loop conditions.
5. `src/converter/agent/deepagent.py` — deep-agent tools, backend, usage callback.
6. `src/converter/testing/pytest_ingest.py` — the supported pytest subset.
7. `src/converter/sandbox/executor.py` — security model.
8. `src/converter/verification/differ.py` — differential rules.
9. `src/converter/translation/prompts.py` — translation/repair/deep-agent contracts.
