// Pure helpers for the country figures (no imports, so they can be unit-tested: frontend/tests/countrychart.test.ts).

export type Point = [number, number];

// The SVG path of a trend line through [year, value] points, scaled to fit a width x height box. Empty for fewer than two points.
export function sparklinePath(points: Point[], width: number, height: number, pad = 2): string {
  if (points.length < 2) return '';
  const years = points.map((p) => p[0]);
  const values = points.map((p) => p[1]);
  const [x0, x1] = [Math.min(...years), Math.max(...years)];
  const [y0, y1] = [Math.min(...values), Math.max(...values)];
  const x = (year: number) => pad + ((year - x0) / (x1 - x0 || 1)) * (width - pad * 2);
  const y = (value: number) => height - pad - ((value - y0) / (y1 - y0 || 1)) * (height - pad * 2);
  return points.map(([year, value], i) => `${i === 0 ? 'M' : 'L'}${x(year).toFixed(1)} ${y(value).toFixed(1)}`).join(' ');
}

export function formatNumber(value: number, decimals: number): string {
  return value.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

// How a figure has moved since the first year of its series, in neutral words (whether up is good depends on the figure).
// Percentages and rates move in points ("down 2.5 points"), because a percentage change of a percentage is misleading; other
// figures move in percent, unless the series touches zero, where a percentage change means nothing and only the start is given.
export function changeText(series: Point[], unit = '', decimals = 1): string | null {
  if (series.length < 2) return null;
  const [firstYear, first] = series[0];
  const last = series[series.length - 1][1];
  if (unit.startsWith('%')) {
    const diff = last - first;
    if (Math.abs(diff) < 0.05) return `little changed since ${firstYear}`;
    return `${diff > 0 ? 'up' : 'down'} ${formatNumber(Math.abs(diff), 1)} points since ${firstYear}`;
  }
  if (series.some((p) => p[1] <= 0)) return `was ${formatNumber(first, decimals)} in ${firstYear}`;
  const change = ((last - first) / first) * 100;
  if (Math.abs(change) < 0.5) return `little changed since ${firstYear}`;
  return `${change > 0 ? 'up' : 'down'} ${formatNumber(Math.abs(change), Math.abs(change) < 10 ? 1 : 0)}% since ${firstYear}`;
}

// 3,366,300,000,000 -> "3.4T", 68,720,337 -> "68.7M": for figures too long to read at a glance.
export function formatCompact(value: number): string {
  return new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 2 }).format(value);
}
