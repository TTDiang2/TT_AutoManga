// Tooltip text for the Assets tab, keyed by control. Shown on hover/keyboard
// focus by components/tooltip/TooltipLayer via a data-tip attribute.
// `zh: typeof en` makes the compiler insist both languages have every key.
const en = {
  natural: 'Draw with the sentence-style prompts from the Prompt Lab (for Qwen, Flux and similar models)',
  tags: 'Draw with the keyword-tag prompts from the Prompt Lab (for SDXL, Illustrious and similar models)',
  viewGenerated: 'This project\'s panels and their pictures',
  viewArchive: 'Your library of saved images, sorted into folders',
  generateAll: 'Draw every panel that has no picture yet, one after another',
  status: 'Whether SwarmUI, the image generator, is reachable. If not, start it and check its address in Settings.',
  // panel slot
  upload: 'Use your own image for this panel. Replaces its current picture.',
  generate: 'Draw this panel with SwarmUI. Replaces its current picture.',
  archive: 'Save a copy of this picture to the Archive library',
  // archive
  sortFolders: 'Order the folder groups',
  newFolder: 'Create a new folder',
  allFolders: 'Show images from every folder',
  group: 'Show the folders in this group',
  folder: 'Show the images in this folder',
  renameFolder: 'Rename this folder',
  groupFolder: 'Put this folder in a group. Leave empty to ungroup it.',
  downloadFolder: 'Download every image in this folder as a ZIP',
  deleteFolder: 'Delete this folder and all images in it (asks first)',
  openImage: 'View this image full size',
  deleteImage: 'Delete this image from the archive (asks first)',
  moveImage: 'Move this image to another folder',
  closePreview: 'Close the preview',
};

const zh: typeof en = {
  natural: '使用提示词页面中的自然语言提示词绘制（适用于 Qwen、Flux 等模型）',
  tags: '使用提示词页面中的标签提示词绘制（适用于 SDXL、Illustrious 等模型）',
  viewGenerated: '本项目的分镜及其图片',
  viewArchive: '已保存图片的库，按文件夹整理',
  generateAll: '依次绘制所有还没有图片的分镜',
  status: '图像生成服务 SwarmUI 是否可连接。若不可用，请启动它并在设置中检查地址。',
  upload: '为这一格使用自己的图片，会替换当前图片。',
  generate: '用 SwarmUI 绘制这一格，会替换当前图片。',
  archive: '把这张图片复制一份保存到归档库',
  sortFolders: '文件夹分组的排序方式',
  newFolder: '新建文件夹',
  allFolders: '显示所有文件夹中的图片',
  group: '显示这个分组中的文件夹',
  folder: '显示这个文件夹中的图片',
  renameFolder: '重命名这个文件夹',
  groupFolder: '把文件夹放入一个分组，留空则取消分组。',
  downloadFolder: '把这个文件夹的所有图片下载为 ZIP',
  deleteFolder: '删除这个文件夹及其中所有图片（会先确认）',
  openImage: '查看大图',
  deleteImage: '从归档中删除这张图片（会先确认）',
  moveImage: '把这张图片移到其他文件夹',
  closePreview: '关闭预览',
};

export default { en, zh };
