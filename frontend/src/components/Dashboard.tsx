import { useEffect, useMemo, useState } from 'react';
import { UserDataError } from '../api/client';
import type { SavedEvent } from '../api/types';
import { outletOf } from '../lib/outlet';
import { colorForSeverity } from '../globe/severity';
import { useUiStore } from '../state/uiStore';
import type { DashboardTab } from '../state/uiStore';
import {
  useCrisesQuery,
  useEntitlements,
  usePrefsQuery,
  useSaveEventMutation,
  useSavedEventsQuery,
  useUpdatePrefsMutation,
} from '../state/queries';
import styles from './Dashboard.module.css';

const TABS: { value: DashboardTab; label: string }[] = [
  { value: 'saved', label: 'Saved' },
  { value: 'sources', label: 'Sources' },
];

const MAX_OUTLET_RESULTS = 40;

function errorText(error: unknown): string {
  const kind = error instanceof UserDataError ? error.kind : 'error';
  if (kind === 'unavailable') return "Your dashboard isn't available right now.";
  if (kind === 'sign_in_required') return 'Sign in to use your dashboard.';
  if (kind === 'premium_required') return 'The dashboard is a premium feature.';
  return "Couldn't load this. Please try again.";
}

function SavedTab({ onOpen }: { onOpen: (event: SavedEvent) => void }) {
  const { data: saved, isLoading, error } = useSavedEventsQuery();
  const mutation = useSaveEventMutation();

  if (isLoading) return <div className={styles.status}>Loading…</div>;
  if (error) return <div className={styles.status}>{errorText(error)}</div>;
  if (!saved || saved.length === 0) {
    return (
      <div className={styles.status}>
        No saved events yet. Open an event in the Analysis panel and press <strong>Save</strong>.
      </div>
    );
  }

  return (
    <ul className={styles.list}>
      {saved.map((event) => (
        <li key={event.crisis_id} className={styles.row}>
          <button type="button" className={styles.rowMain} onClick={() => onOpen(event)}>
            <span className={styles.rowTitle}>{event.title}</span>
            <span className={styles.rowMeta}>
              <span className={styles.dot} style={{ backgroundColor: colorForSeverity(event.severity) }} />
              {event.country} &middot; saved {new Date(event.saved_at).toLocaleDateString()}
            </span>
          </button>
          <button
            type="button"
            className={styles.remove}
            aria-label={`Remove ${event.title} from saved`}
            disabled={mutation.isPending}
            onClick={() => mutation.mutate({ id: event.crisis_id, save: false })}
          >
            &times;
          </button>
        </li>
      ))}
    </ul>
  );
}

function SourcesTab() {
  const scope = useUiStore((s) => s.scope);
  const timeRange = useUiStore((s) => s.timeRange);
  // Unfiltered on purpose: this is where you find outlets to hide (and see
  // what the ones you've hidden are contributing).
  const { data: crises } = useCrisesQuery(scope, timeRange);
  const { data: prefs, isLoading, error } = usePrefsQuery();
  const update = useUpdatePrefsMutation();
  const [search, setSearch] = useState('');

  const hidden = useMemo(() => prefs?.hidden_outlets ?? [], [prefs]);
  const hiddenSet = useMemo(() => new Set(hidden), [hidden]);

  const counts = useMemo(() => {
    const map = new Map<string, number>();
    for (const crisis of crises ?? []) {
      const outlet = outletOf(crisis.source_url);
      if (outlet) map.set(outlet, (map.get(outlet) ?? 0) + 1);
    }
    return map;
  }, [crises]);

  const results = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return [...counts.entries()]
      .filter(([outlet]) => !needle || outlet.includes(needle))
      .sort((a, b) => b[1] - a[1])
      .slice(0, MAX_OUTLET_RESULTS);
  }, [counts, search]);

  const hiddenEventCount = hidden.reduce((sum, outlet) => sum + (counts.get(outlet) ?? 0), 0);

  if (isLoading) return <div className={styles.status}>Loading…</div>;
  if (error) return <div className={styles.status}>{errorText(error)}</div>;

  return (
    <div>
      <div className={styles.summary}>
        {hidden.length} outlet{hidden.length === 1 ? '' : 's'} hidden &middot; {hiddenEventCount} event
        {hiddenEventCount === 1 ? '' : 's'} currently hidden
      </div>
      {update.isError && <div className={styles.status}>{errorText(update.error)}</div>}

      {hidden.length > 0 && (
        <>
          <div className={styles.sectionTitle}>Hidden outlets</div>
          <ul className={styles.list}>
            {hidden.map((outlet) => (
              <li key={outlet} className={styles.row}>
                <span className={styles.rowMain}>
                  <span className={styles.rowTitle}>{outlet}</span>
                  <span className={styles.rowMeta}>{counts.get(outlet) ?? 0} events right now</span>
                </span>
                <button
                  type="button"
                  className={styles.action}
                  disabled={update.isPending}
                  onClick={() => update.mutate(hidden.filter((o) => o !== outlet))}
                >
                  Show again
                </button>
              </li>
            ))}
          </ul>
        </>
      )}

      <div className={styles.sectionTitle}>{search.trim() ? 'Matching outlets' : 'Most frequent outlets right now'}</div>
      <input
        type="search"
        className={styles.search}
        placeholder="Search outlets (e.g. dailymail.com)"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />
      {results.length === 0 ? (
        <div className={styles.status}>No outlets match.</div>
      ) : (
        <ul className={styles.list}>
          {results.map(([outlet, count]) => (
            <li key={outlet} className={styles.row}>
              <span className={styles.rowMain}>
                <span className={styles.rowTitle}>{outlet}</span>
                <span className={styles.rowMeta}>{count} events right now</span>
              </span>
              {hiddenSet.has(outlet) ? (
                <span className={styles.rowMeta}>Hidden</span>
              ) : (
                <button
                  type="button"
                  className={styles.action}
                  disabled={update.isPending}
                  onClick={() => update.mutate([...hidden, outlet])}
                >
                  Hide
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// "My dashboard" overlay, opened from the account chip (premium).
export default function Dashboard() {
  const { premium } = useEntitlements();
  const open = useUiStore((s) => s.dashboardOpen) && premium;
  const tab = useUiStore((s) => s.dashboardTab);
  const setOpen = useUiStore((s) => s.setDashboardOpen);
  const setTab = useUiStore((s) => s.setDashboardTab);
  const selectCrisis = useUiStore((s) => s.selectCrisis);
  const setRightOpen = useUiStore((s) => s.setRightOpen);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [open, setOpen]);

  if (!open) return null;

  // Open a saved event in Analysis from its stored snapshot.
  function openSaved(event: SavedEvent) {
    selectCrisis({
      id: event.crisis_id,
      title: event.title,
      country: event.country,
      type: event.type,
      severity: event.severity,
      date: event.event_date ?? event.saved_at,
      lat: event.lat,
      lon: event.lon,
      source_url: event.source_url ?? '',
    });
    setOpen(false);
    setRightOpen(true);
  }

  return (
    <div className={styles.backdrop} data-ui-hover-surface onClick={() => setOpen(false)}>
      <div
        className={styles.panel}
        role="dialog"
        aria-modal="true"
        aria-label="My dashboard"
        onClick={(e) => e.stopPropagation()}
      >
        <div className={styles.header}>
          <span className={styles.heading}>My dashboard</span>
          <button type="button" className={styles.close} aria-label="Close dashboard" onClick={() => setOpen(false)}>
            &times;
          </button>
        </div>
        <div className={styles.tabs}>
          {TABS.map((t) => (
            <button
              key={t.value}
              type="button"
              className={`${styles.tab} ${tab === t.value ? styles.tabActive : ''}`}
              onClick={() => setTab(t.value)}
            >
              {t.label}
            </button>
          ))}
        </div>
        <div className={styles.body}>{tab === 'saved' ? <SavedTab onOpen={openSaved} /> : <SourcesTab />}</div>
      </div>
    </div>
  );
}
