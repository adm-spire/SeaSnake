import * as monaco from 'monaco-editor';
import { loader } from '@monaco-editor/react';
import EditorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker';

window.MonacoEnvironment = {
  getWorker: () => new EditorWorker(),
};

loader.config({ monaco });
