You are helping me build a production-grade agentic Python-to-Rust code converter. 
I learn by reading complete working code, understanding it, then improving it, so 
generate FULL working code, explain each module's design as you build it, and keep 
it clean, idiomatic, and well-commented. Favor clarity over cleverness.

WHAT TO BUILD:
An agent that takes Python code (plus optional tests), establishes a verified test 
baseline, converts the code to Rust, and verifies the Rust against that baseline. 
It loops through a repair step until the pass criteria are met or a max-attempt cap 
is hit.

INPUT:
- Python code, up to 500 lines (enforce the limit).
- Optional: user-provided pytest tests.
- Config: test_mode = "user" | "generate" | "augment" (auto-select "generate" 
  when no tests are given; "augment" = user tests + generated tests to fill gaps).

TWO TEST PATHS (converge into one shared verification pipeline):

PATH A — user provides tests:
1. ingest_tests: parse the user's pytest tests into a normalized test-case format.
2. validate_tests: run them against the ORIGINAL Python. Tests that pass become the 
   baseline. Tests that FAIL on the original Python are NOT silently dropped. 
   Report them to the user as "fails on original code" (likely a bug or stale 
   test) and exclude them from the baseline.
3. (augment mode only) generate additional tests for uncovered behavior, then 
   validate those too.

PATH B — no tests provided:
1. generate_tests: generate a categorized test suite:
   - happy_path: normal expected inputs and outputs
   - edge_case: boundaries, empty inputs, zero/negative numbers, large values, 
     single-element collections, unicode strings, etc.
   - error_condition / negative: invalid inputs that should raise exceptions; 
     record the exact exception type (and message pattern where meaningful)
2. validate_tests: run against the ORIGINAL Python; keep only tests whose recorded 
   expectation matches actual Python behavior (a generated test is only a guess 
   until Python confirms it). Regenerate to fill coverage gaps, max N rounds.

SHARED PIPELINE (both paths):
3. capture_baseline: for every validated test, record input -> outcome, where 
   outcome is either a return value OR an error (exception type). Tag each case 
   with its category and source (user | generated).
4. translate: convert the Python code to Rust.
5. compile: build in the sandbox.
6. verify: differential testing. Run every baseline input through the Rust and 
   compare outcomes:
   - value outcomes: Rust output must equal the Python output
   - error outcomes: use an explicit ERROR-MAPPING CONVENTION. Python exceptions map 
     to Rust error variants (e.g. ValueError -> Err(ConvError::ValueError(..)), 
     IndexError/KeyError -> corresponding variants). The test passes if the Rust 
     returns the mapped Err variant. Define this mapping in one place and document 
     it. Decide and document how panics are treated (default: a panic where an 
     Err was expected counts as a FAIL).
7. repair: on compile failure or any mismatch, feed exact compiler diagnostics + 
   the failing cases (input, expected outcome, actual outcome, category) back to 
   the LLM; increment attempt; retry from compile.
8. Stop when pass_criteria are met or attempt == max_attempts. pass_criteria is 
   configurable, e.g. 100% overall, or per-category thresholds (100% happy_path 
   and error_condition, >=95% edge_case).

FINAL REPORT: per-category pass rates, test source breakdown (user vs generated), 
user tests that failed on the original Python, number of repair iterations, final 
Rust code, total tokens/cost/latency.

SCOPE (Phase 1): constrain to a practical Python subset (pure functions, basic 
types, minimal stdlib, no C-extension deps). Document the supported subset in README.

STACK:
- Python, LangGraph (StateGraph with typed state; this is a CYCLIC graph with a 
  repair loop and a branch on test_mode; do NOT use legacy LangChain chains), Pydantic
- Provider-agnostic LLM client (DeepSeek now; swappable via config)
- Rust toolchain (cargo/rustc) run in an ISOLATED sandbox
- Langfuse for tracing
- FastAPI submit endpoint

STATE (typed): {python_src, user_tests, test_mode, test_cases (normalized, with 
category + source), invalid_user_tests, baseline (input -> value|error outcome), 
rust_code, rust_results, diagnostics, attempt, max_attempts, pass_criteria, status, 
report}

ARCHITECTURE (one responsibility per module):
- agent/         LangGraph machine: nodes ingest_tests, generate_tests, 
                 validate_tests, capture_baseline, translate, compile, verify, 
                 repair, report; conditional edges for the test_mode branch, the 
                 test-regeneration loop, and the repair loop
- testing/       normalized test-case model, pytest ingestion, categorized 
                 generation, validation against Python, baseline capture
- errors_map/    the Python-exception -> Rust-error-variant convention (single 
                 source of truth, used by translation AND verification)
- sandbox/       isolated execution for BOTH Python test runs and Rust 
                 compile/run: temp dirs, subprocess with TIMEOUTS and resource 
                 limits, no network, killed on timeout (Docker preferred). All 
                 generated code and user-supplied code is UNTRUSTED.
- translation/   prompts for translate + repair; instruct the LLM to follow the 
                 error-mapping convention; structured error feedback on repair
- verification/  differential outcome comparison (value and error), per-category 
                 scoring, pass_criteria evaluation
- observability/ Langfuse tracing of every node, regeneration round, and repair 
                 iteration
- evals/         benchmark of 5-10 Python programs, some with user tests and some 
                 without; metrics: compile rate, per-category match rate, avg 
                 repair iterations, test-validation rejection rate, cost/run
- core/          env config (no hardcoded keys), logging, error types, 
                 LLM-boundary retries, per-run token/latency/cost tracking
- api/           FastAPI endpoint accepting code + optional tests + test_mode
- tests/         pytest for state transitions, both routing branches, and the 
                 error-mapping logic
- README.md      architecture, both test paths, error-mapping convention, 
                 supported subset, security notes, how to run

PROCESS:
1. First, lay out the directory structure, the typed state schema, the normalized 
   test-case model, the error-mapping convention, and the graph (nodes + conditional 
   edges for the test_mode branch and both loops). Stop and let me confirm.
2. Then build module by module in dependency order (core -> sandbox -> errors_map -> 
   testing -> translation -> verification -> agent -> observability -> evals -> api), 
   explaining each as you go.
3. End with the README and run guide.

Don't skip the explanations. Understanding the code is the point.