/**
 * Point d'entrée du bundle de graphiques DataZen.
 *
 * Le HTML est rendu par Django ; ce script ne fait qu'« hydrater » les
 * emplacements marqués `[data-dz-chart]` en remplaçant le PNG de repli par un
 * canvas interactif. Si JavaScript est désactivé, ou si l'appel réseau échoue,
 * les images PNG produites par matplotlib restent affichées : la page ne
 * dépend jamais du bundle.
 */

import { createRoot } from "react-dom/client";

// Doit être importé avant tout composant : enregistre les briques Chart.js.
import "./register.js";
import ChartApp from "./App.jsx";

function mount(container) {
  const url = container.getAttribute("data-dz-chart-data-url");
  if (!url) return;

  const root = document.createElement("div");
  root.className = "dz-charts-root";
  container.appendChild(root);
  createRoot(root).render(<ChartApp container={container} url={url} />);
}

function start() {
  document.querySelectorAll("[data-dz-charts]").forEach(mount);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", start);
} else {
  start();
}
