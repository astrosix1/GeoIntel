import { useState } from 'react';
import type { CascadeEffect, CascadeResult as Result } from '../api/types';
import { Badge } from '../ui/Display';
import type { BadgeTone } from '../ui/Display';
import { useUiStore } from '../state/uiStore';
import styles from './Cascade.module.css';

const TONES: Record<CascadeEffect['exposure'], BadgeTone> = { High: 'alertRed', Moderate: 'alertOrange', Low: 'neutral' };
const SHOWN = 25;
const HORIZON_ORDER = ['days to weeks', 'weeks', 'weeks to months', 'months'];

// The answer to "who is exposed": counts, a ranked list where each country opens its evidence, and what the method does not cover.
// Everything here comes from the server; the only words of ours are the labels.
export default function CascadeResult({ result, onOpenCountry, onShowMap }: { result: Result; onOpenCountry?: () => void; onShowMap?: () => void }) {
  const [all, setAll] = useState(false);
  const selectCountry = useUiStore((s) => s.selectCountry);
  const t = result.trigger;
  const shown = all ? result.effects : result.effects.slice(0, SHOWN);
  // How soon: the effects grouped by the horizon their mechanism gives (days, weeks, months), soonest first.
  const horizons = HORIZON_ORDER.map((h) => ({ h, n: result.effects.filter((e) => e.horizon === h).length })).filter((x) => x.n > 0);
  return (
    <div>
      <p className={styles.assumes}>
        <strong>
          {t.label}: {t.country_name}
          {t.commodity_label ? `, ${t.commodity_label.toLowerCase()}` : ''}
        </strong>
        <br />
        {result.assumes}
      </p>
      {result.started_from && <p className={styles.assumes}>{result.started_from}</p>}
      {result.notes.map((n) => (
        <p key={n} className={styles.assumes}>
          {n}
        </p>
      ))}
      <div className={styles.counts} aria-label="Exposure counts">
        <Badge tone="alertRed">{result.counts.High} High</Badge>
        <Badge tone="alertOrange">{result.counts.Moderate} Moderate</Badge>
        <Badge>{result.counts.Low} Low</Badge>
      </div>
      {horizons.length > 0 && (
        <p className={styles.assumes}>
          How soon: {horizons.map((x) => `${x.n} in ${x.h}`).join(', ')}. Each row shows its own horizon and the reason is its mechanism.
        </p>
      )}
      {onShowMap && result.effects.length > 0 && (
        <button type="button" className={styles.showAll} onClick={onShowMap}>
          Show on the map
        </button>
      )}
      {result.effects.length === 0 ? (
        <p className={styles.assumes}>No country reaches the thresholds for this trigger in the data we have.</p>
      ) : (
        <ul className={styles.list}>
          {shown.map((e) => (
            <li key={e.iso} className={styles.row}>
              <div className={styles.rowHead}>
                <Badge tone={TONES[e.exposure]}>{e.exposure}</Badge>
                <button
                  type="button"
                  className={styles.nameButton}
                  onClick={() => {
                    selectCountry(e.iso);
                    onOpenCountry?.();
                  }}
                  title={`Open the ${e.name} analysis`}
                >
                  {e.name}
                </button>
                <span className={styles.meta}>
                  {e.mechanisms.join(' and ').toLowerCase()} &middot; {e.horizon}
                </span>
              </div>
              <details className={styles.why}>
                <summary>Why</summary>
                <ul>
                  {e.evidence.map((ev, i) => (
                    <li key={i}>
                      {ev.text} <span className={styles.meta}>({ev.source}{ev.as_of ? `, ${ev.as_of}` : ''})</span>
                    </li>
                  ))}
                  {e.caveats.map((c, i) => (
                    <li key={`c${i}`} className={styles.caveat}>
                      {c}
                    </li>
                  ))}
                </ul>
              </details>
            </li>
          ))}
        </ul>
      )}
      {!all && result.effects.length > SHOWN && (
        <button type="button" className={styles.showAll} onClick={() => setAll(true)}>
          Show all {result.effects.length}
        </button>
      )}
      {result.would_change.length > 0 && (
        <div className={styles.foot}>
          <h4>What could soften it</h4>
          <ul>
            {result.would_change.map((w) => (
              <li key={w.text}>
                {w.text} <span className={styles.meta}>({w.source}{w.as_of ? `, ${w.as_of}` : ''})</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className={styles.foot}>
        <h4>How exposure is decided</h4>
        <ul>
          {Object.entries(result.method).map(([key, text]) => (
            <li key={key}>{text}</li>
          ))}
        </ul>
        <h4>Not modelled</h4>
        <ul>
          {result.not_modelled.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
        <p>
          Data: {result.data.source ?? 'CIA World Factbook'} and UN Comtrade, {result.data.countries_in_graph} countries
          {result.data.built_at ? `, prepared ${result.data.built_at.slice(0, 10)}` : ''}. This shows structural exposure, not a forecast.
        </p>
      </div>
    </div>
  );
}
