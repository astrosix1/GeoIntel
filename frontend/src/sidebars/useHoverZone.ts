import { useEffect } from 'react';
import { useUiStore } from '../state/uiStore';

/**
 * Phase 10.2/10.3 rework: replaces the old invisible-10%-of-screen hover
 * zones and the "pinned selection keeps Analysis open" sticky mechanic with
 * pure hover-driven visibility, sourced from two places per side:
 *  - the visible EdgeTab.tsx handle fixed to that edge (hover or click)
 *  - the sidebar's own rendered content, once it's open (the pre-existing
 *    "panel-hover fusion" pattern — keeps a panel open while the cursor
 *    moves from its tab onto its content)
 *
 * Visibility is entirely separate from `pinnedSelection` now: clicking a
 * pin/country only ever updates what Analysis *would* show, never whether
 * it's currently shown.
 *
 * The one rule that overrides everything else: hovering the globe/map
 * canvas force-closes both sidebars immediately and unconditionally, even
 * right after a click. Because the map fills the entire viewport behind
 * every overlay (sidebars, edge tabs, mode switcher), "the cursor is over
 * the globe" is detected the same way as "the cursor is over the page but
 * not over any known UI overlay" — every overlay this hook cares about is
 * marked with `data-ui-hover-surface` so a single document-level listener
 * can tell the two cases apart without Globe.tsx needing to know anything
 * about sidebar state.
 */
export function useHoverZone() {
  const leftEdgeHovered = useUiStore((s) => s.leftEdgeHovered);
  const rightEdgeHovered = useUiStore((s) => s.rightEdgeHovered);
  const leftPanelHovered = useUiStore((s) => s.leftPanelHovered);
  const rightPanelHovered = useUiStore((s) => s.rightPanelHovered);
  const leftManualOpen = useUiStore((s) => s.leftManualOpen);
  const rightManualOpen = useUiStore((s) => s.rightManualOpen);
  const setLeftOpen = useUiStore((s) => s.setLeftOpen);
  const setRightOpen = useUiStore((s) => s.setRightOpen);
  const forceCloseAll = useUiStore((s) => s.forceCloseAll);

  // Derive visibility from every hover/click source for that side.
  useEffect(() => {
    setLeftOpen(leftEdgeHovered || leftPanelHovered || leftManualOpen);
  }, [leftEdgeHovered, leftPanelHovered, leftManualOpen, setLeftOpen]);

  useEffect(() => {
    setRightOpen(rightEdgeHovered || rightPanelHovered || rightManualOpen);
  }, [rightEdgeHovered, rightPanelHovered, rightManualOpen, setRightOpen]);

  // Globe-hover force-close: a single document-level listener, since the
  // globe is "everything that isn't a known UI overlay" rather than a
  // specific element this hook has a ref to.
  useEffect(() => {
    function handlePointerOver(e: PointerEvent) {
      const target = e.target as Element | null;
      if (target?.closest('[data-ui-hover-surface]')) return;
      forceCloseAll();
    }

    document.addEventListener('pointerover', handlePointerOver);
    return () => document.removeEventListener('pointerover', handlePointerOver);
  }, [forceCloseAll]);
}
