import { useEffect, useState } from 'react';
import type { CrisisSummary } from '../../api/types';
import { useCrisisBriefingQuery } from '../../state/queries';
import Scenarios from './Scenarios';
import Comments from './Comments';
import SaveButton from '../../components/SaveButton';
import { colorForSeverity, labelForSeverity } from '../../globe/severity';
import styles from './EventAnalysis.module.css';

export default function EventAnalysis({ crisis }: { crisis: CrisisSummary }) {
  const { data: briefing, isLoading, isError } = useCrisisBriefingQuery(crisis.id);
  const [imageFailed, setImageFailed] = useState(false);
  const [tab, setTab] = useState<'analysis' | 'comments'>('analysis');

  // Prefer the real image extracted from the crisis's own source article
  // (og:image) over the generic Wikipedia illustrative image — it's the
  // more specific, more relevant real photo when both are present.
  // GDELT's Goldstein-derived severity is known-unreliable for scope='local'
  // content (routine local crime/accident/human-interest stories that reliably
  // mis-score as severe, e.g. a "school fights student" story scoring 100) —
  // don't present that number at face value; mute it and caveat it instead.
  const isLocalScope = crisis.scope === 'local';

  const imageSrc = briefing?.source_media?.image_url || briefing?.image?.src;
  const imageCaption = briefing?.source_media?.image_url ? null : briefing?.image?.caption;
  const videoUrl = briefing?.source_media?.video_url;

  // A newly-selected crisis's image may fail differently than the last
  // one's — reset the "hide broken image" flag whenever the underlying URL
  // changes, rather than sticking on a real image just because a previous
  // one 404'd.
  useEffect(() => {
    setImageFailed(false);
  }, [imageSrc]);

  return (
    <div>
      <h2 className={styles.title}>{crisis.title}</h2>
      <div className={styles.metaRow}>
        {isLocalScope ? (
          <span className={`${styles.badge} ${styles.severityBadgeMuted}`} title="Local reports' severity scores are known-unreliable and not shown at face value.">
            Local report &middot; severity unreliable
          </span>
        ) : (
          <span
            className={`${styles.badge} ${styles.severityBadge}`}
            style={{ backgroundColor: colorForSeverity(crisis.severity) }}
          >
            {labelForSeverity(crisis.severity)} &middot; {crisis.severity}
          </span>
        )}
        <span className={styles.badge}>{crisis.country}</span>
        <span className={styles.badge}>{crisis.type}</span>
        <span className={styles.badge}>{new Date(crisis.date).toLocaleDateString()}</span>
        <SaveButton crisisId={crisis.id} />
      </div>

      <div className={styles.tabs} role="tablist">
        {(['analysis', 'comments'] as const).map((value) => (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={tab === value}
            className={`${styles.tab} ${tab === value ? styles.tabActive : ''}`}
            onClick={() => setTab(value)}
          >
            {value === 'analysis' ? 'Analysis' : 'Comments'}
          </button>
        ))}
      </div>

      {tab === 'comments' && <Comments crisisId={crisis.id} />}

      {tab === 'analysis' && (
        <>
      {imageSrc && !imageFailed && (
        <div className={styles.section}>
          <img
            className={styles.media}
            src={imageSrc}
            alt={crisis.title}
            onError={() => setImageFailed(true)}
          />
          {imageCaption && <div className={styles.mediaCaption}>{imageCaption}</div>}
        </div>
      )}

      {videoUrl && (
        <div className={styles.section}>
          {/* A plain link-out rather than an inline <video>/<iframe> embed —
              og:video URLs point at arbitrary third-party source articles,
              so an inline embed would frequently hit cross-origin/CORS or
              X-Frame-Options failures with no reliable way to detect that
              in advance. A link is lower-risk and always works. */}
          <a className={styles.videoLink} href={videoUrl} target="_blank" rel="noreferrer">
            Watch source video ↗
          </a>
        </div>
      )}

      {crisis.source_url && (
        <div className={styles.section}>
          <div className={styles.sectionTitle}>Source</div>
          <a
            className={styles.sourceLink}
            href={crisis.source_url}
            target="_blank"
            rel="noreferrer"
          >
            {crisis.source_url}
          </a>
        </div>
      )}

      <div className={styles.section}>
        <div className={styles.sectionTitle}>Analysis</div>
        {isLoading && <div className={styles.loading}>Loading analysis...</div>}
        {isError && <div className={styles.error}>Failed to load analysis.</div>}
        {briefing && <div className={styles.briefingText}>{briefing.briefing}</div>}
      </div>

      <Scenarios key={crisis.id} crisisId={crisis.id} />
        </>
      )}
    </div>
  );
}
