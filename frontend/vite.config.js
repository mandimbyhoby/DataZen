import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Les bundles sont écrits directement dans les fichiers statiques de Django :
// aucun serveur Node n'est nécessaire en production, `collectstatic` les
// récupère comme n'importe quel autre asset.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../static/js/charts",
    emptyOutDir: true,
    manifest: false,
    rollupOptions: {
      // Entrée JavaScript directe : le HTML est rendu par Django, Vite ne doit
      // donc produire qu'un seul fichier JS (pas de page `index.html`).
      input: "src/main.jsx",
      output: {
        entryFileNames: "datazen-charts.js",
        chunkFileNames: "datazen-charts-[name].js",
        assetFileNames: "datazen-charts.[ext]",
      },
    },
  },
});
