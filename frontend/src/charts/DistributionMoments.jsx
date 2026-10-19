import { useMemo } from "react";
import { Bar } from "react-chartjs-2";

import { BRAND, baseOptions, categoryScale, valueScale } from "../theme";
import { sweepMotion } from "../motion";

/**
 * Forme des distributions : asymétrie et aplatissement (moments centrés)
 * par colonne numérique, en barres divergentes autour de zéro.
 *
 * ``data.items`` : ``[{ label, skewness, kurtosis }]``
 * ``data.labels`` : ``{ skewness, kurtosis }``
 */
export default function DistributionMoments({ data, theme, formatNumber }) {
  const items = data.items || [];
  const labels = data.labels || {};

  const plugins = useMemo(() => [sweepMotion({ period: 6000 })], []);

  const chartData = {
    labels: items.map((item) => item.label),
    datasets: [
      {
        label: labels.skewness,
        data: items.map((item) => item.skewness),
        backgroundColor: `${BRAND[0]}dd`,
        borderColor: BRAND[0],
        borderWidth: 1,
        borderRadius: 4,
        borderSkipped: false,
        maxBarThickness: 26,
      },
      {
        label: labels.kurtosis,
        data: items.map((item) => item.kurtosis),
        backgroundColor: `${BRAND[2]}dd`,
        borderColor: BRAND[2],
        borderWidth: 1,
        borderRadius: 4,
        borderSkipped: false,
        maxBarThickness: 26,
      },
    ],
  };

  const options = baseOptions(theme, {
    layout: { padding: { top: 16 } },
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
          callback: (value) => formatNumber(value, 1),
        },
      }),
    },
    plugins: {
      legend: {
        display: true,
        position: "bottom",
        labels: {
          color: theme.text,
          usePointStyle: true,
          boxWidth: 8,
          padding: 14,
        },
      },
      tooltip: {
        backgroundColor: theme.surface,
        titleColor: theme.text,
        bodyColor: theme.text,
        borderColor: theme.border,
        borderWidth: 1,
        padding: 10,
        cornerRadius: 8,
        callbacks: {
          label: (item) => `${item.dataset.label} ${formatNumber(item.parsed.y, 2)}`,
        },
      },
    },
  });

  return (
    <div
      className="dz-chart-canvas"
      style={{ height: `${Math.max(300, items.length * 34 + 180)}px` }}
    >
      <Bar data={chartData} options={options} plugins={plugins} />
    </div>
  );
}
