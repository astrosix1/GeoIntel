import { useEffect, useRef, useState } from 'react';
import type { CrisisDetail, CrisisSummary } from '../../api/types';
import {
  useCrisisBriefingQuery,
  useCrisisDetailQuery,
  useEntitlements,
  useEventHazardsQuery,
  useRefineLocationMutation,
  useStormsQuery,
} from '../../state/queries';
import { useUiStore } from '../../state/uiStore';
import Scenarios from './Scenarios';
import Comments from './Comments';
import SaveButton from '../../components/SaveButton';
import { colorForSeverity, labelForSeverity } from '../../globe/severity';
import { hazardIcon } from '../../globe/hazards';
import styles from './EventAnalysis.module.css';

// How the pin's position was found, in words. Only GDELT events carry the
// feed's coarse positions; other sources have their own and get no note.
function describeLocation(detail: CrisisDetail): string | null {
  if (detail.event_kind === 'statement') {
    return 'Statement or talks: the pin shows where the story is set, not where it happened';
  }
  if (detail.location_refined_name) return `Location: from the article, ${detail.location_refined_name}`;
  if (detail.source !== 'GDELT') return null;
  const level = detail.location_confidence >= 85 ? 'city' : detail.location_confidence >= 70 ? 'region' : 'country';
  return `Location: approximate (${level} level)`;
}

export default function EventAnalysis({ crisis }: { crisis: CrisisSummary }) {
  const { data: briefing, isLoading, isError } = useCrisisBriefingQuery(crisis.id);
  const { premium } = useEntitlements();
  const { data: detail } = useCrisisDetailQuery(crisis.id);
  const { data: hazardLinks } = useEventHazardsQuery(crisis.id);
  const { data: stormData } = useStormsQuery(true);
  const setActiveMode = useUiStore((s) => s.setActiveMode);
  const selectHazard = useUiStore((s) => s.selectHazard);
  const refine = useRefineLocationMutation();
  const refineAsked = useRef(false);
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

  // A premium user opening a GDELT event whose pin hasn't been refined yet
  // asks the server to refine it (once per opening; the server remembers the
  // answer, so everyone then sees the better pin). When it moves, re-select
  // the event at its new spot so the globe recentres, but only if the user
  // is still looking at this event.
  useEffect(() => {
    if (!premium || !detail || refineAsked.current) return;
    if (detail.source !== 'GDELT' || detail.location_refined_at || detail.event_kind === 'statement') return;
    refineAsked.current = true;
    refine.mutate(crisis.id, {
      onSuccess: (result) => {
        const ui = useUiStore.getState();
        if (result.status === 'refined' && ui.pinnedSelection?.kind === 'event' && ui.pinnedSelection.crisis.id === crisis.id) {
          ui.selectCrisis({ ...crisis, lat: result.location.lat, lon: result.location.lon });
        }
      },
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [premium, detail, crisis.id]);

  const locationNote = refine.isPending ? 'Refining location from the article\u2026' : detail ? describeLocation(detail) : null;

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
      {locationNote && <div className={styles.locationNote}>{locationNote}</div>}

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

      {hazardLinks && hazardLinks.links.length > 0 && (
        <div className={styles.section}>
          <div className={styles.sectionTitle}>Nearby hazard</div>
          <ul className={styles.sourceList}>
            {hazardLinks.links.map((link) => {
              const storm = stormData?.storms.find(
                (s) => s.event_type === link.hazard.event_type && s.id === link.hazard.id,
              );
              return (
                <li key={`${link.hazard.event_type}-${link.hazard.id}`}>
                  <span>
                    {hazardIcon(link.hazard.event_type)} {link.hazard.name ?? link.hazard.hazard ?? 'Weather hazard'}
                    {link.hazard.alert_level ? ` (${link.hazard.alert_level} alert)` : ''}
                  </span>
                  <span className={styles.sourceOutlet}>
                    {link.approximate ? 'Approximate: ' : ''}
                    {link.basis}
                    {link.hours_after_hazard_ended > 0 ? `; ${link.hours_after_hazard_ended} h after it ended` : '; while it was active'}
                  </span>
                  {storm && (
                    <button
                      type="button"
                      className={styles.sourceLink}
                      style={{ background: 'none', border: 0, padding: 0, cursor: 'pointer', textAlign: 'left' }}
                      onClick={() => {
                        setActiveMode('weather');
                        selectHazard(storm);
                      }}
                    >
                      Open in Weather mode
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
          <div className={styles.mediaCaption}>Shown because the two are in the same place at the same time. It does not mean one caused the other.</div>
        </div>
      )}

      {detail?.severity_basis && !isLocalScope && (
        <div className={styles.section}>
          <div className={styles.sectionTitle}>Why this rating ({detail.severity_basis.name})</div>
          <ul className={styles.sourceList}>
            {detail.severity_basis.basis.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </div>
      )}

      {detail && detail.news.length > 1 ? (
        <div className={styles.section}>
          <div className={styles.sectionTitle}>
            Sources ({detail.source_count} outlet{detail.source_count === 1 ? '' : 's'})
          </div>
          <ul className={styles.sourceList}>
            {detail.news.map((item) => (
              <li key={item.url}>
                <a className={styles.sourceLink} href={item.url} target="_blank" rel="noopener noreferrer">
                  {item.title || item.url}
                </a>
                <span className={styles.sourceOutlet}>{item.source}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : crisis.source_url && (
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
