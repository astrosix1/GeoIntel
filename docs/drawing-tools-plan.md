# Drawing tools: measure, plan, present, and keep

Plan for replacing the bolt-on drawing toolbar with a tool that looks like the rest of the app, measures properly, supports scenario planning and presentation, and saves to the user's account. Earlier plans: `docs/ui-redesign-plan.md`, `docs/story-pipeline-plan.md`.

## What the owner asked for, and what was decided

Today's problems: it looks out of place, it is missing tools, and nothing is saved. What it is for: **distances, planning potential outcomes and scenarios, area, angles, and drawing over places for presentations.**

Decisions:
- **Free:** drawing and measuring, in the browser, for the visit.
- **Premium:** saving. Drawings are **saved to the account** and open on any device. Exporting a drawing to a file counts as saving, so it is premium too.
- **Build our own tool on the `terra-draw` engine** (already installed and doing the drawing today) instead of the third-party toolbar plugin. The plugin's toolbar cannot be restyled to the design tokens or made touch-friendly, and its measuring is limited to length and area.

## What exists today

`frontend/src/globe/DrawMeasureControl.tsx` mounts `@watergis/maplibre-gl-terradraw`'s ready-made control (bottom right, ten modes: point, line, polygon, rectangle, circle, freehand, select, delete selection, delete all). It labels line length and polygon area in fixed units (km, km²). It ignores the Units setting, the Light theme, the kit's buttons and phones. Nothing about a drawing is stored, and a shape has no colour, name or notes. It loads as a separate chunk (about 64 KB gzipped) after the map.

## What the tool should do

**Draw:** point, line, polygon, rectangle, circle (by radius), freehand, arrow, text label. Select, move, reshape, duplicate, delete. Undo and redo. Snap to existing vertices.

**Measure** (geodesic, so correct on the globe and the flat map, not flat-plane maths):
- **Distance:** every segment and the running total, as the line is drawn.
- **Area and perimeter** of any polygon, rectangle or circle.
- **Angles:** the angle at any vertex of a line or polygon, a dedicated three-point angle tool, and the **bearing** of each segment.
- **Radius** of a circle, and coordinates of a point.
- Units follow Settings: metric, imperial and nautical for distance; km², hectares, square miles and acres for area.

**Plan scenarios:**
- Drawings sit in **named layers** ("Scenario A: blockade", "Evacuation route"), each shown or hidden separately and given notes. Switch layers on and off to compare outcomes side by side.
- Each shape can carry a label and a note; the shape's measurements can be shown on the map or hidden.

**Present:**
- Colour, line width, fill and opacity, dashed or solid, per shape; a short palette that works on dark and satellite maps.
- Text labels and arrows for annotation.
- **Presentation mode:** hides the panels and bars so only the map and the drawing show.
- **Save the view as an image** (PNG of the map with the drawing) for slides.

**Keep (premium):** save, rename, reopen and delete drawings in the account; export and import GeoJSON.

## Design

- **Where it lives:** a Draw button in the top bar opens a compact tool strip over the map (a bottom sheet on phones) plus a panel for the selected shape (style, label, note, measurements) and the layer list. Built from the kit (`Button`, `Segmented`, `Section`, `Chip`), tokens only, Light and Dark, 44 px targets on touch.
- **State:** a `drawStore` (tool, selected shape, layers, history) separate from `uiStore`; the drawing engine stays behind a small wrapper (`globe/draw/`), so the React side never calls the library directly.
- **Data format:** a GeoJSON FeatureCollection. Each feature carries its style, label, note and layer in `properties`. This is what is stored, exported and imported. Circles are stored as a centre and radius with the polygon computed from them, so they stay exact.
- **Measurement code is pure TypeScript with tests** (Turf is already in the bundle through the plugin): distance, area, bearing, angle, unit conversion, and formatting.
- **Account storage (premium):** a new Supabase table `geointel_drawings` (id, user id, name, GeoJSON, created and updated times) behind row level security with the service-role key only, as the saved events are. Routes under `/api/me/drawings` with `@require_premium`. Limits to keep it safe and cheap: 50 drawings per user, 1 MB of GeoJSON each, a cap on vertices per drawing, validation of the GeoJSON (types, coordinate ranges, no scripts in text). The browser keeps an unsaved draft in local storage so a refresh does not lose work.
- **Free users:** can use everything above for the visit and keep an unsaved draft locally; the Save and Export buttons show the standard premium lock.

## Stages (each checked before the next)

**D0: our own tool, nothing lost.** Replace the plugin with `terra-draw` behind our wrapper. A Draw button, our tool strip, the existing modes (point, line, polygon, rectangle, circle, freehand, select, delete) at parity, undo and redo, and the distance and area labels at parity with unit settings. Remove the plugin and its CSS. Works on the globe, the flat map, and touch. Done when it does everything today's tool does and looks like the app.

**D1: measuring.** Per-segment distances and totals, perimeter, vertex angles, the three-point angle tool, segment bearings, radius, point coordinates; the unit sets above. All pure and unit-tested; checked against known distances and areas.

**D2: styling, labels, annotation.** Colour, width, fill, opacity, dashes; labels and notes; the text and arrow tools; duplicate.

**D3: layers and scenarios.** Named layers with show and hide and notes; a layer list; moving shapes between layers; the side-by-side compare workflow.

**D4: save to the account (premium).** The Supabase migration, the backend service and routes with tests, the frontend save, open, rename and delete, the local draft, GeoJSON export and import, free-user locks.

**D5: presentation.** Presentation mode, save the view as a PNG, and a clean print-friendly style for labels.

**D6: polish.** Phones (bottom-sheet tool strip), Light theme, an accessibility pass (keyboard drawing and selecting, labels for every tool), performance with large drawings, and the flat map's date-line behaviour.

## D0 as built

- **Our own tool replaces the plugin.** `@watergis/maplibre-gl-terradraw` and `DrawMeasureControl.tsx` are gone. `src/globe/draw/engine.ts` is the only file that touches `terra-draw`; the rest of the app sees a small interface (`setTool`, `undo`, `redo`, `deleteSelected`, `clear`, `features`). It loads as its own chunk the first time the tool is opened: **41 KB gzipped, down from 64 KB** with the plugin.
- **Draw button and tool strip.** A Draw button in the top bar opens a strip over the map built from the kit's buttons: select and edit, point, line, area, rectangle, circle (by radius), freehand, undo, redo, delete the selected shape, clear everything, and Done (hides the tools; the drawing stays on the map). Tools have names for screen readers, a hint line says how to finish each shape, and targets are 44 px on touch. On phones the strip runs along the top of the map and the Draw button moves to a pill at the bottom centre (the top bar had no room).
- **Measuring at parity, and better:** lines show their length; areas (rectangles and circles too) show area and perimeter. All geodesic, in the user's Units setting (metric or imperial), updating live while a shape is drawn. A shape with no size yet shows no label. `src/globe/draw/measure.ts` is pure and tested against known values (London to Paris, New York to Los Angeles, a degree square at the equator, date-line cases, holes, every unit format).
- **Undo and redo** (also Ctrl+Z and Ctrl+Y) come from the engine's own session history. Snapping to existing corners is on for lines and areas. Circles stay true circles on the globe and the flat map.
- **Map clicks stand down while the tool is open:** pins, clusters, countries, zones and the weather point forecast ignore clicks, so drawing never selects something underneath.
- **Risk retired early:** the library accepts a style per shape (colour, width, dash) as a function of the shape, so D2 styling needs no workaround. It also ships undo and redo, snapping, marker, sector and polyline modes, which simplifies D1 and D2.
- **Checked in the browser:** a line, an area and a circle drawn with real clicks on the globe and the flat map, labels in miles and square miles, undo and redo toggling, Done hiding the tools while the drawing and labels stay, and the phone layout; no console errors. Not yet checked by hand: select-and-edit dragging, delete selected, and the Light theme.
- **Development note:** after removing a dependency the dev server must be restarted before the new chunk loads.

## D1 as built (measuring)

- **Angle tool, no custom mode needed.** The library's line mode can finish on its Nth corner, so the Angle tool is a line that ends on its third click (end of one leg, the corner, end of the other leg). It always shows the angle at the corner and the length of both legs. Its three corners can be moved but not added to or removed. This retires the plan's risk about a custom drawing mode.
- **Measuring options** (a ruler button on the tool strip): **Units** (Auto follows the Units setting; Metric; Imperial; Nautical, with nautical miles for distance and the metric units for area), and three switches: **length of each side**, **angle at each corner**, **compass bearing of each side**. Choices are remembered in this browser (`geointel.draw`). On phones the options open as a panel below the strip.
- **What the labels show.** A line: its total length (with the bearing when it has a single segment). A polygon or rectangle: area and perimeter, and each side and corner angle when switched on (up to 12 corners; more than that shows the total only, so the map is not buried). A circle: radius, area and circumference. A point: its coordinates. Segment lengths sit at the great-circle midpoint of each segment; totals are larger than per-segment figures and angles are in their own colour, offset from the corner.
- **Angles** are the smaller angle between the two sides (0 to 180 degrees), so a reflex polygon corner reads as its smaller supplement. **Bearings** are the initial great-circle bearing, degrees clockwise from north, with the compass point (047 degrees NE).
- **Pure and tested** (`globe/draw/measure.ts`, `prefs.ts`): bearings against the four cardinal directions, right and straight angles, midpoints including across the date line and bowing towards the pole on a long east-west line, coordinates with hemispheres, nautical formats, every label rule (the options, the angle tool, circles, many-cornered polygons, empty shapes). 215 frontend tests in all (20 new).
- **Bug found while checking in the browser:** the engine's helper points (a shape's corners, closing and snapping points) carry the shape's mode name, so they were being counted as shapes and labelled with coordinates. They are now excluded by their flags, which also fixes the shape count behind "Clear everything".
- **Checked in the browser:** an angle drawn with real clicks at 1000 px wide (legs "2,746 km, 129 degrees SE" and "2,454 km, 075 degrees E", angle 122.7 degrees at the corner), all three switches and the units control, preferences persisting, and the options panel on a phone (moved below the strip after the first look); no console errors. Not yet checked by hand: the options on polygons and circles, and the Light theme.

## Risks and how they are handled

- **`terra-draw` has no text tool and no three-point angle mode.** Text labels are drawn as map symbols from the feature data rather than as drawn shapes, and the angle tool is a small custom mode. Both are part of D1 and D2 and tested before the stages build on them. If the custom mode proves awkward, the angle is computed and shown on a normal line instead (the fallback keeps the feature).
- **Per-shape styling** relies on the engine accepting a style per feature. This is checked at the start of D2; if it does not, shapes are rendered from our own layers and the engine is used only for editing.
- **Globe and flat projections** both need geodesic measuring; measurements never use screen distance.
- **Cost:** none beyond a small Supabase table. No AI calls.
- **Abuse and size:** per-user limits, size caps and GeoJSON validation on the server; text labels are always rendered as text, never as HTML.

## Testing

- Unit tests for every measurement and unit conversion, for GeoJSON validation, and for the drawing-store history (undo, redo, layers).
- Backend tests in the pattern of `test_user_data.py`: scoping by user id, premium enforcement, limits, validation, and unavailable storage.
- Browser checks at 1440 and 375 px in both themes and both map views: drawing each shape, measuring against known values, saving and reopening, and the free-user locks (with `?demo=premium` off and on).
- Style guard, type check, build and the full test suites stay green at every stage.

## Owner actions

- Run the new Supabase migration for `geointel_drawings` before D4 goes live (the SQL will be written to `backend/supabase/`, like the earlier ones).
- Decide before D5 whether to include a watermark or credit line on exported images (map data credits are required by the map sources).

## Out of scope for now

Sharing a drawing with another user, real-time collaboration, drawing-based alerts and "events inside this shape" (a good follow-up once drawings are stored), 3D shapes, and importing formats other than GeoJSON.
