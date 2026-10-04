import { useState } from 'react';
import { UserDataError } from '../api/client';
import type { GeoResult, WatchPlace } from '../api/types';
import { ALERT_COLORS, hazardIcon } from '../globe/hazards';
import { useAddPlaceMutation, useDeletePlaceMutation, usePlaceSearch, useWatchQuery } from '../state/queries';
import { useUiStore } from '../state/uiStore';
import dashboard from './Dashboard.module.css';
import styles from './Watchlist.module.css';

const DEFAULT_RADIUS_KM = 200;

function describeError(error: unknown): string {
  const kind = error instanceof UserDataError ? error.kind : 'error';
  if (kind === 'exists') return 'You already have a place with that name. Pick another name.';
  if (kind === 'limit_reached') return "You've reached the limit of places. Remove one to add another.";
  if (kind === 'invalid') return 'Check the name and radius (10 to 2000 km) and try again.';
  if (kind === 'unavailable') return "Your watchlist isn't available right now.";
  if (kind === 'sign_in_required') return 'Sign in to use your watchlist.';
  if (kind === 'premium_required') return 'The watchlist is a premium feature.';
  return "Couldn't save that. Please try again.";
}

function coords(lat: number, lon: number): string {
  return `${Math.abs(lat).toFixed(2)}°${lat >= 0 ? 'N' : 'S'}, ${Math.abs(lon).toFixed(2)}°${lon >= 0 ? 'E' : 'W'}`;
}

function resultLabel(r: GeoResult): string {
  return [r.name, r.admin1, r.country].filter(Boolean).join(', ');
}

// Place being added: from a search result, or a point picked on the map.
interface Draft {
  name: string;
  lat: number;
  lon: number;
}

function AddPlaceForm() {
  const pending = useUiStore((s) => s.pendingWatchPoint);
  const setPending = useUiStore((s) => s.setPendingWatchPoint);
  const add = useAddPlaceMutation();

  const [draft, setDraft] = useState<Draft | null>(pending);
  const [radius, setRadius] = useState(DEFAULT_RADIUS_KM);
  const [searchText, setSearchText] = useState('');
  const [submitted, setSubmitted] = useState('');
  const search = usePlaceSearch(submitted);

  function choose(result: GeoResult) {
    setDraft({ name: result.name, lat: result.lat, lon: result.lon });
    setSubmitted('');
    setSearchText('');
    add.reset();
  }

  function clear() {
    setDraft(null);
    setPending(null);
    add.reset();
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!draft || !draft.name.trim()) return;
    add.mutate(
      { name: draft.name.trim(), lat: draft.lat, lon: draft.lon, radius_km: radius },
      { onSuccess: clear },
    );
  }

  return (
    <div className={styles.addBox}>
      <div className={dashboard.sectionTitle}>Add a place</div>

      {!draft && (
        <form
          className={styles.searchRow}
          onSubmit={(e) => {
            e.preventDefault();
            setSubmitted(searchText.trim());
          }}
        >
          <input
            type="search"
            className={dashboard.search}
            placeholder="Search a city, port or region"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            maxLength={80}
          />
          <button type="submit" className={dashboard.action} disabled={searchText.trim().length < 2}>
            Search
          </button>
        </form>
      )}
      {!draft && submitted && search.isLoading && <div className={dashboard.status}>Searching…</div>}
      {!draft && submitted && search.isError && (
        <div className={dashboard.status}>Place search isn&apos;t available right now.</div>
      )}
      {!draft && submitted && search.data && search.data.length === 0 && (
        <div className={dashboard.status}>No places found for &ldquo;{submitted}&rdquo;.</div>
      )}
      {!draft && search.data && search.data.length > 0 && (
        <ul className={dashboard.list}>
          {search.data.map((result) => (
            <li key={`${result.lat}:${result.lon}:${result.name}`}>
              <button type="button" className={styles.suggestion} onClick={() => choose(result)}>
                <span className={dashboard.rowTitle}>{resultLabel(result)}</span>
                <span className={dashboard.rowMeta}>{coords(result.lat, result.lon)}</span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {draft && (
        <form className={styles.form} onSubmit={submit}>
          <label className={styles.field}>
            <span>Name</span>
            <input
              className={dashboard.search}
              value={draft.name}
              maxLength={80}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            />
          </label>
          <div className={dashboard.rowMeta}>{coords(draft.lat, draft.lon)}</div>
          <label className={styles.field}>
            <span>Alert radius: {radius} km</span>
            <input
              type="range"
              min={10}
              max={2000}
              step={10}
              value={radius}
              onChange={(e) => setRadius(Number(e.target.value))}
            />
          </label>
          <div className={styles.buttons}>
            <button type="submit" className={dashboard.action} disabled={add.isPending || !draft.name.trim()}>
              {add.isPending ? 'Adding…' : 'Add to watchlist'}
            </button>
            <button type="button" className={dashboard.action} onClick={clear}>
              Cancel
            </button>
          </div>
        </form>
      )}
      {add.isError && <div className={dashboard.status}>{describeError(add.error)}</div>}
    </div>
  );
}

function PlaceRow({ place, hazardsAvailable }: { place: WatchPlace; hazardsAvailable: boolean }) {
  const remove = useDeletePlaceMutation();
  const [confirming, setConfirming] = useState(false);

  return (
    <li className={styles.place}>
      <div className={styles.placeHeader}>
        <span className={dashboard.rowMain}>
          <span className={dashboard.rowTitle}>{place.name}</span>
          <span className={dashboard.rowMeta}>
            {coords(place.lat, place.lon)} &middot; {place.radius_km} km radius
          </span>
        </span>
        {confirming ? (
          <span className={styles.confirm}>
            <button
              type="button"
              className={dashboard.action}
              disabled={remove.isPending}
              onClick={() => remove.mutate(place.id)}
            >
              Yes, remove
            </button>
            <button type="button" className={dashboard.action} onClick={() => setConfirming(false)}>
              Cancel
            </button>
          </span>
        ) : (
          <button
            type="button"
            className={dashboard.remove}
            aria-label={`Remove ${place.name}`}
            onClick={() => setConfirming(true)}
          >
            &times;
          </button>
        )}
      </div>
      {remove.isError && <div className={dashboard.status}>{describeError(remove.error)}</div>}
      <div className={styles.nearby}>
        {!hazardsAvailable ? (
          <span className={dashboard.rowMeta}>Live hazard data isn&apos;t available right now.</span>
        ) : place.nearby.length === 0 ? (
          <span className={dashboard.rowMeta}>No active hazards within {place.radius_km} km.</span>
        ) : (
          place.nearby.map((h) => (
            <span key={`${h.event_type}-${h.id}`} className={styles.hazard}>
              <span
                className={dashboard.dot}
                style={{ backgroundColor: ALERT_COLORS[h.alert_level ?? 'Unknown'] ?? ALERT_COLORS.Unknown }}
              />
              {hazardIcon(h.event_type ?? '')} {h.name ?? h.hazard ?? 'Hazard'} &middot; {h.distance_km} km
            </span>
          ))
        )}
      </div>
    </li>
  );
}

export default function WatchlistTab() {
  const { data, isLoading, error } = useWatchQuery();

  return (
    <div>
      <AddPlaceForm />
      {isLoading && <div className={dashboard.status}>Loading…</div>}
      {error && <div className={dashboard.status}>{describeError(error)}</div>}
      {data && (
        <>
          <div className={dashboard.summary}>
            {data.places.length} of {data.limit} places &middot; alerts when a hazard comes within a place&apos;s radius
          </div>
          {data.places.length === 0 ? (
            <div className={dashboard.status}>
              No places yet. Search for one above, or click the map in Weather mode and press{' '}
              <strong>Add to watchlist</strong>.
            </div>
          ) : (
            <ul className={dashboard.list}>
              {data.places.map((place) => (
                <PlaceRow key={place.id} place={place} hazardsAvailable={data.hazards_available} />
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
