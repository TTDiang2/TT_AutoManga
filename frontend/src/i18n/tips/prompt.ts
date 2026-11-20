// Tooltip text for the Prompt Lab tab, keyed by control. Shown on hover/keyboard
// focus by components/tooltip/TooltipLayer via a data-tip attribute.
// `zh: typeof en` makes the compiler insist both languages have every key.
const en = {
  natural: 'Write prompts as full sentences, for models like Qwen Image or Flux',
  tags: 'Write prompts as comma-separated keywords, for SDXL models like Illustrious or NoobAI',
  generateAll: 'Let the AI write a prompt for every panel at once. Replaces existing prompts of this style.',
  panel: 'Choose which panel to work on. Its scene is loaded as the input.',
  import: 'Paste prompts written elsewhere as JSON and add them to panels',
  input: 'The scene description the AI turns into an image prompt. Edit it freely first.',
  generate: 'Ask the AI to turn the input into a prompt for the selected panel',
  output: 'The prompt sent to the image model. Edit it by hand if you like, then Save.',
  negative: 'Things the picture should avoid, e.g. "blurry, extra fingers". Optional.',
  seed: 'A number that fixes the random variation: the same seed and prompt give the same picture. Empty = random.',
  randomSeed: 'Pick a new random seed',
  removeBG: 'Draw the picture with a transparent background, e.g. a character to place over other art',
  copy: 'Copy the prompt to the clipboard',
  save: 'Store this prompt, negative prompt, seed and background setting on the selected panel',
  edit: 'Load this panel into the editor above',
  importJson: 'One entry per panel: "panel" (number), "positive" (prompt), optional "negative" and "seed"',
  copyExample: 'Copy the example JSON to see the expected format',
  importConfirm: 'Add these prompts to the matching panels',
};

const zh: typeof en = {
  natural: '用完整句子写提示词，适用于 Qwen Image、Flux 等模型',
  tags: '用逗号分隔的关键词写提示词，适用于 Illustrious、NoobAI 等 SDXL 模型',
  generateAll: '让 AI 一次为所有分镜写提示词，会替换这种风格的现有提示词。',
  panel: '选择要编辑的分镜，它的画面描述会载入为输入。',
  import: '粘贴在别处写好的 JSON 提示词并加入分镜',
  input: 'AI 会把这段画面描述变成图像提示词，可以先自由修改。',
  generate: '让 AI 把输入变成所选分镜的提示词',
  output: '发送给图像模型的提示词。可以手动修改，然后保存。',
  negative: '画面要避免的内容，例如“模糊，多余的手指”。可选。',
  seed: '决定随机变化的数字：相同种子和提示词会得到相同图片。留空表示随机。',
  randomSeed: '随机生成一个新种子',
  removeBG: '生成透明背景的图片，例如要叠加在其他画面上的角色',
  copy: '把提示词复制到剪贴板',
  save: '把提示词、反向提示词、种子和背景设置保存到所选分镜',
  edit: '把这个分镜载入上方的编辑区',
  importJson: '每格一条：“panel”（序号）、“positive”（提示词），可选“negative”和“seed”',
  copyExample: '复制示例 JSON，查看所需格式',
  importConfirm: '把这些提示词加入对应的分镜',
};

export default { en, zh };
