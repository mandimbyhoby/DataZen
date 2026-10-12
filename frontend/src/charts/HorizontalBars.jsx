import { useMemo } from "react";
import { Bar } from "react-chartjs-2";
import { BRAND, baseOptions, categoryScale, valueScale } from "../theme";
import { trackPlugin } from "../plugins";
import { sweepMotion } from "../motion";

/**
 * Barres horizontales posées sur une piste claire (dimensions du score,
 * complétude par colonne, valeurs aberrantes).
 *
 * ``data.items`` : ``[{ label, value, color?, note? }]``
 * ``data.total`` : valeur de la piste (100 pour un pourcentage, ``null`` sinon)
 */
export default function HorizontalBars({ data, theme, formatNumber }) {
  const items = data.items || [];
  const total = data.total ?? null;

  const plugins = useMemo(() => {
    const list = [sweepMotion({ delay: items.length ? 0 : 400 })];
    if (total) list.unshift(trackPlugin(total, theme.grid));
    return list;
  }, [total, theme.grid, items.length]);

  const chartData = {
    labels: items.map((item) => item.label),
    datasets: [
      {
        data: items.map((item) => item.value),
        backgroundColor: items.map(
          (item, index) => item.color || BRAND[index % BRAND.length],
        ),
        borderRadius: 6,
        borderSkipped: false,
        barPercentage: 0.72,
        categoryPercentage: 0.82,
      },
    ],
  };

  const options = baseOptions(theme, {
    indexAxis: "y",
    layout: { padding: { right: 56 } },
    scales: {
      x: valueScale(theme, {
        max: total ? Math.round(total * 1.22) : undefined,
        ticks: {
          color: theme.muted,
          font: { size: 11 },
          padding: 6,
          callback: (value) => formatNumber(value),
        },
      }),
      y: categoryScale(theme, {
        ticks: { color: theme.text, font: { size: 11.5 }, padding: 8 },
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
            const note = items[item.dataIndex]?.note;
            const value = formatNumber(item.parsed.x, 1);
            return note ? `${value} — ${note}` : value;
          },
        },
      },
    },
  });

  return (
    <div
      className="dz-chart-canvas"
      style={{ height: `${Math.max(180, items.length * 42 + 60)}px` }}
    >
      <Bar data={chartData} options={options} plugins={plugins} />
    </div>
  );
}
