import { useMemo, useState } from 'react';
import { loadWorkHours } from '../lib/clocks';
import { formatLine, hourCategory, localParts, pairGapNotes, parseTimeInput } from '../lib/planner';
import { cityName } from '../lib/timezones';
import { useUiStore } from '../state/uiStore';
import styles from './Planner.module.css';

// Type a time ("9am New York", "14:00 UTC", "2026-11-02 17:30 Tokyo") and see it in every pinned place.
// Only a small set of forms is understood; anything else is refused with a reason, never guessed.
export default function ConverterPanel() {
  const clocks = useUiStore((s) => s.clocks);
  const hour12 = useUiStore((s) => s.clockPrefs.hour12);
  const [text, setText] = useState('');
  const [fallback, setFallback] = useState('UTC');
  const [copied, setCopied] = useState(false);
  const work = useMemo(loadWorkHours, []);

  const zone = fallback === 'UTC' || clocks.includes(fallback) ? fallback : 'UTC';
  const result = useMemo(() => (text.trim() === '' ? null : parseTimeInput(text, new Date(), zone)), [text, zone]);
  const places = clocks.length ? clocks : [];
  const instant = result && result.ok ? result.instant : null;
  const notes = instant && places.length > 1 ? pairGapNotes(places, instant) : [];

  const lines = instant ? ['UTC ' + formatLine('UTC', instant, hour12).replace(/^UTC /, ''), ...places.map((z) => formatLine(z, instant, hour12))] : [];

  async function copy() {
    const body = lines.join('\n');
    try {
      await navigator.clipboard.writeText(body);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2500);
    } catch {
      window.prompt('Copy these times:', body);
    }
  }

  return (
    <div className={styles.panel}>
      <input
        className={styles.input}
        type="text"
        value={text}
        placeholder='e.g. "9am New York" or "14:00 UTC"'
        onChange={(e) => { setText(e.target.value); setCopied(false); }}
        aria-label="Time to convert"
        maxLength={80}
      />
      <div className={styles.row} style={{ marginTop: 8 }}>
        <label>
          If no place is typed, use
          <select className={styles.field} value={zone} onChange={(e) => setFallback(e.target.value)} aria-label="Place to use when none is typed">
            <option value="UTC">UTC</option>
            {clocks.map((z) => <option key={z} value={z}>{cityName(z)}</option>)}
          </select>
        </label>
      </div>

      {result && !result.ok && <div className={styles.error}>{result.error}</div>}
      {result && result.ok && (
        <div className={styles.summary}>
          <div className={styles.note} style={{ marginTop: 0 }}>{result.label}{result.ambiguous ? ' (this time happens twice when clocks go back; the first one is used)' : ''}</div>
          <div className={styles.summaryLine}><strong>UTC</strong><span>{formatLine('UTC', result.instant, hour12).replace(/^UTC /, '')}</span></div>
          {places.map((z) => {
            const category = hourCategory(localParts(z, result.instant).hour, work);
            return (
              <div key={z} className={styles.summaryLine}>
                <strong>{cityName(z)}</strong>
                <span>{formatLine(z, result.instant, hour12).replace(`${cityName(z)} `, '')} <em>({category === 'working' ? 'working hours' : category})</em></span>
              </div>
            );
          })}
          {notes.map((note) => <div key={note} className={styles.warn}>{note}</div>)}
          <button type="button" className={styles.copy} onClick={copy}>{copied ? 'Copied' : 'Copy as text'}</button>
        </div>
      )}
      {!result && (
        <div className={styles.note}>
          Understood forms: &ldquo;14:00 UTC&rdquo;, &ldquo;9am New York&rdquo;, &ldquo;2026-11-02 17:30 Tokyo&rdquo;, &ldquo;noon London&rdquo;,
          &ldquo;tomorrow 9am Tokyo&rdquo;, &ldquo;14:00 UTC+5:30&rdquo;. Abbreviations like CST or IST are refused because they
          mean different things in different places.{clocks.length === 0 ? ' Pin places on the Clocks tab to see the time in each.' : ''}
        </div>
      )}
    </div>
  );
}
