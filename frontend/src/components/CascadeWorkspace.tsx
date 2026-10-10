import { useState } from 'react';
import { CascadeError, getUpgradeUrlSafe } from './cascadeHelpers';
import { isSignInConfigured, signIn } from '../auth/session';
import {
  useCascadeOptionsQuery,
  useDeleteScenarioMutation,
  useEntitlements,
  useNarrativeMutation,
  useOpenScenarioMutation,
  useRunCascadeMutation,
  useSaveScenarioMutation,
  useSavedScenariosQuery,
} from '../state/queries';
import { useUiStore } from '../state/uiStore';
import Button from '../ui/Button';
import { Drawer } from '../ui/Overlay';
import type { CascadeRequest, CascadeResult as Result, SavedScenario } from '../api/types';
import CascadeCompare from './CascadeCompare';
import CascadeResult from './CascadeResult';
import dashboard from './Dashboard.module.css';
import styles from './Cascade.module.css';

export const CASCADE_ABOUT =
  'Cascade shows which countries are exposed when something happens, such as an attack, sanctions or a key producer cut off, and through which trade or energy link, with the numbers and sources behind each one. It shows exposure, not a forecast.';

export function cascadeErrorText(error: unknown): string {
  const e = error instanceof CascadeError ? error : null;
  if (e?.kind === 'warming') return 'The cascade data is being prepared. Please try again in a minute.';
  if (e?.kind === 'invalid') return e.detail ?? 'That trigger is not valid.';
  if (e?.kind === 'premium_required') return 'Cascade is a premium feature.';
  if (e?.kind === 'sign_in_required') return 'Sign in to use Cascade.';
  return "Couldn't run that. Please try again.";
}

export function CascadeLocked() {
  const { signedIn, loading } = useEntitlements();
  const upgradeUrl = getUpgradeUrlSafe();
  if (loading) return <div className={dashboard.status}>Loading…</div>;
  return (
    <div className={dashboard.status}>
      <p>
        <strong>This feature is for premium subscribers only.</strong>
      </p>
      <p>{CASCADE_ABOUT}</p>
      {!signedIn && isSignInConfigured() ? (
        <Button size="sm" onClick={signIn}>
          Sign in
        </Button>
      ) : signedIn && upgradeUrl ? (
        <a href={upgradeUrl}>Upgrade to premium</a>
      ) : null}
    </div>
  );
}

// The Cascade workspace: pick what happens and where, and see who is exposed. Premium.
export default function CascadeWorkspace() {
  const { premium } = useEntitlements();
  const open = useUiStore((s) => s.cascadeOpen);
  const setOpen = useUiStore((s) => s.setCascadeOpen);
  const options = useCascadeOptionsQuery(open && premium);
  const run = useRunCascadeMutation();
  const [template, setTemplate] = useState('embargo');
  const [country, setCountry] = useState('');
  const [commodity, setCommodity] = useState('');
  const [chokepoint, setChokepoint] = useState('');
  const setShownResult = useUiStore((st) => st.setCascadeResult);
  const saved = useSavedScenariosQuery(open && premium);
  const save = useSaveScenarioMutation();
  const remove = useDeleteScenarioMutation();
  const openScenario = useOpenScenarioMutation();
  const narrative = useNarrativeMutation();
  const [lastRequest, setLastRequest] = useState<CascadeRequest | null>(null);
  const [opened, setOpened] = useState<SavedScenario | null>(null);
  const [name, setName] = useState('');
  const [picked, setPicked] = useState<string[]>([]);
  const [comparing, setComparing] = useState<[SavedScenario, SavedScenario] | null>(null);
  const shown: Result | null = opened?.result ?? run.data ?? null;
  const spec = options.data?.templates.find((t) => t.key === template);
  const needsCommodity = spec?.commodity === 'required' || spec?.commodity === 'optional';
  const isChokepoint = template === 'chokepoint';

  return (
    <Drawer open={open} title="Cascade" onClose={() => setOpen(false)}>
      {!premium ? (
        <CascadeLocked />
      ) : (
        <>
          {options.isLoading && <div className={dashboard.status}>Loading…</div>}
          {options.error && <div className={dashboard.status}>{cascadeErrorText(options.error)}</div>}
          {options.data && (
            <form
              className={styles.form}
              onSubmit={(e) => {
                e.preventDefault();
                if (isChokepoint ? !chokepoint : !country) return;
                const request: CascadeRequest = isChokepoint
                  ? { template, chokepoint, commodity: commodity || null }
                  : { template, country, commodity: needsCommodity && commodity ? commodity : null };
                setLastRequest(request);
                setOpened(null);
                narrative.reset();
                run.mutate(request);
              }}
            >
              <label className={styles.field}>
                <span>What happens</span>
                <select className={styles.select} value={template} onChange={(e) => setTemplate(e.target.value)}>
                  {options.data.templates.map((t) => (
                    <option key={t.key} value={t.key}>
                      {t.label}
                    </option>
                  ))}
                </select>
              </label>
              {spec && <p className={styles.assumes}>{spec.assumes}</p>}
              {isChokepoint ? (
                <label className={styles.field}>
                  <span>Which route</span>
                  <select className={styles.select} value={chokepoint} onChange={(e) => setChokepoint(e.target.value)} required>
                    <option value="">Choose a route</option>
                    {options.data.chokepoints.map((c) => (
                      <option key={c.key} value={c.key}>
                        {c.label}
                      </option>
                    ))}
                  </select>
                </label>
              ) : (
                <label className={styles.field}>
                  <span>Where</span>
                  <select className={styles.select} value={country} onChange={(e) => setCountry(e.target.value)} required>
                    <option value="">Choose a country</option>
                    {options.data.countries.map((c) => (
                      <option key={c.iso} value={c.iso}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              {isChokepoint && chokepoint && <p className={styles.assumes}>{options.data.chokepoints.find((c) => c.key === chokepoint)?.summary}</p>}
              {needsCommodity && (
                <label className={styles.field}>
                  <span>Commodity{spec?.commodity === 'optional' ? ' (optional)' : ''}</span>
                  <select className={styles.select} value={commodity} onChange={(e) => setCommodity(e.target.value)} required={spec?.commodity === 'required'}>
                    <option value="">{spec?.commodity === 'optional' ? 'Everything it trades' : 'Choose a commodity'}</option>
                    {options.data.commodities.map((c) => (
                      <option key={c.key} value={c.key}>
                        {c.label}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <Button type="submit" disabled={run.isPending || (isChokepoint ? !chokepoint : !country)}>
                {run.isPending ? 'Running…' : 'Run cascade'}
              </Button>
              {run.error && <div className={styles.error}>{cascadeErrorText(run.error)}</div>}
            </form>
          )}
          {comparing ? (
            <CascadeCompare a={comparing[0]} b={comparing[1]} onClose={() => setComparing(null)} />
          ) : (
            <>
              {shown && (
                <>
                  {opened && <p className={styles.assumes}>Saved scenario: <strong>{opened.name}</strong>, as it was when saved.</p>}
                  {!opened && lastRequest && (
                    <div className={styles.saveRow}>
                      <input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} placeholder="Name this scenario to save it" aria-label="Scenario name" />
                      <Button
                        size="sm"
                        disabled={save.isPending || !name.trim()}
                        onClick={() => save.mutate({ name: name.trim(), request: lastRequest }, { onSuccess: () => setName('') })}
                      >
                        {save.isPending ? 'Saving…' : 'Save'}
                      </Button>
                      <Button size="sm" disabled={narrative.isPending} onClick={() => narrative.mutate(lastRequest)}>
                        {narrative.isPending ? 'Writing…' : 'Write a summary'}
                      </Button>
                    </div>
                  )}
                  {save.isSuccess && !opened && <div className={styles.meta}>Saved.</div>}
                  {save.error && <div className={styles.error}>{cascadeErrorText(save.error)}</div>}
                  {narrative.data && (
                    <p className={styles.summary}>
                      {narrative.data.text}
                      <br />
                      <span className={styles.meta}>Written by an AI from the figures below only. The evidence under each country is the record.</span>
                    </p>
                  )}
                  {narrative.error && <div className={styles.error}>Summaries are not available right now.</div>}
                  <CascadeResult result={shown} onOpenCountry={() => setOpen(false)} onShowMap={() => setOpen(false)} />
                </>
              )}
              {saved.data && saved.data.scenarios.length > 0 && (
                <div className={styles.foot}>
                  <h4>Saved scenarios ({saved.data.scenarios.length} of {saved.data.limit})</h4>
                  <ul className={styles.savedList}>
                    {saved.data.scenarios.map((sc) => (
                      <li key={sc.id}>
                        <input
                          type="checkbox"
                          aria-label={`Compare ${sc.name}`}
                          checked={picked.includes(sc.id)}
                          onChange={(e) => setPicked((p) => (e.target.checked ? [...p, sc.id].slice(-2) : p.filter((id) => id !== sc.id)))}
                        />
                        <span className={styles.savedName}>{sc.name}</span>
                        <button
                          type="button"
                          className={styles.showAll}
                          onClick={() =>
                            openScenario.mutate(sc.id, {
                              onSuccess: (full) => {
                                setOpened(full);
                                setShownResult(full.result);
                                narrative.reset();
                              },
                            })
                          }
                        >
                          Open
                        </button>
                        <button type="button" className={styles.showAll} disabled={remove.isPending} onClick={() => remove.mutate(sc.id)}>
                          Delete
                        </button>
                      </li>
                    ))}
                  </ul>
                  {picked.length === 2 && (
                    <Button
                      size="sm"
                      onClick={async () => {
                        const [x, y] = await Promise.all(picked.map((id) => openScenario.mutateAsync(id)));
                        setComparing([x, y]);
                      }}
                    >
                      Compare the two ticked
                    </Button>
                  )}
                  {picked.length < 2 && saved.data.scenarios.length > 1 && <p className={styles.meta}>Tick two to compare them.</p>}
                </div>
              )}
              {saved.error && <div className={styles.error}>{cascadeErrorText(saved.error)}</div>}
            </>
          )}
        </>
      )}
    </Drawer>
  );
}
