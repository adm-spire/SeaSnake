import Editor, { type OnMount } from '@monaco-editor/react';

interface CodeEditorProps {
  path: string;
  language: 'python' | 'cpp';
  value: string;
  readOnly?: boolean;
  onChange?: (value: string) => void;
  onCursorChange?: (line: number, column: number) => void;
}

export function CodeEditor({
  path,
  language,
  value,
  readOnly = false,
  onChange,
  onCursorChange,
}: CodeEditorProps) {
  const handleMount: OnMount = (editor) => {
    editor.onDidChangeCursorPosition((event) => {
      onCursorChange?.(event.position.lineNumber, event.position.column);
    });
  };

  return (
    <Editor
      path={path}
      language={language}
      value={value}
      theme="vs-dark"
      height="100%"
      onChange={(next) => onChange?.(next ?? '')}
      onMount={handleMount}
      loading={<div className="editor-loading">Loading editor…</div>}
      options={{
        readOnly,
        readOnlyMessage: { value: 'Generated C — read only' },
        fontSize: 14,
        fontFamily:
          "'JetBrains Mono', 'Fira Code', 'Cascadia Code', Menlo, Consolas, monospace",
        fontLigatures: true,
        minimap: { enabled: true, renderCharacters: false },
        smoothScrolling: true,
        cursorBlinking: 'smooth',
        cursorSmoothCaretAnimation: 'on',
        renderLineHighlight: 'all',
        scrollBeyondLastLine: false,
        padding: { top: 12 },
        tabSize: 4,
        insertSpaces: true,
        bracketPairColorization: { enabled: true },
        guides: { bracketPairs: true, indentation: true },
        renderWhitespace: 'selection',
        automaticLayout: true,
      }}
    />
  );
}
