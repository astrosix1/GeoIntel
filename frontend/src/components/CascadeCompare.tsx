import type { CascadeExposure, SavedScenario } from '../api/types';
import { Badge } from '../ui/Display';
import type { BadgeTone } from '../ui/Display';
import styles from './Cascade.module.css';

const TONES: Record<CascadeExposure, BadgeTone> = { High: 'alertRed', Moderate: 'alertOrange', Low: 'neutral' };
const RANK: Record<CascadeExposure, number> = { High: 0, Moderate: 1, Low: 2 };

function describe(s: SavedScenario): string {
  const t = s.result.trigger;
  return `${t.label}: ${t.country_name}${t.commodity_label ? `, ${t.commodity_label.toLowerCase()}` : ''}`;
}

// Two saved scenarios side by side: every country either one lists, with its exposure in each, differences marked.
export default function CascadeCompare({ a, b, onClose }: { a: SavedScenario; b: SavedScenario; onClose: () => void }) {
  const left = new Map(a.result.effects.map((e) => [e.iso, e]));
  const right = new Map(b.result.effects.map((e) => [e.iso, e]));
  const isos = [...new Set([...left.keys(), ...right.keys()])];
  const rows = isos
    .map((iso) => {
      const l = left.get(iso);
      const r = right.get(iso);
      return { iso, name: (l ?? r)!.name, l: l?.exposure, r: r?.exposure, best: Math.min(l ? RANK[l.exposure] : 9, r ? RANK[r.exposure] : 9) };
    })
    .sort((x, y) => x.best - y.best || x.name.localeCompare(y.name));
  const differing = rows.filter((r) => r.l !== r.r).length;
  return (
    <div>
      <button type="button" className={styles.showAll} onClick={onClose}>
        Back
      </button>
      <h3 className={styles.compareTitle}>Comparison</h3>
      <p className={styles.assumes}>
        <strong>A: {a.name}</strong> ({describe(a)})
        <br />
        <strong>B: {b.name}</strong> ({describe(b)})
      </p>
      <p className={styles.assumes}>
        {rows.length} countries in either; {differing} differ. Saved results show what was found when each was saved.
      </p>
      <table className={styles.compare}>
        <thead>
          <tr>
            <th scope="col">Country</th>
            <th scope="col">A</th>
            <th scope="col">B</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.iso} className={r.l !== r.r ? styles.differs : undefined}>
              <th scope="row">{r.name}</th>
              <td>{r.l ? <Badge tone={TONES[r.l]}>{r.l}</Badge> : <span className={styles.meta}>not listed</span>}</td>
              <td>{r.r ? <Badge tone={TONES[r.r]}>{r.r}</Badge> : <span className={styles.meta}>not listed</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
