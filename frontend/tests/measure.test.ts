// Run with: npm test
import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import {
  angleAt, bearingBetween, compassPoint, distanceBetween, formatAngle, formatArea, formatBearing, formatCoordinates, formatDistance,
  labelsFor, lineLength, midpointBetween, pointAlong, polygonArea, ringArea, ringCenter, segmentLengths,
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

describe('bearings and angles', () => {
  it('gives the compass bearing between points', () => {
    near(bearingBetween([0, 0], [0, 1]), 0, 0.001, 'north');
    near(bearingBetween([0, 0], [1, 0]), 90, 0.001, 'east');
    near(bearingBetween([0, 0], [0, -1]), 180, 0.001, 'south');
    near(bearingBetween([0, 0], [-1, 0]), 270, 0.001, 'west');
    near(bearingBetween([0, 0], [1, 1]), 45, 0.1, 'north-east');
  });

  it('names the eight compass points and pads bearings to three digits', () => {
    assert.equal(compassPoint(0), 'N');
    assert.equal(compassPoint(47), 'NE');
    assert.equal(compassPoint(350), 'N');
    assert.equal(compassPoint(180), 'S');
    assert.equal(compassPoint(271), 'W');
    assert.equal(formatBearing(47.2), '047° NE');
    assert.equal(formatBearing(0), '000° N');
    assert.equal(formatBearing(359.7), '000° N');
  });

  it('measures a right angle and a straight line', () => {
    near(angleAt([0, 1], [0, 0], [1, 0]), 90, 0.01, 'right angle');
    near(angleAt([-1, 0], [0, 0], [1, 0]), 180, 0.01, 'straight');
    near(angleAt([0, 1], [0, 0], [0, 2]), 0, 0.01, 'folded back');
  });

  it('never reports more than 180 degrees, whichever way round the corners are given', () => {
    near(angleAt([1, 0], [0, 0], [0, 1]), angleAt([0, 1], [0, 0], [1, 0]), 0.001, 'order');
    near(angleAt([-1, 0.01], [0, 0], [0, 1]), 90, 1, 'obtuse side');
  });

  it('formats angles to one decimal', () => {
    assert.equal(formatAngle(90), '90°');
    assert.equal(formatAngle(62.349), '62.3°');
  });
});

describe('midpoints and coordinates', () => {
  it('finds the great-circle midpoint, including across the date line', () => {
    const middle = midpointBetween([0, 0], [2, 0]);
    near(middle[0], 1, 0.001, 'equator longitude');
    near(middle[1], 0, 0.001, 'equator latitude');
    const across = midpointBetween([179, 0], [-179, 0]);
    assert.ok(Math.abs(Math.abs(across[0]) - 180) < 0.001, `date line ${across[0]}`);
  });

  it('bows towards the pole on a long east-west line', () => {
    const middle = midpointBetween([-60, 50], [60, 50]);
    assert.ok(middle[1] > 50, `latitude ${middle[1]}`);
  });

  it('formats coordinates with hemispheres', () => {
    assert.equal(formatCoordinates([-0.1278, 51.5074]), '51.5074° N, 0.1278° W');
    assert.equal(formatCoordinates([151.2093, -33.8688]), '33.8688° S, 151.2093° E');
  });
});

describe('nautical units', () => {
  it('formats nautical miles, and metres when short', () => {
    assert.equal(formatDistance(1852, 'nautical'), '1 nm');
    assert.equal(formatDistance(18_520, 'nautical'), '10 nm');
    assert.equal(formatDistance(120, 'nautical'), '120 m');
  });

  it('uses the metric area units', () => {
    assert.equal(formatArea(3_200_000, 'nautical'), '3.2 km²');
  });
});

describe('labels for drawn shapes', () => {
  const plain = { units: 'metric' as const, segments: false, angles: false, bearings: false };
  const line = (id: string, coordinates: [number, number][], mode = 'linestring') => ({ id, properties: { mode }, geometry: { type: 'LineString', coordinates } });
  const polygon = (id: string, ring: [number, number][], mode = 'polygon') => ({ id, properties: { mode }, geometry: { type: 'Polygon', coordinates: [ring] } });
  const square: [number, number][] = [[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]];

  it('labels a line with its length and a polygon with its area and perimeter, and a point with its coordinates', () => {
    const labels = labelsFor(
      [line('a', [[0, 0], [1, 0]]), polygon('b', square), { id: 'c', properties: { mode: 'point' }, geometry: { type: 'Point', coordinates: [10, 20] } }, line('d', [[0, 0]])],
      plain,
    );
    assert.deepEqual(labels.map((l) => l.id), ['a', 'b', 'c']);
    assert.equal(labels[0].text, '111 km');
    assert.ok(labels[1].text.startsWith('12,36') && labels[1].text.includes('around'), labels[1].text);
    assert.equal(labels[2].text, '20.0000° N, 10.0000° E');
  });

  it('shows nothing for a shape that has no size yet', () => {
    const tiny: [number, number][] = [[10, 10], [10.0000001, 10.0000001], [10.0000002, 10], [10, 10]];
    assert.deepEqual(labelsFor([polygon('x', tiny), line('y', [[10, 10], [10, 10.0000001]])], plain), []);
  });

  it('adds a length for every segment of a line only when asked', () => {
    const bent = line('l', [[0, 0], [1, 0], [1, 1]]);
    assert.equal(labelsFor([bent], plain).filter((l) => l.kind === 'segment').length, 0);
    const segments = labelsFor([bent], { ...plain, segments: true }).filter((l) => l.kind === 'segment');
    assert.equal(segments.length, 2);
    assert.ok(segments.every((l) => l.text.endsWith('km')));
  });

  it('adds bearings, and puts a single segment bearing on the total label', () => {
    const single = labelsFor([line('l', [[0, 0], [0, 1]])], { ...plain, bearings: true });
    assert.equal(single.length, 1);
    assert.equal(single[0].text, '111 km · 000° N');
    const bent = labelsFor([line('l', [[0, 0], [1, 0], [1, 1]])], { ...plain, bearings: true }).filter((l) => l.kind === 'segment');
    assert.deepEqual(bent.map((l) => l.text), ['090° E', '000° N']);
  });

  it('adds the angle at each inner corner of a line, and at every corner of a polygon', () => {
    const bent = labelsFor([line('l', [[0, 1], [0, 0], [1, 0]])], { ...plain, angles: true }).filter((l) => l.kind === 'angle');
    assert.equal(bent.length, 1);
    assert.equal(bent[0].text, '90°');
    const corners = labelsFor([polygon('p', square)], { ...plain, angles: true }).filter((l) => l.kind === 'angle');
    assert.equal(corners.length, 4);
  });

  it('labels the angle tool with the angle and both legs, whatever the switches say', () => {
    const labels = labelsFor([line('a', [[0, 1], [0, 0], [1, 0]], 'angle')], plain);
    assert.deepEqual(labels.map((l) => l.kind).sort(), ['angle', 'segment', 'segment']);
    assert.equal(labels.find((l) => l.kind === 'angle')?.text, '90°');
  });

  it('labels a circle with its radius, area and circumference', () => {
    const ring: [number, number][] = [];
    for (let i = 0; i <= 64; i++) {
      const angle = (i / 64) * 2 * Math.PI;
      ring.push([Math.cos(angle) * 0.1, Math.sin(angle) * 0.1]);
    }
    const [label] = labelsFor([polygon('c', ring, 'circle')], plain);
    assert.ok(label.text.startsWith('r 11.1 km'), label.text);
    assert.ok(label.text.includes('around'));
  });

  it('keeps a many-cornered polygon to its total', () => {
    const ring: [number, number][] = [];
    for (let i = 0; i <= 40; i++) {
      const angle = (i / 40) * 2 * Math.PI;
      ring.push([Math.cos(angle), Math.sin(angle)]);
    }
    const labels = labelsFor([polygon('many', ring)], { ...plain, segments: true, angles: true });
    assert.equal(labels.length, 1);
  });
});

describe('names and text on shapes', () => {
  const plain = { units: 'metric' as const, segments: false, angles: false, bearings: false };

  it('adds the shape name at the shape, alongside its measurements', () => {
    const labels = labelsFor(
      [{ id: 'a', properties: { mode: 'linestring', label: 'Evacuation route' }, geometry: { type: 'LineString', coordinates: [[0, 0], [1, 0]] } }],
      plain,
    );
    assert.deepEqual(labels.map((l) => l.kind).sort(), ['name', 'total']);
    assert.equal(labels.find((l) => l.kind === 'name')?.text, 'Evacuation route');
  });

  it('names an area and a point too', () => {
    const labels = labelsFor(
      [
        { id: 'p', properties: { mode: 'polygon', label: 'Zone A' }, geometry: { type: 'Polygon', coordinates: [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]] } },
        { id: 'q', properties: { mode: 'point', label: 'Checkpoint' }, geometry: { type: 'Point', coordinates: [5, 5] } },
      ],
      plain,
    );
    assert.deepEqual(labels.filter((l) => l.kind === 'name').map((l) => l.text).sort(), ['Checkpoint', 'Zone A']);
  });

  it('draws the Text tool as its text alone, in the shape colour, with no coordinates', () => {
    const labels = labelsFor([{ id: 't', properties: { mode: 'text', label: 'Staging area', color: '#ef4444' }, geometry: { type: 'Point', coordinates: [5, 5] } }], plain);
    assert.equal(labels.length, 1);
    assert.deepEqual([labels[0].kind, labels[0].text, labels[0].color], ['text', 'Staging area', '#ef4444']);
  });

  it('gives the Text tool a placeholder until it has words', () => {
    const labels = labelsFor([{ id: 't', properties: { mode: 'text' }, geometry: { type: 'Point', coordinates: [5, 5] } }], plain);
    assert.equal(labels[0].text, 'Text');
  });

  it('ignores a name that is not text', () => {
    const labels = labelsFor([{ id: 'a', properties: { mode: 'linestring', label: 7 }, geometry: { type: 'LineString', coordinates: [[0, 0], [1, 0]] } }], plain);
    assert.deepEqual(labels.map((l) => l.kind), ['total']);
  });
});
