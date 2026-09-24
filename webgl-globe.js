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
};

function init(canvasEl) {
  state.renderer = new THREE.WebGLRenderer({ canvas: canvasEl, antialias: true, alpha: true });
  state.renderer.setClearColor(0x07090f, 1);

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

  // Directional light stands in for the sun — positioned from the real
  // subsolar point (see setSunDirection). A soft ambient keeps the night
  // side dimly visible rather than pure black, matching how the old CPU
  // night-mask capped its darkening at 0.55 alpha rather than 1.0.
  // Intensities are much larger than pre-r155 Three.js code would use —
  // this Three.js version's lights use physically-based units, where
  // "1" reads as near-black; these values were tuned empirically against
  // the actual rendered output, not guessed.
  state.light = new THREE.DirectionalLight(0xffffff, 18);
  state.scene.add(state.light);
  state.ambient = new THREE.AmbientLight(0x33455a, 6);
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

function resize(cssW, cssH, dpr) {
  if (!state.ready) return;
  state.renderer.setPixelRatio(dpr);
  state.renderer.setSize(cssW, cssH, false);
}

function render() {
  if (!state.ready) return;
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
  resize,
  render,
  get ready() { return state.ready; },
};
window.dispatchEvent(new Event('globegl-ready'));
