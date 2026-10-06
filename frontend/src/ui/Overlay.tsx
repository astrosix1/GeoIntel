import { useEffect, useId, useRef, useState } from 'react';
import type { KeyboardEvent, ReactNode } from 'react';
import Button, { IconButton } from './Button';
import type { IconName } from './Icon';
import styles from './Overlay.module.css';

// ---- Popover ------------------------------------------------------------------------------------------------------

// A button that opens a small panel (filters, layers, settings). Escape or a click outside closes it, and
// focus goes back to the button.
export function Popover({
  label,
  icon,
  align = 'start',
  children,
}: {
  label: string;
  icon?: IconName;
  align?: 'start' | 'end';
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLDivElement | null>(null);
  const trigger = useRef<HTMLButtonElement | null>(null);
  const id = useId();

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: PointerEvent) => {
      if (wrap.current && !wrap.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('pointerdown', onPointer);
    return () => document.removeEventListener('pointerdown', onPointer);
  }, [open]);

  function onKeyDown(event: KeyboardEvent) {
    if (event.key === 'Escape' && open) {
      event.stopPropagation();
      setOpen(false);
      trigger.current?.focus();
    }
  }

  return (
    <div className={styles.popoverWrap} ref={wrap} onKeyDown={onKeyDown}>
      <Button
        ref={trigger}
        icon={icon}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        onClick={() => setOpen(!open)}
      >
        {label}
      </Button>
      {open && (
        <div id={id} role="dialog" aria-label={label} className={`${styles.popover} ${align === 'end' ? styles.alignEnd : styles.alignStart}`}>
          {children}
        </div>
      )}
    </div>
  );
}

// ---- Drawer --------------------------------------------------------------------------------------------------------

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

// A panel that slides in from the right over a dimmed page (the dashboard, settings on phones). Focus moves into it,
// Tab stays inside it, Escape or the close button or a click on the dim area closes it, and focus returns.
export function Drawer({ open, title, onClose, children }: { open: boolean; title: string; onClose: () => void; children: ReactNode }) {
  const panel = useRef<HTMLDivElement | null>(null);
  const titleId = useId();

  useEffect(() => {
    if (!open) return;
    const before = document.activeElement as HTMLElement | null;
    panel.current?.querySelector<HTMLElement>(FOCUSABLE)?.focus();
    return () => before?.focus?.();
  }, [open]);

  if (!open) return null;

  function onKeyDown(event: KeyboardEvent) {
    if (event.key === 'Escape') {
      event.stopPropagation();
      onClose();
      return;
    }
    if (event.key !== 'Tab' || !panel.current) return;
    const items = Array.from(panel.current.querySelectorAll<HTMLElement>(FOCUSABLE));
    if (items.length === 0) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  return (
    <>
      <div className={styles.scrim} onClick={onClose} aria-hidden="true" />
      <div ref={panel} className={styles.drawer} role="dialog" aria-modal="true" aria-labelledby={titleId} onKeyDown={onKeyDown}>
        <div className={styles.drawerHead}>
          <h2 id={titleId} className={styles.drawerTitle}>{title}</h2>
          <IconButton icon="close" label="Close" onClick={onClose} />
        </div>
        <div className={styles.drawerBody}>{children}</div>
      </div>
    </>
  );
}
