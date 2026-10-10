import type { CascadeMethods } from '../api/types';
import styles from './Cascade.module.css';

// The methods page, in plain words: what Cascade shows and does not, the rule behind every colour, and where each piece of data comes
// from and how fresh it is. All rules and dates come from the server, so this page cannot drift from what the engine actually does.
export default function CascadeMethodsPanel({ methods }: { methods: CascadeMethods }) {
  return (
    <details className={styles.methods}>
      <summary>How Cascade works</summary>
      <h4>What it shows</h4>
      <p>
        Which countries are exposed when something happens, through which link, with the numbers and sources behind each one. It follows trade
        and energy dependence, where a country&apos;s emigrants already live, mutual-defence treaties and shipping routes. It shows structural
        exposure. It does not forecast, and it never gives a probability.
      </p>
      <h4>What the colours mean</h4>
      <p>
        High, Moderate and Low come from fixed thresholds on published figures, listed below. A country that does not reach a threshold is not
        listed. &quot;Why&quot; under each country shows the figures and their source.
      </p>
      <h4>The rules</h4>
      <ul>
        {Object.entries(methods.rules).map(([key, text]) => (
          <li key={key}>{text}</li>
        ))}
      </ul>
      <h4>What it does not cover</h4>
      <ul>
        {methods.not_modelled.map((n) => (
          <li key={n}>{n}</li>
        ))}
      </ul>
      <h4>Where the data comes from</h4>
      <ul>
        {methods.sources.map((s) => (
          <li key={s.name}>
            <strong>{s.name}</strong>: {s.used_for} <span className={styles.meta}>{s.fresh}</span>
          </li>
        ))}
      </ul>
    </details>
  );
}
