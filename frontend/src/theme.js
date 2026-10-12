/**
 * Palette et thème des graphiques DataZen.
 *
 * Les couleurs sont lues depuis les variables CSS de l'application
 * (`--dz-*`) afin que les graphiques suivent automatiquement le thème clair
 * ou sombre, sans duplication de valeurs.
 */

import { ENTRY_DURATION, ENTRY_STAGGER, ENTRY_STAGGER_MAX } from "./motion.js";

export const BRAND = [
  "#4f46e5",
  "#7c3aed",
  "#06b6d4",
  "#f59e0b",
  "#ef4444",
  "#10b981",
  "#8b5cf6",
  "#ec4899",
];

export const COLOR_OK = "#10b981";
export const COLOR_WARN = "#f59e0b";
export const COLOR_BAD = "#ef4444";

/** Couleur sémantique associée à un score de qualité (sur 100). */
export function scoreColor(total) {
  if (total >= 90) return COLOR_OK;
  if (total >= 75) return "#06b6d4";
  if (total >= 50) return COLOR_WARN;
  return COLOR_BAD;
}

/** Couleur sémantique associée à un taux de complétude (en %). */
export function completenessColor(value) {
  if (value >= 95) return COLOR_OK;
  if (value >= 80) return COLOR_WARN;
  return COLOR_BAD;
}

function cssVar(name, fallback) {
  if (typeof window === "undefined") return fallback;
  const value = getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
  return value || fallback;
}

/** Lit le thème courant (couleurs de texte, grille, surfaces). */
export function readTheme() {
  return {
    text: cssVar("--dz-text", "#0f172a"),
    muted: cssVar("--dz-text-muted", "#64748b"),
    grid: cssVar("--dz-border", "rgba(15, 23, 42, 0.08)"),
    surface: cssVar("--dz-surface", "#ffffff"),
    border: cssVar("--dz-border-strong", "rgba(15, 23, 42, 0.14)"),
  };
}

/**
 * Animation d'entrée commune à tous les graphiques.
 *
 * Les éléments apparaissent en cascade (`delay`) et les barres poussent depuis
 * leur base (`animations.bar` pilote la propriété `base`, qui n'est pas dans le
 * registre animable par défaut de Chart.js).
 */
export function entryAnimation() {
  return {
    animation: {
      duration: ENTRY_DURATION,
      easing: "easeOutQuart",
      delay: (ctx) =>
        Math.min(ctx.dataIndex || 0, ENTRY_STAGGER_MAX) * ENTRY_STAGGER,
    },
    animations: {
      bar: {
        duration: ENTRY_DURATION,
        easing: "easeOutQuart",
        properties: ["base", "x", "y"],
      },
    },
  };
}

/**
 * Options Chart.js communes : grille discrète, pas de cadre superflu,
 * infobulles arrondies et police héritée de l'application.
 */
export function baseOptions(theme, overrides = {}) {
  const { plugins = {}, scales = {}, ...rest } = overrides;
  return {
    responsive: true,
    maintainAspectRatio: false,
    // Rendu net sur écrans haute densité (le canvas est mis à l'échelle par
    // le facteur devicePixelRatio du navigateur).
    devicePixelRatio: Math.max(2, window.devicePixelRatio || 1),
    ...entryAnimation(),
    interaction: { mode: "nearest", intersect: false },
    font: { family: "inherit" },
    color: theme.muted,
    plugins: {
      legend: { display: false, labels: { color: theme.text, usePointStyle: true } },
      tooltip: {
        backgroundColor: theme.surface,
        titleColor: theme.text,
        bodyColor: theme.text,
        borderColor: theme.border,
        borderWidth: 1,
        padding: 10,
        cornerRadius: 8,
        displayColors: false,
        titleFont: { weight: "600" },
      },
      ...plugins,
    },
    scales,
    ...rest,
  };
}

/** Axe à catégories sans graduations saillantes. */
export function categoryScale(theme, extra = {}) {
  return {
    grid: { display: false },
    border: { display: false },
    ticks: { color: theme.muted, font: { size: 11 } },
    ...extra,
  };
}

/** Axe de valeurs avec grille discrète tracée sous les données. */
export function valueScale(theme, extra = {}) {
  return {
    beginAtZero: true,
    grid: { color: theme.grid, drawTicks: false, lineWidth: 1 },
    border: { display: false },
    ticks: { color: theme.muted, font: { size: 11 }, padding: 6 },
    ...extra,
  };
}
