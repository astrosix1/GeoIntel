import styles from './Logo.module.css';

// Fixed top-left wordmark (step 9 of the rewrite plan). Deliberately simple —
// this is an internal tool's rewrite, not a branded product, so a text
// wordmark plus a globe glyph is enough. "GeoIntel" is the app's existing
// real name, taken from the old index.html's <title>
// ("GeoIntel — Geopolitical Intelligence Platform"). Positioned top-left so
// it never collides with ModeSwitcher (top-center) or either sidebar.
export default function Logo() {
  return (
    <div className={styles.logo} data-ui-hover-surface>
      <span className={styles.glyph} aria-hidden="true">
        🌐
      </span>
      <span className={styles.wordmark}>GeoIntel</span>
    </div>
  );
}
