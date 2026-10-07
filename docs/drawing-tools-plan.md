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

## D2 as built (styling, names, text, arrows, duplicate)

- **Per-shape look, kept on the shape.** Colour (six: blue, red, green, purple, black, white), line or outline width (thin, medium, thick), area fill (none, light, medium) and line pattern (solid, dashed) are stored in the shape's own properties (`globe/draw/style.ts`), so they are copied by Duplicate and will be saved with the drawing in D4. The engine asks for each shape's colour and width as it draws, so a restyle shows at once. Dashes apply to lines, arrows and angles (the library has no dashed area outline). The amber used for the selected shape is deliberately not in the palette.
- **Shape panel** (opens beside the tool strip when a shape is selected): name, note, colour, width, fill, pattern, Duplicate and Delete. The name and note commit when the field is left or Enter is pressed, so one edit is one undo step, not one per keystroke. Text is capped (80 and 2,000 characters), stripped of control characters, and only ever drawn as text, never as HTML.
- **Name on the map.** A shape's name is drawn at the shape, above its measurements; the note stays in the panel.
- **Text tool.** Click where the words go and the panel opens with the field focused; the words are drawn on the map in the shape's colour (white words get a dark outline). The anchor point is invisible except while it is selected.
- **Arrow tool.** A two-click line with an arrowhead at the tip that follows the great-circle bearing of the last segment and takes the arrow's colour (a coloured map symbol, `layers.ts`). It shows its length and bearing like a single line.
- **Duplicate** copies the selected shape about 30 pixels over and down at any zoom, keeps its style and name, and selects the copy.
- **Pure and tested:** the style readers and cleaners (valid values only, defaults, palette, text limits, markup treated as text), the arrowhead placement and bearing, and the new label kinds (names, Text tool words with colour). 232 frontend tests in all (17 new).
- **Found and fixed while checking in the browser:**
  - The library styles each shape by the mode it was drawn in, so styling a separate "hidden" mode did nothing; the leftover corner dots on finished shapes are gone by not drawing corner dots at all (each click still shows in the line).
  - Duplicate was refused for having too many decimal places; moved copies are now rounded to the engine's precision.
  - A new text label lost its selection because the app re-applied the Select tool; asking the engine for the tool it is already in now does nothing.
  - The first arrowhead was too small to read; it is now sized to match the line.
- **Checked in the browser:** an arrow restyled (red, dashed, named "Advance north") with its head and "956 mi" label; a green rectangle duplicated, each copy with area and perimeter; a red "Staging area" text label; no console errors. Not yet checked by hand: the panel on a phone, the Light theme, circle duplicate, and dragging text labels.

## D3 as built (layers and scenarios)

- **Named layers.** A drawing has up to 20 layers, starting with "Layer 1". Every shape is on one layer; new shapes go on the active layer (highlighted in the list). The Layers button on the tool strip opens the panel: an eye to show or hide each layer, its name (click to make it the active layer), a count of its shapes, **New layer**, and for the active layer its **name**, a **note** (for what a scenario assumes), **Show only this layer** (a second press shows them all again) and **Delete layer** (two steps: it says how many shapes go with it; the last layer cannot be deleted).
- **Hiding is real.** A hidden layer's shapes are taken off the map (so they cannot be selected or edited by accident, and their measurements and labels go too) and put back, with the same ids and styling, when it is shown again. Choosing a hidden layer to draw on shows it, so a new shape never vanishes.
- **Moving shapes between layers.** The shape panel has a Layer picker (when there is more than one layer); a shape moved to a hidden layer leaves the map at once. Duplicate keeps the original's layer.
- **Layer membership lives beside the shapes, not in them** (`engine.ts` keeps a shape-to-layer map): moving a shape or hiding a layer is not an undo step, which keeps Ctrl+Z to what was drawn. `allFeatures()` returns every shape, hidden ones too, each with its layer id, which is what D4 will save; the layer list (names, notes, visibility) is cleaned by `cleanLayers` when read back.
- **Pure and tested** (`globe/draw/drawlayers.ts`): default names, name and note cleaning, reading a layer list back (bad entries, repeated ids, caps, always at least one), per-layer counts, hidden ids, and the solo toggle. 243 frontend tests in all (11 new).
- **Checked in the browser:** a rectangle on Layer 1 and a circle on Layer 2 (each with its measurements); hiding Layer 1 (struck through in the list, rectangle gone from the map, circle kept) and showing it again (rectangle back with its area and perimeter); Show only this layer and Show all layers; deleting Layer 2 (circle removed, only Layer 1 left, delete disabled); moving a shape to another layer with the picker (counts 0 and 1); no console errors.
- **Not yet checked by hand:** the layers panel on a phone, the Light theme, moving a shape to a hidden layer, and the layer list surviving a reload (it does not yet: saving arrives in D4, with a local draft for people who are not premium).

## D4 as built (saving, opening, exporting)

- **Account storage (premium).** New table `geointel_drawings` (`backend/supabase/006_geointel_drawings.sql`: id, user id, name, the drawing as JSON, shape and layer counts, created and updated times) behind row level security with no policies, so only the backend's service-role key reaches it, always scoped to the verified user. Routes under `/api/me/drawings` (list, create, open, rename or replace, delete) with `@require_premium`, in the same pattern as saved events. Limits: 50 drawings per user, 1 MB each, 500 shapes, 20,000 points, 20 layers; a body over the limit is refused with 413 before it is read.
- **Nothing the browser sends is stored as it came.** `services/drawings.py` rebuilds the drawing from allowed parts only: the shape kinds the tool draws, checked coordinates (finite numbers, real latitudes, longitudes within the flat map's range), the palette colours and the width, fill and pattern steps, a name and note with control characters removed and a length cap, and layers cleaned and de-duplicated; a shape on an unknown layer moves to the first one. Booleans and lists are not taken for numbers or strings. Text is only ever drawn as text.
- **Panel** (the disk button on the tool strip): the drawing's name and whether it is saved ("Not saved to your account", "Saved", "Unsaved changes"), **Save to account** (or **Save** once it has been saved), **New drawing**, **Export GeoJSON**, **Import**, and, for premium users, the list of saved drawings (shape and layer counts, date) with **Open** and a two-step **Delete**. Replacing a drawing that has unsaved changes (New, Open, Import) asks first. A saved drawing is renamed by changing the name field and pressing Save.
- **Free users** can draw and measure as before and use New drawing; Save, Export and Import show the usual premium lock (sign-in lock for visitors); the saved list is hidden. **Export and Import are premium** (a file is a copy to keep), as decided.
- **Draft in this browser, for everyone.** The drawing in progress (shapes, layers, name) is saved to local storage a moment after each change and restored the next time Draw is opened, so a refresh or a closed tab loses nothing. It is capped at the save size and removed when the drawing is empty.
- **GeoJSON.** Export is a standard FeatureCollection with the layers in a `geointel` member (ignored by other tools, read back by this one) and each shape's style, name and layer in its properties. Import reads this tool's files and any plain GeoJSON: points, lines and polygons become shapes (names from `name` or `title`); multi-part shapes and other kinds are left out and counted in the message.
- **Pure and tested.** Backend: 68 new tests (cleaning and rejection of every field, limits, scoping so users cannot reach each other's drawings, premium and sign-in gates, the switch that opens premium still needing a sign-in, malformed ids never reaching a query, storage down and unconfigured). Frontend: file building and reading (own format, foreign GeoJSON, skipped shapes, limits), the draft (round trip, corrupt data, blocked storage, size cap). 1,114 backend and 265 frontend tests in all.
- **Found and fixed while checking:** the backend reported an over-size drawing as a format error (its own exception was caught by a broader one); and after an import the browser draft still held the previous drawing, because loading is deliberately not counted as an edit, so opening, importing, starting a new drawing and renaming now update the draft directly.
- **Checked in the browser** against an in-memory stand-in for the API (real sign-in is not possible in the preview; the real routes are covered by the backend tests): save creating a drawing and the list refreshing; New clearing the map; Open restoring the name, layers and shapes; Export producing `gulf-plan.geojson`; Import of a plain GeoJSON file (2 shapes drawn, 1 multi-part shape left out, name from the file); the unsaved-changes prompt; the draft restoring after a reload; and the free-user view with the three locks. No console errors.
- **Not yet checked by hand:** against the real backend and a real premium sign-in (needs the SQL file run, below), the panel on a phone, the Light theme, and a drawing near the size limits.
- **Owner action before this works live:** run `backend/supabase/006_geointel_drawings.sql` in the Supabase SQL editor (safe to run more than once).

## D5 as built (presentation)

- **Presentation mode** (the monitor button on the tool strip): the top bar, mode strip, status bar, both panels, the edge tabs, the tool strip, the time and radar bars and the map's zoom and compass buttons are hidden, and the map fills the page, for a talk or a screen share. The drawing stays, with its text drawn 30 percent larger so it reads from across a room. The map credits stay (the data sources require them). One faint "Exit presentation" button remains, and Escape leaves. Where the browser allows it the page also goes full screen, and leaving full screen by the browser's own Escape leaves presentation mode too.
- **Nothing can be changed while presenting:** clicks on pins, clusters, countries, zones and the weather point forecast are ignored (as while drawing), and the drawing tools are switched off, so a slip cannot open a panel or draw a stray shape in front of an audience. The tool strip, panels and layers come back exactly as they were on exit.
- **Save the view as an image** (the camera button): a PNG of what the map shows, drawing, measurements and pins included, taken the moment the map is drawn so the picture is always the current frame. The map credits are added along the bottom exactly as the map shows them (so satellite, radar or elevation credits appear when those layers are on), and the drawing's name is added along the top when it has been given one. The file is named after the drawing. Weather pins are page elements, not part of the map's own picture, so they are not in the image. **Saving an image is free** (a screenshot is always possible; saving a drawing's data is what is premium).
- **Download fix:** the temporary file link is now released two seconds after the click rather than at once (some browsers are still starting the download), in both the image and the GeoJSON export.
- **Pure and tested** (`imagetext.ts`): the credit text tidy, word wrapping to a width with a stand-in for text measuring (no line wider than the limit, a too-long word kept whole, all words kept in order), and safe image file names. 272 frontend tests in all (7 new).
- **Checked in the browser:** a rectangle saved as a PNG (875 by 749 pixels, 522 KB, `image/png`) and looked at: the map, event pins, the rectangle with its area and perimeter, and the credit line along the bottom; presentation mode (header, panels, tool strip and zoom buttons gone, the canvas filling the whole page, credits and the Exit button kept, larger text), a click on a pin doing nothing, Escape restoring the bars, tool strip and panels; presentation mode on a phone (the Draw button hidden, no sideways scroll); no console errors. Not yet checked by hand: the image in the Light theme and with satellite on, full screen (the preview does not grant it), and the image of a flat map.
- **Print-friendly labels:** the text already has a white outline and dark text so it prints and projects well; the larger size in presentation mode is the only change.

## D6 as built (polish)

- **Flat map and the date line.** The engine stores longitudes from -180 to 180, so a shape drawn across the date line on the flat map comes back with a longitude that jumps (170 then -170). Measuring now treats a run of longitudes as continuous (`unwrapLongitudes`): the area of a shape written either way is the same, a line's label sits on the date line rather than on the far side of the world, and distances were already right. Import wraps a longitude written past 180 (a file that carries on 181, 182...) round to the same place, because the engine refuses anything outside GeoJSON's range; both ways of writing a date-line shape now import.
- **Big drawings.** Hiding or showing a layer, loading a saved drawing and importing a file now each make one call to the engine for all the shapes instead of one per shape (the engine redraws after every call). Importing 500 shapes dropped from about 2,000 ms to about 110 ms; the engine's part of hiding or showing 500 shapes is about 5 to 20 ms (the rest is the browser drawing the map, which is slow in the software-rendered preview and fast on a real graphics card). The map's text is redrawn at most once per frame however many changes arrive, so dragging a shape in a big drawing does not queue work.
- **Imports no longer lose shapes to long decimals.** Files from other tools often carry 12 to 15 decimal places and the engine refuses more than nine; positions are rounded to nine (about a tenth of a millimetre) on the way in. Found by importing 500 generated shapes and seeing some left out.
- **Phones.** The tool strip's buttons were being squeezed to 18 px wide in the scrolling strip; they now keep 44 by 44 and the strip scrolls sideways. The Drawings, Layers (with its shape list), shape and Measuring panels open full width under the strip, scroll when taller than the screen, and the page has no sideways scroll.
- **Light theme.** All the drawing panels open together (Drawings, Layers with the shape panel, Measuring) were audited for text contrast against their real backgrounds: 44 pieces of text, none below 4.5:1.
- **Keyboard and screen readers.**
  - The tool strip is a toolbar: the arrow keys, Home and End move along it (Tab still leaves it). Every tool and button has a name; toggles say whether they are pressed or expanded.
  - **Shape list:** the Layers panel lists the shapes on the active layer ("Point: Depot", "Area: Zone A"); pressing one selects it and opens its panel, so a shape's name, note, colour, layer, duplicate and delete can all be reached without a mouse.
  - **Announcements:** a polite live region says what was just drawn with its main measurement ("Line added: 1,918 mi").
  - **Pointer needed for geometry:** drawing a new shape's outline still needs a pointer (the engine is pointer-based); shapes can be created without one only by importing a file. Say if keyboard drawing (for example, place a point at the map centre and nudge it) should be a later stage.
- **Pure and tested:** the date-line maths and the coordinate rounding and wrapping. 279 frontend tests in all (7 more than D5), 1,114 backend.
- **Checked in the browser:** a 500-shape import, hide and show; arrow keys down the strip; the shape list selecting a shape and opening its panel; the live announcement; the Light theme audit; the phone panels (after the button-size fix); both date-line forms on the flat map; no console errors.
- **Not done:** a real-device pass (touch gestures to draw on a phone, and a screen reader run-through with real speech), and the flat-map picture export. These are worth doing before announcing the tool.

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
