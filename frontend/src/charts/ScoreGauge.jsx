import { useMemo } from "react";
import { Doughnut } from "react-chartjs-2";
import { scoreColor } from "../theme";
import { centerTextPlugin } from "../plugins";
import { pulseMotion } from "../motion";

/**
 * Jauge en anneau du score global de qualité.
 *
 * Le score est écrit au centre du canvas : il reste net à toute résolution
 * puisque le texte est dessiné vectoriellement par le navigateur.
 */
export default function ScoreGauge({ data, theme, formatNumber }) {
  const total = Math.max(0, Math.min(100, Number(data.value) || 0));
  const color = scoreColor(total);

  const plugins = useMemo(
    () => [
      centerTextPlugin([
        {
          text: formatNumber(total, Number.isInteger(total) ? 0 : 1),
          size: 46,
          weight: "700",
          color,
          offset: -14,
        },
        { text: "/ 100", size: 15, weight: "500", color: theme.muted, offset: 22 },
        { text: data.label, size: 13, weight: "600", color: theme.text, offset: 52 },
      ]),
      pulseMotion(color),
    ],
    [total, color, theme, data.label, formatNumber],
  );

  const chartData = {
    labels: [data.label, ""],
    datasets: [
      {
        data: [total, Math.max(0, 100 - total)],
        backgroundColor: [color, theme.grid],
        borderWidth: 0,
        hoverBackgroundColor: [color, theme.grid],
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    devicePixelRatio: Math.max(2, window.devicePixelRatio || 1),
    cutout: "72%",
    rotation: -90,
    circumference: 360,
    animation: { duration: 1100, easing: "easeOutCubic" },
    plugins: {
      legend: { display: false },
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
          label: (item) =>
            item.dataIndex === 0
              ? `${data.label} : ${formatNumber(total, 1)} / 100`
              : "",
        },
      },
    },
  };

  return (
    <div className="dz-chart-canvas dz-chart-canvas--gauge">
      <Doughnut data={chartData} options={options} plugins={plugins} />
    </div>
  );
}
