// JavaScript personnalisé DataZen

// --- Mode sombre ---------------------------------------------------------
// Le thème est appliqué le plus tôt possible (voir le script inline dans
// base.html) pour éviter un flash clair. Ici on gère la bascule et la
// persistance du choix de l'utilisateur.
(function () {
    "use strict";

    const STORAGE_KEY = "datazen-theme";

    function applyTheme(theme) {
        document.documentElement.setAttribute("data-bs-theme", theme);
        const btn = document.getElementById("theme-toggle");
        if (btn) {
            btn.textContent = theme === "dark" ? "☀️" : "🌙";
            btn.setAttribute(
                "aria-label",
                theme === "dark" ? "Activer le thème clair" : "Activer le thème sombre"
            );
        }
    }

    function currentTheme() {
        return document.documentElement.getAttribute("data-bs-theme") || "light";
    }

    document.addEventListener("DOMContentLoaded", function () {
        applyTheme(currentTheme());

        const btn = document.getElementById("theme-toggle");
        if (btn) {
            btn.addEventListener("click", function () {
                const next = currentTheme() === "dark" ? "light" : "dark";
                localStorage.setItem(STORAGE_KEY, next);
                applyTheme(next);
            });
        }

        initTableSearch();
    });
})();

// --- Recherche et tri dans les tableaux ----------------------------------
// Ajoute une zone de recherche au-dessus de chaque tableau marqué
// `data-searchable` et rend les entêtes cliquables pour trier les colonnes.
function initTableSearch() {
    "use strict";

    document.querySelectorAll("table[data-searchable]").forEach(function (table) {
        const tbody = table.tBodies[0];
        if (!tbody) {
            return;
        }

        // Zone de recherche.
        const wrapper = document.createElement("div");
        wrapper.className = "mb-2";
        const input = document.createElement("input");
        input.type = "search";
        input.className = "form-control form-control-sm table-search";
        input.placeholder = "🔍 Filtrer les lignes…";
        input.setAttribute("aria-label", "Filtrer les lignes du tableau");
        wrapper.appendChild(input);
        // Insère la zone de recherche avant le conteneur scrollable s'il
        // existe, pour qu'elle ne défile pas avec le tableau.
        const anchor = table.closest(".table-responsive") || table;
        anchor.parentNode.insertBefore(wrapper, anchor);

        input.addEventListener("input", function () {
            const term = input.value.trim().toLowerCase();
            Array.from(tbody.rows).forEach(function (row) {
                const text = row.textContent.toLowerCase();
                row.style.display = !term || text.includes(term) ? "" : "none";
            });
        });

        // Tri par clic sur l'entête.
        const headers = table.querySelectorAll("thead th");
        headers.forEach(function (th, index) {
            th.style.cursor = "pointer";
            th.title = "Cliquer pour trier";
            let asc = true;
            th.addEventListener("click", function () {
                const rows = Array.from(tbody.rows);
                rows.sort(function (a, b) {
                    const va = (a.cells[index] ? a.cells[index].textContent : "").trim();
                    const vb = (b.cells[index] ? b.cells[index].textContent : "").trim();
                    const na = parseFloat(va.replace(",", "."));
                    const nb = parseFloat(vb.replace(",", "."));
                    let cmp;
                    if (!isNaN(na) && !isNaN(nb)) {
                        cmp = na - nb;
                    } else {
                        cmp = va.localeCompare(vb, "fr", { numeric: true });
                    }
                    return asc ? cmp : -cmp;
                });
                asc = !asc;
                rows.forEach(function (row) {
                    tbody.appendChild(row);
                });
            });
        });
    });
}
