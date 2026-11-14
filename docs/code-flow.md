# Code Flow

Mermaid diagrams for the Python-to-C converter. See `README.md` for the prose
architecture and `STATUS.md` for the current verification snapshot.

## 1. System overview

```mermaid
flowchart TD
    UI["React frontend<br/>Monaco editor + output/report panel"]
    API["FastAPI<br/>POST /convert · GET /health"]
    RUN["agent.runner.run_conversion<br/>validates input, streams the graph"]
    SERVICES["Services<br/>SandboxExecutor · LLMClient · UsageTracker · Tracer"]
    GRAPH["LangGraph StateGraph<br/>ConverterState"]
    LLM["LLM provider<br/>OpenAI-compatible / DeepSeek"]
    EXEC["SandboxExecutor<br/>Docker first, subprocess fallback"]
    HARNESS["C harness<br/>Makefile + harness.c + user_code.c"]

    UI -->|"python_code, tests, test_mode, max_attempts"| API
    API --> RUN
    RUN --> SERVICES
    RUN -->|"graph.stream(state)"| GRAPH
    GRAPH -->|"translate / generate / repair"| LLM
    GRAPH -->|"validate tests / compile / differential run"| EXEC
    EXEC -->|"python3 or make + binary"| HARNESS
    GRAPH -->|"final ConverterState"| RUN
    RUN -->|"run_id, status, c_code, report"| API
    API -->|"ConvertResponse"| UI
```

## 2. Conversion graph

The graph has three loops: test regeneration, translation repair, and the
verification gate. `report` is terminal.

```mermaid
flowchart TD
    START([START]) --> ROUTE{"route_test_mode"}

    ROUTE -->|"test_mode = generate"| GEN["generate_tests<br/>LLM proposes categorized cases"]
    ROUTE -->|"test_mode = user / augment"| ING["ingest_tests<br/>parse constrained pytest AST"]

    ING --> VAL["validate_tests<br/>run cases against original Python"]
    GEN --> VAL

    VAL --> AFTER{"route_after_validate"}
    AFTER -->|"coverage gaps and rounds left"| GEN
    AFTER -->|"no gaps / round cap reached"| BASE["capture_baseline<br/>confirmed input → value or error oracle"]

    BASE --> TR["translate<br/>deep agent or single-shot"]
    TR --> COMP["compile<br/>make -B inside the sandbox"]

    COMP --> RC{"route_after_compile"}
    RC -->|"compile_ok"| VER["verify<br/>run baseline through the C binary"]
    RC -->|"failed and attempts left"| REP["repair<br/>compiler diagnostics + failing cases"]
    RC -->|"failed and attempt cap reached"| REPORT["report<br/>score, diagnostics, usage"]

    REP --> COMP

    VER --> RV{"route_after_verify"}
    RV -->|"pass criteria met"| REPORT
    RV -->|"failed and attempts left"| REP
    RV -->|"failed and attempt cap reached"| REPORT

    REPORT --> END([END])
```

## 3. `POST /convert` sequence

```mermaid
sequenceDiagram
    autonumber
    participant UI as React UI
    participant API as FastAPI
    participant RUN as run_conversion
    participant G as LangGraph
    participant LLM as LLM provider
    participant EX as SandboxExecutor
    participant BIN as C binary

    UI->>API: POST /convert (python_code, tests, test_mode, max_attempts)
    API->>API: validate request → ConversionRequest
    API->>RUN: run_conversion(request)
    RUN->>RUN: enforce source limit, select test mode, build Services
    RUN->>G: stream(ConverterState)
    G->>EX: python3 runs normalized tests
    EX-->>G: Python outcomes
    G->>LLM: generate tests / translate / repair
    LLM-->>G: JSON cases or full src/user_code.c
    G->>EX: make -B (build C harness + user_code.c)
    EX-->>G: binary + compiler diagnostics
    G->>EX: ./converter_sandbox cases.json results.json
    EX->>BIN: execute
    BIN-->>EX: results.json
    EX-->>G: raw value/error/crash outcomes
    G->>G: compare, score, evaluate pass criteria, build Report
    G-->>RUN: final ConverterState
    RUN-->>API: run_id, status, c_code, report
    API-->>UI: ConvertResponse
```

## 4. Deep-agent translate/repair loop

The inner agent owns only `src/user_code.c`; the outer graph still recompiles
and re-verifies it, so the agent never certifies itself.

```mermaid
flowchart LR
    NODE["translate / repair node"] --> AGENT["Deep agent<br/>ChatOpenAI"]
    AGENT -->|"write_file / edit_file / read_file"| FILE["src/user_code.c"]
    AGENT -->|"build_c"| BUILD["build_existing<br/>make -B"]
    BUILD --> DIAG["compiler diagnostics"]
    AGENT -->|"run_differential"| RUN["run_cases"]
    RUN --> BIN["converter_sandbox"]
    BIN --> RESULTS["results.json"]
    RESULTS --> SCORE["score_results"]
    SCORE -->|"failing cases + expected/actual"| AGENT
    DIAG --> AGENT
    AGENT -->|"final file"| NODE
    NODE -->|"outer compile + verify"| OUTER["deterministic C build<br/>and differential run"]
```

## 5. Sandbox build/run internals

```mermaid
flowchart TD
    PREP["c_runner.prepare_workdir"] --> COPY["copy c_harness template<br/>+ errors_map/c_prelude.h"]
    COPY --> STUB["write placeholder user_code.c<br/>if none exists"]
    STUB --> WRITE["write LLM-authored src/user_code.c"]
    WRITE --> MAKE["make -B<br/>cc harness.c + user_code.c -lm"]
    MAKE --> CHECK{"binary exists<br/>and exit code 0?"}
    CHECK -->|"no"| DIAG["BuildResult<br/>ok=false + diagnostics"]
    CHECK -->|"yes"| CASES["write cases.json"]
    CASES --> RUNBIN["./converter_sandbox<br/>cases.json results.json"]
    RUNBIN --> OUTCOMES["read results.json<br/>actual_from_raw → ActualOutcome"]
    OUTCOMES --> SCORE["score_results + pass criteria"]
```

## 6. Key modules

| Layer | Module | Responsibility |
|---|---|---|
| API | `converter/api/main.py` | `/health`, `/convert`, CORS, serves `frontend/dist` |
| Orchestration | `converter/agent/runner.py` | validate input, build services, stream graph |
| Graph | `converter/agent/graph.py`, `routing.py` | node wiring, branches, loop caps |
| Nodes | `converter/agent/nodes/*` | ingest, generate, validate, baseline, translate, compile, verify, repair, report |
| Testing | `converter/testing/*` | pytest AST ingestion, generation, validation, baseline |
| Translation | `converter/translation/*` | prompts and LLM-facing translate/repair |
| Deep agent | `converter/agent/deepagent.py` | filesystem backend, `build_c`, `run_differential`, usage callback |
| Sandbox | `converter/sandbox/executor.py` | Docker-first isolation, subprocess fallback |
| C runner | `converter/sandbox/c_runner.py` | prepare workdir, build, run cases |
| C harness | `converter/sandbox/c_harness/` | JSON I/O, argument/value helpers, `dispatch` |
| Errors | `converter/errors_map/mapping.py`, `c_prelude.h` | Python exception → `ConvErrorKind` |
| Verification | `converter/verification/*` | differential comparison, scoring, pass criteria |
| UI | `frontend/src/App.tsx` | VS Code-style editor, conversion controls, report panel |
