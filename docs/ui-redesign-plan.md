# UI redesign: tighter, sharper, more professional

Plan for a new look for GeoIntel. The goal is a denser, calmer interface where the data gets the space and the chrome gets out of the way. This is a separate plan from the product plans (`docs/story-pipeline-plan.md`, `docs/weather-mode-plan.md`, `docs/timezone-mode-plan.md`); it changes how things look and are laid out, not what they do.

Status: **Stage 0 (foundations) committed (91be044). Stage 1 (shell and Settings) implemented** (not committed); Stages 2 to 7 planned. In the numbered build order below, "Stage 0" is item 1 and "Stage 1" is item 2. The six open questions have been answered (see "Decisions made"). Measurements below were taken from the running app at 1440 x 900 on 6 October 2026.

## Stage 0 as built

- **Removed:** `App.css` and every starter rule in `index.css`. `index.css` now only imports the two files below.
- **`src/styles/tokens.css`:** the colour, spacing, radius, type-size and motion tokens, dark values from the colours the app already uses and a light override on `:root[data-theme='light']`. Two small changes to the old values, both needed to pass the contrast check: the panel is a solid `#0a0e14` (the old 75% see-through panel cannot meet 4.5:1 over a bright map; a separate 92% `--panel-overlay` is kept for overlay mode), and the muted text strength is 60% (was a mix of 55 and 60). Severity badge text on Critical red is white, because the dark text used before measured only 3.7:1.
- **`src/styles/base.css`:** 13 px body at 1.4 line height, system font stack, tabular numerals, focus ring, thin scrollbars, reduced-motion rule. It deliberately does not set `box-sizing` globally, because existing screens mix the two; the new components set it themselves.
- **Shared components in `src/ui/`:** Button and IconButton, Segmented, Chip, Badge (severity and alert tones), Tabs (arrow keys, Home, End), Toolbar, Section (collapsible), KeyValue, ListRow, StateMessage (empty, loading, error), Popover, Drawer, and an inline-SVG Icon set of 20. No new dependencies.
- **Hidden kit page:** open the app with `?ui` (a query, not a path, so it works on the static host). It shows every component in dark, light or system, including a 40-row dense list and the colour and type scales. It is a separate chunk and is not linked from the app.
- **Theme handling:** `src/ui/theme.ts` (Dark default, Light, Match my system; remembered in the browser; storage-blocked safe). It is applied at start-up; the Settings control that changes it arrives in Stage 2.
- **Guards:** `npm run lint` now also runs `scripts/check-styles.mjs`, which fails on a hard-coded colour, a font size outside the six, or a radius outside the two, in the folders listed in `CONVERTED` (just `src/ui` for now; each later stage adds the folders it converts). `tests/contrast.test.ts` reads the tokens and checks 4.5:1 for text and 3:1 for marks, focus ring and control edges, in both themes (it was checked to fail when a token is weakened).
- **Checked:** keyboard behaviour of Tabs, Popover (Escape, outside click, focus return) and Drawer (focus moves in, Tab wraps both ways, Escape closes and focus returns) in the browser; 51 new tests (137 frontend tests in all).
- **Effect on the current app, from the base layer alone** (same script as the audit, 1440 x 900): first event 262 px from the top of the panel (was 304); row height 85 px (was 107); events fully visible 7 (was about 5). The remaining text sizes and spacing are the old components' own and change as each stage converts them.

## Stage 1 as built (shell and Settings)

- **New frame** (`src/shell/`): a 40 px top bar (wordmark, mode switch, Layers, Settings, Dashboard, account), a thin context strip under it (the pin key in Events; the hazard chips and honest notices in Weather; nothing in Time Zone), the working area, and a 24 px status bar (how fresh the data is and any problem, plus the UTC time). The old floating groups are gone: `Logo`, `ModeSwitcher`, `AccountChip`, `LayerControl`, `MapLegend` and `WeatherLegend` were deleted and replaced by these.
- **Docked panels by default.** The events and analysis panels are columns beside the map (300 and 360 px); the events panel is open from the start and the analysis panel opens when something is selected; a tab on the map's edge collapses or restores each. The map resizes to the space left and the globe is **fitted to it** (about 88% of the smaller side) until the user zooms for themselves, so it is no longer a small disc in the middle of a big screen. Under 900 px wide the panels fall back to the old overlay behaviour automatically.
- **Layers menu:** Satellite and Topography (premium), the Weather radar and its loop, the Time Zone night side and zone labels, each shown only in the mode where it means something. Radar, Night and Labels chips are gone from their old places.
- **Settings menu:** Panels (Docked, or Overlay on hover as before), Theme, Starfield (on by default, off switch works), Units (metric or imperial), Forecast times (place local or UTC), Clock (24 or 12 hour) and Date format. Units, forecast time zone and clock choices moved here from the forecast panel and the world clock, and everything is remembered in this browser.
- **Light theme is offered but switched off in the app** (greyed, with an explanation) until every screen is converted, because the unconverted screens would be unreadable on a light surface. It is complete in the tokens and visible at `?ui`. Flip `LIGHT_THEME_READY` in `src/state/settings.ts` when the last stage is done.
- **Time bar** now sits inside the map area, slimmer, with Night and Labels moved to Layers.
- **Guard and tests:** `src/shell` and `src/globe/TimeBar.module.css` join `CONVERTED` (9 stylesheets checked), the guard now accepts single files, and 6 new tests cover the stored preferences (143 frontend tests in all).
- **Checked in the browser** (1440 and 800 px wide): docked layout, selection opening the analysis panel and the globe refitting, collapsing and reopening the events panel four times and switching Docked and Overlay with no console errors, Settings changes taking effect and persisting, each mode's Layers contents and strip, the narrow-window fallback, and the Dashboard lock.
- **Measured at 1440 x 900, both panels open:** map 780 px wide, **54% of the window** (the plan's 60% target was wrong for its own 300 + 360 panels; the target is now 54%). First event 204 px below the panel top (was 304) and rows 104 px (was 107): the list itself is rebuilt in the next stage, which is where the "first event under 110 px, 20 or more events visible" targets are met.
- **Unchanged on purpose:** panel contents, the dashboard modal, map popups and the pin emoji are converted in later stages.

## Stage 2 as built (lists)

- **Events list:** dense, virtualised rows (title, compact severity badge, country, short age such as `5m`, `3h`, `2d`). Filters moved into one Filters popover (Show: All, Major only, By category; category chips; "first reported at night"; Clear filters) with a count badge on the button. A sort strip (Severity, Newest, Country) toggles direction; ties break predictably (`sortCrises` in `lib/filters.ts`).
- **Weather list:** same row, with a hazard icon (cyclone, flood, fire, drought, warning), alert badge, country and age; filters All, Major (Orange and Red), By type.
- **World clock:** rebuilt on the shared Tabs, Badge and StateMessage; each row shows UTC offset and the next clock change (`nextChangeShort`); the planner uses token fills for working, early/late and night hours.
- **Analysis, edge tabs and planner stylesheets** are on tokens; `CONVERTED` now covers 14 stylesheets.
- **Measured at 1440 x 900:** first event 101 px below the panel top (target under 110, met); rows 35 px (was 107); **19 fully visible, the 20th partly** (target 20 or more, just short).
- **Fixed during checking:** the Filters popover opened left-aligned and was clipped by the panel; it is now right-aligned inside it.
- **Checks:** `tsc`, the style guard, the production build and 156 tests pass.

## What is wrong today (measured)

- **Too few events per screen.** The first event starts 304 px down the left panel, and each event row is 107 px tall. At 900 px high, about five events are visible.
- **The page is set in the starter template's type.** The base is 18 px with 145% line height and added letter spacing (`index.css`, left over from the Vite starter). Buttons and rows inherit it, which is why rows are so tall even though components ask for 12 to 14 px text.
- **No shared design values.** Text sizes on screen: 11, 12, 12.5, 13, 13.5, 14 and 18 px. Corner radii in use: 6, 7, 8, 10 px and fully round. Colours are written out as about 20 different translucent whites. There are no tokens; the light/dark variables in `index.css` are unused.
- **Dead code.** `App.css` is the starter's counter and hero styles, unused.
- **The globe is small.** With both panels open, the globe is roughly 30% of the window width, in the middle of a starfield. The panels are overlays that open on hover, so the map is not sized to the space that is actually free.
- **Six separate floating groups of controls:** logo and mode tabs (top centre), account chip (top left), Satellite and Topography (right edge), the key (bottom left), the time bar (bottom centre), the ruler (bottom right).
- **Four stacked control rows above the event list:** Global / Local, 24h / 48h / 7 days, All / Major / Categories, and "Reported at night". About 170 px of buttons before a single event.
- **A large image in the analysis panel** (166 px tall) pushes the analysis down. The image is whatever the article's page offers, and is often irrelevant (a mugshot above an event summary).
- **Frosted-glass panels everywhere** (blur behind translucent surfaces). It costs performance over a live map; it is already switched off on phones for that reason.
- **23 stylesheets, about 2,300 lines**, each with its own spacing and sizes, so screens do not line up with each other.

## Design direction

**Dense, flat, quiet.** An analyst's tool, closer to a trading or operations screen than a consumer app.

- **Type:** one UI stack (system fonts), **13 px body at 1.4 line height**, tabular numerals for every number and time, three weights at most. Sizes limited to a six-step scale (11, 12, 13, 14, 16, 20). No letter spacing on body text.
- **Space:** a 4 px grid. Row padding 4 to 6 px, panel padding 12 px, section gaps 12 px. Touch screens get larger targets through a coarse-pointer rule, not by making the desktop loose.
- **Surfaces:** flat, solid panels with hairline (1 px) borders instead of blur and glow. Three surface levels (app, panel, raised) and nothing else.
- **Colour: the current palette is kept.** The app's existing near-black blue-grey, its light-blue accent, the five severity colours, the GDACS Green / Orange / Red alert colours and the amber warning colour all stay exactly as they are today. What changes is that each becomes a named token, used the same way everywhere, instead of about 20 hand-written variants. Colour is used for structure only in neutral greys, and for meaning (severity, alerts, warnings) everywhere else. No hard-coded colours in components.
- **Shape:** two radii (3 px for controls, 6 px for panels and popovers). Pills only for small status chips.
- **Motion:** short (120 ms) and functional; none when the user asks for reduced motion.
- **Icons:** a small single-weight set drawn as inline SVG, replacing the emoji used for hazards and mode icons. (Emoji render differently on every system and look unprofessional.)
- **Themes:** dark is the primary theme and the default; a light theme is an option (Settings: Dark, Light, or Match my system). Both come from the same token names, so no component knows which theme is active.

### Token set (values are the ones in use today; Stage 0 names them)

| Role | Dark (current) | Notes |
|---|---|---|
| Text | `#e6e9ef`; secondary at 70% and muted at 55% of it | the same three text strengths already used |
| Panel | `rgba(10, 14, 20, 0.75)` on desktop, `0.94` on phones | made solid-looking by dropping the blur; Stage 0 checks the exact result |
| Raised / hover | `rgba(255, 255, 255, 0.06)` and `0.1` | inputs, hover, selected rows |
| Line | `rgba(255, 255, 255, 0.08)` and `0.12` | hairlines and stronger dividers |
| Accent | `#5aa0ff` (active fills at 25%) | selection, focus ring, primary button |
| Sky | `#7dd3fc` | the sliders, weather highlights |
| Warning | `#fcd34d` | notes, "not now", unusual offsets |
| Severity | Critical `#dc2626`, Severe `#f97316`, Serious `#eab308`, Moderate `#84cc16`, Minor `#22c55e` | unchanged |
| Hazard alerts | Red `#ff2d55`, Orange `#ff9500`, Green `#34c759` | unchanged |
| Spacing | 4, 8, 12, 16, 24 | |
| Radius | 3, 6 | |

**Light theme:** the same hues on light surfaces, with the text, line, panel and raised tokens swapped for light equivalents, and the severity, alert, accent and warning colours darkened just enough to keep 4.5:1 contrast on white (the dark theme's values are tuned for dark backgrounds). The base map stays as it is in both themes; the panels and controls change. The exact light values are set in Stage 0 and checked pair by pair.

## Layout

At 1440 x 900 the target is: **top bar 40 px, left panel 300 px, right panel 360 px, status bar 24 px, and the map filling everything between.**

- **Top bar (40 px, one row):** logo, mode tabs (Events, Weather, Time Zone), then on the right: Layers menu, Dashboard, account. This replaces the six floating groups.
- **Docked panels (default).** On a desktop-width window the two panels are part of the layout (collapsible with a keyboard shortcut and a small handle), and the map is sized to the space left, so the globe is as large as the window allows. This changes the current hover-to-open behaviour. **Settings has a "Panels" choice: Docked (default) or Overlay on hover**, which is today's behaviour with a full-screen map.
- **Layers menu:** one popover holding everything that is a map overlay: Satellite, Topography, Radar and its play control, Night, Labels. The weather hazard chips and the map key become a single compact strip under the top bar.
- **Time bar:** stays at the bottom of the map in Time Zone mode, thinner, joined to the status bar's row.
- **Status bar (24 px):** data age ("Events updated 4 min ago"), counts, and the connection state. This is the single home for the "honest state" messages that now appear as notes in many places.
- **Map:** the map fills its area. **The starfield is kept by default, with a Settings switch to turn it off** (plain dark background). Popups restyled to match.
- **Settings (new):** a gear in the top bar opens a small popover (a drawer on phones) with: Panels (Docked / Overlay on hover), Theme (Dark / Light / Match my system), Map (Globe / Flat), Starfield (on / off), Units and time (the existing metric/imperial, local/UTC and 12/24 hour choices, gathered in one place). Choices are remembered in this browser, as the existing ones are. Nothing here changes on the server.

## Components

A small shared set, so every screen is built from the same parts. Each is a CSS module over the tokens, with no new libraries.

- **Button** (default, primary, quiet, icon), **Segmented** control (replaces the many ad-hoc toggle rows), **Chip**, **Badge**, **Tabs**, **Toolbar**.
- **List row** with a dense single-line default (title, severity chip, country, age) and a two-line variant when selected or on wide panels.
- **Section** with a title bar that can collapse, hairline separators, and a **KeyValue** grid for facts.
- **Popover** and **Drawer** (for filters, layers and the dashboard).
- **Empty / loading / error** states in one consistent style.

## Screen by screen

**Events list (left panel).**
- One 32 px toolbar: scope and time range as two small segmented controls on one row; a **Filters** popover for category and "Reported at night" (with a count badge when a filter is active). Target: the first event starts under 110 px from the top of the panel.
- Rows of 36 px: title on one line (ellipsis, full title on hover), severity chip, country, age. Selected row gets a 2 px accent bar. Target: 20 or more events visible at 900 px high.
- Column header strip (Severity, Country, Age) that is also the sort control.

**Event analysis (right panel).**
- Header in two lines: title (up to two lines), then severity chip, country, type, date and the Save button in one row.
- Tabs for Analysis and Comments, then collapsible sections: Summary, Why this rating, Sources, Nearby hazard, Scenarios. Each starts open or closed by importance.
- The article image becomes a 56 px thumbnail beside the title (or hidden), so it never pushes the content down. The location note and "first reported" line collapse into one muted line with an info icon for the detail.
- Premium locks use one small lock chip, not a full-width banner, until the user clicks.

**Weather.**
- Hazard list uses the same row component (icon, name, alert chip, country, distance or age).
- Hazard panel: facts in a KeyValue grid; track and exposure as a section; the timeline and compare tables restyled as compact data tables.
- Point forecast: the 24-hour strip and 7-day table tightened to fixed 28 px rows.

**Time Zone.**
- World clock rows at 40 px (city, offset, next clock change in muted text on the same line, time right-aligned in tabular numerals).
- Planner grid: smaller cells with a sticky header; legend inline. Converter: result as a small table.
- Time bar slimmed; map labels keep their amber highlight.

**Dashboard (Saved, Sources, Watchlist, Alerts).** From a centred modal to a right-hand drawer with the same tabs; lists become dense tables with inline actions.

**Account and gates.** Account becomes an avatar menu in the top bar (sign out inside it). Premium gates become inline lock chips with a short explanation on click.

**Mobile and touch (coarse pointer or under 768 px).** Panels become bottom sheets (peek, half, full) over the map; the top bar collapses to the logo, mode tabs and a menu; tap targets are 44 px; type stays 14 px minimum. Density is a desktop-pointer feature.

## Accessibility and performance

- Colour contrast at least 4.5:1 for text, 3:1 for UI edges, checked per token pair in Stage 0. A visible focus ring (2 px accent) on everything interactive; full keyboard operation of lists, tabs, popovers and the time slider.
- Severity and alert levels always carry their word, not only a colour.
- Respect `prefers-reduced-motion`. "Match my system" follows `prefers-color-scheme`; the default for a first visit is dark either way.
- Remove the blur effects (they cost frames over WebGL). Target: no regression in map frame rate, and a smaller CSS bundle than today.

## Build order

Each stage ships on its own, is visible in the app, and is checked before the next. **No new dependencies in stages 0 to 5** (plain CSS modules and inline SVG).

1. **Foundations.** Delete the starter leftovers (`App.css`, unused `index.css` rules); add `tokens.css` with the dark values above and the light overrides; a base layer (13 px body, no letter spacing, tabular numerals, focus ring, scrollbar style); the shared components; and a hidden `/ui` page showing every component in every state, in both themes. Add a check that fails the build if a component stylesheet uses a hard-coded colour or a font size outside the scale.
2. **Shell and Settings.** Top bar, docked panels with map resizing, Layers menu, status bar, the compact weather chip strip and key, and the **Settings popover with Panels, Theme and Starfield working** (Map and Units arrive with their own stages below; Units and time are moved here from where they are now). The old hover behaviour moves behind the Panels setting. This is the largest visual change.
3. **Lists.** Events list (toolbar, Filters popover, dense rows, sortable header), Weather list, World clock.
4. **Analysis panels.** Event, hazard, forecast and zone panels rebuilt on Section, KeyValue and the thumbnail pattern.
5. **Overlays and edges.** Dashboard drawer, account menu, premium gates, map popups, legends, notices.
6. **Flat map option.** A Settings choice of Globe (today) or Flat. Map projection is a MapLibre setting, but several things were built for the globe and need checking for the flat view: the Weather storm pins and other DOM markers hide when they are on the far side of the globe and must simply always show when flat; the camera, zoom limits, double-click and wrap-around at the date line; the night shading, zone labels, hazard geometry and radar layers; pin clustering and the stacked-pin grouping at flat-map scales. The choice is remembered. A flat map also gives a denser overview, so the default view when flat is the whole world fitted to the window.
7. **Mobile and touch, then polish.** Bottom sheets, coarse-pointer targets, an accessibility pass in both themes, a performance pass, and removal of any old styles left behind.

## How each stage is checked

- `tsc`, the production build, lint and the existing frontend tests stay green; the backend suite is a regression check only (no backend change is planned).
- **Measured targets**, re-measured with the same script as the audit above: first event under 110 px from the panel top; 20 or more events visible at 900 px; 6 or fewer distinct text sizes; 2 radii; 0 hard-coded colours in component stylesheets; map width at least 54% of the window at 1440 with both panels open (300 + 360 px panels).
- Screenshots at 1440, 1024 and 390 px wide for each screen in Events, Weather and Time Zone, before and after, in dark and light, kept in the repo's docs for comparison.
- Contrast of every text and UI-edge token pair is computed for both themes and the results are recorded; any pair under 4.5:1 (text) or 3:1 (edges) is fixed before the stage is called done.
- Each Settings choice is tested: it takes effect immediately, survives a reload, and falls back to the default if browser storage is blocked.
- A manual pass with keyboard only and with the screen at 200% zoom.

## Decisions made

1. **Panels:** docked by default, with an "Overlay on hover" option in Settings.
2. **Theme:** dark is primary and the default; light is an option (plus "Match my system").
3. **Typeface:** the system font stack. No download.
4. **Colours:** the current palette is kept and turned into tokens.
5. **Starfield:** kept by default, with a Settings switch to turn it off.
6. **Flat map:** added as a Settings option (Globe or Flat), built as its own stage.

Still open (small, can be decided when we reach them): the exact light-theme values (set and contrast-checked in Stage 0), whether Settings choices should later follow the user's account across devices (this plan keeps them per browser), and whether a "comfortable" density setting is wanted after the compact one is in.

## Out of scope

Changing what any feature does, new features beyond the Settings panel and the flat map option, a rebrand of the product name, a bundled typeface, account-synced settings, and changes to the backend or data.
