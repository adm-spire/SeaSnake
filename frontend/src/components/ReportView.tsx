import type { ConvertResponse, FailureCase, Report } from '../types';

const CATEGORY_LABELS: Record<string, string> = {
  happy_path: 'Happy path',
  edge_case: 'Edge case',
  error_condition: 'Error condition',
};

const CATEGORY_ORDER = ['happy_path', 'edge_case', 'error_condition'];

function formatJson(value: unknown): string {
  if (value === undefined) return 'undefined';
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function describeExpected(test: FailureCase): string {
  if (test.expected.kind === 'error') {
    const pattern = test.expected.message_pattern ? ` (match "${test.expected.message_pattern}")` : '';
    return `raises ${test.expected.exception_type ?? 'Error'}${pattern}`;
  }
  return `= ${formatJson(test.expected.value)}`;
}

function describeActual(test: FailureCase): string {
  switch (test.actual.kind) {
    case 'value':
      return `= ${formatJson(test.actual.value)}`;
    case 'error':
      return `${test.actual.error_variant ?? 'Error'}${test.actual.message ? `: ${test.actual.message}` : ''}`;
    case 'timeout':
      return 'timed out';
    case 'crash':
      return test.actual.message ?? 'crashed';
    default:
      return test.actual.kind;
  }
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="stat">
      <span className="stat-value">{value}</span>
      <span className="stat-label">{label}</span>
    </div>
  );
}

interface ReportViewProps {
  report: Report | null;
  response: ConvertResponse | null;
}

export function ReportView({ report, response }: ReportViewProps) {
  if (!report) {
    return (
      <div className="empty-state">
        <p>No report yet.</p>
        <p className="empty-state-hint">Run a conversion to see the differential verification report.</p>
      </div>
    );
  }

  const categories = Object.entries(report.per_category).sort(
    ([a], [b]) => CATEGORY_ORDER.indexOf(a) - CATEGORY_ORDER.indexOf(b),
  );

  return (
    <div className="report">
      <div className={`report-banner report-banner--${report.status}`}>
        <div className="report-banner-main">
          <span className={`pill pill--${report.status}`}>{report.status.toUpperCase()}</span>
          <span className="report-run">run {report.run_id}</span>
        </div>
        <div className="report-banner-side">
          <span>{report.total_tests} tests</span>
          <span>{report.compile_ok ? 'compiled' : 'not compiled'}</span>
        </div>
      </div>

      {response?.c_code && (
        <p className="report-note">Generated C is available in the user_code.c tab.</p>
      )}

      {report.last_error && (
        <div className="callout callout--error">
          <strong>Last error.</strong> {report.last_error}
        </div>
      )}

      {report.pass_criteria_failures.length > 0 && (
        <div className="callout callout--warn">
          <strong>Pass criteria not met.</strong>
          <ul>
            {report.pass_criteria_failures.map((failure) => (
              <li key={failure}>{failure}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="stat-grid">
        <Stat label="Total tests" value={report.total_tests} />
        <Stat label="Repair iterations" value={report.repair_iterations} />
        <Stat label="Generation rounds" value={report.generation_rounds} />
        <Stat label="Compile" value={report.compile_ok ? 'OK' : 'Failed'} />
      </div>

      {categories.length > 0 && (
        <section className="report-section">
          <h3>Per-category pass rate</h3>
          <div className="category-list">
            {categories.map(([name, score]) => {
              const pct = Math.round(score.rate * 100);
              return (
                <div className="category-row" key={name}>
                  <span className="category-name">{CATEGORY_LABELS[name] ?? name}</span>
                  <div className="bar">
                    <div className={`bar-fill ${pct === 100 ? 'bar-fill--ok' : 'bar-fill--warn'}`} style={{ width: `${pct}%` }} />
                  </div>
                  <span className="category-score">
                    {score.passed}/{score.total} · {pct}%
                  </span>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {Object.keys(report.source_breakdown).length > 0 && (
        <section className="report-section">
          <h3>Test sources</h3>
          <div className="chip-row">
            {Object.entries(report.source_breakdown).map(([source, count]) => (
              <span className="chip" key={source}>
                {source}: {count}
              </span>
            ))}
          </div>
        </section>
      )}

      {report.failed_tests.length > 0 && (
        <section className="report-section">
          <h3>Failed differential cases ({report.failed_tests.length})</h3>
          <div className="failure-list">
            {report.failed_tests.map((test) => (
              <div className="failure" key={test.test_id}>
                <div className="failure-head">
                  <span className="failure-name">{test.name}</span>
                  <span className="chip chip--muted">{CATEGORY_LABELS[test.category] ?? test.category}</span>
                  <span className="chip chip--muted">{test.source}</span>
                </div>
                <code className="failure-call">
                  {test.function}({test.args.map(formatJson).join(', ')})
                </code>
                <div className="failure-grid">
                  <div>
                    <span className="failure-label">expected</span>
                    <span className="failure-value">{describeExpected(test)}</span>
                  </div>
                  <div>
                    <span className="failure-label">actual</span>
                    <span className="failure-value">{describeActual(test)}</span>
                  </div>
                </div>
                <p className="failure-reason">{test.reason}</p>
              </div>
            ))}
          </div>
        </section>
      )}

      {report.invalid_user_tests.length > 0 && (
        <section className="report-section">
          <h3>Rejected user tests ({report.invalid_user_tests.length})</h3>
          <ul className="plain-list">
            {report.invalid_user_tests.map((test) => (
              <li key={test.name}>
                <span className="mono">{test.name}</span> — {test.reason}
              </li>
            ))}
          </ul>
        </section>
      )}

      {report.diagnostics.length > 0 && (
        <section className="report-section">
          <h3>Diagnostics</h3>
          <ul className="diagnostic-list">
            {report.diagnostics.map((diag, index) => (
              <li key={`${diag.stage}-${index}`} className={`diagnostic diagnostic--${diag.severity}`}>
                <span className="diagnostic-stage">{diag.stage}</span>
                <span className="diagnostic-message">{diag.message}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="report-section">
        <h3>Usage</h3>
        <div className="stat-grid">
          <Stat label="Prompt tokens" value={report.usage.prompt_tokens} />
          <Stat label="Completion tokens" value={report.usage.completion_tokens} />
          <Stat label="Total tokens" value={report.usage.total_tokens} />
          <Stat label="LLM calls" value={report.usage.llm_calls} />
          <Stat label="Latency" value={`${report.usage.latency_ms} ms`} />
          <Stat label="Cost" value={`$${report.usage.cost_usd.toFixed(4)}`} />
        </div>
      </section>
    </div>
  );
}
