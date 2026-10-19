/**
 * Répartiteur des graphiques : récupère le payload JSON une seule fois pour
 * toute la page, puis rend le composant correspondant au type de graphique.
 *
 * En cas d'échec réseau, le composant ne rend rien et le PNG produit par
 * matplotlib reste affiché : la page reste utilisable sans JavaScript.
 */

import { useEffect, useMemo, useState } from "react";

import { makeFormatter } from "./format";
import { readTheme } from "./theme";
import BoxPlots from "./charts/BoxPlots";
import CategoryPanels from "./charts/CategoryPanels";
import CorrelationHeatmap from "./charts/CorrelationHeatmap";
import DistributionMoments from "./charts/DistributionMoments";
import Histograms from "./charts/Histograms";
import HorizontalBars from "./charts/HorizontalBars";
import ScoreGauge from "./charts/ScoreGauge";
import VerticalBars from "./charts/VerticalBars";

const COMPONENTS = {
  gauge: ScoreGauge,
  hbar: HorizontalBars,
  vbar: VerticalBars,
  histograms: Histograms,
  boxplots: BoxPlots,
  heatmap: CorrelationHeatmap,
  categories: CategoryPanels,
  moments: DistributionMoments,
};

// Une seule requête par URL, partagée par tous les graphiques de la page.
const payloads = new Map();

function loadPayload(url) {
  if (!payloads.has(url)) {
    payloads.set(
      url,
      fetch(url, {
        headers: { Accept: "application/json" },
        credentials: "same-origin",
      }).then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
      }),
    );
    // Un échec ne doit pas rester en cache : le prochain affichage réessaiera.
    payloads.get(url).catch(() => payloads.delete(url));
  }
  return payloads.get(url);
}

/** Thème courant, réévalué quand l'utilisateur bascule clair/sombre. */
function useTheme() {
  const [theme, setTheme] = useState(readTheme);
  useEffect(() => {
    const observer = new MutationObserver(() => setTheme(readTheme()));
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-bs-theme", "class"],
    });
    return () => observer.disconnect();
  }, []);
  return theme;
}

export default function ChartApp({ container, url }) {
  const slug = container.getAttribute("data-dz-chart");
  const [payload, setPayload] = useState(null);
  const [failed, setFailed] = useState(false);
  const theme = useTheme();

  useEffect(() => {
    let active = true;
    loadPayload(url).then(
      (result) => active && setPayload(result),
      () => active && setFailed(true),
    );
    return () => {
      active = false;
    };
  }, [url]);

  const chart = useMemo(() => {
    if (!payload) return null;
    return (payload.charts || []).find((item) => item.slug === slug) || null;
  }, [payload, slug]);

  const Component = chart ? COMPONENTS[chart.kind] : null;

  // Le PNG de repli est masqué dès que le canvas est prêt, et restauré si le
  // graphique ne peut pas être rendu.
  useEffect(() => {
    container.classList.toggle("dz-chart-live", Boolean(Component));
  }, [container, Component]);

  const formatNumber = useMemo(
    () => makeFormatter(payload ? payload.separators : null),
    [payload],
  );

  if (failed || !Component) return null;

  return (
    <Component data={chart.data} theme={theme} formatNumber={formatNumber} />
  );
}
