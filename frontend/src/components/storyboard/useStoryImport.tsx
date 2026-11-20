import { useRef, useState } from 'react';
import type { ChangeEvent, DragEvent } from 'react';
import { useTranslation } from '../../hooks/useTranslation';
import { IMPORT_ACCEPT, readStoryFile } from './storyImport';

/**
 * Import a story file into a text box, by file picker or by dropping it on
 * the box. `current` is the box's text (asked before it is replaced).
 * Render `fileInput` once, call `open()` from a button, spread `dropProps`
 * on the textarea and add a class while `dragOver` is true.
 */
export function useStoryImport(current: string, setText: (text: string) => void) {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);

  const importFile = async (file: File) => {
    const res = await readStoryFile(file);
    if (!res.ok) {
      alert(res.reason === 'type' ? t.storyboard.importInvalid
        : res.reason === 'size' ? t.storyboard.importTooLarge
        : t.storyboard.importEmpty);
      return;
    }
    if (current.trim() && !confirm(t.storyboard.importReplaceConfirm)) return;
    setText(res.text);
  };

  const onChange = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';   // the same file can be picked again
    if (file) void importFile(file);
  };

  const dropProps = {
    onDragOver: (e: DragEvent<HTMLTextAreaElement>) => {
      if (e.dataTransfer.types.includes('Files')) {
        e.preventDefault();
        setDragOver(true);
      }
    },
    onDragLeave: () => setDragOver(false),
    onDrop: (e: DragEvent<HTMLTextAreaElement>) => {
      setDragOver(false);
      const file = e.dataTransfer.files?.[0];
      if (!file) return;   // dropped text: let the textarea insert it
      e.preventDefault();
      void importFile(file);
    },
  };

  const fileInput = (
    <input ref={inputRef} type="file" accept={IMPORT_ACCEPT} style={{ display: 'none' }} onChange={onChange} />
  );

  return { fileInput, open: () => inputRef.current?.click(), dragOver, dropProps };
}
