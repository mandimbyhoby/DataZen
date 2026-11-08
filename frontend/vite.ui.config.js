import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Îlots React de l'interface (zone d'envoi, jauges de score, compteurs,
// notifications). Bundle séparé de celui des graphiques : il est chargé sur
// toutes les pages et n'embarque donc pas Chart.js.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../static/js/ui",
    emptyOutDir: true,
    manifest: false,
    rollupOptions: {
      input: "src/ui/main.jsx",
      output: {
        format: "iife",
        entryFileNames: "datazen-ui.js",
        assetFileNames: "datazen-ui.[ext]",
      },
    },
  },
});
