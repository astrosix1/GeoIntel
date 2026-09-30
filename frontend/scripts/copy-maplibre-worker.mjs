// MapLibre GL JS loads its tile-parsing worker from a URL it builds
// dynamically at runtime (not a static import Vite's build can detect and
// bundle/hash automatically), and always requests it at
// "<base>/assets/maplibre-gl-worker.mjs". We copy the package's real
// worker file into public/assets under that exact name so Vite serves it
// verbatim at that path in both dev and the production build — without
// this, the worker request 404s (or, behind our SPA catch-all route,
// silently gets index.html back with the wrong MIME type) and MapLibre
// falls back to main-thread tile parsing with a console error.
import { copyFileSync, mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..');
const src = path.join(root, 'node_modules', 'maplibre-gl', 'dist', 'maplibre-gl-worker.mjs');
const destDir = path.join(root, 'public', 'assets');
const dest = path.join(destDir, 'maplibre-gl-worker.mjs');

mkdirSync(destDir, { recursive: true });
copyFileSync(src, dest);
console.log('[copy-maplibre-worker] copied maplibre-gl worker to public/assets/');
