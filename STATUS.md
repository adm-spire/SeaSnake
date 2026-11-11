# Project Status — Agentic Python-to-C Converter

Last updated: 2026-11-11
Phase: **Phase 1 complete + deep-agent translator + React frontend**, retargeted
from Rust to C (implementation, tests, Docker sandbox, docs, VS Code-style UI)

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
| C harness | Fixed converter-owned harness; LLM writes only `src/user_code.c` |
| State model | Pydantic `ConverterState` inside LangGraph `StateGraph` |
| LLM provider | OpenAI-compatible client, DeepSeek defaults |
| Translator | LangChain **deep agent** for translate/repair by default; single-shot prompters retained behind `DEEP_AGENT_ENABLED=false` |
| Deep-agent tool boundary | `FilesystemBackend` rooted at the temp C project; agent writes only `src/user_code.c`; make/run go through `SandboxExecutor` |
| Deep-agent certification | Outer graph always recompiles/re-verifies the agent's file; the agent never certifies itself |
| Tracing | Optional local MLflow; no hosting/account; no-op if disabled |

---

## 2. Current verification snapshot

Run from the project root:

```bash
.venv/bin/pytest -q
.venv/bin/ruff check src tests
.venv/bin/mypy src
cd frontend && npm run build
```

Last results (after the C retarget):

- `pytest`: **57 passed**
- `ruff`: clean
- `mypy`: clean (63 source files)
- `npm run build` (`frontend/`): clean Vite production build
- C harness: compiled with the host `cc`; JSON value/error/crash outcomes verified
- Subprocess executor end-to-end: real `make` build + differential run passed for
  value, error, and integer-overflow cases
- Wheel packaging: `c_harness/src/*.c`, `c_harness/src/*.h`,
  `c_harness/Makefile`, and `c_prelude.h` are included
- Docker: `docker/Dockerfile.sandbox` uses Alpine 3.20
  (`gcc`, `musl-dev`, `make`, `python3`); `converter-sandbox:latest` is rebuilt
  at **284 MB** (down from 1.33 GB) and C build/run plus Python were verified
  through `DockerSandboxExecutor`

Earlier checks (performed before the C retarget; re-run on C when convenient):

- Fake-LLM graph run: generate -> validate -> translate -> compile -> verify passed.
- Fake-LLM repair run: bad translation -> verification failure -> repair -> passed.
- User-test path, augment path, `POST /convert`, MLflow tracing, and the eval CLI.
- Live DeepSeek API calls succeeded (key loaded from `.env`, `deepseek-chat`).
- Deep-agent integration with a scripted model wrote `src/user_code.c`, ran
  `build_c`/`run_differential`, and cleaned up the workdir.
- A live provider end-to-end run through the deep-agent path is still outstanding.

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
│   ├── mapping.py          # single Python-exception -> C-variant source of truth
│   └── c_prelude.h         # injected ConvErrorKind enum
├── sandbox/
│   ├── executor.py         # Docker executor + subprocess fallback
│   ├── python_runner.py    # sandboxed Python validation batch
│   ├── c_runner.py         # make build + differential run; prepare_workdir
│   │                       #   and build_existing support the deep agent
│   └── c_harness/
│       ├── Makefile
│       └── src/{main.c,harness.c,harness.h,user_code.h}
├── translation/
│   ├── prompts.py          # translate + repair prompts
│   └── translator.py       # LLM-facing translate/repair + code validation
├── verification/
│   ├── models.py           # ActualOutcome, MatchResult, FailureCase
│   ├── differ.py           # value/error/crash comparison
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
- `docker/Dockerfile.sandbox`
- `frontend/` (Vite + React + Monaco UI)
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
- [x] Translation to C.
- [x] Sandboxed compile.
- [x] Differential verification with value and error outcomes.
- [x] Repair loop on compile errors and mismatches, capped by `max_attempts`.
- [x] Deep-agent translator/repairer with filesystem, build, and differential
      tools; enabled by default with a single-shot fallback.
- [x] Configurable pass criteria (overall + per category).
- [x] Final report with per-category rates, source breakdown, invalid user tests,
      repair iterations, final C code, usage/cost/latency.

### Architecture

- [x] `agent/` LangGraph state machine with cycles and test-mode branch.
- [x] `testing/` normalized model, AST ingestion, generation, validation, baseline.
- [x] `errors_map/` single source of truth used by prompt and verifier.
- [x] `sandbox/` Docker-first untrusted execution for Python and C.
- [x] `translation/` translate + repair prompts with structured feedback,
      including the deep-agent system/task prompts.
- [x] `agent/deepagent.py` LangChain deep agent for translate/repair: sandboxed
      filesystem backend, `build_c`/`run_differential` tools, DeepSeek
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

### C harness input/output

Input cases:

```json
{"test_id":"t1","function":"add","args":[1,2],"kwargs":{}}
```

C output rows:

```json
{"test_id":"t1","kind":"value","value":3}
{"test_id":"t2","kind":"error","error_variant":"ValueError","message":"..."}
{"test_id":"t3","kind":"crash"}
```

### LLM C entry point

The LLM must provide `src/user_code.c` containing:

```c
ConvResult dispatch(const Case *test_case);
```

Helpers available: `arg_int`, `arg_double`, `arg_bool`, `arg_string`,
`arg_value`, `ensure_kwargs`, the `value_*` constructors/accessors, and
`conv_ok` / `conv_error` / `conv_other` / `conv_fail`.

### Error mapping

Python exception names map to same-named C variants (`CONV_VALUE_ERROR`,
`CONV_TYPE_ERROR`, ...). MRO fallback is used for subclasses. Unknown exceptions
map to `CONV_OTHER` with the Python type name. Crashes always fail, even when an
error was expected.

### Deep-agent boundary

- The agent owns only `src/user_code.c`. Harness files and the error prelude
  stay converter-owned.
- Its filesystem backend is `FilesystemBackend(root_dir=<temp C project>,
  virtual_mode=True)`: `/` maps to the temp C project and `..` traversal is
  rejected, so paths like `/etc/passwd` resolve inside the project, not the host.
- All command execution goes through `SandboxExecutor`; the agent has no direct
  shell. `build_c` compiles in place; `run_differential` reuses the verified
  baseline and scoring.
- `run_deep_agent` seeds prior code for repair, reads the final file, rejects the
  placeholder or a file lacking `dispatch`, and deletes the workdir.
- The outer `compile`/`verify` nodes rebuild a fresh C project and re-run the
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
| `MLFLOW_EXPERIMENT_NAME` | `python-to-c` |

---

## 7. Commands

```bash
# Setup
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp .env.example .env            # set LLM_API_KEY

# Docker sandbox (preferred)
docker build -f docker/Dockerfile.sandbox -t converter-sandbox:latest .

# Optional: subprocess fallback requires a host C compiler and make
cc --version && make --version

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
- Docker daemon is accessible; `converter-sandbox:latest` is an Alpine 3.20
  image (284 MB) with `gcc`, `musl-dev`, `make`, and `python3`.
- Host C toolchain is available (`cc`/`gcc` and `make`).
- The C harness has no third-party dependencies, so runtime builds are offline
  against the toolchain installed in the Docker image.
- `src/agentic_py2rust.egg-info/` is regenerated (the distribution name is
  unchanged) and, like `__pycache__`, is ignored by `.gitignore`.
- A live `LLM_API_KEY` was configured in `.env` and real DeepSeek calls/evals
  succeeded (see section 2). The deep-agent path itself has only been exercised
  with scripted models so far.

---

## 9. Gotchas encountered (already handled)

1. **`RLIMIT_NPROC` is per-user**, not per-process. Applying the Docker PID cap
   in the subprocess fallback throttled the build's processes. It was removed from
   the fallback; PID isolation is Docker-only.
2. **`RLIMIT_AS` breaks compiler builds** by preventing pthread stack reservation.
   It was removed from the subprocess fallback; memory isolation is Docker-only.
3. **The fallback must not strip the toolchain** — it passes `CC`, `CFLAGS`, and
   `LDFLAGS` through while keeping application secrets out.
4. **The Docker image must ship `cc` and `make`:** runtime is offline, so the
   toolchain has to be installed at image build time.
5. **Wheel package data** needs explicit patterns for nested files:
   `c_harness/src/*.c` and `*.h`, not just `c_harness/*`.
6. **Eval programs must be a package** (`__init__.py`) to be included in the
   wheel; the discovery logic skips `__init__.py`.
7. **Tracing was switched from Langfuse to local MLflow** at the user's request.
   This supersedes the Langfuse references still present in the original
   `agents.md` requirements. MLflow is optional at runtime; if absent, tracing
   is a no-op.
8. **`FilesystemBackend(virtual_mode=True)` is what keeps deep-agent paths
   contained.** A path like `/etc/passwd` is rewritten under the temp C project;
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
- Message-pattern checks can be strict because C message text may differ.
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
- Frontend has no automated tests; `tsc --noEmit` runs as part of `npm run build`.
- No CI configuration yet.

---

## 11. Suggested next-session priorities

1. Re-run the live end-to-end paths (user tests, generated tests, repair) against
   the Alpine sandbox in Docker mode.
2. Run the deep-agent path against the live provider (`DEEP_AGENT_ENABLED=true`)
   and compare compile rate, match rate, repair iterations, and cost against the
   single-shot baseline (`DEEP_AGENT_ENABLED=false`).
3. Turn the fake-LLM smoke scripts into repeatable integration tests (subprocess
   executor, no real provider) for both paths and the repair loop.
4. Decide whether infrastructure failures inside the graph should surface as
   HTTP 502 while still returning the partial report.
5. Add `pytest-asyncio`-style/class-based test support or broaden the ingester
   deliberately.
6. Improve coverage heuristics (per-function edge/error requirements, branch
   awareness).
7. Add a job queue + polling endpoint for long-running conversions.
8. Add CI (ruff, mypy, pytest, frontend build, optional Docker build).
9. Add a pricing table for DeepSeek so cost reporting is meaningful.

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
