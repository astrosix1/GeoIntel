// Run with: npm test
import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import {
  distanceBetween, formatArea, formatDistance, labelsFor, lineLength, pointAlong, polygonArea, ringArea, ringCenter, segmentLengths,
} from '../src/globe/draw/measure.ts';

const near = (actual: number, expected: number, tolerance: number, what: string) =>
  assert.ok(Math.abs(actual - expected) <= tolerance, `${what}: got ${actual}, expected ${expected} +/- ${tolerance}`);

describe('distances', () => {
  it('one degree along the equator is about 111.2 km', () => {
    near(distanceBetween([0, 0], [1, 0]), 111_195, 50, 'equator degree');
  });

  it('London to Paris is about 344 km', () => {
    near(distanceBetween([-0.1278, 51.5074], [2.3522, 48.8566]), 343_500, 2_000, 'London-Paris');
  });

  it('New York to Los Angeles is about 3,936 km', () => {
    near(distanceBetween([-74.006, 40.7128], [-118.2437, 34.0522]), 3_936_000, 15_000, 'NYC-LA');
  });

  it('is zero for the same point and works across the date line', () => {
    assert.equal(distanceBetween([10, 10], [10, 10]), 0);
    near(distanceBetween([179.5, 0], [-179.5, 0]), 111_195, 50, 'date line degree');
  });

  it('adds up a line segment by segment', () => {
    const line: [number, number][] = [[0, 0], [1, 0], [1, 1]];
    const parts = segmentLengths(line);
    assert.equal(parts.length, 2);
    near(lineLength(line), parts[0] + parts[1], 0.001, 'total');
    near(lineLength(line), 222_390, 100, 'two degrees');
  });

  it('a line with fewer than two points has no length', () => {
    assert.equal(lineLength([]), 0);
    assert.equal(lineLength([[1, 1]]), 0);
  });
});

describe('areas', () => {
  const square = (size: number, lat = 0): [number, number][] => [[0, lat], [size, lat], [size, lat + size], [0, lat + size], [0, lat]];

  it('one degree square at the equator is about 12,364 square km', () => {
    near(ringArea(square(1)), 12_364e6, 40e6, 'equator square');
  });

  it('a degree square is smaller near the pole than at the equator', () => {
    assert.ok(ringArea(square(1, 60)) < ringArea(square(1, 0)) * 0.6);
  });

  it('does not depend on the ring direction or on repeating the first point', () => {
    const ring = square(1);
    near(ringArea([...ring].reverse()), ringArea(ring), 1, 'reversed');
    near(ringArea(ring.slice(0, -1)), ringArea(ring), 1, 'open ring');
  });

  it('subtracts holes', () => {
    const outer = square(2);
    const hole: [number, number][] = [[0.5, 0.5], [1.5, 0.5], [1.5, 1.5], [0.5, 1.5], [0.5, 0.5]];
    near(polygonArea([outer, hole]), ringArea(outer) - ringArea(hole), 1, 'with hole');
  });

  it('is zero for fewer than three corners', () => {
    assert.equal(ringArea([[0, 0], [1, 1]]), 0);
    assert.equal(polygonArea([]), 0);
  });
});

describe('label positions', () => {
  it('finds the middle of a line by distance, not by vertex count', () => {
    const middle = pointAlong([[0, 0], [1, 0], [3, 0]]);
    assert.ok(middle);
    near(middle![0], 1.5, 0.01, 'middle longitude');
  });

  it('averages a ring across the date line to the right side of the world', () => {
    const center = ringCenter([[179, 0], [-179, 0], [-179, 2], [179, 2], [179, 0]]);
    assert.ok(center);
    assert.ok(Math.abs(Math.abs(center![0]) - 180) < 0.01, `longitude ${center![0]}`);
  });
});

describe('formatting', () => {
  it('formats metric distances', () => {
    assert.equal(formatDistance(850, 'metric'), '850 m');
    assert.equal(formatDistance(12_340, 'metric'), '12.3 km');
    assert.equal(formatDistance(1_500_000, 'metric'), '1,500 km');
    assert.equal(formatDistance(1_000, 'metric'), '1 km');
  });

  it('formats imperial distances', () => {
    assert.equal(formatDistance(100, 'imperial'), '328 ft');
    assert.equal(formatDistance(5_000, 'imperial'), '3.11 mi');
  });

  it('formats metric areas in m2, hectares and km2', () => {
    assert.equal(formatArea(8_200, 'metric'), '8,200 m²');
    assert.equal(formatArea(124_000, 'metric'), '12.4 ha');
    assert.equal(formatArea(3_200_000, 'metric'), '3.2 km²');
  });

  it('formats imperial areas in ft2, acres and mi2', () => {
    assert.equal(formatArea(50, 'imperial'), '538 ft²');
    assert.equal(formatArea(40_469, 'imperial'), '10 acres');
    assert.equal(formatArea(13_000_000, 'imperial'), '5.02 mi²');
  });

  it('gives nothing for nonsense', () => {
    assert.equal(formatDistance(NaN, 'metric'), '');
    assert.equal(formatArea(-1, 'imperial'), '');
  });
});

describe('labels for drawn shapes', () => {
  it('shows nothing for a shape that has no size yet', () => {
    const tiny = [[10, 10], [10.0000001, 10.0000001], [10.0000002, 10], [10, 10]];
    assert.deepEqual(labelsFor([{ id: 'x', geometry: { type: 'Polygon', coordinates: [tiny] } }], 'metric'), []);
    assert.deepEqual(labelsFor([{ id: 'y', geometry: { type: 'LineString', coordinates: [[10, 10], [10, 10.0000001]] } }], 'metric'), []);
  });

  it('labels a line with its length and a polygon with its area and perimeter, and skips points', () => {
    const labels = labelsFor(
      [
        { id: 'a', geometry: { type: 'LineString', coordinates: [[0, 0], [1, 0]] } },
        { id: 'b', geometry: { type: 'Polygon', coordinates: [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]] } },
        { id: 'c', geometry: { type: 'Point', coordinates: [0, 0] } },
        { id: 'd', geometry: { type: 'LineString', coordinates: [[0, 0]] } },
      ],
      'metric',
    );
    assert.deepEqual(labels.map((l) => l.id), ['a', 'b']);
    assert.equal(labels[0].text, '111 km');
    assert.ok(labels[1].text.startsWith('12,36'), labels[1].text);
    assert.ok(labels[1].text.includes('around'));
  });
});
