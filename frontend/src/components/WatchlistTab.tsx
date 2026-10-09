import { useState } from 'react';
import { UserDataError } from '../api/client';
import type { ConditionKey, GeoResult, PlaceAlertPrefs, WatchPlace } from '../api/types';
import { alertTone, HAZARD_TYPES, hazardIconName } from '../globe/hazards';
import Icon from '../ui/Icon';
import { Badge } from '../ui/Display';
import { useAddPlaceMutation, useAlertSettingsQuery, useDeletePlaceMutation, usePlaceSearch, useSavePlaceAlertPrefsMutation, useWatchQuery } from '../state/queries';
import { useUiStore } from '../state/uiStore';
import { CONDITIONS } from './conditions';
import dashboard from './Dashboard.module.css';
import styles from './Watchlist.module.css';

const DEFAULT_RADIUS_KM = 200;

function describeError(error: unknown): string {
  const kind = error instanceof UserDataError ? error.kind : 'error';
  if (kind === 'exists') return 'You already have a place with that name. Pick another name.';
  if (kind === 'limit_reached') return "You've reached the limit of places. Remove one to add another.";
  if (kind === 'invalid') return 'Check the name and radius (10 to 2000 km) and try again.';
  if (kind === 'unavailable') {
    const setup = error instanceof UserDataError && (error.reason === 'table_missing' || error.reason === 'column_missing');
    return setup ? "The watchlist hasn't been set up on the server yet. Please try again later." : "Your watchlist isn't available right now.";
  }
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
          <li className={dashboard.status}>
            Place search: &copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a> contributors.
          </li>
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

const LEVEL_CHOICES = [
  { value: 'green', label: 'Green and above (all)' },
  { value: 'orange', label: 'Orange and Red' },
  { value: 'red', label: 'Red only' },
] as const;

// Which alerts this place raises. A new place starts with the choices of the one added before it; "Use for all my places"
// saves these choices for every place at once.
function PlaceAlertChoices({ place }: { place: WatchPlace }) {
  const save = useSavePlaceAlertPrefsMutation();
  const stored = place.alert_prefs?.hazards ?? {};
  const [types, setTypes] = useState<string[]>(stored.types ?? HAZARD_TYPES.map((t) => t.code));
  const [level, setLevel] = useState<string>(stored.min_level ?? '');
  const [all, setAll] = useState(false);
  const sit = place.alert_prefs?.situations ?? {};
  const [sitOn, setSitOn] = useState(sit.enabled === true);
  const [sitLevel, setSitLevel] = useState<string>(sit.min_severity ?? 'serious');
  const [sitStatements, setSitStatements] = useState(sit.statements === true);
  const [clockOn, setClockOn] = useState(place.alert_prefs?.clock?.enabled === true);
  // Forecast limits: this place's own, or (when off) the ones on the Alerts tab.
  const settings = useAlertSettingsQuery().data;
  const [ownWeather, setOwnWeather] = useState(place.alert_prefs?.weather !== undefined);
  const [limits, setLimits] = useState<Partial<Record<ConditionKey, string>>>(
    Object.fromEntries(Object.entries(place.alert_prefs?.weather ?? {}).map(([k, v]) => [k, String(v)])),
  );
  const offered = CONDITIONS.filter((c) => !settings?.unavailable_conditions?.includes(c.key));

  function toggle(code: string) {
    setTypes((current) => (current.includes(code) ? current.filter((c) => c !== code) : [...current, code]));
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const prefs: PlaceAlertPrefs = { hazards: { types, ...(level ? { min_level: level as 'green' | 'orange' | 'red' } : {}) } };
    prefs.clock = { enabled: clockOn };
    prefs.situations = { enabled: sitOn, min_severity: sitLevel as 'serious' | 'severe' | 'critical', statements: sitStatements };
    if (ownWeather) {
      const weather: Partial<Record<ConditionKey, number>> = {};
      for (const spec of offered) {
        const raw = limits[spec.key];
        if (raw === undefined || raw.trim() === '') continue;
        const n = Number(raw);
        if (Number.isFinite(n)) weather[spec.key] = Math.min(spec.max, Math.max(spec.min, n));
      }
      prefs.weather = weather;
    }
    save.mutate({ id: place.id, prefs, applyToAll: all });
  }

  return (
    <form className={styles.choices} onSubmit={submit}>
      <fieldset className={styles.choiceGroup}>
        <legend className={dashboard.rowMeta}>Alert me about</legend>
        {HAZARD_TYPES.map((t) => (
          <label key={t.code} className={styles.choice}>
            <input type="checkbox" checked={types.includes(t.code)} onChange={() => toggle(t.code)} />
            <Icon name={hazardIconName(t.code)} size={14} /> {t.label}
          </label>
        ))}
      </fieldset>
      <label className={styles.field}>
        <span>Minimum level</span>
        <select className={dashboard.search} value={level} onChange={(e) => setLevel(e.target.value)}>
          <option value="">Default (Orange and Red)</option>
          {LEVEL_CHOICES.map((l) => (
            <option key={l.value} value={l.value}>
              {l.label}
            </option>
          ))}
        </select>
      </label>
      <label className={styles.choice}>
        <input type="checkbox" checked={sitOn} onChange={(e) => setSitOn(e.target.checked)} /> Tell me when a situation or serious event starts inside the radius
      </label>
      {sitOn && (
        <div className={styles.indent}>
          <label className={styles.field}>
            <span>Minimum severity</span>
            <select className={dashboard.search} value={sitLevel} onChange={(e) => setSitLevel(e.target.value)}>
              <option value="serious">Serious and above</option>
              <option value="severe">Severe and above</option>
              <option value="critical">Critical only</option>
            </select>
          </label>
          <label className={styles.choice}>
            <input type="checkbox" checked={sitStatements} onChange={(e) => setSitStatements(e.target.checked)} /> Include statements and talks
          </label>
          <div className={dashboard.rowMeta}>One alert covers a whole situation, however many stories it has.</div>
        </div>
      )}
      <label className={styles.choice}>
        <input type="checkbox" checked={clockOn} onChange={(e) => setClockOn(e.target.checked)} /> Tell me when the clocks change here (up to a week ahead)
      </label>
      <label className={styles.choice}>
        <input type="checkbox" checked={ownWeather} onChange={(e) => setOwnWeather(e.target.checked)} /> Set weather limits for this place
      </label>
      {!ownWeather && (
        <div className={dashboard.rowMeta}>
          {Object.keys(settings?.alert_conditions ?? {}).length > 0
            ? 'This place uses the account-wide forecast limits you set earlier. Set limits here to replace them.'
            : 'No weather limits for this place.'}
        </div>
      )}
      {ownWeather &&
        offered.map((spec) => (
          <label key={spec.key} className={styles.field}>
            <span>
              {spec.label} ({spec.min} to {spec.max}
              {spec.unit ? ` ${spec.unit}` : ''}), blank for off
            </span>
            <input
              type="number"
              className={dashboard.search}
              min={spec.min}
              max={spec.max}
              placeholder={`for example ${spec.fallback}`}
              value={limits[spec.key] ?? ''}
              onChange={(e) => setLimits({ ...limits, [spec.key]: e.target.value })}
            />
          </label>
        ))}
      <label className={styles.choice}>
        <input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} /> Use these choices for all my places
      </label>
      <div className={styles.buttons}>
        <button type="submit" className={dashboard.action} disabled={save.isPending}>
          {save.isPending ? 'Saving…' : 'Save'}
        </button>
        {save.isSuccess && <span className={dashboard.rowMeta}>Saved</span>}
      </div>
      {save.isError && <div className={dashboard.status}>{describeError(save.error)}</div>}
    </form>
  );
}

function PlaceRow({ place, hazardsAvailable }: { place: WatchPlace; hazardsAvailable: boolean }) {
  const remove = useDeletePlaceMutation();
  const [confirming, setConfirming] = useState(false);
  const [editing, setEditing] = useState(false);

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
      <button type="button" className={dashboard.action} aria-expanded={editing} onClick={() => setEditing(!editing)}>
        {editing ? 'Hide alert choices' : 'Choose alerts'}
      </button>
      {editing && <PlaceAlertChoices place={place} />}
      <div className={styles.nearby}>
        {!hazardsAvailable ? (
          <span className={dashboard.rowMeta}>Live hazard data isn&apos;t available right now.</span>
        ) : place.nearby.length === 0 ? (
          <span className={dashboard.rowMeta}>No active hazards within {place.radius_km} km.</span>
        ) : (
          place.nearby.map((h) => (
            <span key={`${h.event_type}-${h.id}`} className={styles.hazard}>
              <Badge compact tone={alertTone(h.alert_level)}>{h.alert_level ?? 'Unknown'}</Badge>
              <Icon name={hazardIconName(h.event_type ?? '')} size={14} /> {h.name ?? h.hazard ?? 'Hazard'} &middot; {h.distance_km} km
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
