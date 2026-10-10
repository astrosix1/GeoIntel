import { useState } from 'react';
import { CascadeError, getUpgradeUrlSafe } from './cascadeHelpers';
import { isSignInConfigured, signIn } from '../auth/session';
import { useCascadeOptionsQuery, useEntitlements, useRunCascadeMutation } from '../state/queries';
import { useUiStore } from '../state/uiStore';
import Button from '../ui/Button';
import { Drawer } from '../ui/Overlay';
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
  const spec = options.data?.templates.find((t) => t.key === template);
  const needsCommodity = spec?.commodity === 'required' || spec?.commodity === 'optional';

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
                if (!country) return;
                run.mutate({ template, country, commodity: needsCommodity && commodity ? commodity : null });
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
              <Button type="submit" disabled={run.isPending || !country}>
                {run.isPending ? 'Running…' : 'Run cascade'}
              </Button>
              {run.error && <div className={styles.error}>{cascadeErrorText(run.error)}</div>}
            </form>
          )}
          {run.data && <CascadeResult result={run.data} onOpenCountry={() => setOpen(false)} onShowMap={() => setOpen(false)} />}
        </>
      )}
    </Drawer>
  );
}
