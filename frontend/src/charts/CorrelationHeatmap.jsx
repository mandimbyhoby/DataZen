/**
 * Matrice de corrélation de Pearson.
 *
 * Rendu en grille HTML plutôt qu'en canvas : le texte reste net à n'importe
 * quelle résolution et la grille s'adapte à la largeur disponible sans
 * redessin. La couleur encode le coefficient (bleu négatif, rouge positif).
 *
 * L'animation est ici purement CSS (voir `style.css`, section 16.7.1) : les
 * cellules apparaissent en cascade puis les corrélations marquées respirent
 * doucement.
 *
 * ``data.labels`` : noms des colonnes
 * ``data.matrix`` : matrice carrée de coefficients (``null`` si indéfini)
 */

/** Délai d'apparition d'une cellule, en millisecondes. */
const CELL_STAGGER = 22;

/** Seuil (|r|) au-delà duquel la cellule respire. */
const STRONG_THRESHOLD = 0.55;

/** Interpole la couleur d'une cellule : -1 → bleu, 0 → neutre, +1 → rouge. */
function cellColor(value, theme) {
  if (value === null || value === undefined) return theme.grid;
  const magnitude = Math.min(1, Math.abs(value));
  const alpha = 0.12 + magnitude * 0.78;
  const rgb = value >= 0 ? "239, 68, 68" : "79, 70, 229";
  return `rgba(${rgb}, ${alpha.toFixed(3)})`;
}

export default function CorrelationHeatmap({ data, theme, formatNumber }) {
  const labels = data.labels || [];
  const matrix = data.matrix || [];

  return (
    <div className="dz-heatmap-scroll">
      <table className="dz-heatmap">
        <thead>
          <tr>
            <th scope="col" />
            {labels.map((label) => (
              <th scope="col" key={label} title={label}>
                <span>{label}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {matrix.map((row, rowIndex) => (
            <tr key={labels[rowIndex]}>
              <th scope="row" title={labels[rowIndex]}>
                {labels[rowIndex]}
              </th>
              {row.map((value, colIndex) => {
                const strong = Math.abs(value ?? 0) > STRONG_THRESHOLD;
                const delay = (rowIndex + colIndex) * CELL_STAGGER;
                return (
                  <td
                    key={labels[colIndex]}
                    className={strong ? "dz-heatmap__strong" : undefined}
                    style={{
                      backgroundColor: cellColor(value, theme),
                      color: strong ? "#ffffff" : theme.text,
                      "--dz-cell-delay": `${delay}ms`,
                      "--dz-cell-breathe": `${(rowIndex * 7 + colIndex * 11) * 40}ms`,
                    }}
                    title={`${labels[rowIndex]} × ${labels[colIndex]} : ${
                      value === null ? "—" : formatNumber(value, 2)
                    }`}
                  >
                    {value === null ? "—" : formatNumber(value, 2)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
