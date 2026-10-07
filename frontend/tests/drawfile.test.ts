// Run with: npm test
import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { buildDrawing, DRAWING_VERSION, drawingSize, exportFileName, MAX_SHAPES, parseDrawing, toGeoJSON } from '../src/globe/draw/drawfile.ts';

const layers = [{ id: 'a', name: 'Scenario A', visible: true, note: 'n' }, { id: 'b', name: 'Scenario B', visible: false, note: '' }];
const square = { type: 'Polygon', coordinates: [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]] };
const feature = (id: string, mode: string, geometry: { type: string; coordinates: unknown }, props: Record<string, unknown> = {}) => ({
  id, type: 'Feature', geometry, properties: { mode, ...props },
});

describe('building a drawing to save', () => {
  it('keeps shapes with their mode, style and layer, and drops everything else', () => {
    const data = buildDrawing(
      [feature('11111111-1111-4111-8111-111111111111', 'polygon', square, { color: '#ef4444', width: 5, label: 'Zone', layer: 'b', zIndex: 9, pointColor: '#fff', selected: false })],
      layers,
    );
    assert.equal(data.version, DRAWING_VERSION);
    assert.deepEqual(data.features[0].properties, { color: '#ef4444', width: 5, label: 'Zone', mode: 'polygon', layer: 'b' });
    assert.equal(data.features[0].id, '11111111-1111-4111-8111-111111111111');
    assert.deepEqual(data.layers.map((l) => l.id), ['a', 'b']);
  });

  it('puts a shape with an unknown layer on the first layer, and skips shapes with no mode or bad geometry', () => {
    const data = buildDrawing(
      [
        feature('x1', 'point', { type: 'Point', coordinates: [1, 2] }, { layer: 'gone' }),
        feature('x2', 'nonsense', { type: 'Point', coordinates: [1, 2] }),
        feature('x3', 'point', { type: 'Point', coordinates: [1, 999] }),
        { geometry: { type: 'Point', coordinates: [1, 2] }, properties: {} },
      ],
      layers,
    );
    assert.equal(data.features.length, 1);
    assert.equal(data.features[0].properties.layer, 'a');
  });

  it('always has at least one layer', () => {
    assert.equal(buildDrawing([], []).layers.length, 1);
  });
});

describe('reading a drawing back', () => {
  it('round-trips its own format', () => {
    const built = buildDrawing([feature('r1', 'linestring', { type: 'LineString', coordinates: [[0, 0], [1, 1]] }, { dash: 'dashed', layer: 'b' })], layers);
    const read = parseDrawing(JSON.parse(JSON.stringify(built)));
    assert.ok(read.ok);
    if (read.ok) {
      assert.deepEqual(read.drawing.data, built);
      assert.equal(read.drawing.skipped, 0);
    }
  });

  it('reads plain GeoJSON from another tool: modes from geometry, names from name or title', () => {
    const read = parseDrawing({
      type: 'FeatureCollection',
      features: [
        { type: 'Feature', geometry: { type: 'Point', coordinates: [10, 20] }, properties: { name: 'Depot' } },
        { type: 'Feature', geometry: { type: 'LineString', coordinates: [[0, 0], [1, 1]] }, properties: { title: 'Road', stroke: '#ff0000' } },
        { type: 'Feature', geometry: square, properties: null },
      ],
    });
    assert.ok(read.ok);
    if (read.ok) {
      const [point, line, area] = read.drawing.data.features;
      assert.deepEqual([point.properties.mode, point.properties.label], ['point', 'Depot']);
      assert.deepEqual([line.properties.mode, line.properties.label], ['linestring', 'Road']);
      assert.equal(area.properties.mode, 'polygon');
      assert.equal(line.properties.color, undefined);
      assert.equal(read.drawing.data.layers.length, 1);
    }
  });

  it('accepts a single Feature', () => {
    const read = parseDrawing({ type: 'Feature', geometry: { type: 'Point', coordinates: [1, 2] }, properties: {} });
    assert.ok(read.ok && read.drawing.data.features.length === 1);
  });

  it('skips shapes it cannot draw and says how many', () => {
    const read = parseDrawing({
      type: 'FeatureCollection',
      features: [
        { type: 'Feature', geometry: { type: 'MultiPolygon', coordinates: [] }, properties: {} },
        { type: 'Feature', geometry: { type: 'Point', coordinates: [1, 2] }, properties: {} },
        { type: 'Feature', geometry: null, properties: {} },
        'junk',
      ],
    });
    assert.ok(read.ok);
    if (read.ok) {
      assert.equal(read.drawing.data.features.length, 1);
      assert.equal(read.drawing.skipped, 3);
    }
  });

  it('rejects anything that is not a drawing or GeoJSON', () => {
    for (const bad of [null, 5, 'x', [], {}, { type: 'Topology' }]) {
      const read = parseDrawing(bad);
      assert.ok(!read.ok && read.error === 'format', JSON.stringify(bad));
    }
  });

  it('reports a file with no shapes at all as empty', () => {
    const read = parseDrawing({ type: 'FeatureCollection', features: [] });
    assert.ok(!read.ok && read.error === 'empty');
  });

  it('keeps only valid style values and strips control characters from text', () => {
    const read = parseDrawing({
      type: 'FeatureCollection',
      features: [{ type: 'Feature', geometry: { type: 'Point', coordinates: [1, 2] }, properties: { color: '#123456', width: 4, label: 'a\u0000b', note: 'ok', evil: '<x>' } }],
    });
    assert.ok(read.ok);
    if (read.ok) assert.deepEqual(read.drawing.data.features[0].properties, { label: 'ab', note: 'ok', mode: 'point', layer: read.drawing.data.layers[0].id });
  });

  it('moves a shape on an unknown layer to the first layer', () => {
    const read = parseDrawing({ version: 1, layers, features: [{ type: 'Feature', geometry: { type: 'Point', coordinates: [1, 2] }, properties: { mode: 'point', layer: 'nope' } }] });
    assert.ok(read.ok && read.drawing.data.features[0].properties.layer === 'a');
  });

  it('enforces the shape and vertex limits', () => {
    const many = Array.from({ length: MAX_SHAPES + 1 }, () => ({ type: 'Feature', geometry: { type: 'Point', coordinates: [1, 2] }, properties: {} }));
    const tooMany = parseDrawing({ type: 'FeatureCollection', features: many });
    assert.ok(!tooMany.ok && tooMany.error === 'too_many_shapes');
    const bigLine = { type: 'Feature', geometry: { type: 'LineString', coordinates: Array.from({ length: 12_000 }, (_, i) => [i / 1000, 0]) }, properties: {} };
    const tooBig = parseDrawing({ type: 'FeatureCollection', features: [bigLine, bigLine] });
    assert.ok(!tooBig.ok && tooBig.error === 'too_many_vertices');
  });
});

describe('export', () => {
  it('writes a GeoJSON FeatureCollection that carries the layers and reads back', () => {
    const data = buildDrawing([feature('e1', 'polygon', square, { layer: 'b', color: '#22c55e' })], layers);
    const text = toGeoJSON(data, 'Gulf plan');
    const parsed = JSON.parse(text);
    assert.equal(parsed.type, 'FeatureCollection');
    assert.equal(parsed.name, 'Gulf plan');
    assert.deepEqual(parsed.geointel.layers.map((l: { id: string }) => l.id), ['a', 'b']);
    const back = parseDrawing(parsed);
    assert.ok(back.ok);
    if (back.ok) {
      assert.deepEqual(back.drawing.data.layers, data.layers);
      assert.equal(back.drawing.data.features[0].properties.layer, 'b');
    }
  });

  it('makes a safe file name', () => {
    assert.equal(exportFileName('Gulf plan: v2!'), 'gulf-plan-v2.geojson');
    assert.equal(exportFileName('../../etc/passwd'), 'etc-passwd.geojson');
    assert.equal(exportFileName('!!!'), 'drawing.geojson');
    assert.ok(exportFileName('x'.repeat(300)).length <= 70);
  });

  it('measures the size of a drawing', () => {
    assert.ok(drawingSize(buildDrawing([], [])) > 20);
  });
});

describe('coordinate precision', () => {
  it('rounds positions to nine decimal places, as the drawing engine requires', () => {
    const read = parseDrawing({
      type: 'FeatureCollection',
      features: [{ type: 'Feature', geometry: { type: 'Point', coordinates: [10.123456789012345, -20.987654321098765] }, properties: {} }],
    });
    assert.ok(read.ok);
    if (read.ok) assert.deepEqual(read.drawing.data.features[0].geometry.coordinates, [10.123456789, -20.987654321]);
  });

  it('keeps ordinary positions exactly', () => {
    const read = parseDrawing({ type: 'Feature', geometry: { type: 'Point', coordinates: [1.5, -2.25] }, properties: {} });
    assert.ok(read.ok);
    if (read.ok) assert.deepEqual(read.drawing.data.features[0].geometry.coordinates, [1.5, -2.25]);
  });
});

describe('longitudes past the date line', () => {
  it('wraps a longitude written past 180 round to the same place and leaves 180 itself alone', () => {
    const read = parseDrawing({
      type: 'FeatureCollection',
      features: [
        { type: 'Feature', geometry: { type: 'Point', coordinates: [190, 5] }, properties: {} },
        { type: 'Feature', geometry: { type: 'Point', coordinates: [-181, 5] }, properties: {} },
        { type: 'Feature', geometry: { type: 'Point', coordinates: [180, 5] }, properties: {} },
        { type: 'Feature', geometry: { type: 'Point', coordinates: [-180, 5] }, properties: {} },
      ],
    });
    assert.ok(read.ok);
    if (read.ok) assert.deepEqual(read.drawing.data.features.map((f) => (f.geometry.coordinates as number[])[0]), [-170, 179, 180, -180]);
  });
});
