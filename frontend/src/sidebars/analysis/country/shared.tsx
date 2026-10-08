import type { AgeBand, ShareItem, Shares } from '../../../api/types';
import countryStyles from '../CountryAnalysis.module.css';
import { number } from './format';
import styles from '../CountryDetail.module.css';


export function Unavailable({ children }: { children: string }) {
  return <div className={countryStyles.unavailable}>{children}</div>;
}

// One label and value in the facts grid; nothing at all when the source gave no value.

export function Fact({ label, children }: { label: string; children: string | null | undefined }) {
  if (!children) return null;
  return (
    <>
      <span className={countryStyles.factLabel}>{label}</span>
      <span className={countryStyles.factValue}>{children}</span>
    </>
  );
}

export function ShareRow({ item, child = false }: { item: ShareItem; child?: boolean }) {
  const percent = `${item.under ? '<' : ''}${item.percent}%`;
  return (
    <div className={`${styles.share} ${child ? styles.child : ''}`}>
      <div className={styles.shareHead}>
        <span>{item.name}</span>
        <span className={styles.shareValue}>
          {percent}
          {item.estimated_count != null && ` · ≈${number(item.estimated_count)}`}
        </span>
      </div>
      <div className={`${styles.bar} ${child ? styles.childBar : ''}`} aria-hidden="true">
        <div className={styles.fill} style={{ width: `${Math.min(item.percent, 100)}%` }} />
      </div>
      {item.children?.map((sub) => <ShareRow key={sub.name} item={sub} child />)}
    </div>
  );
}

export function ShareList({ title, shares }: { title: string; shares: Shares | null | undefined }) {
  return (
    <div className={styles.group}>
      <div className={styles.groupTitle}>{title}</div>
      {shares ? (
        <>
          {shares.items.map((item) => <ShareRow key={item.name} item={item} />)}
          <div className={styles.asOf}>
            {shares.as_of ? `Estimate for ${shares.as_of}. ` : ''}{shares.items.some((item) => item.estimated_count != null) && 'Head counts (≈) are the percentage applied to the population.'}
          </div>
          {shares.note && <div className={styles.asOf}>{shares.note}</div>}
        </>
      ) : (
        <Unavailable>{`No ${title.toLowerCase()} breakdown is published for this country.`}</Unavailable>
      )}
    </div>
  );
}

export function Ages({ bands }: { bands: AgeBand[] | null | undefined }) {
  return (
    <div className={styles.group}>
      <div className={styles.groupTitle}>Age groups</div>
      {bands ? (
        <>
          {bands.map((band) => (
            <ShareRow
              key={band.band}
              item={{ name: band.band, percent: band.percent, under: false, estimated_count: band.count ?? undefined }}
            />
          ))}
          <div className={styles.asOf}>Counts are the Factbook&apos;s own.</div>
        </>
      ) : (
        <Unavailable>Age structure is unavailable for this country.</Unavailable>
      )}
    </div>
  );
}

