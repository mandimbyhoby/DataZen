/**
 * Plugins Chart.js personnalisés : piste de fond des barres et texte centré
 * de la jauge. Chart.js n'offre ni l'un ni l'autre nativement.
 */

/**
 * Dessine une piste claire derrière chaque barre horizontale, jusqu'à
 * ``total``. Donne l'effet « jauge » des graphiques de complétude.
 */
export function trackPlugin(total, color) {
  return {
    id: "dzTrack",
    beforeDatasetsDraw(chart) {
      const { ctx, chartArea } = chart;
      const xScale = chart.scales.x;
      const meta = chart.getDatasetMeta(0);
      if (!xScale || !meta?.data?.length) return;

      const start = xScale.getPixelForValue(0);
      const end = xScale.getPixelForValue(total);
      const radius = 6;

      ctx.save();
      ctx.fillStyle = color;
      ctx.globalAlpha = 0.28;
      meta.data.forEach((bar) => {
        const height = bar.height ?? 12;
        const y = bar.y - height / 2;
        const width = Math.max(0, end - start);
        ctx.beginPath();
        if (ctx.roundRect) {
          ctx.roundRect(start, y, width, height, radius);
        } else {
          ctx.rect(start, y, width, height);
        }
        ctx.fill();
      });
      ctx.restore();
      void chartArea;
    },
  };
}

/**
 * Écrit un texte au centre du graphique (score et libellé de la jauge).
 */
export function centerTextPlugin(lines) {
  return {
    id: "dzCenterText",
    afterDraw(chart) {
      const { ctx, chartArea } = chart;
      if (!chartArea) return;
      const centerX = (chartArea.left + chartArea.right) / 2;
      const centerY = (chartArea.top + chartArea.bottom) / 2;

      ctx.save();
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      lines.forEach((line) => {
        ctx.font = `${line.weight || "600"} ${line.size}px ${line.family || "inherit"}`;
        ctx.fillStyle = line.color;
        ctx.fillText(line.text, centerX, centerY + (line.offset || 0));
      });
      ctx.restore();
    },
  };
}

/**
 * Dessine les moustaches et les valeurs extrêmes d'une boîte à moustaches
 * au-dessus des barres flottantes (Q1 → Q3).
 */
export function boxWhiskerPlugin(stats, color) {
  return {
    id: "dzBoxWhisker",
    afterDatasetsDraw(chart) {
      const { ctx } = chart;
      const yScale = chart.scales.y;
      const meta = chart.getDatasetMeta(0);
      if (!yScale || !meta?.data?.length) return;

      ctx.save();
      ctx.strokeStyle = color;
      ctx.fillStyle = color;
      ctx.lineWidth = 1.6;

      meta.data.forEach((bar, index) => {
        const stat = stats[index];
        if (!stat) return;
        const x = bar.x;
        const halfWidth = Math.max(8, (bar.width ?? 20) / 2);
        const yMin = yScale.getPixelForValue(stat.min);
        const yMax = yScale.getPixelForValue(stat.max);
        const yQ1 = yScale.getPixelForValue(stat.q1);
        const yQ3 = yScale.getPixelForValue(stat.q3);

        // Moustaches verticales + chapeaux.
        ctx.beginPath();
        ctx.moveTo(x, yQ3);
        ctx.lineTo(x, yMax);
        ctx.moveTo(x - halfWidth * 0.5, yMax);
        ctx.lineTo(x + halfWidth * 0.5, yMax);
        ctx.moveTo(x, yQ1);
        ctx.lineTo(x, yMin);
        ctx.moveTo(x - halfWidth * 0.5, yMin);
        ctx.lineTo(x + halfWidth * 0.5, yMin);
        ctx.stroke();

        // Médiane.
        ctx.lineWidth = 2.4;
        ctx.beginPath();
        ctx.moveTo(x - halfWidth, yScale.getPixelForValue(stat.median));
        ctx.lineTo(x + halfWidth, yScale.getPixelForValue(stat.median));
        ctx.stroke();
        ctx.lineWidth = 1.6;

        // Valeurs extrêmes (points).
        ctx.globalAlpha = 0.55;
        (stat.outliers || []).forEach((value) => {
          ctx.beginPath();
          ctx.arc(x, yScale.getPixelForValue(value), 2.6, 0, Math.PI * 2);
          ctx.fill();
        });
        ctx.globalAlpha = 1;
      });

      ctx.restore();
    },
  };
}
