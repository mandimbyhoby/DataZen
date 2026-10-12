/**
 * Animation continue des graphiques DataZen.
 *
 * Chart.js n'anime que l'apparition des données (une seule fois). Pour que les
 * graphiques « bougent » en permanence, un unique `requestAnimationFrame`
 * pilote tous les canvas de la page à cadence plafonnée : à chaque image on
 * avance la phase du mouvement puis on redessine le graphique (`chart.draw()`).
 *
 * Les graphiques hors écran sont ignorés (IntersectionObserver) et le réglage
 * système « réduire les animations » désactive complètement le mouvement, ce
 * que la feuille de style ne peut pas faire pour du canvas.
 *
 * Deux effets sont fournis :
 *  - `sweepMotion()` : un reflet de lumière qui balaie les barres ;
 *  - `pulseMotion()` : des anneaux qui s'échappent de l'anneau du score.
 */

/** Durée de l'animation d'entrée d'un graphique, en millisecondes. */
export const ENTRY_DURATION = 900;

/** Décalage entre deux éléments à l'apparition, en millisecondes. */
export const ENTRY_STAGGER = 45;

/** Nombre d'éléments décalés avant plafonnement du décalage. */
export const ENTRY_STAGGER_MAX = 14;

/**
 * Cadence de rafraîchissement du mouvement.
 *
 * Volontairement basse : chaque image redessine entièrement le canvas, donc
 * 25 images/s suffisent à rendre le reflet fluide sans saturer le processeur.
 */
const FRAME_MS = 1000 / 25;

const REDUCED_MOTION = "(prefers-reduced-motion: reduce)";

const registry = new Set();

/** Entrée de mouvement associée à un canvas (sans fuite mémoire). */
const visibility = new WeakMap();

let frameId = null;
let lastPaint = 0;
let observer;

/** Le visiteur demande-t-il à limiter les animations ? */
export function prefersReducedMotion() {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return false;
  }
  return window.matchMedia(REDUCED_MOTION).matches;
}

/** Décalage avant le démarrage du mouvement, une fois l'entrée terminée. */
export function startDelay(chart, extra = 0) {
  const count = chart?.data?.datasets?.[0]?.data?.length || 0;
  const stagger = Math.min(count, ENTRY_STAGGER_MAX) * ENTRY_STAGGER;
  return ENTRY_DURATION + stagger + extra + 120;
}

function ensureObserver() {
  if (observer !== undefined) return observer;
  if (typeof IntersectionObserver === "undefined") {
    observer = null;
    return observer;
  }
  observer = new IntersectionObserver(
    (records) => {
      records.forEach((record) => {
        const entry = visibility.get(record.target);
        if (entry) entry.visible = record.isIntersecting;
      });
    },
    { rootMargin: "120px" },
  );
  return observer;
}

function schedule() {
  if (frameId !== null || registry.size === 0) return;
  frameId = requestAnimationFrame(tick);
}

function tick(now) {
  frameId = null;
  if (registry.size === 0) return;
  if (now - lastPaint >= FRAME_MS) {
    lastPaint = now;
    registry.forEach((entry) => {
      if (entry.visible && now >= entry.startAt) entry.paint(now);
    });
  }
  schedule();
}

/**
 * Fabrique un plugin Chart.js qui entretient un mouvement perpétuel.
 *
 * ``paint(chart, phase)`` est appelé avant chaque rendu avec une phase
 * normalisée dans ``[0, 1[`` qui boucle indéfiniment.
 */
function createLiveMotion(id, paint, { period = 4600, delay = 0 } = {}) {
  return {
    id,

    afterInit(chart) {
      if (prefersReducedMotion()) return;
      const canvas = chart.canvas;
      if (!canvas) return;

      const entry = {
        visible: true,
        live: false,
        phase: 0,
        startAt: performance.now() + startDelay(chart, delay),
        paint(now) {
          entry.phase = ((now - entry.startAt) % period) / period;
          entry.live = true;
          chart.draw();
        },
      };

      chart.$dzMotionEntry = entry;
      visibility.set(canvas, entry);
      registry.add(entry);

      const io = ensureObserver();
      if (io) {
        io.observe(canvas);
      } else {
        const rect = canvas.getBoundingClientRect();
        entry.visible = rect.bottom > -120 && rect.top < window.innerHeight + 120;
      }

      schedule();
    },

    // Dessiné après les données : le reflet doit passer par-dessus les barres
    // (et non derrière la piste grise du `trackPlugin`).
    afterDatasetsDraw(chart) {
      const entry = chart.$dzMotionEntry;
      if (!entry || !entry.live) return;
      paint(chart, entry.phase);
    },

    afterDestroy(chart) {
      const entry = chart.$dzMotionEntry;
      if (!entry) return;
      registry.delete(entry);
      visibility.delete(entry.canvas || chart.canvas);
      if (observer) observer.unobserve((entry.canvas || chart.canvas));
      delete chart.$dzMotionEntry;
    },
  };
}

/** Boîte englobante d'une barre, dans le repère du canvas. */
function barBounds(bar) {
  const { x, y, base, width, height } = bar.getProps(
    ["x", "y", "base", "width", "height"],
    true,
  );
  if (![x, y, base, width, height].every(Number.isFinite)) return null;

  if (bar.horizontal) {
    const half = height / 2;
    return {
      left: Math.min(x, base),
      right: Math.max(x, base),
      top: Math.min(y - half, y + half),
      bottom: Math.max(y - half, y + half),
    };
  }
  const half = width / 2;
  return {
    left: Math.min(x - half, x + half),
    right: Math.max(x - half, x + half),
    top: Math.min(y, base),
    bottom: Math.max(y, base),
  };
}

function clipRounded(ctx, bounds, radius) {
  const width = bounds.right - bounds.left;
  const height = bounds.bottom - bounds.top;
  ctx.beginPath();
  if (ctx.roundRect) {
    const r = Math.max(0, Math.min(radius, width / 2, height / 2));
    ctx.roundRect(bounds.left, bounds.top, width, height, r);
  } else {
    ctx.rect(bounds.left, bounds.top, width, height);
  }
  ctx.clip();
}

/** Longueur (ou largeur) du reflet, en pixels. */
function sweepBand(span) {
  return Math.max(28, span * 0.34);
}

/** Décalage du reflet d'une barre à l'autre, pour créer une onde. */
const SWEEP_WAVE = 0.14;

/**
 * Reflet de lumière qui parcourt chaque barre sur toute sa longueur.
 *
 * Le reflet voyage dans la barre elle-même (et non sur toute la surface du
 * graphique) : chaque barre scintille donc en permanence, même les plus
 * courtes, et un léger décalage par index donne une onde qui traverse la série.
 */
function sweepPaint(chart, phase) {
  const { ctx } = chart;
  if (!ctx) return;

  const bars = chart.getDatasetMeta(0)?.data;
  if (!bars?.length) return;

  const horizontal = Boolean(bars[0].horizontal);

  ctx.save();
  bars.forEach((bar, index) => {
    const bounds = barBounds(bar);
    if (!bounds) return;

    const span = horizontal
      ? bounds.right - bounds.left
      : bounds.bottom - bounds.top;
    if (span <= 2) return;

    const band = sweepBand(span);
    // Aller-retour sinusoïdal : aucun saut visible en fin de cycle.
    const wave = (phase + index * SWEEP_WAVE) % 1;
    const travel = 0.5 - 0.5 * Math.cos(wave * 2 * Math.PI);
    const head = -band + travel * (span + band * 2);

    ctx.save();
    clipRounded(ctx, bounds, 8);

    let gradient;
    if (horizontal) {
      const start = bounds.left + head;
      gradient = ctx.createLinearGradient(start, 0, start + band, 0);
    } else {
      const start = bounds.bottom - head;
      gradient = ctx.createLinearGradient(0, start, 0, start - band);
    }
    gradient.addColorStop(0, "rgba(255, 255, 255, 0)");
    gradient.addColorStop(0.5, "rgba(255, 255, 255, 0.42)");
    gradient.addColorStop(1, "rgba(255, 255, 255, 0)");

    ctx.fillStyle = gradient;
    ctx.fillRect(
      bounds.left,
      bounds.top,
      bounds.right - bounds.left,
      bounds.bottom - bounds.top,
    );
    ctx.restore();
  });
  ctx.restore();
}

/**
 * Anneaux qui s'échappent de l'anneau du score puis s'estompent, comme une
 * onde de mesure en direct.
 */
function makePulsePaint(color) {
  return (chart, phase) => {
    const { ctx } = chart;
    const arc = chart.getDatasetMeta(0)?.data?.[0];
    if (!ctx || !arc) return;

    const { x, y, outerRadius, startAngle, endAngle } = arc.getProps(
      ["x", "y", "outerRadius", "startAngle", "endAngle"],
      true,
    );
    if (![x, y, outerRadius, startAngle, endAngle].every(Number.isFinite)) return;
    if (outerRadius <= 0) return;

    const spread = Math.max(16, outerRadius * 0.24);

    ctx.save();
    ctx.lineCap = "round";
    [0, 0.5].forEach((offset) => {
      const progress = (phase + offset) % 1;
      const alpha = Math.sin(progress * Math.PI) * 0.45;
      if (alpha <= 0.01) return;
      ctx.beginPath();
      ctx.globalAlpha = alpha;
      ctx.lineWidth = 2.6;
      ctx.strokeStyle = color;
      ctx.arc(x, y, outerRadius + progress * spread, startAngle, endAngle);
      ctx.stroke();
    });
    ctx.restore();
  };
}

/** Mouvement « reflet balayant » pour les graphiques en barres. */
export function sweepMotion(options) {
  return createLiveMotion("dzSweep", sweepPaint, { period: 4200, ...options });
}

/** Mouvement « onde » pour la jauge de score. */
export function pulseMotion(color, options) {
  return createLiveMotion("dzPulse", makePulsePaint(color), {
    period: 2600,
    ...options,
  });
}
