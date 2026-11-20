// Tooltip text for the Composer tab, keyed by control. Shown on hover/keyboard
// focus by components/tooltip/TooltipLayer via a data-tip attribute.
// `zh: typeof en` makes the compiler insist both languages have every key.
const en = {
  // page list
  duplicatePage: 'Copy this page, with everything on it, right after it',
  deletePage: 'Delete this page (the last page cannot be deleted)',
  addPage: 'Add an empty page at the end',
  autoPages: 'Saves, then builds new pages from the project\'s drawn panels, 4 per page, with speech bubbles. Adds to the existing pages.',

  // tools
  select: 'Select, move and resize things on the page. Drag corner handles to reshape a frame.',
  split: 'Drag a line across a frame to cut it in two with a gutter. On an empty page it makes two frames.',
  text: 'Click the page to place a text box (titles, captions, sound effects). Double-click it to type.',
  bubble: 'Click the page to place a speech bubble in the style chosen next to this. Double-click it to type.',
  bubbleType: {
    speech: 'Normal speech: an oval balloon with a tail',
    thought: 'Thinking: a cloud with small circles instead of a tail',
    shout: 'Shouting: a spiky burst',
    whisper: 'Whispering: a dashed outline',
    narration: 'Narration or captions: a box with no tail, for scene changes like "Next morning…"',
    'inner-voice': 'Inner voice: unspoken thoughts in a softer balloon',
  },

  // layouts and extras
  template: 'Apply a panel layout to this page. It replaces everything on the page, pictures and bubbles too (Undo brings them back).',
  addFrame: 'Add a new empty frame to this page',
  addImage: 'Add a free-floating image on top of everything, not clipped to a frame. Good for characters breaking out of panels.',
  sfx: 'Add a sound effect word (BOOM, 轰…) as large outlined text',
  saveTemplate: 'Save this page\'s frame layout (no images) to reuse on other pages',
  manageTemplates: 'Your saved layouts: delete ones you no longer need',
  deleteTemplate: 'Delete this saved layout',

  // history, zoom, saving
  undo: 'Undo the last change (Ctrl+Z)',
  redo: 'Redo the change you undid (Ctrl+Shift+Z)',
  zoomOut: 'Zoom out',
  zoomIn: 'Zoom in',
  save: 'Save the pages to Showcase now. Changes are also saved automatically.',
  export: 'Download the pages as a PNG, PDF or ZIP of images',
  exportPng: 'Only the page you are looking at, as one PNG image',
  exportPdf: 'All pages as one PDF, ready to read or print',
  exportZip: 'All pages as separate PNG images in a ZIP file',
  reload: 'Load the newer pages from the server. Unsaved changes here are lost.',
  dismiss: 'Hide this message',
  cancelTool: 'Stop placing and go back to the Select tool',
  closeDialog: 'Close without saving',
  projectName: 'The name the comic gets in Showcase',
  templateName: 'A name to find this layout by in the layout list',

  // properties: page-wide
  frameBorder: 'Thickness of the black border around every frame on this page',
  frameBorderDefault: 'Reset the frame border to the standard 1.5 px',
  snapToEdge: 'Line up frames near the page edge with it, leaving an even 2% margin',
  gap: 'How wide the gutter between touching frames should be, in % of the page',
  gapApply: 'Open up an even gutter between frames that touch. Frames keep their place; touching edges shrink.',

  // properties: any element
  x: 'Distance from the left page edge, in % of the page width',
  y: 'Distance from the top page edge, in % of the page height',
  width: 'Width in % of the page width',
  height: 'Height in % of the page height',
  rotation: 'Rotation in degrees; negative turns it counter-clockwise',
  deleteElement: 'Remove this from the page (Undo brings it back)',

  // properties: frames and images
  cornersReset: 'Make the frame a plain rectangle again',
  cornerX: 'Move this corner sideways, in % of the frame\'s own width. Slanted corners give a more dynamic panel.',
  cornerY: 'Move this corner up or down, in % of the frame\'s own height',
  replaceImage: 'Pick another picture for this frame',
  offsetReset: 'Centre the picture in the frame again',
  offsetX: 'Shift the picture inside the frame left or right, in % of the frame width',
  offsetY: 'Shift the picture inside the frame up or down, in % of the frame height',
  scaleReset: 'Back to the original size',
  scale: 'Zoom the picture inside its frame: 1 = fit, above 1 crops in closer',

  // properties: bubbles
  tail: {
    top: 'Tail under the bubble, pointing down: for a speaker below the bubble',
    bottom: 'Tail on top of the bubble, pointing up: for a speaker above it',
    left: 'No tail is drawn for this side; use "Point tail" to aim sideways',
    right: 'No tail is drawn for this side; use "Point tail" to aim sideways',
  },
  pointTail: 'Aim a pointed tail at any spot: drag the orange handle to the speaker\'s mouth. Not for narration boxes.',
  tailX: 'Where the tail points, across: % of the bubble\'s width (0 = left edge, 100 = right edge, beyond = outside)',
  tailY: 'Where the tail points, down: % of the bubble\'s height (100 = bottom edge, beyond = below the bubble)',
  bubbleAlign: 'Line up the text in the bubble to the left, centre or right',
  stars: 'Write *word* to set that word in bold slanted emphasis (horizontal text only)',
  direction: 'Horizontal lines, or vertical columns read right to left (best for Chinese and Japanese)',
  bubbleFontSize: 'Text size in pixels on a standard 600×900 page; exports scale it up',
  bgColor: 'Fill colour inside the bubble',
  borderColor: 'Outline colour of the bubble',

  // properties: text
  textFontSize: 'Text size in pixels on a standard 600×900 page; exports scale it up',
  outline: 'Outline around each letter, 0-20 px. Use a thick one for sound effects.',
  fontWeight: 'Normal or bold letters',
  textAlign: 'Line up the text to the left, centre or right',
  fontColor: 'Colour of the letters',

  // canvas
  tailHandle: 'Drag to aim the tail at the speaker',
  addSlotImage: 'Put a picture in this frame',

  // image picker
  closePicker: 'Close without choosing a picture',
  fromPanels: 'Pictures drawn for this project\'s panels',
  fromArchive: 'Every image you have saved, sorted in folders',
  folder: 'Show the images of one archive folder',
  upload: 'Use a picture from your computer',
};

const zh: typeof en = {
  duplicatePage: '复制这一页及其全部内容，放在它后面',
  deletePage: '删除这一页（最后一页不能删除）',
  addPage: '在末尾添加一个空白页',
  autoPages: '先保存，再用项目中已绘制的分镜自动生成新页面（每页 4 格，带对话气泡），追加在现有页面之后。',

  select: '选择、移动和缩放页面上的元素。拖动分格的角点可以改变形状。',
  split: '在分格上拖出一条线，把它切成两格并留出间隙。在空白页上会生成两个分格。',
  text: '点击页面放置文本框（标题、旁白、音效字），双击后输入文字。',
  bubble: '点击页面放置对话气泡，样式在旁边选择。双击后输入文字。',
  bubbleType: {
    speech: '普通对话：带尾巴的椭圆气泡',
    thought: '内心想法：云朵形，用小圆圈代替尾巴',
    shout: '大喊：爆炸形尖刺气泡',
    whisper: '低语：虚线边框',
    narration: '旁白或说明：没有尾巴的方框，用于“第二天早上……”这类场景转换',
    'inner-voice': '内心独白：未说出口的话，气泡更柔和',
  },

  template: '为这一页套用分格版式。会替换页面上的全部内容，包括图片和气泡（可以撤销）。',
  addFrame: '在这一页添加一个空白分格',
  addImage: '添加一张浮在最上层、不受分格裁切的图片，适合让角色“破格”而出。',
  sfx: '添加音效字（轰、BOOM……），以带描边的大字显示',
  saveTemplate: '把这一页的分格版式（不含图片）存为模板，在其他页面复用',
  manageTemplates: '已保存的版式：删除不再需要的',
  deleteTemplate: '删除这个已保存的版式',

  undo: '撤销上一步（Ctrl+Z）',
  redo: '恢复刚撤销的操作（Ctrl+Shift+Z）',
  zoomOut: '缩小',
  zoomIn: '放大',
  save: '立即把页面保存到作品。修改也会自动保存。',
  export: '把页面下载为 PNG、PDF 或图片 ZIP',
  exportPng: '只导出当前页，一张 PNG 图片',
  exportPdf: '所有页面合成一个 PDF，可阅读或打印',
  exportZip: '所有页面分别导出为 PNG，打包成 ZIP',
  reload: '从服务器载入更新的页面，这里未保存的修改会丢失。',
  dismiss: '隐藏这条消息',
  cancelTool: '停止放置，回到选择工具',
  closeDialog: '关闭，不保存',
  projectName: '漫画在作品中显示的名称',
  templateName: '在版式列表中用来找到这个版式的名称',

  frameBorder: '这一页所有分格黑色边框的粗细',
  frameBorderDefault: '把分格边框恢复为标准的 1.5 像素',
  snapToEdge: '让靠近页面边缘的分格与边缘对齐，统一留出 2% 的边距',
  gap: '相邻分格之间的间隙宽度（页面的百分比）',
  gapApply: '在相互接触的分格之间留出均匀间隙。分格位置不变，相接的边会收缩。',

  x: '距页面左边缘的距离（页面宽度的百分比）',
  y: '距页面上边缘的距离（页面高度的百分比）',
  width: '宽度（页面宽度的百分比）',
  height: '高度（页面高度的百分比）',
  rotation: '旋转角度，负数为逆时针',
  deleteElement: '从页面移除（可以撤销）',

  cornersReset: '把分格恢复为普通矩形',
  cornerX: '左右移动这个角（分格自身宽度的百分比）。倾斜的角让分格更有动感。',
  cornerY: '上下移动这个角（分格自身高度的百分比）',
  replaceImage: '为这个分格换一张图片',
  offsetReset: '让图片重新居中',
  offsetX: '在分格内左右移动图片（分格宽度的百分比）',
  offsetY: '在分格内上下移动图片（分格高度的百分比）',
  scaleReset: '恢复原始大小',
  scale: '缩放分格内的图片：1 为适配，大于 1 会放大裁切',

  tail: {
    top: '尾巴在气泡下方、朝下：用于说话人在气泡下面',
    bottom: '尾巴在气泡上方、朝上：用于说话人在气泡上面',
    left: '这一侧不画尾巴；想指向侧面请用“指向尾巴”',
    right: '这一侧不画尾巴；想指向侧面请用“指向尾巴”',
  },
  pointTail: '让尖尾巴指向任意位置：把橙色手柄拖到说话人嘴边。旁白框不适用。',
  tailX: '尾巴横向指向的位置：气泡宽度的百分比（0 为左边缘，100 为右边缘，超出即在气泡外）',
  tailY: '尾巴纵向指向的位置：气泡高度的百分比（100 为下边缘，超出即在气泡下方）',
  bubbleAlign: '气泡内文字左对齐、居中或右对齐',
  stars: '写成 *词语* 会把这个词设为加粗倾斜的强调（仅横排）',
  direction: '横排，或从右到左的竖排（适合中文和日文）',
  bubbleFontSize: '文字大小，以标准 600×900 页面的像素计；导出时会按比例放大',
  bgColor: '气泡内部的填充颜色',
  borderColor: '气泡轮廓的颜色',

  textFontSize: '文字大小，以标准 600×900 页面的像素计；导出时会按比例放大',
  outline: '每个字的描边，0-20 像素。音效字适合用粗描边。',
  fontWeight: '常规或加粗',
  textAlign: '文字左对齐、居中或右对齐',
  fontColor: '文字颜色',

  tailHandle: '拖动让尾巴指向说话人',
  addSlotImage: '在这个分格里放一张图片',

  closePicker: '关闭，不选择图片',
  fromPanels: '为本项目分镜绘制的图片',
  fromArchive: '所有已保存的图片，按文件夹分类',
  folder: '只显示一个归档文件夹的图片',
  upload: '使用电脑上的一张图片',
};

export default { en, zh };
