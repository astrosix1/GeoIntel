import type { ReactNode } from 'react';
import { LIGHT_THEME_READY, useSettings } from '../state/settings';
import { useUiStore } from '../state/uiStore';
import { Popover } from '../ui/Overlay';
import Segmented from '../ui/Segmented';
import styles from './Menus.module.css';

function Setting({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className={styles.setting}>
      <span className={styles.settingLabel}>{label}</span>
      {children}
    </div>
  );
}

// One home for the choices that used to be scattered (units on the forecast, clock format on the clocks list, and so
// on). Every choice is remembered in this browser and takes effect straight away.
export default function SettingsMenu() {
  const s = useSettings();
  const clock = useUiStore((u) => u.clockPrefs);
  const setClock = useUiStore((u) => u.setClockPrefs);
  const lightHint = 'Light theme arrives when every screen has been converted to the new design. Preview it at ?ui.';

  return (
    <Popover label="Settings" icon="settings" align="end">
      <div className={styles.menu}>
        <Setting label="Panels">
          <Segmented
            label="Panels"
            size="sm"
            value={s.panels}
            onChange={s.setPanels}
            options={[{ value: 'docked', label: 'Docked' }, { value: 'overlay', label: 'Overlay on hover' }]}
          />
        </Setting>
        <Setting label="Theme">
          <Segmented
            label="Theme"
            size="sm"
            value={LIGHT_THEME_READY ? s.theme : 'dark'}
            onChange={s.setTheme}
            options={[
              { value: 'dark', label: 'Dark' },
              { value: 'light', label: 'Light', disabled: !LIGHT_THEME_READY, hint: lightHint },
              { value: 'system', label: 'System', disabled: !LIGHT_THEME_READY, hint: lightHint },
            ]}
          />
        </Setting>
        {!LIGHT_THEME_READY && <p className={styles.hint}>Light theme is built and shown in the component kit; it switches on here once every screen is converted.</p>}
        <Setting label="Map">
          <Segmented
            label="Map"
            size="sm"
            value={s.mapView}
            onChange={s.setMapView}
            options={[{ value: 'globe', label: 'Globe' }, { value: 'flat', label: 'Flat' }]}
          />
        </Setting>
        <Setting label="Starfield">
          <Segmented
            label="Starfield"
            size="sm"
            value={s.starfield ? 'on' : 'off'}
            onChange={(v) => s.setStarfield(v === 'on')}
            options={[{ value: 'on', label: 'On' }, { value: 'off', label: 'Off' }]}
          />
        </Setting>
        <div className={styles.divider} />
        <Setting label="Units">
          <Segmented
            label="Units"
            size="sm"
            value={s.units}
            onChange={s.setUnits}
            options={[{ value: 'metric', label: '°C · km/h' }, { value: 'imperial', label: '°F · mph' }]}
          />
        </Setting>
        <Setting label="Forecast times">
          <Segmented
            label="Forecast times"
            size="sm"
            value={s.timeZone}
            onChange={s.setTimeZone}
            options={[{ value: 'local', label: 'Place local' }, { value: 'utc', label: 'UTC' }]}
          />
        </Setting>
        <Setting label="Clock">
          <Segmented
            label="Clock"
            size="sm"
            value={clock.hour12 ? '12' : '24'}
            onChange={(v) => setClock({ ...clock, hour12: v === '12' })}
            options={[{ value: '24', label: '24 hour' }, { value: '12', label: '12 hour' }]}
          />
        </Setting>
        <Setting label="Date">
          <Segmented
            label="Date"
            size="sm"
            value={clock.dateFormat}
            onChange={(v) => setClock({ ...clock, dateFormat: v })}
            options={[{ value: 'long', label: 'Wed, Oct 7' }, { value: 'iso', label: '2026-10-07' }]}
          />
        </Setting>
      </div>
    </Popover>
  );
}
