// JavaScript personnalisé DataZen

// --- Libellés traduits ---------------------------------------------------
// Les chaînes générées par le JS ne passent pas par gettext : elles sont
// exposées par `templates/core/base.html` via des attributs `data-dz-msg-*`
// posés sur <body> (voir `tools/translations/ui_strings.py`).
function dzMsg(key, fallback) {
    "use strict";
    const host = document.body;
    const value = host && host.dataset ? host.dataset["dzMsg" + key] : "";
    return value || fallback;
}

// --- Sélecteur de fichier traduisible ------------------------------------
(function () {
    "use strict";

    document.addEventListener("DOMContentLoaded", function () {
        document.querySelectorAll(".dz-file-picker").forEach(function (picker) {
            const input = picker.querySelector('input[type="file"]');
            const name = picker.querySelector(".dz-file-name");
            if (!input || !name || input.dataset.filePickerInitialized === "true") {
                return;
            }
            input.dataset.filePickerInitialized = "true";

            input.addEventListener("change", function () {
                name.textContent = input.files && input.files.length
                    ? input.files[0].name
                    : name.dataset.emptyLabel;
            });
        });
    });
})();

// --- Affichage / masquage des mots de passe ------------------------------
// Ajoute automatiquement un bouton « œil » à chaque champ de type password
// (connexion, inscription, réinitialisation…). Aucune modification des
// templates n'est nécessaire : les champs sont détectés au chargement.
(function () {
    "use strict";

    const EYE_OPEN =
        '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 16 16" aria-hidden="true">' +
        '<path d="M16 8s-3-5.5-8-5.5S0 8 0 8s3 5.5 8 5.5S16 8 16 8M1.173 8a13 13 0 0 1 1.66-2.043C4.12 4.668 5.88 3.5 8 3.5s3.879 1.168 5.168 2.457A13 13 0 0 1 14.828 8q-.086.13-.195.288c-.335.48-.83 1.12-1.465 1.755C11.879 11.332 10.119 12.5 8 12.5s-3.879-1.168-5.168-2.457A13 13 0 0 1 1.172 8z"/>' +
        '<path d="M8 5.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5M4.5 8a3.5 3.5 0 1 1 7 0 3.5 3.5 0 0 1-7 0"/>' +
        "</svg>";
    const EYE_CLOSED =
        '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 16 16" aria-hidden="true">' +
        '<path d="M13.359 11.238C15.06 9.72 16 8 16 8s-3-5.5-8-5.5a7 7 0 0 0-2.79.588l.77.771A6 6 0 0 1 8 3.5c2.12 0 3.879 1.168 5.168 2.457A13 13 0 0 1 14.828 8q-.086.13-.195.288c-.335.48-.83 1.12-1.465 1.755q-.247.248-.517.486z"/>' +
        '<path d="M11.297 9.176a3.5 3.5 0 0 0-4.474-4.474l.823.823a2.5 2.5 0 0 1 2.829 2.829zm-2.943 1.299.822.822a3.5 3.5 0 0 1-4.474-4.474l.823.823a2.5 2.5 0 0 0 2.829 2.829"/>' +
        '<path d="M3.35 5.47q-.27.24-.518.487A13 13 0 0 0 1.172 8l.195.288c.335.48.83 1.12 1.465 1.755C4.121 11.332 5.881 12.5 8 12.5c.716 0 1.39-.133 2.02-.36l.77.772A7 7 0 0 1 8 13.5C3 13.5 0 8 0 8s.939-1.721 2.641-3.238l.708.709zm10.296 8.884-12-12 .708-.708 12 12z"/>' +
        "</svg>";

    function fieldLabel(input) {
        // Priorité au <label> associé (texte français du formulaire), puis au
        // placeholder, puis à un libellé générique.
        if (input.id) {
            const label = document.querySelector(
                'label[for="' + CSS.escape(input.id) + '"]'
            );
            if (label) {
                const text = label.textContent.replace(/\s+/g, " ").trim();
                if (text) {
                    return text;
                }
            }
        }
        if (input.placeholder) {
            return input.placeholder;
        }
        if (input.id) {
            const implicit = input.closest("label");
            if (implicit) {
                const text = implicit.textContent.replace(/\s+/g, " ").trim();
                if (text) {
                    return text;
                }
            }
        }
        return "mot de passe";
    }

    function enhance(input) {
        if (input.dataset.passwordToggle === "done") {
            return;
        }
        input.dataset.passwordToggle = "done";

        // Le champ doit pouvoir accueillir le bouton sans chevauchement.
        const wrapper = document.createElement("div");
        wrapper.className = "password-toggle-wrapper position-relative";
        input.parentNode.insertBefore(wrapper, input);
        wrapper.appendChild(input);
        if (!input.classList.contains("form-control")) {
            input.classList.add("form-control");
        }
        input.classList.add("password-toggle-input");

        const label = fieldLabel(input);
        const button = document.createElement("button");
        button.type = "button";
        button.className = "password-toggle-btn";
        button.setAttribute("aria-label", dzMsg("Show", "Afficher") + " : " + label);
        button.setAttribute("title", dzMsg("ShowPassword", "Afficher le mot de passe"));
        button.setAttribute("aria-pressed", "false");
        button.innerHTML = EYE_OPEN;
        button.disabled = input.disabled;
        wrapper.appendChild(button);

        button.addEventListener("click", function () {
            const show = input.type === "password";
            input.type = show ? "text" : "password";
            button.innerHTML = show ? EYE_CLOSED : EYE_OPEN;
            const action = show
                ? dzMsg("Hide", "Masquer")
                : dzMsg("Show", "Afficher");
            // Les champs de mot de passe ont une tournure dédiée : la
            // concaténation « action + libellé » ne se traduit pas telle quelle.
            const isPassword = /mot de passe|password|senha|wachtwoord/i.test(label);
            const phrase = isPassword
                ? dzMsg(
                      show ? "HidePassword" : "ShowPassword",
                      show ? "Masquer le mot de passe" : "Afficher le mot de passe"
                  )
                : action + " : " + label;
            button.setAttribute("aria-label", phrase);
            button.setAttribute("title", phrase);
            button.setAttribute("aria-pressed", show ? "true" : "false");
            input.focus({ preventScroll: true });
        });

        // Échap remet le mot de passe en mode masqué.
        input.addEventListener("keydown", function (event) {
            if (event.key === "Escape" && input.type === "text") {
                button.click();
            }
        });
    }

    function initPasswordToggles() {
        document
            .querySelectorAll('input[type="password"]')
            .forEach(enhance);
    }

    window.DataZen = window.DataZen || {};
    window.DataZen.initPasswordToggles = initPasswordToggles;

    document.addEventListener("DOMContentLoaded", initPasswordToggles);
})();

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
                theme === "dark"
                    ? dzMsg("ThemeLight", "Activer le thème clair")
                    : dzMsg("ThemeDark", "Activer le thème sombre")
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

// --- Ombre de la barre de navigation -------------------------------------
// La barre est translucide et collée en haut : on ajoute une ombre dès que la
// page défile, pour la détacher visuellement du contenu.
(function () {
    "use strict";

    document.addEventListener("DOMContentLoaded", function () {
        const navbar = document.getElementById("dz-navbar");
        if (!navbar) {
            return;
        }

        function update() {
            navbar.classList.toggle("is-scrolled", window.scrollY > 8);
        }

        update();
        window.addEventListener("scroll", update, { passive: true });
    });
})();

// --- Menu de navigation sur mobile ---------------------------------------
// Sur petit écran, le menu se déploie en panneau : on le referme dès qu'un
// lien est activé, sinon il masque le contenu. On le referme aussi si la
// fenêtre est agrandie au-delà du point de rupture.
(function () {
    "use strict";

    document.addEventListener("DOMContentLoaded", function () {
        const collapseEl = document.getElementById("navbarNav");
        if (!collapseEl || !window.bootstrap) {
            return;
        }

        const collapse = bootstrap.Collapse.getOrCreateInstance(collapseEl, {
            toggle: false
        });

        function hideIfOpen() {
            if (collapseEl.classList.contains("show")) {
                collapse.hide();
            }
        }

        // Fermeture au clic sur un lien de navigation (hors menu déroulant).
        collapseEl.querySelectorAll("a.nav-link:not(.dropdown-toggle), a.btn").forEach(
            function (link) {
                link.addEventListener("click", hideIfOpen);
            }
        );

        // Fermeture au retour au format bureau.
        const desktop = window.matchMedia("(min-width: 992px)");
        const onChange = function (event) {
            if (event.matches) {
                hideIfOpen();
            }
        };
        if (desktop.addEventListener) {
            desktop.addEventListener("change", onChange);
        } else if (desktop.addListener) {
            desktop.addListener(onChange);
        }
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
        input.placeholder = dzMsg("FilterRows", "🔍 Filtrer les lignes…");
        input.setAttribute(
            "aria-label",
            dzMsg("FilterRowsLabel", "Filtrer les lignes du tableau")
        );
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
            th.title = dzMsg("SortHint", "Cliquer pour trier");
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

// --- Copie dans le presse-papiers ----------------------------------------
// Tout élément marqué `data-dz-copy` (sélecteur CSS ou identifiant) copie la
// valeur cible, puis confirme visuellement pendant quelques secondes.
(function () {
    "use strict";

    document.addEventListener("DOMContentLoaded", function () {
        document.querySelectorAll("[data-dz-copy]").forEach(function (button) {
            button.addEventListener("click", function () {
                const target = document.querySelector(button.dataset.dzCopy);
                if (!target) {
                    return;
                }
                const value = target.value || target.textContent;
                const confirmCopy = function () {
                    const original = button.textContent;
                    button.textContent =
                        button.dataset.dzCopyLabel || dzMsg("Copied", "✓ Copié");
                    button.classList.add("btn-success");
                    button.classList.remove("btn-outline-secondary");
                    window.setTimeout(function () {
                        button.textContent = original;
                        button.classList.remove("btn-success");
                        button.classList.add("btn-outline-secondary");
                    }, 2000);
                };
                if (navigator.clipboard && navigator.clipboard.writeText) {
                    navigator.clipboard.writeText(value).then(confirmCopy, function () {});
                } else {
                    target.focus();
                    target.select();
                    confirmCopy();
                }
            });
        });
    });
})();

// --- Confirmation générique des formulaires -------------------------------
// Évite les `onclick` en ligne : le message est porté par l'attribut
// `data-dz-confirm` du formulaire.
(function () {
    "use strict";

    document.addEventListener("DOMContentLoaded", function () {
        document.querySelectorAll("form[data-dz-confirm]").forEach(function (form) {
            form.addEventListener("submit", function (event) {
                if (!window.confirm(form.dataset.dzConfirm)) {
                    event.preventDefault();
                }
            });
        });
    });
})();

// --- Palette de recherche globale (Ctrl+K) -------------------------------
// Interroge `core:global_search` et affiche les fichiers, règles, pages,
// activités, jetons et webhooks correspondants. Navigation clavier complète,
// sans dépendance externe.
(function () {
    "use strict";

    const MIN_LENGTH = 2;

    document.addEventListener("DOMContentLoaded", function () {
        const palette = document.getElementById("dz-palette");
        if (!palette) {
            return;
        }

        const input = document.getElementById("dz-palette-input");
        const results = document.getElementById("dz-palette-results");
        const MESSAGES = {
            help: palette.dataset.dzMsgHelp || "Type at least two characters.",
            empty: palette.dataset.dzMsgEmpty || "No result.",
            loading: palette.dataset.dzMsgLoading || "Searching…",
            error: palette.dataset.dzMsgError || "Search unavailable."
        };

        let items = [];
        let activeIndex = -1;
        let lastQuery = "";
        let controller = null;

        function isOpen() {
            return !palette.hasAttribute("hidden");
        }

        function searchUrl() {
            return palette.dataset.dzSearchUrl || "/search/";
        }

        function setMessage(text) {
            results.innerHTML = "";
            const p = document.createElement("p");
            p.className = "dz-palette__empty";
            p.textContent = text;
            results.appendChild(p);
            items = [];
            activeIndex = -1;
        }

        function highlight(index) {
            Array.from(results.children).forEach(function (child, position) {
                child.classList.toggle("is-active", position === index);
            });
            activeIndex = index;
            const active = results.children[index];
            if (active && active.scrollIntoView) {
                active.scrollIntoView({ block: "nearest" });
            }
        }

        function open() {
            palette.removeAttribute("hidden");
            document.body.style.overflow = "hidden";
            input.value = lastQuery;
            input.focus();
            if (lastQuery.length >= MIN_LENGTH) {
                search(lastQuery);
            }
        }

        function close() {
            palette.setAttribute("hidden", "");
            document.body.style.overflow = "";
            if (controller) {
                controller.abort();
                controller = null;
            }
        }

        // Construit le libellé en mettant en évidence la portion trouvée.
        // Le texte vient du serveur : on n'utilise jamais innerHTML, on
        // assemble des nœuds texte et un <mark>.
        function buildLabel(item) {
            const label = document.createElement("span");
            label.className = "dz-palette__item-label";
            const text = item.label || "";
            const mark = item.highlight || "";
            const position = mark ? text.toLowerCase().indexOf(mark.toLowerCase()) : -1;
            if (position < 0) {
                label.textContent = text;
                return label;
            }
            label.appendChild(document.createTextNode(text.slice(0, position)));
            const emphasis = document.createElement("mark");
            emphasis.className = "dz-palette__mark";
            emphasis.textContent = text.slice(position, position + mark.length);
            label.appendChild(emphasis);
            label.appendChild(
                document.createTextNode(text.slice(position + mark.length))
            );
            return label;
        }

        function render(payload) {
            results.innerHTML = "";
            items = payload.results || [];
            activeIndex = -1;
            if (!items.length) {
                setMessage(MESSAGES.empty);
                return;
            }
            items.forEach(function (item, index) {
                const button = document.createElement("button");
                button.type = "button";
                button.className = "dz-palette__item";
                button.setAttribute("role", "option");

                const icon = document.createElement("span");
                icon.className = "dz-palette__item-icon";
                icon.setAttribute("aria-hidden", "true");
                icon.textContent = item.icon || "🔎";
                button.appendChild(icon);

                const body = document.createElement("span");
                body.className = "dz-palette__item-body";
                body.appendChild(buildLabel(item));
                const hint = document.createElement("span");
                hint.className = "dz-palette__item-hint";
                hint.textContent = item.hint || "";
                body.appendChild(hint);
                button.appendChild(body);

                const type = document.createElement("span");
                type.className = "dz-palette__item-type";
                type.textContent = item.type_label || item.type || "";
                button.appendChild(type);

                button.addEventListener("click", function () {
                    window.location.href = item.url;
                });
                results.appendChild(button);
                if (index === 0) {
                    highlight(0);
                }
            });
        }

        function search(query) {
            if (controller) {
                controller.abort();
            }
            controller = new AbortController();
            fetch(searchUrl() + "?q=" + encodeURIComponent(query), {
                headers: { "X-Requested-With": "fetch" },
                signal: controller.signal
            })
                .then(function (response) {
                    return response.ok ? response.json() : null;
                })
                .then(function (payload) {
                    if (payload) {
                        render(payload);
                    } else {
                        setMessage(MESSAGES.error);
                    }
                })
                .catch(function () {
                    /* requête annulée : nouvelle saisie en cours */
                });
        }

        const trigger = document.getElementById("dz-search-open");
        if (trigger && trigger.dataset.dzSearchUrl) {
            palette.dataset.dzSearchUrl = trigger.dataset.dzSearchUrl;
        }
        if (trigger) {
            trigger.addEventListener("click", open);
        }

        input.addEventListener("input", function () {
            const query = input.value.trim();
            lastQuery = query;
            window.clearTimeout(input.dataset.dzTimer);
            if (query.length < MIN_LENGTH) {
                setMessage(MESSAGES.help);
                return;
            }
            setMessage(MESSAGES.loading);
            input.dataset.dzTimer = window.setTimeout(function () {
                search(query);
            }, 180);
        });

        input.addEventListener("keydown", function (event) {
            if (event.key === "ArrowDown" || event.key === "ArrowUp") {
                event.preventDefault();
                if (!items.length) {
                    return;
                }
                const step = event.key === "ArrowDown" ? 1 : -1;
                const next = (activeIndex + step + items.length) % items.length;
                highlight(next);
            } else if (event.key === "Enter") {
                if (activeIndex >= 0 && results.children[activeIndex]) {
                    results.children[activeIndex].click();
                }
            }
        });

        document.addEventListener("keydown", function (event) {
            const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(
                document.activeElement ? document.activeElement.tagName : ""
            );
            if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
                event.preventDefault();
                if (isOpen()) {
                    close();
                } else {
                    open();
                }
                return;
            }
            if (event.key === "Escape" && isOpen()) {
                close();
                return;
            }
            if (event.key === "/" && !typing && !isOpen()) {
                event.preventDefault();
                open();
            }
        });

        palette.querySelectorAll("[data-dz-palette-close]").forEach(function (element) {
            element.addEventListener("click", close);
        });
    });
})();
