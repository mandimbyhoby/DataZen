import { useMemo } from "react";
import { Bar } from "react-chartjs-2";

import { baseOptions, categoryScale, valueScale } from "../theme";
import { sweepMotion } from "../motion";

/**
 * Grille des valeurs les plus fréquentes : un graphique par colonne
 * catégorielle, en barres horizontales.
 *
 * ``data.panels`` : ``[{ label, color, items: [{ label, value }] }]``
 */
export default function CategoryPanels({ data, theme, formatNumber }) {
  const panels = data.panels || [];
  const plugins = useMemo(
    () => [sweepMotion({ period: 6000, delay: 300 })],
    [],
  );

  return (
    <div className="dz-chart-grid">
      {panels.map((panel) => {
        const items = panel.items || [];

        const chartData = {
          labels: items.map((item) => item.label),
          datasets: [
            {
              data: items.map((item) => item.value),
              backgroundColor: panel.color,
              borderRadius: 5,
              borderSkipped: false,
              barPercentage: 0.7,
              categoryPercentage: 0.84,
            },
          ],
        };

        const options = baseOptions(theme, {
          indexAxis: "y",
          layout: { padding: { right: 40 } },
          scales: {
            x: valueScale(theme, {
              ticks: {
                color: theme.muted,
                font: { size: 10 },
                padding: 4,
                precision: 0,
                callback: (value) => formatNumber(value),
              },
            }),
            y: categoryScale(theme, {
              ticks: {
                color: theme.text,
                font: { size: 11 },
                padding: 6,
                autoSkip: false,
              },
            }),
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
                title: (entries) => `${panel.label} : ${entries[0]?.label ?? ""}`,
                label: (item) => formatNumber(item.parsed.x),
              },
            },
          },
        });

        return (
          <figure className="dz-chart-panel" key={panel.label}>
            <figcaption className="dz-chart-panel__title">
              {panel.label}
            </figcaption>
            <div
              className="dz-chart-canvas"
              style={{ height: `${Math.max(180, items.length * 34 + 60)}px` }}
            >
              <Bar data={chartData} options={options} plugins={plugins} />
            </div>
          </figure>
        );
      })}
    </div>
  );
}
