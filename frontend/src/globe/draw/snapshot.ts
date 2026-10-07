import type * as maplibregl from 'maplibre-gl';
import { cleanCredit, wrapText } from './imagetext';

// Saves what the map shows, drawing included, as a PNG for a slide or a document. The map's own picture is taken the moment it
// is drawn (the only time its buffer is guaranteed to hold the frame); the map credits are then added along the bottom, as
// the map data sources require, and the drawing's name along the top if there is one. Weather pins are page elements, not part
// of the map's picture, so they are not in the image.
function nextFrame(map: maplibregl.Map): Promise<HTMLCanvasElement | null> {
  return new Promise((resolve) => {
    const timer = window.setTimeout(() => resolve(null), 4000);
    map.once('render', () => {
      window.clearTimeout(timer);
      const source = map.getCanvas();
      const copy = document.createElement('canvas');
      copy.width = source.width;
      copy.height = source.height;
      copy.getContext('2d')?.drawImage(source, 0, 0);
      resolve(copy);
    });
    map.triggerRepaint();
  });
}

export async function captureMapImage(map: maplibregl.Map, title: string | null): Promise<Blob | null> {
  const frame = await nextFrame(map);
  if (!frame) return null;
  const context = frame.getContext('2d');
  if (!context) return null;
  // Device pixels per CSS pixel, so text is the same size on screen and in the file.
  const ratio = frame.width / Math.max(1, map.getCanvas().clientWidth);
  const pad = 8 * ratio;

  const credit =
    cleanCredit(document.querySelector('.maplibregl-ctrl-attrib-inner')?.textContent ?? '') || 'Map data © OpenStreetMap contributors';
  context.font = `${Math.round(11 * ratio)}px system-ui, -apple-system, 'Segoe UI', sans-serif`;
  const lineHeight = 14 * ratio;
  const lines = wrapText(credit, frame.width - pad * 2, (text) => context.measureText(text).width);
  const bandHeight = lines.length * lineHeight + pad * 1.2;
  context.fillStyle = 'rgba(255, 255, 255, 0.88)';
  context.fillRect(0, frame.height - bandHeight, frame.width, bandHeight);
  context.fillStyle = '#1f2937';
  context.textBaseline = 'top';
  lines.forEach((line, i) => context.fillText(line, pad, frame.height - bandHeight + pad * 0.6 + i * lineHeight));

  if (title) {
    context.font = `600 ${Math.round(18 * ratio)}px system-ui, -apple-system, 'Segoe UI', sans-serif`;
    const width = Math.min(frame.width - pad * 2, context.measureText(title).width + pad * 2);
    context.fillStyle = 'rgba(255, 255, 255, 0.88)';
    context.fillRect(pad, pad, width, 28 * ratio);
    context.fillStyle = '#0f172a';
    context.fillText(title, pad * 2, pad + 5 * ratio, width - pad * 2);
  }

  return new Promise((resolve) => frame.toBlob((blob) => resolve(blob), 'image/png'));
}
