import { useEffect, useRef } from 'react';
import { isLiteDevice } from '../lite';

// Purely decorative solar-system background rendered on a single full-viewport
// 2D canvas, positioned BEHIND the MapLibre globe (see App.tsx DOM order / CSS
// z-index). This is explicitly exempt from the app's no-fabrication rule
// (see the "Solar-system background" bullet in the UI/UX Design section of
// the rewrite plan) — positions, orbits, and object counts are all
// hand-picked for a pleasant ambiance, not real astronomical data.
//
// Kept intentionally cheap: a few dozen static-position stars, a handful of
// faint constellation line-groupings connecting nearby stars, and rare
// shooting-star / UFO sprites spawned on randomized timers. No object
// pooling, no worker threads, no physics.

const STAR_COUNT = 90;
const CONSTELLATION_COUNT = 4;
const CONSTELLATION_MAX_LINK_DIST = 160;

// Shooting star pacing: every 8-20s, matching the old app's own prior
// implementation of this feature (used here as a pacing reference only).
const SHOOTING_STAR_MIN_MS = 8000;
const SHOOTING_STAR_MAX_MS = 20000;

// UFOs are a rare easter-egg flourish, much less frequent than shooting stars.
const UFO_MIN_MS = 45000;
const UFO_MAX_MS = 120000;

interface Star {
  x: number;
  y: number;
  radius: number;
  baseOpacity: number;
  twinkleSpeed: number;
  twinklePhase: number;
}

interface Constellation {
  points: { x: number; y: number }[];
  twinkleSpeed: number;
  twinklePhase: number;
}

interface ShootingStar {
  x: number;
  y: number;
  vx: number;
  vy: number;
  life: number; // 0..1 remaining
  maxLife: number;
  length: number;
}

interface Ufo {
  x: number;
  y: number;
  vx: number;
  vy: number;
  bobPhase: number;
  life: number; // ms remaining before forced despawn
}

function rand(min: number, max: number) {
  return min + Math.random() * (max - min);
}

export default function SolarSystem() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Lite mode for phones / low-core devices: 1x pixel density, ~30fps,
    // and no shooting stars/UFOs. The map is the expensive thing on screen;
    // this decorative layer must not compete with it. Reduced-motion users
    // get one static frame instead of an animation loop.
    const lite = isLiteDevice();
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const maxDpr = lite ? 1 : 2;

    let width = window.innerWidth;
    let height = window.innerHeight;
    let dpr = Math.min(window.devicePixelRatio || 1, maxDpr);

    function resize() {
      width = window.innerWidth;
      height = window.innerHeight;
      dpr = Math.min(window.devicePixelRatio || 1, maxDpr);
      canvas!.width = width * dpr;
      canvas!.height = height * dpr;
      canvas!.style.width = `${width}px`;
      canvas!.style.height = `${height}px`;
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
      // A resize clears the canvas; the static (reduced-motion) frame has no
      // loop to repaint it.
      if (reducedMotion && running) requestAnimationFrame(tick);
    }
    let running = false;
    resize();
    window.addEventListener('resize', resize);

    // --- Starfield: static positions, seeded once on mount ---
    const stars: Star[] = Array.from({ length: STAR_COUNT }, () => ({
      x: rand(0, width),
      y: rand(0, height),
      radius: rand(0.5, 1.8),
      baseOpacity: rand(0.25, 0.9),
      twinkleSpeed: rand(0.0005, 0.002),
      twinklePhase: rand(0, Math.PI * 2),
    }));

    // --- Constellations: faint static lines connecting a few nearby stars ---
    // For each grouping, pick a random anchor star, then greedily chain to its
    // nearest not-yet-used neighbors within CONSTELLATION_MAX_LINK_DIST. Purely
    // decorative - positions come straight from the existing star field.
    const constellations: Constellation[] = [];
    {
      const used = new Set<number>();
      for (let c = 0; c < CONSTELLATION_COUNT && used.size < stars.length; c++) {
        let anchorIdx = -1;
        for (let attempt = 0; attempt < stars.length; attempt++) {
          const idx = Math.floor(rand(0, stars.length));
          if (!used.has(idx)) {
            anchorIdx = idx;
            break;
          }
        }
        if (anchorIdx === -1) break;

        const groupSize = Math.floor(rand(3, 6)); // 3-5 stars per grouping
        const groupIndices = [anchorIdx];
        used.add(anchorIdx);

        while (groupIndices.length < groupSize) {
          const last = stars[groupIndices[groupIndices.length - 1]];
          let bestIdx = -1;
          let bestDist = Infinity;
          for (let i = 0; i < stars.length; i++) {
            if (used.has(i)) continue;
            const d = Math.hypot(stars[i].x - last.x, stars[i].y - last.y);
            if (d < bestDist && d <= CONSTELLATION_MAX_LINK_DIST) {
              bestDist = d;
              bestIdx = i;
            }
          }
          if (bestIdx === -1) break;
          groupIndices.push(bestIdx);
          used.add(bestIdx);
        }

        if (groupIndices.length >= 2) {
          constellations.push({
            points: groupIndices.map((i) => ({ x: stars[i].x, y: stars[i].y })),
            twinkleSpeed: rand(0.00008, 0.00018),
            twinklePhase: rand(0, Math.PI * 2),
          });
        }
      }
    }

    let shootingStar: ShootingStar | null = null;
    let nextShootingStarAt = performance.now() + rand(SHOOTING_STAR_MIN_MS, SHOOTING_STAR_MAX_MS);

    let ufo: Ufo | null = null;
    let nextUfoAt = performance.now() + rand(UFO_MIN_MS, UFO_MAX_MS);

    function spawnShootingStar(now: number) {
      const fromLeft = Math.random() < 0.5;
      const startY = rand(0, height * 0.5);
      const speed = rand(9, 16);
      const angle = rand(0.25, 0.5); // downward diagonal, radians
      shootingStar = {
        x: fromLeft ? -20 : width + 20,
        y: startY,
        vx: (fromLeft ? 1 : -1) * speed * Math.cos(angle),
        vy: speed * Math.sin(angle),
        life: 1,
        maxLife: 1,
        length: rand(60, 120),
      };
      nextShootingStarAt = now + rand(SHOOTING_STAR_MIN_MS, SHOOTING_STAR_MAX_MS);
    }

    function spawnUfo(now: number) {
      const fromLeft = Math.random() < 0.5;
      const y = rand(height * 0.1, height * 0.6);
      const speed = rand(1.2, 2.2);
      ufo = {
        x: fromLeft ? -60 : width + 60,
        y,
        vx: fromLeft ? speed : -speed,
        vy: 0,
        bobPhase: 0,
        life: 20000,
      };
      nextUfoAt = now + rand(UFO_MIN_MS, UFO_MAX_MS);
    }

    function drawStars(now: number) {
      for (const s of stars) {
        const twinkle = 0.5 + 0.5 * Math.sin(now * s.twinkleSpeed + s.twinklePhase);
        const opacity = s.baseOpacity * (0.6 + 0.4 * twinkle);
        ctx!.beginPath();
        ctx!.fillStyle = `rgba(255, 255, 255, ${opacity.toFixed(3)})`;
        ctx!.arc(s.x, s.y, s.radius, 0, Math.PI * 2);
        ctx!.fill();
      }
    }

    function drawConstellations(now: number) {
      for (const c of constellations) {
        const twinkle = 0.5 + 0.5 * Math.sin(now * c.twinkleSpeed + c.twinklePhase);
        const opacity = 0.08 + 0.1 * twinkle;
        ctx!.save();
        ctx!.strokeStyle = `rgba(200, 215, 255, ${opacity.toFixed(3)})`;
        ctx!.lineWidth = 1;
        ctx!.beginPath();
        c.points.forEach((pt, i) => {
          if (i === 0) ctx!.moveTo(pt.x, pt.y);
          else ctx!.lineTo(pt.x, pt.y);
        });
        ctx!.stroke();
        ctx!.restore();
      }
    }

    function drawShootingStar(now: number, dt: number) {
      if (!shootingStar && now >= nextShootingStarAt) {
        spawnShootingStar(now);
      }
      if (!shootingStar) return;
      const s = shootingStar;
      s.x += s.vx * (dt / 16);
      s.y += s.vy * (dt / 16);
      s.life -= dt / 900; // ~0.9s visible lifetime

      if (s.life <= 0 || s.x < -150 || s.x > width + 150 || s.y > height + 150) {
        shootingStar = null;
        return;
      }

      const tailX = s.x - (s.vx / Math.hypot(s.vx, s.vy)) * s.length;
      const tailY = s.y - (s.vy / Math.hypot(s.vx, s.vy)) * s.length;
      const grad = ctx!.createLinearGradient(s.x, s.y, tailX, tailY);
      const alpha = Math.max(0, Math.min(1, s.life));
      grad.addColorStop(0, `rgba(255, 255, 255, ${alpha})`);
      grad.addColorStop(1, 'rgba(255, 255, 255, 0)');
      ctx!.save();
      ctx!.strokeStyle = grad;
      ctx!.lineWidth = 2;
      ctx!.lineCap = 'round';
      ctx!.beginPath();
      ctx!.moveTo(s.x, s.y);
      ctx!.lineTo(tailX, tailY);
      ctx!.stroke();
      // bright head
      ctx!.beginPath();
      ctx!.fillStyle = `rgba(255, 255, 255, ${alpha})`;
      ctx!.arc(s.x, s.y, 1.6, 0, Math.PI * 2);
      ctx!.fill();
      ctx!.restore();
    }

    function drawUfo(now: number, dt: number) {
      if (!ufo && now >= nextUfoAt) {
        spawnUfo(now);
      }
      if (!ufo) return;
      const u = ufo;
      u.bobPhase += dt * 0.004;
      u.x += u.vx * (dt / 16);
      u.y += Math.sin(u.bobPhase) * 0.4;
      u.life -= dt;

      if (u.life <= 0 || u.x < -100 || u.x > width + 100) {
        ufo = null;
        return;
      }

      ctx!.save();
      ctx!.translate(u.x, u.y);
      // saucer body
      ctx!.beginPath();
      ctx!.fillStyle = 'rgba(150, 200, 190, 0.85)';
      ctx!.ellipse(0, 0, 22, 7, 0, 0, Math.PI * 2);
      ctx!.fill();
      // dome
      ctx!.beginPath();
      ctx!.fillStyle = 'rgba(210, 240, 235, 0.9)';
      ctx!.ellipse(0, -6, 9, 8, 0, Math.PI, 0);
      ctx!.fill();
      // lights
      for (let i = -1; i <= 1; i++) {
        const flicker = 0.5 + 0.5 * Math.sin(now * 0.01 + i);
        ctx!.beginPath();
        ctx!.fillStyle = `rgba(255, 230, 140, ${0.4 + 0.6 * flicker})`;
        ctx!.arc(i * 9, 3, 1.8, 0, Math.PI * 2);
        ctx!.fill();
      }
      ctx!.restore();
    }

    let animationFrame: number;
    let lastTime = performance.now();

    function tick(now: number) {
      if (!running) return;
      if (lite && !reducedMotion && now - lastTime < 33) {
        animationFrame = requestAnimationFrame(tick);
        return;
      }
      const dt = Math.min(now - lastTime, 50); // clamp to avoid big jumps on tab-away
      lastTime = now;

      // The deep-space backdrop gradient is CSS on the canvas element (below),
      // not redrawn here — refilling the whole screen with a gradient every
      // frame was the bulk of this layer's cost.
      ctx!.clearRect(0, 0, width, height);

      drawStars(now);
      drawConstellations(now);
      if (!lite) {
        drawShootingStar(now, dt);
        drawUfo(now, dt);
      }

      if (!reducedMotion) animationFrame = requestAnimationFrame(tick);
    }

    function start() {
      running = true;
      lastTime = performance.now();
      animationFrame = requestAnimationFrame(tick);
    }
    function stop() {
      running = false;
      cancelAnimationFrame(animationFrame);
    }
    // Don't animate a hidden tab.
    function onVisibilityChange() {
      if (document.hidden) stop();
      else start();
    }
    document.addEventListener('visibilitychange', onVisibilityChange);
    if (!document.hidden) start();

    return () => {
      stop();
      document.removeEventListener('visibilitychange', onVisibilityChange);
      window.removeEventListener('resize', resize);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: 'fixed',
        inset: 0,
        width: '100vw',
        height: '100vh',
        zIndex: 0,
        pointerEvents: 'none',
        display: 'block',
        // deep-space backdrop, kept dark to read well behind translucent UI
        background: 'radial-gradient(circle max(80vw, 80vh) at 50% 40%, #0b0f1e, #03040a)',
      }}
      aria-hidden="true"
    />
  );
}
