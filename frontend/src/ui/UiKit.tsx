import { useState } from 'react';
import Button, { IconButton } from './Button';
import { Badge, Chip, KeyValue, ListRow, Section, StateMessage, Tabs, Toolbar } from './Display';
import type { BadgeTone } from './Display';
import Icon, { ICON_NAMES } from './Icon';
import { Drawer, Popover } from './Overlay';
import Segmented from './Segmented';
import { applyTheme, loadTheme, saveTheme } from './theme';
import type { ThemeChoice } from './theme';
import styles from './UiKit.module.css';

// The hidden component page (open the app with ?ui). Every shared component in every state, in either theme, so
// a change to a token or a component can be checked in one place. It is not linked from anywhere in the app.
const SEVERITY: { tone: BadgeTone; word: string; mark: string }[] = [
  { tone: 'sev1', word: 'Minor', mark: '--sev-1-mark' },
  { tone: 'sev2', word: 'Moderate', mark: '--sev-2-mark' },
  { tone: 'sev3', word: 'Serious', mark: '--sev-3-mark' },
  { tone: 'sev4', word: 'Severe', mark: '--sev-4-mark' },
  { tone: 'sev5', word: 'Critical', mark: '--sev-5-mark' },
];

const ALERTS: { tone: BadgeTone; word: string; mark: string }[] = [
  { tone: 'alertGreen', word: 'Green alert', mark: '--alert-green-mark' },
  { tone: 'alertOrange', word: 'Orange alert', mark: '--alert-orange-mark' },
  { tone: 'alertRed', word: 'Red alert', mark: '--alert-red-mark' },
];

const TOKENS = ['--bg-app', '--panel', '--raised', '--raised-strong', '--line-strong', '--edge-control', '--text', '--text-2', '--text-3', '--accent', '--sky', '--warn'];
const FONTS = ['--font-1', '--font-2', '--font-3', '--font-4', '--font-5', '--font-6'];

const SAMPLE_ROWS = Array.from({ length: 40 }, (_, i) => ({
  title: i % 5 === 0 ? 'A much longer headline that will not fit on one line and has to be cut off with an ellipsis' : `Event headline number ${i + 1}`,
  detail: i % 3 === 0 ? 'Second line of detail, muted' : undefined,
  severity: SEVERITY[i % 5],
  country: ['Nigeria', 'Ukraine', 'Japan', 'Brazil'][i % 4],
}));

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className={styles.card}>
      <h2 className={styles.cardTitle}>{title}</h2>
      {children}
    </div>
  );
}

export default function UiKit() {
  const [theme, setTheme] = useState<ThemeChoice>(loadTheme);
  const [scope, setScope] = useState<'global' | 'local'>('global');
  const [range, setRange] = useState<'24h' | '48h' | '7d'>('48h');
  const [tab, setTab] = useState<'analysis' | 'comments' | 'scenarios'>('analysis');
  const [chip, setChip] = useState(true);
  const [selected, setSelected] = useState(1);
  const [drawer, setDrawer] = useState(false);

  function chooseTheme(next: ThemeChoice) {
    setTheme(next);
    saveTheme(next);
    applyTheme(next);
  }

  return (
    <div className={styles.page}>
      <div className={styles.bar}>
        <span className={styles.barTitle}>GeoIntel component kit</span>
        <Segmented
          label="Theme"
          size="sm"
          value={theme}
          onChange={chooseTheme}
          options={[{ value: 'dark', label: 'Dark' }, { value: 'light', label: 'Light' }, { value: 'system', label: 'System' }]}
        />
      </div>
      <div className={styles.main}>
        <Card title="Buttons">
          <div className={styles.stack}>
            <div className={styles.wrap}>
              <Button>Default</Button>
              <Button variant="primary">Primary</Button>
              <Button variant="quiet">Quiet</Button>
              <Button disabled>Disabled</Button>
            </div>
            <div className={styles.wrap}>
              <Button size="sm">Small</Button>
              <Button size="sm" variant="primary" icon="plus">With icon</Button>
              <IconButton icon="settings" label="Settings" />
              <IconButton icon="close" label="Close" size="sm" />
              <IconButton icon="lock" label="Locked" variant="default" />
            </div>
            <div className={styles.wrap}>
              <input className={styles.input} placeholder="Text input" aria-label="Sample input" />
              <Chip pressed={chip} onClick={() => setChip(!chip)} count={12}>Filter chip</Chip>
              <Chip pressed={!chip} onClick={() => setChip(!chip)}>Other</Chip>
            </div>
          </div>
        </Card>

        <Card title="Segmented, tabs, toolbar">
          <div className={styles.stack}>
            <Toolbar label="Sample toolbar">
              <Segmented label="Scope" size="sm" value={scope} onChange={setScope} options={[{ value: 'global', label: 'Global' }, { value: 'local', label: 'Local' }]} />
              <Segmented label="Range" size="sm" value={range} onChange={setRange} options={[{ value: '24h', label: '24h' }, { value: '48h', label: '48h' }, { value: '7d', label: '7 days' }]} />
              <Popover label="Filters" icon="layers">
                <KeyValue items={[{ label: 'Category', value: 'All' }, { label: 'Night only', value: 'Off' }]} />
              </Popover>
            </Toolbar>
            <Segmented label="Full width" block value={scope} onChange={setScope} options={[{ value: 'global', label: 'Global' }, { value: 'local', label: 'Local' }]} />
            <Tabs label="Sample tabs" value={tab} onChange={setTab} tabs={[{ id: 'analysis', label: 'Analysis' }, { id: 'comments', label: 'Comments' }, { id: 'scenarios', label: 'Scenarios' }]} />
          </div>
        </Card>

        <Card title="Badges: severity and alerts carry their word">
          <div className={styles.stack}>
            <div className={styles.wrap}>
              {SEVERITY.map((s) => <Badge key={s.tone} tone={s.tone}>{s.word}</Badge>)}
            </div>
            <div className={styles.wrap}>
              {ALERTS.map((a) => <Badge key={a.tone} tone={a.tone}>{a.word}</Badge>)}
            </div>
            <div className={styles.wrap}>
              <Badge>Neutral</Badge>
              <Badge tone="accent">Selected</Badge>
              <Badge tone="warn">Not now</Badge>
            </div>
            <div className={styles.wrap}>
              {SEVERITY.concat(ALERTS).map((s) => (
                <span key={s.word}>
                  <span className={styles.mark} style={{ background: `var(${s.mark})` }} />
                  {s.word}
                </span>
              ))}
            </div>
          </div>
        </Card>

        <Card title="Sections and facts">
          <Section title="Summary">
            <p>A static section with a hairline above it and a small uppercase title.</p>
          </Section>
          <Section title="Why this rating" collapsible>
            <KeyValue items={[{ label: 'Type', value: 'Armed conflict' }, { label: 'Killed', value: '5, stated in the article' }, { label: 'Outlets', value: '4' }]} />
          </Section>
          <Section title="Sources" collapsible defaultOpen={false}>
            <p>Starts closed.</p>
          </Section>
        </Card>

        <Card title="Dense list (40 rows)">
          <div className={styles.list}>
            {SAMPLE_ROWS.map((row, i) => (
              <ListRow
                key={i}
                title={row.title}
                detail={row.detail}
                selected={selected === i}
                onClick={() => setSelected(i)}
                leading={<Badge tone={row.severity.tone}>{row.severity.word}</Badge>}
                trailing={<span>{row.country}</span>}
              />
            ))}
          </div>
        </Card>

        <Card title="States and overlays">
          <div className={styles.stack}>
            <StateMessage kind="loading" title="Loading events…" />
            <StateMessage kind="empty" title="No events match" hint="Try a wider time range." />
            <StateMessage kind="error" title="Couldn't load events" hint="The server did not answer." actionLabel="Try again" onAction={() => undefined} />
            <Button onClick={() => setDrawer(true)}>Open drawer</Button>
          </div>
        </Card>

        <Card title="Icons">
          <div className={styles.wrap}>
            {ICON_NAMES.map((name) => (
              <span key={name} title={name} style={{ display: 'inline-flex' }}>
                <Icon name={name} size={20} />
              </span>
            ))}
          </div>
        </Card>

        <Card title="Colour tokens">
          <div className={styles.swatches}>
            {TOKENS.map((token) => (
              <div key={token} className={styles.swatch}>
                <div className={styles.chipFill} style={{ background: `var(${token})` }} />
                {token}
              </div>
            ))}
          </div>
        </Card>

        <Card title="Type scale">
          <div className={styles.scale}>
            {FONTS.map((token) => (
              <div key={token} style={{ fontSize: `var(${token})` }}>
                {token.replace('--', '')} &middot; The quick brown fox 0123456789 21:45
              </div>
            ))}
          </div>
        </Card>
      </div>
      <Drawer open={drawer} title="Drawer" onClose={() => setDrawer(false)}>
        <Section title="Contents">
          <p>Focus moves in, Tab stays inside, Escape or the close button or the dimmed area closes it.</p>
          <div style={{ marginTop: 'var(--space-3)' }} className={styles.wrap}>
            <Button variant="primary">Primary</Button>
            <Button>Other</Button>
          </div>
        </Section>
      </Drawer>
    </div>
  );
}
