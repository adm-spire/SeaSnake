import type { EditableFile, TabId, TestMode } from '../types';
import { DownloadIcon, PlayIcon, Spinner } from './Icons';

interface ExplorerProps {
  files: Record<EditableFile, string>;
  activeFile: TabId;
  hasC: boolean;
  testMode: TestMode;
  maxAttempts: string;
  running: boolean;
  onOpen: (tab: TabId) => void;
  onTestModeChange: (mode: TestMode) => void;
  onMaxAttemptsChange: (value: string) => void;
  onRun: () => void;
  onDownloadC: () => void;
}

const TEST_MODES: { value: TestMode; label: string }[] = [
  { value: 'auto', label: 'Auto (detect)' },
  { value: 'user', label: 'User tests only' },
  { value: 'generate', label: 'Generate tests' },
  { value: 'augment', label: 'Augment user tests' },
];

function fileBadge(kind: 'py' | 'test' | 'c') {
  if (kind === 'c') return <span className="file-badge file-badge--c">C</span>;
  if (kind === 'test') return <span className="file-badge file-badge--test">T</span>;
  return <span className="file-badge file-badge--py">Py</span>;
}

export function Explorer({
  files,
  activeFile,
  hasC,
  testMode,
  maxAttempts,
  running,
  onOpen,
  onTestModeChange,
  onMaxAttemptsChange,
  onRun,
  onDownloadC,
}: ExplorerProps) {
  const lines = (content: string) => content.split('\n').length;

  return (
    <aside className="sidebar">
      <div className="sidebar-section">
        <div className="sidebar-title">Explorer</div>
        <div className="tree">
          <div className="tree-folder">
            <span className="tree-chevron">▾</span>
            <span className="tree-folder-name">CONVERTER</span>
          </div>
          <button
            type="button"
            className={`tree-file ${activeFile === 'main.py' ? 'active' : ''}`}
            onClick={() => onOpen('main.py')}
          >
            {fileBadge('py')}
            <span className="tree-file-name">main.py</span>
            <span className="tree-file-meta">{lines(files['main.py'])}</span>
          </button>
          <button
            type="button"
            className={`tree-file ${activeFile === 'tests.py' ? 'active' : ''}`}
            onClick={() => onOpen('tests.py')}
          >
            {fileBadge('test')}
            <span className="tree-file-name">tests.py</span>
            <span className="tree-file-meta">{lines(files['tests.py'])}</span>
          </button>
          {hasC && (
            <button
              type="button"
              className={`tree-file ${activeFile === 'user_code.c' ? 'active' : ''}`}
              onClick={() => onOpen('user_code.c')}
            >
              {fileBadge('c')}
              <span className="tree-file-name">user_code.c</span>
              <span className="tree-file-meta">generated</span>
            </button>
          )}
        </div>
      </div>

      <div className="sidebar-section sidebar-section--conversion">
        <div className="sidebar-title">Conversion</div>

        <label className="field">
          <span className="field-label">Test mode</span>
          <select
            className="field-input"
            value={testMode}
            onChange={(event) => onTestModeChange(event.target.value as TestMode)}
          >
            {TEST_MODES.map((mode) => (
              <option key={mode.value} value={mode.value}>
                {mode.label}
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          <span className="field-label">Max repair attempts</span>
          <input
            className="field-input"
            type="number"
            min={0}
            max={10}
            placeholder="default (3)"
            value={maxAttempts}
            onChange={(event) => onMaxAttemptsChange(event.target.value)}
          />
        </label>

        <button type="button" className="run-button" onClick={onRun} disabled={running}>
          {running ? <Spinner /> : <PlayIcon size={14} />}
          <span>{running ? 'Converting…' : 'Convert to C'}</span>
        </button>

        <p className="field-hint">
          {testMode === 'auto'
            ? 'Uses tests.py when present, otherwise generates tests.'
            : 'Mode is sent explicitly to /convert.'}
        </p>

        {hasC && (
          <button type="button" className="ghost-button" onClick={onDownloadC}>
            <DownloadIcon />
            <span>Download user_code.c</span>
          </button>
        )}
      </div>
    </aside>
  );
}
