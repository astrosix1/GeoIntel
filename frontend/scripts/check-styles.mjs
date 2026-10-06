// Style guard for the redesigned stylesheets. Fails (exit 1) if a stylesheet in a converted folder uses a
// hard-coded colour, a font size outside the six-step scale, or a radius outside the two-step scale, so the
// design tokens (src/styles/tokens.css) stay the only source of those values.
//
// Run: npm run lint (it runs after oxlint), or  node scripts/check-styles.mjs
// Folders are added to CONVERTED as each stage of docs/ui-redesign-plan.md converts them.
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

// Entries are folders (every .css inside) or single .css files.
export const CONVERTED = [
  'src/ui',
  'src/shell',
  'src/globe/TimeBar.module.css',
  'src/sidebars/EventsSidebar.module.css',
  'src/sidebars/AnalysisSidebar.module.css',
  'src/sidebars/EdgeTab.module.css',
  'src/sidebars/WorldClock.module.css',
  'src/sidebars/Planner.module.css',
  'src/sidebars/analysis',
  'src/components/SaveButton.module.css',
  'src/components/CopyLinkButton.module.css',
];

const NAMED_COLOURS = /\b(white|black|red|green|blue|yellow|orange|purple|pink|gray|grey|silver|gold|navy|teal|cyan|magenta|lime|maroon|olive|aqua)\b/i;

// Returns [{ line, rule, text }] for every problem in a stylesheet's text.
export function checkCss(text) {
  const problems = [];
  // Comments are free text (they may mention colours); blank them but keep line numbers.
  const stripped = text.replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, ' '));
  stripped.split('\n').forEach((raw, i) => {
    const line = raw.trim();
    if (!line || line.startsWith('@import')) return;
    const add = (rule) => problems.push({ line: i + 1, rule, text: line });

    if (/#[0-9a-f]{3,8}\b/i.test(line)) add('hard-coded hex colour: use a colour token');
    if (/\b(rgba?|hsla?|hwb|lab|lch|oklab|oklch)\(/i.test(line)) add('hard-coded colour function: use a colour token');

    // Every declaration on the line (a rule can be written on one line: ".a { color: white; }").
    for (const match of line.matchAll(/([a-z-]+)\s*:\s*([^;{}]+)/gi)) {
      const name = match[1].toLowerCase();
      const value = match[2].trim();

      if (/^(color|background|background-color|border|border-color|border-top|border-right|border-bottom|border-left|outline|outline-color|fill|stroke|box-shadow|text-shadow)$/.test(name)
        && NAMED_COLOURS.test(value.replace(/var\([^)]*\)/g, ''))) add('named colour: use a colour token');

      if (name === 'font-size' && !/^var\(--font-[1-6]\)$/.test(value) && !/^(inherit|unset|initial)$/.test(value)) {
        add('font size outside the scale: use var(--font-1) to var(--font-6)');
      }

      if (/^border(-[a-z]+)*-radius$/.test(name)
        && !/^(var\(--radius-(1|2|pill)\)|0|50%|inherit)( (var\(--radius-(1|2|pill)\)|0|50%))*$/.test(value)) {
        add('radius outside the scale: use var(--radius-1), var(--radius-2) or var(--radius-pill)');
      }
    }
  });
  return problems;
}

function* cssFiles(dir) {
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) yield* cssFiles(path);
    else if (path.endsWith('.css')) yield path;
  }
}

function main() {
  const root = fileURLToPath(new URL('..', import.meta.url));
  let failures = 0;
  let files = 0;
  for (const entry of CONVERTED) {
    const target = join(root, entry);
    const list = statSync(target).isDirectory() ? cssFiles(target) : [target];
    for (const file of list) {
      files++;
      for (const problem of checkCss(readFileSync(file, 'utf8'))) {
        failures++;
        console.error(`${relative(root, file)}:${problem.line}  ${problem.rule}\n    ${problem.text}`);
      }
    }
  }
  if (failures) {
    console.error(`\n${failures} style problem(s) in ${files} converted stylesheet(s).`);
    process.exit(1);
  }
  console.log(`Style check passed (${files} converted stylesheet(s)).`);
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) main();
