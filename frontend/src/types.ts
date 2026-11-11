export type TestMode = 'auto' | 'user' | 'generate' | 'augment';

export type EditableFile = 'main.py' | 'tests.py';

export type TabId = EditableFile | 'user_code.c';

export interface CategoryScore {
  total: number;
  passed: number;
  rate: number;
}

export interface ExpectedOutcome {
  kind: 'value' | 'error';
  value?: unknown;
  exception_type?: string | null;
  exception_mro?: string[];
  message_pattern?: string | null;
  approx?: boolean;
}

export interface ActualOutcome {
  kind: 'value' | 'error' | 'crash' | 'timeout';
  value?: unknown;
  error_variant?: string | null;
  message?: string | null;
}

export interface FailureCase {
  test_id: string;
  name: string;
  function: string;
  args: unknown[];
  kwargs: Record<string, unknown>;
  category: string;
  source: string;
  expected: ExpectedOutcome;
  actual: ActualOutcome;
  reason: string;
}

export interface InvalidUserTest {
  name: string;
  reason: string;
  raw_source?: string | null;
}

export interface Diagnostic {
  stage: string;
  severity: 'info' | 'warning' | 'error';
  message: string;
  raw?: string | null;
}

export interface Usage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number;
  latency_ms: number;
  llm_calls: number;
}

export interface Report {
  run_id: string;
  status: 'passed' | 'failed' | 'error';
  total_tests: number;
  per_category: Record<string, CategoryScore>;
  source_breakdown: Record<string, number>;
  invalid_user_tests: InvalidUserTest[];
  repair_iterations: number;
  generation_rounds: number;
  compile_ok: boolean | null;
  pass_criteria_failures: string[];
  failed_tests: FailureCase[];
  c_code?: string | null;
  usage: Usage;
  diagnostics: Diagnostic[];
  last_error?: string | null;
}

export interface ConvertResponse {
  run_id: string;
  status: string;
  c_code: string | null;
  report: Report | null;
}

export type LogLevel = 'info' | 'success' | 'warn' | 'error';

export interface LogLine {
  id: number;
  time: string;
  level: LogLevel;
  message: string;
}
