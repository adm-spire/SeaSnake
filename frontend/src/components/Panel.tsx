import type { ConvertResponse, LogLine, Report } from '../types';
import { ChevronIcon, Spinner } from './Icons';
import { ReportView } from './ReportView';

type PanelTab = 'output' | 'report' | 'json';

interface PanelProps {
  open: boolean;
  tab: PanelTab;
  logs: LogLine[];
  report: Report | null;
  response: ConvertResponse | null;
  running: boolean;
  onToggle: () => void;
  onTabChange: (tab: PanelTab) => void;
}

const MARKERS: Record<LogLine['level'], string> = {
  info: '›',
  success: '✓',
  warn: '!',
  error: '✕',
};

function OutputTab({ logs, running }: { logs: LogLine[]; running: boolean }) {
  return (
    <div className="log-list">
      {logs.length === 0 && (
        <div className="log-empty">No output yet — run a conversion to see progress here.</div>
      )}
      {logs.map((line) => (
        <div className={`log-line log-${line.level}`} key={line.id}>
          <span className="log-time">{line.time}</span>
          <span className="log-marker">{MARKERS[line.level]}</span>
          <span className="log-message">{line.message}</span>
        </div>
      ))}
      {running && (
        <div className="log-line log-info log-thinking">
          <span className="log-time">…</span>
          <span className="log-marker">
            <Spinner size={12} />
          </span>
          <span className="log-message">Waiting for the backend (translate → compile → verify)…</span>
        </div>
      )}
    </div>
  );
}

export function Panel({
  open,
  tab,
  logs,
  report,
  response,
  running,
  onToggle,
  onTabChange,
}: PanelProps) {
  const raw = response ? JSON.stringify(response, null, 2) : '';

  const selectTab = (next: PanelTab) => {
    onTabChange(next);
    if (!open) onToggle();
  };

  return (
    <section className={`panel ${open ? '' : 'panel--closed'}`}>
      <div className="panel-header">
        <div className="panel-tabs">
          <button
            type="button"
            className={`panel-tab ${tab === 'output' ? 'active' : ''}`}
            onClick={() => selectTab('output')}
          >
            Output
          </button>
          <button
            type="button"
            className={`panel-tab ${tab === 'report' ? 'active' : ''}`}
            onClick={() => selectTab('report')}
          >
            Report
            {report && <span className={`tab-badge tab-badge--${report.status}`}>{report.status}</span>}
          </button>
          <button
            type="button"
            className={`panel-tab ${tab === 'json' ? 'active' : ''}`}
            onClick={() => selectTab('json')}
            disabled={!response}
          >
            Raw JSON
          </button>
        </div>
        <div className="panel-actions">
          {running && (
            <span className="panel-running">
              <Spinner size={12} /> running
            </span>
          )}
          <button
            type="button"
            className={`icon-button ${open ? '' : 'icon-button--flipped'}`}
            onClick={onToggle}
            title={open ? 'Collapse panel' : 'Expand panel'}
            aria-label={open ? 'Collapse panel' : 'Expand panel'}
          >
            <ChevronIcon />
          </button>
        </div>
      </div>

      {open && (
        <div className="panel-body">
          {tab === 'output' && <OutputTab logs={logs} running={running} />}
          {tab === 'report' && <ReportView report={report} response={response} />}
          {tab === 'json' && <pre className="raw-json">{raw || '// No response yet'}</pre>}
        </div>
      )}
    </section>
  );
}

export type { PanelTab };
