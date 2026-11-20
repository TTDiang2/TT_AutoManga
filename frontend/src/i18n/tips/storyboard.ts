// Tooltip text for the Storyboard tab, keyed by control. Shown on hover/keyboard
// focus by components/tooltip/TooltipLayer via a data-tip attribute.
// `zh: typeof en` makes the compiler insist both languages have every key.
const en = {
  story: 'Paste a chapter or a few paragraphs, or drop a .md/.txt file here. The AI splits it into panels.',
  detail: 'Fewer, broader panels on the left; more, finer panels on the right.',
  generate: 'Split the text into panels with the AI model from Settings → API. This replaces the current panels.',
  importFile: 'Load a .md or .txt file into the text box (UTF-8, UTF-16 or GBK). You can also drop it on the box.',
  addPanel: 'Add an empty panel at the end to write yourself',
  drag: 'Drag to change the panel order',
  remove: 'Delete this panel',
  edit: 'Edit the scene and dialogue',
  scene: 'What the picture shows: place, people, action',
  dialogue: 'One line per bubble. Write "Name: line" to mark who speaks.',
  save: 'Keep these changes',
  cancel: 'Discard these changes',
};

const zh: typeof en = {
  story: '粘贴一章或几段文字，或把 .md/.txt 文件拖到这里。AI 会把它拆成分镜。',
  detail: '向左分镜更少更概括，向右更多更细致。',
  generate: '用 设置 → API 中的 AI 模型拆分文本，会替换当前分镜。',
  importFile: '把 .md 或 .txt 文件载入文本框（支持 UTF-8、UTF-16、GBK），也可以直接拖到文本框里。',
  addPanel: '在末尾添加一个空白分镜，自己填写',
  drag: '拖动调整分镜顺序',
  remove: '删除这个分镜',
  edit: '编辑画面和台词',
  scene: '画面内容：地点、人物、动作',
  dialogue: '一行一个气泡。写成“名字：台词”标明说话的人。',
  save: '保存修改',
  cancel: '放弃修改',
};

export default { en, zh };
