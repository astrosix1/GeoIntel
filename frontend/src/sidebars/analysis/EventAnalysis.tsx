import { useEffect, useRef, useState } from 'react';
import type { CrisisDetail, CrisisSummary } from '../../api/types';
import {
  useCrisisBriefingQuery,
  useCrisisDetailQuery,
  useEntitlements,
  useEventHazardsQuery,
  useEventAnalysisQuery,
  useRefineLocationMutation,
  useStormsQuery,
} from '../../state/queries';
import { useUiStore } from '../../state/uiStore';
import Scenarios from './Scenarios';
import EventPattern from './EventPattern';
import Comments from './Comments';
import SaveButton from '../../components/SaveButton';
import { labelForSeverity, severityTone } from '../../globe/severity';
import { hazardIconName } from '../../globe/hazards';
import Icon from '../../ui/Icon';
import { Badge, Section, Tabs } from '../../ui/Display';
import { describeScope } from '../../lib/scopeWhy';
import { hasReportTime, reportedLocalTime } from '../../lib/eventTime';
import { zoneAt } from '../../lib/zoneLookup';
import { cityName } from '../../lib/timezones';
import { useZoneIndex } from '../../state/useZoneIndex';
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
  const { unlocked: premium } = useEntitlements();
  const { data: detail } = useCrisisDetailQuery(crisis.id);
  const { data: hazardLinks } = useEventHazardsQuery(crisis.id);
  const { data: patternData } = useEventAnalysisQuery(crisis.id);
  // When the first report appeared, as a clock time at the event's own pin (news-feed events only).
  const zoneIndex = useZoneIndex(hasReportTime(crisis.id));
  const reportZone = zoneIndex ? zoneAt(zoneIndex, crisis.lat, crisis.lon) : null;
  const reported = reportZone ? reportedLocalTime(crisis.date, reportZone, crisis.location_confidence) : null;
  const { data: stormData } = useStormsQuery(true);
  const setActiveMode = useUiStore((s) => s.setActiveMode);
  const selectHazard = useUiStore((s) => s.selectHazard);
  const refine = useRefineLocationMutation();
  const refineAsked = useRef(false);
  const [imageFailed, setImageFailed] = useState(false);
  const [tab, setTab] = useState<'analysis' | 'info' | 'comments'>('analysis');

  // Prefer the real image extracted from the crisis's own source article
  // (og:image) over the generic Wikipedia illustrative image — it's the
  // more specific, more relevant real photo when both are present.
  const scopeWhy = describeScope(crisis.scope, detail?.scope_basis);

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
        <Badge tone={severityTone(crisis.severity)}>
          {labelForSeverity(crisis.severity)} &middot; {crisis.severity}
        </Badge>
        {crisis.scope && <Badge>{crisis.scope === 'local' ? 'Local' : 'Global'}</Badge>}
        <Badge>{crisis.country}</Badge>
        <Badge>{crisis.type}</Badge>
        <Badge>{new Date(crisis.date).toLocaleDateString()}</Badge>
        <SaveButton crisisId={crisis.id} />
      </div>
      <div className={styles.tabs}>
        <Tabs
          label="Event panel"
          value={tab}
          onChange={setTab}
          tabs={[
            { id: 'analysis', label: 'Analysis' },
            { id: 'info', label: 'More Info' },
            { id: 'comments', label: 'Comments' },
          ]}
        />
      </div>

      {tab === 'comments' && <Comments crisisId={crisis.id} />}

      {tab === 'info' && (
        <>
          <Section title="Location">
            <div className={styles.briefingText}>{locationNote ?? 'No extra detail about this pin.'}</div>
          </Section>
          {reported && reportZone && (
            <Section title="First reported">
              <div className={styles.briefingText}>
                {reported.time} local time{reported.night ? ' (night there)' : ''}
                {reported.approximate ? ', approximate: the pin is only country or region level' : ''} &middot; {cityName(reportZone)} time. This is when
                the report appeared, not necessarily when it happened.
              </div>
            </Section>
          )}
      {detail?.severity_basis && (
        <Section title={`Why this rating (${detail.severity_basis.name})`}>
          <ul className={styles.sourceList}>
            {detail.severity_basis.basis.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </Section>
      )}

      {scopeWhy && (
        <Section title={`Why ${crisis.scope === 'local' ? 'Local' : 'Global'}`}>
          <div className={styles.briefingText}>{scopeWhy.summary}</div>
          {scopeWhy.terms.length > 0 && <div className={styles.mediaCaption}>Matched: {scopeWhy.terms.join(', ')}</div>}
        </Section>
      )}

      {detail && detail.news.length > 1 ? (
        <Section title={`Sources (${detail.source_count} outlet${detail.source_count === 1 ? '' : 's'})`}>
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
        </Section>
      ) : crisis.source_url && (
        <Section title="Source">
          <a
            className={styles.sourceLink}
            href={crisis.source_url}
            target="_blank"
            rel="noreferrer"
          >
            {crisis.source_url}
          </a>
        </Section>
      )}
        </>
      )}

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
        <Section title="Nearby hazard">
          <ul className={styles.sourceList}>
            {hazardLinks.links.map((link) => {
              const storm = stormData?.storms.find(
                (s) => s.event_type === link.hazard.event_type && s.id === link.hazard.id,
              );
              return (
                <li key={`${link.hazard.event_type}-${link.hazard.id}`}>
                  <span>
                    <Icon name={hazardIconName(link.hazard.event_type)} size={14} /> {link.hazard.name ?? link.hazard.hazard ?? 'Weather hazard'}
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
                      className={`${styles.sourceLink} ${styles.linkButton}`}
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
        </Section>
      )}

      <Section title="Analysis">
        {isLoading && <div className={styles.loading}>Loading analysis...</div>}
        {isError && <div className={styles.error}>Failed to load analysis.</div>}
        {briefing && <div className={styles.briefingText}>{briefing.briefing}</div>}
      </Section>

      {patternData && <EventPattern data={patternData} />}

      <Scenarios key={crisis.id} crisisId={crisis.id} />
        </>
      )}
    </div>
  );
}
