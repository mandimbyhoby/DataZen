/**
 * Enregistrement des composants Chart.js utilisés par les graphiques.
 *
 * `react-chartjs-2` s'appuie sur l'entrée « tree-shakeable » de Chart.js :
 * seuls les contrôleurs, éléments, échelles et plugins déclarés ici sont
 * embarqués dans le bundle. Enregistrer explicitement évite d'importer
 * `chart.js/auto` (tous les types de graphiques) et garde le fichier léger.
 */

import {
  ArcElement,
  BarController,
  BarElement,
  CategoryScale,
  Chart,
  DoughnutController,
  Legend,
  LineController,
  LineElement,
  LinearScale,
  PointElement,
  Tooltip,
} from "chart.js";

Chart.register(
  // Contrôleurs : anneau du score, barres (horizontales et verticales),
  // courbe de densité superposée aux histogrammes.
  DoughnutController,
  BarController,
  LineController,
  // Éléments graphiques.
  ArcElement,
  BarElement,
  LineElement,
  PointElement,
  // Échelles.
  CategoryScale,
  LinearScale,
  // Plugins.
  Tooltip,
  Legend,
);

export default Chart;