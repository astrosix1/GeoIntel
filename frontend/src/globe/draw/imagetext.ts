// The words that go on a saved image of the map: the map credits (required by the map data sources, so they are always on the
// image) and the drawing's title, wrapped to fit. This file imports nothing so it can be unit-tested
// (frontend/tests/imagetext.test.ts).

// The credit line as the map shows it, tidied: runs of spaces and line breaks become single spaces.
export function cleanCredit(raw: string): string {
  return raw.replace(/\s+/g, ' ').trim();
}

// Splits text into lines no wider than `maxWidth`, breaking at spaces. `measure` gives the width of a piece of text (the
// canvas's own measureText when drawing). A single word wider than a line is left on a line of its own.
export function wrapText(text: string, maxWidth: number, measure: (text: string) => number): string[] {
  const words = text.split(' ').filter((w) => w !== '');
  const lines: string[] = [];
  let line = '';
  for (const word of words) {
    const candidate = line === '' ? word : `${line} ${word}`;
    if (line !== '' && measure(candidate) > maxWidth) {
      lines.push(line);
      line = word;
    } else {
      line = candidate;
    }
  }
  if (line !== '') lines.push(line);
  return lines;
}

// A safe file name for a saved image: letters, digits and dashes, never empty.
export function imageFileName(name: string): string {
  const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60);
  return `${slug || 'map'}.png`;
}
