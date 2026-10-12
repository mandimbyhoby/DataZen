import { useMemo } from "react";
import { Bar } from "react-chartjs-2";

import { baseOptions, categoryScale, valueScale } from "../theme";
import { sweepMotion } from "../motion";

/**
 * Grille d'histogrammes : une distribution par colonne numérique.
 *
 * ``data.panels`` : ``[{ label, color, edges, counts, density }]``
 *
 * La courbe de densité est tracée en second jeu de données (type « line »)
 * sur le même axe, comme la courbe KDE des graphiques matplotlib.
 */
export default function Histograms({ data, theme, formatNumber }) {
  const panels = data.panels || [];
  const plugins = useMemo(
    () => [sweepMotion({ period: 5600, delay: 200 })],
    [],
  );

  return (
    <div className="dz-chart-grid">
      {panels.map((panel) => {
        const centers = panel.edges
          .slice(0, -1)
          .map((edge, index) => (edge + panel.edges[index + 1]) / 2);

        const chartData = {
          labels: centers.map((value) => formatNumber(value, 1)),
          datasets: [
            {
              type: "bar",
              data: panel.counts,
              backgroundColor: panel.color,
              borderRadius: 4,
              borderSkipped: false,
              barPercentage: 1,
              categoryPercentage: 0.98,
            },
            {
              type: "line",
              data: (panel.density || []).map((point) => ({
                x: formatNumber(point.x, 1),
                y: point.y,
              })),
              borderColor: theme.text,
              borderWidth: 1.8,
              pointRadius: 0,
              tension: 0.4,
              yAxisID: "density",
            },
          ],
        };

        const options = baseOptions(theme, {
          scales: {
            x: categoryScale(theme, {
              ticks: {
                color: theme.muted,
                font: { size: 10 },
                maxRotation: 0,
                autoSkip: true,
                maxTicksLimit: 6,
              },
            }),
            y: valueScale(theme, {
              ticks: {
                color: theme.muted,
                font: { size: 10 },
                padding: 4,
                precision: 0,
                callback: (value) => formatNumber(value),
              },
            }),
            density: {
              display: false,
              beginAtZero: true,
              position: "right",
            },
          },
          plugins: {
            tooltip: {
              backgroundColor: theme.surface,
              titleColor: theme.text,
              bodyColor: theme.text,
              borderColor: theme.border,
              borderWidth: 1,
              padding: 10,
              cornerRadius: 8,
              displayColors: false,
              callbacks: {
                title: (items) => `${panel.label} : ${items[0]?.label ?? ""}`,
                label: (item) =>
                  item.dataset.type === "line"
                    ? ""
                    : formatNumber(item.parsed.y),
              },
            },
          },
        });

        return (
          <figure className="dz-chart-panel" key={panel.label}>
            <figcaption className="dz-chart-panel__title">
              {panel.label}
            </figcaption>
            <div className="dz-chart-canvas" style={{ height: "220px" }}>
              <Bar data={chartData} options={options} plugins={plugins} />
            </div>
          </figure>
        );
      })}
    </div>
  );
}
