import { useId, useRef, useState } from 'react';
import type { HTMLAttributes, KeyboardEvent, ReactNode, Ref } from 'react';
import Button from './Button';
import Icon from './Icon';
import styles from './Display.module.css';

// ---- Chip -------------------------------------------------------------------------------------------------------

export function Chip({ pressed, onClick, count, children }: { pressed: boolean; onClick: () => void; count?: number; children: ReactNode }) {
  return (
    <button type="button" aria-pressed={pressed} className={`${styles.chip} ${pressed ? styles.chipOn : ''}`} onClick={onClick}>
      {children}
      {count !== undefined && <span className={styles.count}>{count}</span>}
    </button>
  );
}

// ---- Badge -------------------------------------------------------------------------------------------------------

export type BadgeTone = 'neutral' | 'accent' | 'warn' | 'sev1' | 'sev2' | 'sev3' | 'sev4' | 'sev5' | 'alertRed' | 'alertOrange' | 'alertGreen';

export function Badge({
  tone = 'neutral',
  compact = false,
  onClick,
  title,
  children,
}: {
  tone?: BadgeTone;
  compact?: boolean;
  // Makes the badge a button (for example a country tag that opens the country's analysis).
  onClick?: () => void;
  title?: string;
  children: ReactNode;
}) {
  const className = `${styles.badge} ${compact ? styles.badgeCompact : ''} ${tone === 'neutral' ? '' : styles[tone]}`;
  if (onClick) {
    return (
      <button type="button" className={`${className} ${styles.badgeButton}`} onClick={onClick} title={title}>
        {children}
      </button>
    );
  }
  return <span className={className}>{children}</span>;
}

// ---- Tabs ---------------------------------------------------------------------------------------------------------

// Arrow keys, Home and End move between tabs; only the selected tab is in the tab order.
export function Tabs<T extends string>({
  tabs,
  value,
  onChange,
  label,
}: {
  tabs: { id: T; label: string }[];
  value: T;
  onChange: (id: T) => void;
  label: string;
}) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});

  function onKey(event: KeyboardEvent, index: number) {
    const last = tabs.length - 1;
    const next = event.key === 'ArrowRight' ? (index === last ? 0 : index + 1)
      : event.key === 'ArrowLeft' ? (index === 0 ? last : index - 1)
      : event.key === 'Home' ? 0
      : event.key === 'End' ? last
      : null;
    if (next === null) return;
    event.preventDefault();
    onChange(tabs[next].id);
    refs.current[tabs[next].id]?.focus();
  }

  return (
    <div className={styles.tabs} role="tablist" aria-label={label}>
      {tabs.map((tab, i) => (
        <button
          key={tab.id}
          ref={(el) => {
            refs.current[tab.id] = el;
          }}
          type="button"
          role="tab"
          aria-selected={tab.id === value}
          tabIndex={tab.id === value ? 0 : -1}
          className={`${styles.tab} ${tab.id === value ? styles.tabOn : ''}`}
          onClick={() => onChange(tab.id)}
          onKeyDown={(e) => onKey(e, i)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}

// ---- Toolbar -------------------------------------------------------------------------------------------------------

export function Toolbar({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className={styles.toolbar} role="toolbar" aria-label={label}>
      {children}
    </div>
  );
}

// ---- Section -------------------------------------------------------------------------------------------------------

export function Section({
  title,
  collapsible = false,
  defaultOpen = true,
  actions,
  children,
}: {
  title: string;
  collapsible?: boolean;
  defaultOpen?: boolean;
  actions?: ReactNode;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const id = useId();
  const shown = !collapsible || open;
  return (
    <section className={styles.section}>
      <div className={`${styles.sectionHead} ${shown ? '' : styles.sectionClosed}`}>
        {collapsible ? (
          <button type="button" className={styles.sectionToggle} aria-expanded={open} aria-controls={id} onClick={() => setOpen(!open)}>
            <Icon name={open ? 'chevron-down' : 'chevron-right'} size={12} />
            <h3 className={styles.sectionTitle}>{title}</h3>
          </button>
        ) : (
          <h3 className={styles.sectionTitle}>{title}</h3>
        )}
        {actions}
      </div>
      {shown && <div id={id}>{children}</div>}
    </section>
  );
}

// ---- KeyValue ---------------------------------------------------------------------------------------------------------

export function KeyValue({ items }: { items: { label: string; value: ReactNode }[] }) {
  return (
    <dl className={styles.facts}>
      {items.map((item) => (
        <div key={item.label} style={{ display: 'contents' }}>
          <dt>{item.label}</dt>
          <dd>{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}

// ---- ListRow -------------------------------------------------------------------------------------------------------------

export function ListRow({
  title,
  detail,
  leading,
  trailing,
  selected = false,
  dense = false,
  onClick,
  ...rest
}: {
  title: string;
  detail?: ReactNode;
  leading?: ReactNode;
  trailing?: ReactNode;
  selected?: boolean;
  // A tighter row (two short lines) for long lists.
  dense?: boolean;
  onClick?: () => void;
} & Omit<HTMLAttributes<HTMLButtonElement>, 'title' | 'onClick'> & { 'data-index'?: number; ref?: Ref<HTMLButtonElement> }) {
  return (
    <button
      type="button"
      className={`${styles.row} ${dense ? styles.rowDense : ''} ${selected ? styles.rowSelected : ''}`}
      aria-current={selected || undefined}
      onClick={onClick}
      {...rest}
    >
      {leading}
      <span className={styles.rowMain}>
        <div className={styles.rowTitle} title={title}>{title}</div>
        {detail && <div className={styles.rowDetail}>{detail}</div>}
      </span>
      {trailing && <span className={styles.rowTrailing}>{trailing}</span>}
    </button>
  );
}

// ---- StateMessage ----------------------------------------------------------------------------------------------------------

export function StateMessage({
  kind,
  title,
  hint,
  actionLabel,
  onAction,
}: {
  kind: 'empty' | 'loading' | 'error';
  title: string;
  hint?: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <div className={`${styles.state} ${kind === 'error' ? styles.error : ''}`} role={kind === 'error' ? 'alert' : 'status'}>
      {kind === 'loading' && <span className={styles.spinner} aria-hidden="true" />}
      {kind === 'error' && <Icon name="warning" size={18} />}
      <div className={styles.stateTitle}>{title}</div>
      {hint && <div className={styles.stateHint}>{hint}</div>}
      {actionLabel && onAction && <Button size="sm" onClick={onAction}>{actionLabel}</Button>}
    </div>
  );
}
