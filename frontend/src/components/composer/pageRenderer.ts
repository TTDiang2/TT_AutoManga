import type { ComposerPage, ImageElement, TextElement, BubbleElement } from '../../types';

export function renderPageToImage(page: ComposerPage): Promise<string> {
  return new Promise(resolve => {
    const w = page.width || 600;
    const h = page.height || 900;
    const canvas = document.createElement('canvas');
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext('2d');
    if (!ctx) { resolve(''); return; }

    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, w, h);

    const sortedEls = [...page.elements]
      .filter(e => e.visible)
      .sort((a, b) => a.zIndex - b.zIndex);

    const imgEls = sortedEls.filter(e => e.type === 'image');

    const drawAll = (loadedImages: Record<string, HTMLImageElement>) => {
      sortedEls.forEach(el => {
        const x = (el.x / 100) * w;
        const y = (el.y / 100) * h;
        const ew = (el.width / 100) * w;
        const eh = (el.height / 100) * h;

        if (el.type === 'image') {
          drawImageEl(ctx, el as ImageElement, loadedImages, x, y, ew, eh);
        } else if (el.type === 'text') {
          drawTextEl(ctx, el as TextElement, x, y, ew, eh);
        } else if (el.type === 'bubble') {
          drawBubbleEl(ctx, el as BubbleElement, x, y, ew, eh);
        }
      });
      resolve(canvas.toDataURL('image/png'));
    };

    if (imgEls.length === 0) {
      drawAll({});
      return;
    }

    let done = 0;
    const loadedImages: Record<string, HTMLImageElement> = {};
    imgEls.forEach(el => {
      const img = new Image();
      img.crossOrigin = 'anonymous';
      img.onload = () => {
        loadedImages[el.id] = img;
        done++;
        if (done === imgEls.length) drawAll(loadedImages);
      };
      img.onerror = () => {
        done++;
        if (done === imgEls.length) drawAll(loadedImages);
      };
      img.src = (el as ImageElement).src;
    });
  });
}

function drawImageEl(
  ctx: CanvasRenderingContext2D,
  el: ImageElement,
  loadedImages: Record<string, HTMLImageElement>,
  x: number, y: number, ew: number, eh: number,
) {
  const img = loadedImages[el.id];
  if (!img) return;
  ctx.save();
  if (el.rotation) {
    ctx.translate(x + ew / 2, y + eh / 2);
    ctx.rotate((el.rotation * Math.PI) / 180);
    ctx.translate(-(x + ew / 2), -(y + eh / 2));
  }
  ctx.beginPath();
  ctx.rect(x, y, ew, eh);
  ctx.clip();

  // object-fit: cover behavior
  const imgW = img.naturalWidth;
  const imgH = img.naturalHeight;
  const imgAspect = imgW / imgH;
  const slotAspect = ew / eh;

  let sx: number, sy: number, sw: number, sh: number;
  if (imgAspect > slotAspect) {
    // image wider than slot → crop sides
    sh = imgH;
    sw = imgH * slotAspect;
    sx = (imgW - sw) / 2;
    sy = 0;
  } else {
    // image taller than slot → crop top/bottom
    sw = imgW;
    sh = imgW / slotAspect;
    sx = 0;
    sy = (imgH - sh) / 2;
  }

  // Apply cropArea offset if present
  if (el.cropArea) {
    const ca = el.cropArea;
    sx = ca.x * imgW;
    sy = ca.y * imgH;
    sw = ca.width * imgW;
    sh = ca.height * imgH;
  }

  ctx.drawImage(img, sx, sy, sw, sh, x, y, ew, eh);
  ctx.restore();
}

function drawTextEl(
  ctx: CanvasRenderingContext2D,
  el: TextElement,
  x: number, y: number, ew: number, eh: number,
) {
  ctx.save();
  ctx.fillStyle = el.color || '#000000';
  const fs = el.fontSize || 14;
  const style = el.fontWeight === 'bold' ? 'bold ' : '';
  ctx.font = `${style}${fs}px ${el.fontFamily || 'sans-serif'}`;
  ctx.textAlign = el.textAlign || 'left';
  ctx.textBaseline = 'top';

  if (el.direction === 'vertical') {
    const chars = (el.content || '').split('');
    const charH = fs * 1.3;
    const totalH = chars.length * charH;
    const startY = y + (eh - totalH) / 2;
    chars.forEach((ch, i) => {
      ctx.fillText(ch, x + ew / 2, startY + i * charH);
    });
  } else {
    let tx = x;
    if (el.textAlign === 'center') tx = x + ew / 2;
    else if (el.textAlign === 'right') tx = x + ew;
    const lines = (el.content || '').split('\n');
    const lineH = fs * 1.4;
    const totalH = lines.length * lineH;
    const startY = y + (eh - totalH) / 2;
    lines.forEach((line, i) => {
      ctx.fillText(line, tx, startY + i * lineH);
    });
  }
  ctx.restore();
}

function drawBubbleEl(
  ctx: CanvasRenderingContext2D,
  el: BubbleElement,
  x: number, y: number, ew: number, eh: number,
) {
  ctx.save();
  if (el.rotation) {
    ctx.translate(x + ew / 2, y + eh / 2);
    ctx.rotate((el.rotation * Math.PI) / 180);
    ctx.translate(-(x + ew / 2), -(y + eh / 2));
  }

  const bt = el.bubbleType;

  if (bt === 'shout') {
    drawShoutShape(ctx, x, y, ew, eh, el);
  } else if (bt === 'narration') {
    drawNarrationShape(ctx, x, y, ew, eh, el);
  } else {
    drawOvalShape(ctx, x, y, ew, eh, el);
  }

  drawTail(ctx, x, y, ew, eh, el);
  drawBubbleText(ctx, x, y, ew, eh, el);
  ctx.restore();
}

function drawOvalShape(
  ctx: CanvasRenderingContext2D,
  x: number, y: number, ew: number, eh: number,
  el: BubbleElement,
) {
  const cx = x + ew / 2;
  const cy = y + eh / 2;
  const rx = ew / 2 - 2;
  const ry = eh / 2 - 2;

  ctx.beginPath();
  ctx.ellipse(cx, cy, Math.max(rx, 1), Math.max(ry, 1), 0, 0, Math.PI * 2);

  ctx.fillStyle = el.backgroundColor || '#ffffff';
  ctx.fill();

  ctx.strokeStyle = el.borderColor || '#000000';
  if (el.bubbleType === 'thought' || el.bubbleType === 'whisper') {
    ctx.setLineDash([5, 5]);
    ctx.lineWidth = el.bubbleType === 'whisper' ? 1 : 2;
  } else {
    ctx.setLineDash([]);
    ctx.lineWidth = 2;
  }
  ctx.stroke();
  ctx.setLineDash([]);
}

function drawShoutShape(
  ctx: CanvasRenderingContext2D,
  x: number, y: number, ew: number, eh: number,
  el: BubbleElement,
) {
  const spikes = 12;
  const cx = x + ew / 2;
  const cy = y + eh / 2;
  const outerRx = ew / 2 - 2;
  const outerRy = eh / 2 - 2;
  const innerRx = outerRx * 0.78;
  const innerRy = outerRy * 0.78;

  ctx.beginPath();
  for (let i = 0; i < spikes * 2; i++) {
    const angle = (Math.PI * 2 * i) / (spikes * 2) - Math.PI / 2;
    const isOuter = i % 2 === 0;
    const rx = isOuter ? outerRx : innerRx;
    const ry = isOuter ? outerRy : innerRy;
    const px = cx + rx * Math.cos(angle);
    const py = cy + ry * Math.sin(angle);
    if (i === 0) ctx.moveTo(px, py);
    else ctx.lineTo(px, py);
  }
  ctx.closePath();

  ctx.fillStyle = el.backgroundColor || '#FFF9C4';
  ctx.fill();
  ctx.strokeStyle = el.borderColor || '#000000';
  ctx.lineWidth = 3;
  ctx.stroke();
}

function drawNarrationShape(
  ctx: CanvasRenderingContext2D,
  x: number, y: number, ew: number, eh: number,
  el: BubbleElement,
) {
  ctx.beginPath();
  ctx.roundRect(x + 2, y + 2, ew - 4, eh - 4, 4);
  ctx.fillStyle = el.backgroundColor || '#F5F5F5';
  ctx.fill();
  ctx.strokeStyle = el.borderColor || '#333333';
  ctx.lineWidth = 2;
  ctx.stroke();
}

function drawTail(
  ctx: CanvasRenderingContext2D,
  x: number, y: number, ew: number, eh: number,
  el: BubbleElement,
) {
  if (el.bubbleType === 'narration') return;
  const tailSize = Math.min(ew, eh) * 0.12;
  const cx = x + ew / 2;
  ctx.fillStyle = el.backgroundColor || '#ffffff';
  ctx.strokeStyle = el.borderColor || '#000000';
  ctx.lineWidth = 2;

  if (el.tailPosition === 'bottom') {
    ctx.beginPath();
    ctx.moveTo(cx - tailSize, y);
    ctx.lineTo(cx, y - tailSize * 1.2);
    ctx.lineTo(cx + tailSize, y);
    ctx.closePath();
    ctx.fill();
    ctx.stroke();
  } else if (el.tailPosition === 'top') {
    ctx.beginPath();
    ctx.moveTo(cx - tailSize, y + eh);
    ctx.lineTo(cx, y + eh + tailSize * 1.2);
    ctx.lineTo(cx + tailSize, y + eh);
    ctx.closePath();
    ctx.fill();
    ctx.stroke();
  }
}

function drawBubbleText(
  ctx: CanvasRenderingContext2D,
  x: number, y: number, ew: number, eh: number,
  el: BubbleElement,
) {
  const fs = el.fontSize || 12;
  const isBold = el.bubbleType === 'shout';
  const isItalic = ['thought', 'whisper', 'narration', 'inner-voice'].includes(el.bubbleType);
  let fontStr = '';
  if (isItalic) fontStr += 'italic ';
  if (isBold) fontStr += 'bold ';
  fontStr += `${fs}px sans-serif`;
  ctx.font = fontStr;

  ctx.fillStyle = el.bubbleType === 'whisper' ? 'rgba(0,0,0,0.7)' : '#000000';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';

  const text = el.text || '';
  const padding = 10;
  const maxW = ew - padding * 2;
  const lines = wrapText(ctx, text, maxW);
  const lineH = fs * 1.4;
  const totalH = lines.length * lineH;
  const startY = y + eh / 2 - totalH / 2 + lineH / 2;

  lines.forEach((line, i) => {
    ctx.fillText(line, x + ew / 2, startY + i * lineH);
  });
}

function wrapText(ctx: CanvasRenderingContext2D, text: string, maxWidth: number): string[] {
  const rawLines = text.split('\n');
  const result: string[] = [];
  for (const raw of rawLines) {
    if (!raw) { result.push(''); continue; }
    let line = '';
    for (const ch of raw) {
      const test = line + ch;
      if (ctx.measureText(test).width > maxWidth && line) {
        result.push(line);
        line = ch;
      } else {
        line = test;
      }
    }
    if (line) result.push(line);
  }
  return result;
}
