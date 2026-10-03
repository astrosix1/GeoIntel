// Phones and low-core devices get the lighter version of anything GPU-heavy
// (the decorative background, 3D terrain). One definition so they agree.
export function isLiteDevice(): boolean {
  return window.matchMedia('(max-width: 768px)').matches || (navigator.hardwareConcurrency ?? 8) <= 4;
}
