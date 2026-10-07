import type * as maplibregl from 'maplibre-gl';

// What the user can do to the map with the pointer and the keyboard. Locked: nothing moves it (drag, scroll, pinch and
// double-click zoom, box zoom, rotation, tilt, arrow-key moves), so a slip of the hand while drawing or presenting cannot move
// the globe. Unlocked: each of those goes back to exactly what it was before the lock (the drawing engine, for one, keeps
// double-click zoom off so that a double click can finish a line), and the flat map cannot be rotated or tilted (it has no use
// for that).
interface Handlers {
  pan: boolean;
  rotate: boolean;
  scroll: boolean;
  box: boolean;
  doubleClick: boolean;
  touch: boolean;
  touchPitch: boolean;
  keyboard: boolean;
}

const before = new WeakMap<maplibregl.Map, Handlers>();

function read(map: maplibregl.Map): Handlers {
  return {
    pan: map.dragPan.isEnabled(),
    rotate: map.dragRotate.isEnabled(),
    scroll: map.scrollZoom.isEnabled(),
    box: map.boxZoom.isEnabled(),
    doubleClick: map.doubleClickZoom.isEnabled(),
    touch: map.touchZoomRotate.isEnabled(),
    touchPitch: map.touchPitch.isEnabled(),
    keyboard: map.keyboard.isEnabled(),
  };
}

function set(handler: { enable: () => void; disable: () => void }, on: boolean): void {
  if (on) handler.enable();
  else handler.disable();
}

export function applyInteraction(map: maplibregl.Map, view: 'globe' | 'flat', locked: boolean): void {
  if (locked) {
    // Remember what was on the first time only; asking again (the lock is re-applied after a drag) must not overwrite it.
    if (!before.has(map)) before.set(map, read(map));
    map.dragPan.disable();
    map.dragRotate.disable();
    map.scrollZoom.disable();
    map.boxZoom.disable();
    map.doubleClickZoom.disable();
    map.touchZoomRotate.disable();
    map.touchPitch.disable();
    map.keyboard.disable();
    return;
  }
  const previous = before.get(map);
  if (previous) {
    set(map.dragPan, previous.pan);
    set(map.dragRotate, previous.rotate);
    set(map.scrollZoom, previous.scroll);
    set(map.boxZoom, previous.box);
    set(map.doubleClickZoom, previous.doubleClick);
    set(map.touchZoomRotate, previous.touch);
    set(map.touchPitch, previous.touchPitch);
    set(map.keyboard, previous.keyboard);
    before.delete(map);
  }
  if (view === 'flat') {
    map.setPitch(0);
    map.setBearing(0);
    map.dragRotate.disable();
    map.touchZoomRotate.disableRotation();
    map.touchPitch.disable();
  } else {
    map.dragRotate.enable();
    map.touchZoomRotate.enableRotation();
    map.touchPitch.enable();
  }
}
