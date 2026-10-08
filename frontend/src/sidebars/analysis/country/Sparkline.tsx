import { sparklinePath, type Point } from './chart';
import styles from './Stat.module.css';

// A tiny trend line for one series of [year, value] points. Decorative detail only: the figures beside it say the same thing
// in words, and the label here is what a screen reader hears.
export default function Sparkline({ points, label, width = 96, height = 26 }: { points: Point[]; label: string; width?: number; height?: number }) {
  const path = sparklinePath(points, width, height);
  if (!path) return null;
  return (
    <svg className={styles.spark} width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={label}>
      <path d={path} fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}
