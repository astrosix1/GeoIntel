import { useMemo, useState } from 'react';
import { loadWorkHours, saveWorkHours } from '../lib/clocks';
import { cleanWorkHours, localParts, pairGapNotes, plannerRows, windowSummary } from '../lib/planner';
import type { HourCategory, WorkHours } from '../lib/planner';
import { cityName } from '../lib/timezones';
import { useUiStore } from '../state/uiStore';
import styles from './Planner.module.css';

const DURATIONS = [30, 60, 90, 120];
const CATEGORY_LABEL: Record<HourCategory, string> = { working: 'working hours', early: 'early', late: 'late', night: 'night' };

function dateValue(parts: { year: number; month: number; day: number }): string {
  return `${parts.year}-${String(parts.month).padStart(2, '0')}-${String(parts.day).padStart(2, '0')}`;
}

// Meeting planner: 24 hours of the chosen place's day down the side, one column per pinned place showing
// that place's own local time, coloured by working hours, early or late, or night.
export default function PlannerPanel() {
  const clocks = useUiStore((s) => s.clocks);
  const [refChoice, setRefChoice] = useState<string | null>(null);
  const [date, setDate] = useState<string | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [minutes, setMinutes] = useState(60);
  const [work, setWork] = useState<WorkHours>(loadWorkHours);
  const [copied, setCopied] = useState(false);

  const ref = refChoice && clocks.includes(refChoice) ? refChoice : clocks[0];
  const day = date ?? (ref ? dateValue(localParts(ref, new Date())) : '');
  const [year, month, dayOfMonth] = day.split('-').map(Number);
  const valid = ref && clocks.length >= 2 && Number.isInteger(year) && month >= 1 && month <= 12 && dayOfMonth >= 1;

  const rows = useMemo(
    () => (valid ? plannerRows(ref, year, month, dayOfMonth, clocks, work) : []),
    [valid, ref, year, month, dayOfMonth, clocks, work],
  );
  const chosen = selected !== null ? rows[selected] : null;
  const summary = chosen?.instant ? windowSummary(chosen.instant, minutes, clocks, work) : [];
  const notes = chosen?.instant ? pairGapNotes(clocks, chosen.instant) : [];

  function chooseWork(next: WorkHours) {
    const cleaned = cleanWorkHours(next);
    setWork(cleaned);
    saveWorkHours(cleaned);
  }

  async function copy() {
    if (!summary.length) return;
    const text = summary.map((p) => `${cityName(p.tzid)} ${p.start}-${p.end} ${p.startDay}`).join('\n');
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2500);
    } catch {
      window.prompt('Copy these times:', text);
    }
  }

  if (clocks.length < 2) {
    return <div className={styles.panel}><div className={styles.note}>Pin at least two places on the Clocks tab to plan a meeting across them.</div></div>;
  }

  return (
    <div className={styles.panel}>
      <div className={styles.row}>
        <label>
          Day in
          <select className={styles.field} value={ref} onChange={(e) => { setRefChoice(e.target.value); setSelected(null); }} aria-label="Place whose day is shown down the side">
            {clocks.map((z) => <option key={z} value={z}>{cityName(z)}</option>)}
          </select>
        </label>
        <input
          className={styles.field}
          type="date"
          value={day}
          onChange={(e) => { setDate(e.target.value || null); setSelected(null); }}
          aria-label="Date"
        />
      </div>
      <div className={styles.row}>
        <label>
          Work
          <select className={styles.field} value={work.start} onChange={(e) => chooseWork({ ...work, start: Number(e.target.value) })} aria-label="Working day starts">
            {Array.from({ length: 24 }, (_, h) => <option key={h} value={h}>{String(h).padStart(2, '0')}:00</option>)}
          </select>
          to
          <select className={styles.field} value={work.end} onChange={(e) => chooseWork({ ...work, end: Number(e.target.value) })} aria-label="Working day ends">
            {Array.from({ length: 24 }, (_, h) => <option key={h + 1} value={h + 1}>{String(h + 1).padStart(2, '0')}:00</option>)}
          </select>
        </label>
        <label>
          Length
          <select className={styles.field} value={minutes} onChange={(e) => setMinutes(Number(e.target.value))} aria-label="Meeting length">
            {DURATIONS.map((m) => <option key={m} value={m}>{m} min</option>)}
          </select>
        </label>
      </div>

      <table className={styles.grid}>
        <thead>
          <tr>
            <th className={styles.hourHead} scope="col" />
            {clocks.map((z) => <th key={z} scope="col" title={z}>{cityName(z)}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) =>
            row.instant === null ? (
              <tr key={row.hour} className={styles.skipped}>
                <td className={styles.hourCell}>{String(row.hour).padStart(2, '0')}</td>
                <td colSpan={clocks.length}>clocks skip this hour</td>
              </tr>
            ) : (
              <tr key={row.hour} className={selected === i ? styles.selected : ''} onClick={() => setSelected(i)} aria-selected={selected === i}>
                <td className={styles.hourCell}>{String(row.hour).padStart(2, '0')}</td>
                {row.cells.map((cell) => (
                  <td key={cell.tzid} className={`${styles.cell} ${styles[cell.category]}`} title={`${cityName(cell.tzid)}: ${CATEGORY_LABEL[cell.category]}`}>
                    {cell.time.slice(0, 5)}
                    {cell.dayOffset !== 0 && <span className={styles.day}>{cell.dayOffset > 0 ? '+1' : '-1'}</span>}
                  </td>
                ))}
              </tr>
            ),
          )}
        </tbody>
      </table>
      <div className={styles.legend}>
        <span><span className={`${styles.swatch} ${styles.working}`} />Working hours</span>
        <span><span className={`${styles.swatch} ${styles.early}`} />Early or late</span>
        <span><span className={`${styles.swatch} ${styles.night}`} />Night</span>
        <span><span className={styles.day}>+1</span> next day</span>
      </div>

      {chosen?.instant ? (
        <div className={styles.summary}>
          {summary.map((place) => (
            <div key={place.tzid} className={styles.summaryLine}>
              <span>{cityName(place.tzid)}</span>
              <span>{place.start}&ndash;{place.end} {place.startDay} <em>({CATEGORY_LABEL[place.worst]})</em></span>
            </div>
          ))}
          {notes.map((note) => <div key={note} className={styles.warn}>{note}</div>)}
          <button type="button" className={styles.copy} onClick={copy}>{copied ? 'Copied' : 'Copy as text'}</button>
        </div>
      ) : (
        <div className={styles.note}>Click an hour to see everyone&apos;s local time for a meeting starting then.</div>
      )}
    </div>
  );
}
