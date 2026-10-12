import { useMemo } from "react";
import { Bar } from "react-chartjs-2";
import { BRAND, baseOptions, categoryScale, valueScale } from "../theme";
import { sweepMotion } from "../motion";

/**
 * Barres verticales : répartition des problèmes restants par catégorie.
 *
 * ``data.items`` : ``[{ label, value }]``
 */
export default function VerticalBars({ data, theme, formatNumber }) {
  const items = data.items || [];

  const plugins = useMemo(() => [sweepMotion({ period: 5200 })], []);

  const chartData = {
    labels: items.map((item) => item.label),
    datasets: [
      {
        data: items.map((item) => item.value),
        backgroundColor: items.map(
          (item, index) => item.color || BRAND[index % BRAND.length],
        ),
        borderRadius: 8,
        borderSkipped: false,
        maxBarThickness: 72,
        barPercentage: 0.7,
      },
    ],
  };

  const options = baseOptions(theme, {
    layout: { padding: { top: 24 } },
    scales: {
      x: categoryScale(theme, {
        ticks: {
          color: theme.text,
          font: { size: 11.5 },
          maxRotation: 24,
          minRotation: 0,
          autoSkip: false,
        },
      }),
      y: valueScale(theme, {
        ticks: {
          color: theme.muted,
          font: { size: 11 },
          padding: 6,
          precision: 0,
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
          label: (item) => formatNumber(item.parsed.y),
        },
      },
    },
  });

  return (
    <div className="dz-chart-canvas" style={{ height: "340px" }}>
      <Bar data={chartData} options={options} plugins={plugins} />
    </div>
  );
}
