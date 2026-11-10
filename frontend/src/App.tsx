import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { convert } from './api';
import type {
  ConvertResponse,
  EditableFile,
  LogLevel,
  LogLine,
  Report,
  TabId,
  TestMode,
} from './types';
import { DEFAULT_FILES } from './lib/samples';
import { ActivityBar } from './components/ActivityBar';
import { CodeEditor } from './components/CodeEditor';
import { Explorer } from './components/Explorer';
import { Panel, type PanelTab } from './components/Panel';
import { StatusBar } from './components/StatusBar';
import { DownloadIcon, PlayIcon, Spinner } from './components/Icons';

const STORAGE_KEY = 'py2rust.files.v1';

function loadFiles(): Record<EditableFile, string> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<Record<EditableFile, string>>;
      return {
        'main.py': parsed['main.py'] ?? DEFAULT_FILES['main.py'],
        'tests.py': parsed['tests.py'] ?? DEFAULT_FILES['tests.py'],
      };
    }
  } catch {
    // Corrupt storage — fall back to samples.
  }
  return DEFAULT_FILES;
}

function tabLanguage(tab: TabId): 'python' | 'rust' {
  return tab === 'user_code.rs' ? 'rust' : 'python';
}

function FileBadge({ tab }: { tab: TabId }) {
  if (tab === 'user_code.rs') return <span className="file-badge file-badge--rs">Rs</span>;
  if (tab === 'tests.py') return <span className="file-badge file-badge--test">T</span>;
  return <span className="file-badge file-badge--py">Py</span>;
}

export default function App() {
  const [files, setFiles] = useState<Record<EditableFile, string>>(loadFiles);
  const [activeFile, setActiveFile] = useState<TabId>('main.py');
  const [rustCode, setRustCode] = useState<string | null>(null);
  const [response, setResponse] = useState<ConvertResponse | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [running, setRunning] = useState(false);
  const [testMode, setTestMode] = useState<TestMode>('auto');
  const [maxAttempts, setMaxAttempts] = useState('');
  const [durationMs, setDurationMs] = useState<number | null>(null);
  const [cursor, setCursor] = useState({ line: 1, column: 1 });
  const [logs, setLogs] = useState<LogLine[]>([]);
  const [panelOpen, setPanelOpen] = useState(true);
  const [panelTab, setPanelTab] = useState<PanelTab>('output');
  const logId = useRef(0);

  const addLog = useCallback((level: LogLevel, message: string) => {
    logId.current += 1;
    const id = logId.current;
    const time = new Date().toLocaleTimeString([], { hour12: false });
    setLogs((prev) => [...prev, { id, time, level, message }]);
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(files));
    } catch {
      // Storage may be unavailable (private mode); editing still works.
    }
  }, [files]);

  const tabs = useMemo<TabId[]>(
    () => (rustCode ? ['main.py', 'tests.py', 'user_code.rs'] : ['main.py', 'tests.py']),
    [rustCode],
  );

  const isRustTab = activeFile === 'user_code.rs';
  const editorValue = isRustTab ? (rustCode ?? '') : files[activeFile as EditableFile];
  const language = tabLanguage(activeFile);

  const handleChange = (value: string) => {
    if (isRustTab) return;
    setFiles((prev) => ({ ...prev, [activeFile]: value }));
  };

  const handleConvert = useCallback(async () => {
    if (running) return;
    setRunning(true);
    setResponse(null);
    setPanelOpen(true);
    setPanelTab('output');

    const modeLabel = testMode === 'auto' ? 'auto' : testMode;
    addLog('info', `POST /convert · mode=${modeLabel}${maxAttempts ? ` · max_attempts=${maxAttempts}` : ''}`);
    const started = performance.now();

    try {
      const trimmedTests = files['tests.py'].trim();
      const attempts = maxAttempts.trim() === '' ? undefined : Number(maxAttempts);
      const res = await convert({
        python_code: files['main.py'],
        tests: trimmedTests ? files['tests.py'] : undefined,
        test_mode: testMode === 'auto' ? undefined : testMode,
        max_attempts: Number.isFinite(attempts as number) ? (attempts as number) : undefined,
      });

      const elapsed = Math.round(performance.now() - started);
      setDurationMs(elapsed);
      setResponse(res);
      setReport(res.report);

      if (res.rust_code) {
        setRustCode(res.rust_code);
        setActiveFile('user_code.rs');
        addLog('success', 'Generated user_code.rs is ready.');
      }

      const level: LogLevel =
        res.status === 'passed' ? 'success' : res.status === 'failed' ? 'warn' : 'error';
      addLog(level, `Run ${res.run_id} finished with status "${res.status}" in ${elapsed} ms.`);

      if (res.report) {
        const { report: r } = res;
        addLog(
          'info',
          `${r.total_tests} tests · compile ${r.compile_ok ? 'ok' : 'failed'} · ${r.repair_iterations} repair(s) · ${r.generation_rounds} generation round(s)`,
        );
        if (r.failed_tests.length > 0) {
          addLog('warn', `${r.failed_tests.length} differential case(s) failed.`);
        }
        if (r.pass_criteria_failures.length > 0) {
          addLog('warn', `${r.pass_criteria_failures.length} pass-criteria failure(s).`);
        }
      }

      setPanelTab('report');
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      addLog('error', message);
      setPanelTab('output');
    } finally {
      setRunning(false);
    }
  }, [addLog, files, maxAttempts, running, testMode]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
        event.preventDefault();
        void handleConvert();
      }
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 's') {
        event.preventDefault();
        addLog('info', 'Saved locally (files persist in this browser).');
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [addLog, handleConvert]);

  const closeRustTab = () => {
    setRustCode(null);
    setActiveFile('main.py');
  };

  const downloadRust = () => {
    if (!rustCode) return;
    const blob = new Blob([rustCode], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = 'user_code.rs';
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const status = response?.status ?? report?.status ?? null;

  return (
    <div className="app">
      <header className="titlebar">
        <div className="titlebar-left">
          <span className="traffic-light traffic-light--red" />
          <span className="traffic-light traffic-light--yellow" />
          <span className="traffic-light traffic-light--green" />
          <span className="titlebar-title">
            <span className="titlebar-app">Python → Rust Converter</span>
            <span className="titlebar-sep">—</span>
            <span className="titlebar-file">{activeFile}</span>
          </span>
        </div>
        <div className="titlebar-right">
          {status && (
            <span className={`pill pill--${status}`}>{status}</span>
          )}
          <button type="button" className="convert-button" onClick={() => void handleConvert()} disabled={running}>
            {running ? <Spinner /> : <PlayIcon size={13} />}
            <span>{running ? 'Converting…' : 'Convert'}</span>
          </button>
        </div>
      </header>

      <div className="workbench">
        <ActivityBar running={running} onRun={() => void handleConvert()} />

        <Explorer
          files={files}
          activeFile={activeFile}
          hasRust={Boolean(rustCode)}
          testMode={testMode}
          maxAttempts={maxAttempts}
          running={running}
          onOpen={setActiveFile}
          onTestModeChange={setTestMode}
          onMaxAttemptsChange={setMaxAttempts}
          onRun={() => void handleConvert()}
          onDownloadRust={downloadRust}
        />

        <main className="editor-area">
          <div className="tabs" role="tablist">
            {tabs.map((tab) => (
              <div
                key={tab}
                className={`tab ${activeFile === tab ? 'active' : ''}`}
                role="tab"
                aria-selected={activeFile === tab}
                onClick={() => setActiveFile(tab)}
              >
                <FileBadge tab={tab} />
                <span className="tab-name">{tab}</span>
                {tab === 'user_code.rs' ? (
                  <button
                    type="button"
                    className="tab-close"
                    title="Close generated file"
                    onClick={(event) => {
                      event.stopPropagation();
                      closeRustTab();
                    }}
                  >
                    ×
                  </button>
                ) : (
                  <span className="tab-dot" aria-hidden="true" />
                )}
              </div>
            ))}
            <div className="tabs-fill" />
            {rustCode && (
              <button type="button" className="tab-action" onClick={downloadRust} title="Download user_code.rs">
                <DownloadIcon />
                <span>Download</span>
              </button>
            )}
          </div>

          <div className="breadcrumbs">
            <span>converter</span>
            <span className="breadcrumb-sep">›</span>
            <span className="breadcrumb-current">{activeFile}</span>
            {isRustTab && <span className="breadcrumb-tag">generated</span>}
          </div>

          <div className="editor-host">
            <CodeEditor
              path={activeFile}
              language={language}
              value={editorValue}
              readOnly={isRustTab}
              onChange={handleChange}
              onCursorChange={(line, column) => setCursor({ line, column })}
            />
          </div>

          <Panel
            open={panelOpen}
            tab={panelTab}
            logs={logs}
            report={report}
            response={response}
            running={running}
            onToggle={() => setPanelOpen((prev) => !prev)}
            onTabChange={setPanelTab}
          />
        </main>
      </div>

      <StatusBar
        running={running}
        status={status}
        runId={response?.run_id ?? report?.run_id ?? null}
        durationMs={durationMs}
        line={cursor.line}
        column={cursor.column}
        language={language}
      />
    </div>
  );
}
