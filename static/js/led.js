// Building frames out of component sprites, and drawing them as LEDs on a <canvas>.
//
// The server draws each component on its own (a "sprite": RGBA pixels the size of its box),
// with the same code that drives the panel. The page places the sprites itself, so dragging
// is instant and still shows exactly the pixels the panel will.

export function decodeBase64(text) {
  const binary = atob(text);
  const bytes = new Uint8ClampedArray(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

// Draws an RGBA sprite onto an RGB frame at (ox, oy), clipped to the frame
function blit(frame, width, height, sprite, ox, oy) {
  const { w, h, pixels } = sprite;
  for (let y = 0; y < h; y++) {
    const fy = oy + y;
    if (fy < 0 || fy >= height) continue;
    for (let x = 0; x < w; x++) {
      const fx = ox + x;
      if (fx < 0 || fx >= width) continue;
      const s = (y * w + x) * 4;
      const a = pixels[s + 3];
      if (!a) continue;
      const f = (fy * width + fx) * 3;
      if (a === 255) {
        frame[f] = pixels[s];
        frame[f + 1] = pixels[s + 1];
        frame[f + 2] = pixels[s + 2];
      } else {
        for (let c = 0; c < 3; c++) frame[f + c] = (pixels[s + c] * a + frame[f + c] * (255 - a)) / 255;
      }
    }
  }
}

// The RGB frame for a screen's widgets, drawn in order (later ones on top) like renderer.py
export function compose(widgets, sprites, width, height) {
  const frame = new Uint8ClampedArray(width * height * 3);
  for (const widget of widgets) {
    if (widget.hidden) continue;
    const sprite = sprites.get(widget.id);
    if (sprite && sprite.pixels) blit(frame, width, height, sprite, widget.x, widget.y);
  }
  return frame;
}

// Draws pixels (RGB, or RGBA with channels: 4) as LEDs, `pitch` CSS pixels apart.
// background / off: colors for the panel and unlit LEDs, or null to leave them out.
export function drawLeds(canvas, pixels, width, height, pitch, options = {}) {
  const { channels = 3, background = '#060708', off = '#16191d' } = options;
  const ratio = window.devicePixelRatio || 1;
  const cssWidth = width * pitch;
  const cssHeight = height * pitch;
  const pixelWidth = Math.round(cssWidth * ratio);
  const pixelHeight = Math.round(cssHeight * ratio);
  if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) {
    canvas.width = pixelWidth;
    canvas.height = pixelHeight;
  }
  canvas.style.width = `${cssWidth}px`;
  canvas.style.height = `${cssHeight}px`;

  const ctx = canvas.getContext('2d');
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, cssWidth, cssHeight);
  if (background) {
    ctx.fillStyle = background;
    ctx.fillRect(0, 0, cssWidth, cssHeight);
  }

  // Group LEDs by color so each color is one fill
  const lit = new Map();
  const unlit = [];
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const i = (y * width + x) * channels;
      const on = (pixels[i] | pixels[i + 1] | pixels[i + 2]) && (channels === 3 || pixels[i + 3]);
      if (on) {
        const key = (pixels[i] << 16) | (pixels[i + 1] << 8) | pixels[i + 2];
        let list = lit.get(key);
        if (!list) lit.set(key, (list = []));
        list.push(x, y);
      } else if (off) {
        unlit.push(x, y);
      }
    }
  }

  const round = pitch >= 5;
  const gap = pitch >= 3 ? 1 : 0;
  const radius = pitch * 0.42;
  const dots = (list, r) => {
    ctx.beginPath();
    for (let i = 0; i < list.length; i += 2) {
      const x = list[i] * pitch;
      const y = list[i + 1] * pitch;
      if (round) {
        ctx.moveTo(x + pitch / 2 + r, y + pitch / 2);
        ctx.arc(x + pitch / 2, y + pitch / 2, r, 0, Math.PI * 2);
      } else {
        ctx.rect(x, y, pitch - gap, pitch - gap);
      }
    }
    ctx.fill();
  };

  if (unlit.length) {
    ctx.fillStyle = off;
    dots(unlit, radius);
  }
  for (const [key, list] of lit) {
    ctx.fillStyle = `rgb(${key >> 16}, ${(key >> 8) & 255}, ${key & 255})`;
    if (round) {
      // A soft halo, like a lit LED behind a diffuser
      ctx.globalAlpha = 0.16;
      dots(list, radius * 1.5);
      ctx.globalAlpha = 1;
    }
    dots(list, radius);
  }
}
