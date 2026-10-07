import { useDrawStore } from '../../state/drawStore';

// Presentation mode: the page shows only the map and the drawing (no bars, panels or tools), for a talk or a screen share.
// It asks the browser for full screen too, where that is allowed. Escape or the Exit button leaves it.
let enteredFullscreen = false;

export function startPresenting(): void {
  useDrawStore.getState().setPresenting(true);
  try {
    if (document.documentElement.requestFullscreen && !document.fullscreenElement) {
      void document.documentElement
        .requestFullscreen()
        .then(() => {
          enteredFullscreen = true;
        })
        .catch(() => {
          /* full screen refused: the page still presents */
        });
    }
  } catch {
    /* no full screen here */
  }
}

export function stopPresenting(): void {
  useDrawStore.getState().setPresenting(false);
  try {
    if (enteredFullscreen && document.fullscreenElement) void document.exitFullscreen();
  } catch {
    /* already out */
  }
  enteredFullscreen = false;
}

// The browser left full screen by itself (its own Escape): leave presentation mode too.
export function handleFullscreenChange(): void {
  if (!document.fullscreenElement && enteredFullscreen) stopPresenting();
}
