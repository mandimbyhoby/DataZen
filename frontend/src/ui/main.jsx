/**
 * Point d'entrée des îlots React de l'interface DataZen (`datazen-ui.js`).
 *
 * Le HTML reste rendu par Django : ce bundle repère des emplacements marqués
 * par des attributs `data-dz-*` et y greffe des composants interactifs. Sans
 * JavaScript, ou si ce fichier ne se charge pas, la page d'origine reste
 * complète et fonctionnelle (amélioration progressive).
 *
 * Îlots :
 *   [data-dz-upload]         zone de dépôt avec progression d'envoi réelle
 *   [data-dz-score-compare]  jauges « score avant → après »
 *   [data-dz-score-ring]     jauge du score moyen
 *   chiffres clés            défilement animé des indicateurs
 *   messages Django          notifications « toast »
 */
import { createRoot } from "react-dom/client";

import CountUps from "./CountUp.jsx";
import { ScoreCompare, ScoreRing } from "./ScoreRing.jsx";
import Toaster from "./Toaster.jsx";
import UploadZone from "./UploadZone.jsx";

function number(value) {
  if (value === undefined || value === null || value === "") return null;
  const parsed = Number(String(value).replace(",", "."));
  return Number.isFinite(parsed) ? parsed : null;
}

/** Crée un conteneur React juste avant `anchor` et masque `hide`. */
function island(anchor, hide, className) {
  const host = document.createElement("div");
  host.className = className;
  anchor.parentNode.insertBefore(host, anchor);
  if (hide) hide.hidden = true;
  return createRoot(host);
}

function mountUploads() {
  document.querySelectorAll("form[data-dz-upload]").forEach((form) => {
    const input = form.querySelector('input[type="file"]');
    const legacy = form.querySelector(".dz-dropzone");
    if (!input || !legacy) return;
    const d = form.dataset;
    const messages = {
      drop: d.dzMsgDrop,
      browse: d.dzMsgBrowse,
      release: d.dzMsgRelease,
      uploading: d.dzMsgUploading,
      done: d.dzMsgDone,
      remove: d.dzMsgRemove,
      failed: d.dzMsgFailed,
      format: d.dzMsgFormat,
      size: d.dzMsgSize,
      empty: d.dzMsgEmpty,
    };
    const accept = (d.dzAccept || ".csv,.xlsx,.xls").split(",").map((ext) => ext.trim().toLowerCase());
    island(legacy, legacy, "dz-upload-root").render(
      <UploadZone
        form={form}
        input={input}
        messages={messages}
        maxSize={Number(d.dzMaxSize) || 20 * 1024 * 1024}
        accept={accept}
      />
    );
    form.classList.add("dz-upload-live");
  });
}

function mountScores() {
  document.querySelectorAll("[data-dz-score-compare]").forEach((element) => {
    const d = element.dataset;
    island(element, element, "dz-score-compare-root").render(
      <ScoreCompare
        before={number(d.dzBefore)}
        after={number(d.dzAfter)}
        labelBefore={d.dzLabelBefore}
        labelAfter={d.dzLabelAfter}
      />
    );
  });
  document.querySelectorAll("[data-dz-score-ring]").forEach((element) => {
    const d = element.dataset;
    const legacy = element.querySelector("[data-dz-score-value]");
    island(legacy || element.firstElementChild, legacy, "dz-score-ring-root").render(
      <ScoreRing value={number(d.dzScoreRing)} label={d.dzLabel} size={128} />
    );
  });
}

function mountCountUps() {
  const elements = Array.from(
    document.querySelectorAll(".dz-kpi-card__value, .dz-stat .dz-stat-value, [data-dz-countup]")
  );
  if (!elements.length) return;
  const host = document.createElement("div");
  host.hidden = true;
  document.body.appendChild(host);
  createRoot(host).render(<CountUps elements={elements} />);
}

function mountToasts() {
  const alerts = Array.from(document.querySelectorAll("main > .dz-page-top > .alert"));
  if (!alerts.length) return;
  const levels = ["success", "danger", "warning", "info", "error"];
  const initial = alerts.map((alert, index) => {
    const level = levels.find((name) => alert.classList.contains(`alert-${name}`)) || "info";
    const clone = alert.cloneNode(true);
    clone.querySelectorAll("button").forEach((button) => button.remove());
    return { id: index, level, text: clone.textContent.trim() };
  });
  const closeButton = alerts[0].querySelector(".btn-close");
  const closeLabel = closeButton ? closeButton.getAttribute("aria-label") : "×";
  const container = alerts[0].parentElement;
  container.hidden = true;
  const host = document.createElement("div");
  document.body.appendChild(host);
  createRoot(host).render(<Toaster initial={initial} closeLabel={closeLabel} />);
}

function start() {
  [mountUploads, mountScores, mountCountUps, mountToasts].forEach((mount) => {
    try {
      mount();
    } catch (error) {
      // Un îlot défaillant ne doit jamais empêcher les autres de démarrer :
      // le HTML d'origine reste en place.
      console.error("[DataZen UI]", error);
    }
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", start);
} else {
  start();
}
