/** Input types that take typed text (and so keep their own Cmd/Ctrl+Z); '' = no type attribute. */
const TEXT_INPUT_TYPES = new Set(['', 'text', 'number', 'search', 'email', 'url', 'tel', 'password']);

/** A control with its own text undo: a text-like <input>, a <textarea> or contentEditable.
    Sliders, checkboxes, selects and colour pickers are not: Cmd/Ctrl+Z there undoes the page. */
export function isTextEntry(node: Element | null): boolean {
  if (!node) return false;
  if (node.tagName === 'TEXTAREA') return true;
  if (node.tagName === 'INPUT') return TEXT_INPUT_TYPES.has((node.getAttribute('type') || '').toLowerCase());
  return (node as HTMLElement).isContentEditable === true;
}
