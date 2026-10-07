import type { ReactNode } from 'react';

// A small single-weight icon set, drawn as inline SVG so it takes the text colour and looks the same on every
// system (unlike emoji). 24 x 24 grid, 1.6 px stroke.
const PATHS: Record<string, ReactNode> = {
  check: <path d="M5 12.5l4.5 4.5L19 7.5" />,
  'chevron-down': <path d="M6 9l6 6 6-6" />,
  'chevron-right': <path d="M9 6l6 6-6 6" />,
  close: <path d="M6 6l12 12M18 6L6 18" />,
  plus: <path d="M12 5v14M5 12h14" />,
  minus: <path d="M5 12h14" />,
  settings: (
    <>
      <path d="M4 7h9M19 7h1M4 17h1M11 17h9" />
      <circle cx="16" cy="7" r="2.2" />
      <circle cx="8" cy="17" r="2.2" />
    </>
  ),
  lock: (
    <>
      <rect x="5" y="11" width="14" height="9" rx="2" />
      <path d="M8 11V8a4 4 0 018 0v3" />
    </>
  ),
  search: (
    <>
      <circle cx="11" cy="11" r="6" />
      <path d="M16 16l4 4" />
    </>
  ),
  layers: <path d="M12 3l9 5-9 5-9-5 9-5zM3 13l9 5 9-5" />,
  info: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v5M12 8h.01" />
    </>
  ),
  sun: (
    <>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6L7 7M17 17l1.4 1.4M5.6 18.4L7 17M17 7l1.4-1.4" />
    </>
  ),
  moon: <path d="M20 14.5A8 8 0 019.5 4 8 8 0 1020 14.5z" />,
  copy: (
    <>
      <rect x="9" y="9" width="11" height="11" rx="2" />
      <path d="M5 15V6a2 2 0 012-2h9" />
    </>
  ),
  link: <path d="M10 14a4 4 0 005.7 0l3-3a4 4 0 00-5.7-5.7l-1 1M14 10a4 4 0 00-5.7 0l-3 3a4 4 0 005.7 5.7l1-1" />,
  warning: <path d="M12 3l10 18H2L12 3zM12 10v5M12 18h.01" />,
  globe: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </>
  ),
  cloud: <path d="M7 18a4 4 0 01-.5-8 5.5 5.5 0 0110.7 1.2A3.5 3.5 0 0117 18H7z" />,
  bolt: <path d="M13 3L5 13h6l-1 8 8-10h-6l1-8z" />,
  cyclone: (
    <>
      <circle cx="12" cy="12" r="1.4" />
      <path d="M12 8.5a3.5 3.5 0 013.5 3.5M12 4.5a7.5 7.5 0 017.5 7.5M12 15.5a3.5 3.5 0 01-3.5-3.5M12 19.5a7.5 7.5 0 01-7.5-7.5" />
    </>
  ),
  flood: <path d="M3 8c2 0 2 2 4.5 2S10 8 12 8s2 2 4.5 2S19 8 21 8M3 14c2 0 2 2 4.5 2S10 14 12 14s2 2 4.5 2S19 14 21 14" />,
  fire: <path d="M12 3c.5 3.5 4.500 4.5 4.500 9.500a4.500 4.500 0 01-9 0c0-1.800.800-3 1.800-4 .200 1.500.900 2.300 1.700 2.600C11 9.500 10.800 6 12 3z" />,
  play: <path d="M8 5l11 7-11 7V5z" />,
  pause: <path d="M8 5v14M16 5v14" />,
  pencil: <path d="M4 20l1-4L16 5l3 3L8 19l-4 1zM14 7l3 3" />,
  pointer: <path d="M6 3l12 7-5 2-2 5L6 3z" />,
  dot: (
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 3v4M12 17v4M3 12h4M17 12h4" />
    </>
  ),
  line: (
    <>
      <path d="M7 17L17 7" />
      <circle cx="5.5" cy="18.5" r="1.8" />
      <circle cx="18.5" cy="5.5" r="1.8" />
    </>
  ),
  angle: <path d="M4 19h16M4 19L16 5M9 19a5 5 0 00-1.6-3.7" />,
  ruler: <path d="M3 15L15 3l6 6L9 21l-6-6zM7 11l2 2M10 8l2 2M13 5l2 2" />,
  arrow: <path d="M5 19L19 5M9 5h10v10" />,
  text: <path d="M5 6h14M12 6v13M9 19h6" />,
  eye: (
    <>
      <path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z" />
      <circle cx="12" cy="12" r="3" />
    </>
  ),
  'eye-off': <path d="M3 3l18 18M10.6 6.2A9.6 9.6 0 0112 6c6 0 10 6 10 6a17 17 0 01-3.2 3.7M6.3 7.7A17 17 0 002 12s4 7 10 7c1.7 0 3.2-.4 4.6-1M9.9 9.9a3 3 0 004.2 4.2" />,
  save: <path d="M5 4h11l3 3v13H5V4zM8 4v5h7V4M8 20v-6h8v6" />,
  download: <path d="M12 4v12M7 11l5 5 5-5M5 20h14" />,
  upload: <path d="M12 16V4M7 9l5-5 5 5M5 20h14" />,
  camera: (
    <>
      <path d="M4 8h3l2-3h6l2 3h3v11H4V8z" />
      <circle cx="12" cy="13" r="3.5" />
    </>
  ),
  present: (
    <>
      <rect x="3" y="4" width="18" height="12" rx="1" />
      <path d="M8 20h8M12 16v4" />
    </>
  ),
  polygon: <path d="M12 4l8 6-3 9H7l-3-9 8-6z" />,
  rectangle: <rect x="4" y="6" width="16" height="12" rx="1" />,
  circle: <circle cx="12" cy="12" r="8" />,
  freehand: <path d="M3 15c3-8 5 3 8-1s4-7 10-1" />,
  undo: <path d="M9 4L5 8l4 4M5 8h8a6 6 0 010 12H8" />,
  redo: <path d="M15 4l4 4-4 4M19 8h-8a6 6 0 000 12h5" />,
  trash: <path d="M5 7h14M10 7V4h4v3M7 7l1 13h8l1-13" />,
  user: (
    <>
      <circle cx="12" cy="8" r="4" />
      <path d="M4 21c1-4 4-6 8-6s7 2 8 6" />
    </>
  ),
};

export type IconName = keyof typeof PATHS;

export const ICON_NAMES = Object.keys(PATHS) as IconName[];

export default function Icon({ name, size = 16, title }: { name: IconName; size?: number; title?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      role={title ? 'img' : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
      focusable="false"
    >
      {PATHS[name]}
    </svg>
  );
}
