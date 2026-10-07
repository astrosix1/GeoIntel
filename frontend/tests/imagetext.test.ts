// Run with: npm test
import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { cleanCredit, imageFileName, wrapText } from '../src/globe/draw/imagetext.ts';

// One unit per character: easy to reason about.
const measure = (text: string) => text.length;

describe('credit text', () => {
  it('collapses spaces and line breaks', () => {
    assert.equal(cleanCredit('  MapLibre |  OpenFreeMap \n © OpenMapTiles\t Data from  OSM '), 'MapLibre | OpenFreeMap © OpenMapTiles Data from OSM');
    assert.equal(cleanCredit(''), '');
  });
});

describe('wrapping text', () => {
  it('keeps short text on one line', () => {
    assert.deepEqual(wrapText('a short line', 40, measure), ['a short line']);
  });

  it('breaks at spaces so no line is wider than the limit', () => {
    const lines = wrapText('one two three four five six seven', 14, measure);
    assert.deepEqual(lines, ['one two three', 'four five six', 'seven']);
    assert.ok(lines.every((l) => l.length <= 14));
  });

  it('leaves a word that is too long on a line of its own', () => {
    assert.deepEqual(wrapText('hi supercalifragilistic there', 10, measure), ['hi', 'supercalifragilistic', 'there']);
  });

  it('copes with empty text and extra spaces', () => {
    assert.deepEqual(wrapText('', 10, measure), []);
    assert.deepEqual(wrapText('  a   b  ', 10, measure), ['a b']);
  });

  it('keeps all the words, in order', () => {
    const text = 'Map data © OpenStreetMap contributors, OpenFreeMap, OpenMapTiles, Sentinel-2 imagery 2016 EOxCloudless (CC BY 4.0)';
    assert.equal(wrapText(text, 30, measure).join(' '), text);
  });
});

describe('image file names', () => {
  it('makes a safe name', () => {
    assert.equal(imageFileName('Gulf plan: v2!'), 'gulf-plan-v2.png');
    assert.equal(imageFileName('../../x'), 'x.png');
    assert.equal(imageFileName('???'), 'map.png');
    assert.ok(imageFileName('y'.repeat(300)).length <= 64);
  });
});
