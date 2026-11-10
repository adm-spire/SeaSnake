interface StatusBarProps {
  running: boolean;
  status: string | null;
  runId: string | null;
  durationMs: number | null;
  line: number;
  column: number;
  language: string;
}

export function StatusBar({
  running,
  status,
  runId,
  durationMs,
  line,
  column,
  language,
}: StatusBarProps) {
  const statusLabel = running ? 'Converting…' : (status ?? 'Ready');
  const statusClass = running
    ? 'pending'
    : status === 'passed'
      ? 'ok'
      : status === 'failed'
        ? 'warn'
        : status === 'error'
          ? 'err'
          : 'idle';

  return (
    <footer className="status-bar">
      <div className="status-left">
        <span className={`status-dot ${statusClass}`} />
        <span className={`status-item status-strong ${statusClass}`}>{statusLabel}</span>
        {runId && <span className="status-item status-mono">run {runId.slice(0, 8)}</span>}
        {durationMs !== null && <span className="status-item">{durationMs} ms</span>}
      </div>
      <div className="status-right">
        <span className="status-item">{language === 'rust' ? 'Rust' : 'Python'}</span>
        <span className="status-item">Ln {line}, Col {column}</span>
        <span className="status-item">Spaces: 4</span>
        <span className="status-item">UTF-8</span>
        <span className="status-item">LF</span>
      </div>
    </footer>
  );
}
