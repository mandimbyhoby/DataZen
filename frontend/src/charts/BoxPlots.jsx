import { useMemo } from "react";
import { Bar } from "react-chartjs-2";

import { boxWhiskerPlugin } from "../plugins";
import { baseOptions, categoryScale, valueScale } from "../theme";
import { sweepMotion } from "../motion";

/**
 * Boîtes à moustaches (méthode IQR) : une boîte par colonne numérique.
 *
 * ``data.items`` : ``[{ label, color, min, q1, median, q3, max, outliers }]``
 *
 * Chart.js ne connaît pas ce type de graphique : la boîte est une barre
 * flottante (Q1 → Q3) et les moustaches, la médiane et les valeurs extrêmes
 * sont dessinées par ``boxWhiskerPlugin``.
 */
export default function BoxPlots({ data, theme, formatNumber }) {
  const items = data.items || [];
  const labels = data.labels || {};

  const plugins = useMemo(
    () => [boxWhiskerPlugin(items, theme.text), sweepMotion({ period: 6400 })],
    [items, theme.text],
  );

  const chartData = {
    labels: items.map((item) => item.label),
    datasets: [
      {
        data: items.map((item) => [item.q1, item.q3]),
        backgroundColor: items.map((item) => `${item.color}cc`),
        borderColor: items.map((item) => item.color),
        borderWidth: 1.4,
        borderRadius: 4,
        borderSkipped: false,
        barPercentage: 0.5,
        categoryPercentage: 0.7,
      },
    ],
  };

  const options = baseOptions(theme, {
    layout: { padding: { top: 16, bottom: 8 } },
    scales: {
      x: categoryScale(theme, {
        ticks: {
          color: theme.text,
          font: { size: 11.5 },
          maxRotation: 24,
          autoSkip: false,
        },
      }),
      y: valueScale(theme, {
        beginAtZero: false,
        ticks: {
          color: theme.muted,
          font: { size: 11 },
          padding: 6,
          callback: (value) => formatNumber(value),
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
          label: (item) => {
            const stat = items[item.dataIndex];
            if (!stat) return "";
            return [
              `${labels.min} ${formatNumber(stat.min)}`,
              `${labels.q1} ${formatNumber(stat.q1)}`,
              `${labels.median} ${formatNumber(stat.median)}`,
              `${labels.q3} ${formatNumber(stat.q3)}`,
              `${labels.max} ${formatNumber(stat.max)}`,
              `${formatNumber(stat.outliers.length)} ${labels.outliers}`,
            ];
          },
        },
      },
    },
  });

  return (
    <div
      className="dz-chart-canvas"
      style={{ height: `${Math.max(300, items.length * 26 + 200)}px` }}
    >
      <Bar data={chartData} options={options} plugins={plugins} />
    </div>
  );
}
