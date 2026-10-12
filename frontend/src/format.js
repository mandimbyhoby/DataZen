/**
 * Formatage localisé des nombres, aligné sur la langue active du serveur.
 *
 * Le serveur transmet le séparateur décimal et le séparateur de milliers
 * utilisés par la langue choisie : les graphiques affichent donc « 1 234,5 »
 * en français et « 1,234.5 » en anglais.
 */

const DEFAULT_SEPARATORS = { decimal: ".", thousand: "," };

export function makeFormatter(separators) {
  const { decimal, thousand } = { ...DEFAULT_SEPARATORS, ...(separators || {}) };

  return function formatNumber(value, decimals = null) {
    const number = Number(value);
    if (!Number.isFinite(number)) return String(value ?? "");

    const fixed =
      decimals === null
        ? String(Number(number.toPrecision(12)))
        : number.toFixed(decimals);

    const [integer, fraction] = fixed.split(".");
    const grouped = integer.replace(/\B(?=(\d{3})+(?!\d))/g, "\u202f");
    const withThousand = grouped.split("\u202f").join(thousand);
    return fraction ? `${withThousand}${decimal}${fraction}` : withThousand;
  };
}

/** Formate un pourcentage avec une décimale au maximum. */
export function formatPercent(value, formatNumber) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  const rounded = Math.round(number * 10) / 10;
  return `${formatNumber(rounded, Number.isInteger(rounded) ? 0 : 1)} %`;
}
