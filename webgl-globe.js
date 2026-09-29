// GPU-rendered globe sphere (ocean + land + borders + terrain relief +
// real-time day/night lighting), replacing what used to be a Canvas2D
// re-projection of tens of thousands of coastline points every frame.
// app.js keeps owning ALL interaction (drag/zoom/inertia/idle-rotation)
// and ALL other rendering (pins, routes, arcs, tooltips, hit-testing) on
// its own transparent #canvas layered on top — this module only ever
// draws the sphere onto #glCanvas beneath it. See the plan file for the
// full architecture and the "why" behind the split.
//
// Exposed as window.GlobeGL. app.js is a classic (non-module) script and
// may run before this module has finished loading/evaluating — this
// module is loaded via <script type="module">, which defers execution
// until after the document has parsed, which can be AFTER a classic
// script earlier in <body> has already run. So: this module fires a
// 'globegl-ready' event on window once window.GlobeGL is assigned, and
// app.js's own startup waits for either "already there" or that event —
// see initWebGLGlobe() in app.js.
import * as THREE from 'three';

// ── Axis convention ──────────────────────────────────────────────────────
// This app's world-space lat/lon → vector convention (see latLonToVec in
// app.js) is Z-polar: north pole at world +Z, lon=0/lat=0 at world +X.
// Three.js's SphereGeometry defaults to Y-polar (north pole at local +Y)
// with its own (phi, theta) UV parametrization. Rather than rotate the
// GEOMETRY to match (which moves vertex positions but does NOT move the
// UV attribute along with them, since UVs are assigned at construction
// time from the ORIGINAL phi/theta — tried first, produced a visibly
// warped texture), the fix is a fixed relationship between Three's local
// vertex space and this app's rotation-aware view space.
//
// The overlay's ground truth (app.js's latLonToViewVec, used by every
// pin/route) is, algebraically, view = Rx(rotX) · P · Rz(rotY) · B, where
// B = latLonToVec(lat,lon) and P is the fixed axis-cycling permutation
// P(x,y,z) = (y,z,x) — NOT simply Rx(rotX) · Rz(rotY) · B. A first version
// of this module used mesh_rotation = Rx(rotX) · Rz(rotY) · Ry(-π/2),
// treating Ry(-π/2) as a constant "axis correction" tacked on after
// Rz(rotY). That only agrees with the overlay when rotY=0: P and Rz(rotY)
// do not commute, so the mesh visibly diverged from pins/routes (and
// wobbled off the polar axis) as soon as the globe was spun horizontally
// — caught by user-reported bugs, not the original marker test, which
// only checked rotY ∈ {0°,90°,180°} at rotX=0 and happened not to expose
// the non-commuting case clearly enough.
//
// The fix: conjugating Rz(θ) by P yields Ry(θ) (P maps the z-axis onto
// the y-axis, and conjugating a rotation by another rotation preserves
// the angle while carrying the axis along) — i.e. P · Rz(rotY) =
// Ry(rotY) · P. Substituting that into the overlay's ground truth and
// solving for the matrix that must be applied to Three's local vertex
// (which is a fixed, rotY-independent linear image of B — see
// setRotation's own comment) collapses the whole thing to:
//     mesh_rotation = Rx(rotX) · Ry(rotY − π/2)
// No separate axis-correction matrix needed at runtime — the old -π/2
// correction and the rotY spin are now one combined Y-axis rotation.
// Verified against latLonToViewVec at 3 independent (lat,lon,rotX,rotY)
// points, including nonzero rotY, where the old formula diverged.
//
// With this in place, the texture bake still needs no longitude offset:
// standard equirect (lon+180)/360, (90-lat)/180 lines up correctly.
// TEXTURE_LON_OFFSET_DEG is kept as a documented escape hatch in case of
// a future flip; expected value is 0.
const TEXTURE_LON_OFFSET_DEG = 0;

const state = {
  renderer: null,
  scene: null,
  camera: null,
  sphereMesh: null,
  light: null,
  ambient: null,
  ready: false,
  // Scratch objects reused every frame instead of allocated fresh, to
  // avoid per-frame GC churn in what's now the hot render path.
  _mX: new THREE.Matrix4(),
  _mY: new THREE.Matrix4(),
  _mCombined: new THREE.Matrix4(),
  // Detail-patch crossfade (see updateDetailPatchFade) — target is what
  // opacity is animating toward; visible only flips to false once a
  // fade-to-0 actually finishes, so the fade-out is visible instead of
  // the patch vanishing the instant hideDetailPatch() is called.
  detailPatchOpacity: 0,
  detailPatchTargetOpacity: 0,
};

function init(canvasEl) {
  state.renderer = new THREE.WebGLRenderer({ canvas: canvasEl, antialias: true, alpha: true });
  // Alpha 0 (was 1): a WebGL clear paints the ENTIRE canvas viewport, not
  // just the sphere's silhouette — at alpha:1 that made #glCanvas a fully
  // opaque rectangle every frame, hiding #starsCanvas (z-index:-1, directly
  // behind it) completely, everywhere, not just around the globe's edge.
  state.renderer.setClearColor(0x07090f, 0);

  state.scene = new THREE.Scene();

  // Orthographic camera, frustum recomputed every frame in setFrustum() to
  // exactly reproduce project()'s sx = CX() + r*x / sy = CY() - r*y screen
  // mapping (derived, not approximated — see the plan file). Placeholder
  // bounds here; real values arrive before the first render.
  state.camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 10);
  state.camera.position.set(0, 0, 3);
  state.camera.lookAt(0, 0, 0);
  state.scene.add(state.camera);

  const geometry = new THREE.SphereGeometry(1, 128, 128);
  // color stays white: material.color multiplies with material.map, and the
  // baked equirect texture (bakeEquirectTexture in app.js) already contains
  // full ocean/land/terrain color — a tinted base here would multiply those
  // colors down (this previously crushed land's green channel under a blue
  // tint, making the whole sphere read as ocean regardless of texture).
  const material = new THREE.MeshLambertMaterial({ color: 0xffffff });
  state.sphereMesh = new THREE.Mesh(geometry, material);
  state.scene.add(state.sphereMesh);

  // Detail patch: a small extra piece of sphere surface, shown only at
  // high zoom and textured with real OpenStreetMap tiles (see
  // updateDetailPatch/setDetailPatchTexture below) instead of the single
  // low-res baked equirect texture the rest of the globe uses — see the
  // plan file for why a full tile-quadtree engine isn't needed: only the
  // patch of sphere actually facing the camera ever needs real detail.
  // Added as a CHILD of sphereMesh (not state.scene) specifically so it
  // inherits sphereMesh's rotation quaternion automatically — no separate
  // rotation math needed to keep it aligned as the globe spins. Radius is
  // fractionally larger (1.002 vs 1) to avoid z-fighting with the parent
  // sphere's own surface. Starts as a degenerate/invisible placeholder;
  // real geometry arrives via the first updateDetailPatch() call.
  //
  // MeshBasicMaterial (unlit), NOT MeshLambertMaterial like the main
  // sphere — confirmed by report: the patch looked washed out/overexposed
  // specifically on the sun-facing side and fine on the night side. The
  // directional "sun" light's intensity (26, see below) was tuned against
  // the main sphere's own baked texture, which is fine since that texture
  // IS meant to be lit; real OSM tile imagery is already a finished,
  // fully-lit image and was getting blown out by having that same strong
  // light multiplied on top a second time. Unlit means the patch always
  // shows the tiles' true colors regardless of which side of the globe
  // it's currently on.
  const patchGeometry = new THREE.SphereGeometry(1.002, 2, 2, 0, 0.001, 0, 0.001);
  // transparent + opacity:0 — the patch crossfades in/out (see
  // updateDetailPatchFade) rather than popping instantly.
  const patchMaterial = new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0 });
  state.detailPatchMesh = new THREE.Mesh(patchGeometry, patchMaterial);
  state.detailPatchMesh.visible = false;
  state.sphereMesh.add(state.detailPatchMesh);

  // Directional light stands in for the sun — positioned from the real
  // subsolar point (see setSunDirection). A soft ambient keeps the night
  // side dimly visible rather than pure black, matching how the old CPU
  // night-mask capped its darkening at 0.55 alpha rather than 1.0.
  // Intensities are much larger than pre-r155 Three.js code would use —
  // this Three.js version's lights use physically-based units, where
  // "1" reads as near-black; these values were tuned empirically against
  // the actual rendered output, not guessed. Raised again (18->26, 6->11)
  // after user feedback that the night side read as too dark — raising
  // BOTH rather than just ambient keeps the day/night contrast strong
  // (a brighter sun alongside a brighter night) instead of flattening the
  // whole sphere into one uniform brightness.
  state.light = new THREE.DirectionalLight(0xffffff, 26);
  state.scene.add(state.light);
  state.ambient = new THREE.AmbientLight(0x33455a, 11);
  state.scene.add(state.ambient);

  state.ready = true;
}

// Recompute the orthographic frustum from the same inputs project() uses
// (see the plan file for the derivation): halfW/halfH in CSS pixels, r in
// CSS pixels (R() in app.js). Cheap — fine to call every frame.
function setFrustum(halfW, halfH, r) {
  if (!state.ready) return;
  const cam = state.camera;
  cam.left = -halfW / r;
  cam.right = halfW / r;
  cam.top = halfH / r;
  cam.bottom = -halfH / r;
  cam.updateProjectionMatrix();
}

// Rotate the sphere to mesh_rotation = Rx(rotX) * Ry(rotY - π/2), derived
// to exactly match latLonToViewVec's view = Rx(rotX) * P * Rz(rotY) *
// world composition for every (lat,lon,rotX,rotY) — see the big comment
// above TEXTURE_LON_OFFSET_DEG for the derivation and why the previous
// Rx(rotX)*Rz(rotY)*Ry(-π/2) version only agreed with the overlay at
// rotY=0. Built from explicit axis-angle matrices, not Three.js's Euler
// `.rotation.x/.y` properties, to sidestep any Euler-order ambiguity.
function setRotation(rotX, rotY) {
  if (!state.ready) return;
  state._mX.makeRotationX(rotX);
  state._mY.makeRotationY(rotY - Math.PI / 2);
  state._mCombined.multiplyMatrices(state._mX, state._mY);
  state.sphereMesh.quaternion.setFromRotationMatrix(state._mCombined);
}

// zoom only affects R() or the frustum today, so it doesn't need any
// separate scene-graph change — kept as a distinct function anyway so
// app.js's call sites read the same as the other setters and in case a
// future need (e.g. LOD swapping by zoom level) wants a hook here.
function setZoom(_zoom) {
  // Intentionally a no-op today — zoom is fully expressed through
  // setFrustum()'s `r` input. See comment above.
}

// (x,y,z) is a pre-rotated view-space direction, computed by app.js via
// latLonToViewVec(lat,lon) — the same rotation-aware function used for
// pins/routes — so the light rotates in lockstep with the mesh and the
// overlay instead of staying fixed in world space while the mesh spins
// under it (this module doesn't duplicate the lat/lon rotation math
// itself, so it can't drift out of sync with setRotation's own formula).
function setSunDirection(x, y, z) {
  if (!state.ready) return;
  state.light.position.set(x, y, z);
}

// Applies a freshly-baked equirectangular canvas (see bakeEquirectTexture
// in app.js) as the sphere's texture. Disposes the previous texture to
// avoid leaking GPU memory across repeated calls (heatmap toggle,
// highlighted-country change, low-res→high-res upgrade).
function regenerateTexture(sourceCanvas) {
  if (!state.ready) return;
  const oldTex = state.sphereMesh.material.map;
  const tex = new THREE.CanvasTexture(sourceCanvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.needsUpdate = true;
  state.sphereMesh.material.map = tex;
  state.sphereMesh.material.needsUpdate = true;
  if (oldTex) oldTex.dispose();
}

// Rebuilds the detail patch's geometry to the exact lon/lat box the
// caller (app.js) just composited a tile texture for — explicit bounds
// rather than a symmetric center+radius, since a real tile grid's edges
// rarely land symmetrically around whatever point was originally asked
// for; passing the box the texture actually covers keeps the two exactly
// aligned instead of stretching one to fit the other.
//
// phi/theta here follow this sphere's existing equirect convention — the
// same one bakeEquirectTexture()/flatProjectForBake() already use, and
// the same one the parent sphere's own UVs were built with (see the
// axis-convention comment atop this file): phi = radians(lon + 180),
// theta = radians(90 - lat), theta increasing southward. Because this
// mesh is a CHILD of sphereMesh (see init()), it automatically inherits
// the parent's rotation — the caller never needs any rotation math of
// its own, just the lon/lat box.
function updateDetailPatch(westLonDeg, eastLonDeg, southLatDeg, northLatDeg, segments) {
  if (!state.ready) return;
  const phiStart = (westLonDeg + 180) * Math.PI / 180;
  const phiEnd = (eastLonDeg + 180) * Math.PI / 180;
  const thetaStart = Math.max(0, (90 - northLatDeg) * Math.PI / 180); // north = smaller theta
  const thetaEnd = Math.min(Math.PI, (90 - southLatDeg) * Math.PI / 180);
  const seg = segments || 48;

  const oldGeom = state.detailPatchMesh.geometry;
  state.detailPatchMesh.geometry = new THREE.SphereGeometry(
    1.002, seg, seg,
    phiStart, phiEnd - phiStart,
    thetaStart, thetaEnd - thetaStart
  );
  oldGeom.dispose();
  // visible is managed by updateDetailPatchFade() based on opacity, not
  // set directly here — setDetailPatchTexture() (always called right after
  // this) sets the fade target to 1, which turns visibility on once the
  // fade actually starts producing a nonzero opacity.
}

function hideDetailPatch() {
  if (!state.ready) return;
  // Don't flip visible=false here — updateDetailPatchFade() does that once
  // the fade-to-0 actually completes, so zooming back out fades the patch
  // away instead of cutting it instantly.
  state.detailPatchTargetOpacity = 0;
}

// Same swap-and-dispose pattern as regenerateTexture(), targeting the
// detail patch's own material instead of the main sphere's.
function setDetailPatchTexture(sourceCanvas) {
  if (!state.ready) return;
  const oldTex = state.detailPatchMesh.material.map;
  const tex = new THREE.CanvasTexture(sourceCanvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.needsUpdate = true;
  state.detailPatchMesh.material.map = tex;
  state.detailPatchMesh.material.needsUpdate = true;
  if (oldTex) oldTex.dispose();
  // Real content is ready — start (or continue) fading toward fully
  // visible. A refresh while already shown (e.g. rotating to a new tile
  // area) just keeps it at/heading to 1, no visible flicker.
  state.detailPatchTargetOpacity = 1;
}

const DETAIL_PATCH_FADE_MS = 800;
// Called once per frame from render() (cheap — a couple of arithmetic ops
// when nothing's transitioning). Steps material.opacity toward whatever
// setDetailPatchTexture()/hideDetailPatch() last set as the target, and
// only turns the mesh fully off once a fade-to-0 has actually reached 0 —
// see hideDetailPatch()'s comment for why that ordering matters.
function updateDetailPatchFade() {
  const cur = state.detailPatchOpacity, target = state.detailPatchTargetOpacity;
  if (cur === target) return;
  const step = 16 / DETAIL_PATCH_FADE_MS; // ~1 frame at 60fps, framerate-independent enough for an 800ms fade
  state.detailPatchOpacity = target > cur
    ? Math.min(target, cur + step)
    : Math.max(target, cur - step);
  state.detailPatchMesh.material.opacity = state.detailPatchOpacity;
  if (state.detailPatchOpacity === 0 && target === 0) {
    state.detailPatchMesh.visible = false;
  } else if (state.detailPatchOpacity > 0) {
    state.detailPatchMesh.visible = true;
  }
}

function resize(cssW, cssH, dpr) {
  if (!state.ready) return;
  state.renderer.setPixelRatio(dpr);
  state.renderer.setSize(cssW, cssH, false);
}

function render() {
  if (!state.ready) return;
  updateDetailPatchFade();
  state.renderer.render(state.scene, state.camera);
}

window.GlobeGL = {
  TEXTURE_LON_OFFSET_DEG,
  init,
  setFrustum,
  setRotation,
  setZoom,
  setSunDirection,
  regenerateTexture,
  updateDetailPatch,
  hideDetailPatch,
  setDetailPatchTexture,
  resize,
  render,
  get ready() { return state.ready; },
};
window.dispatchEvent(new Event('globegl-ready'));
