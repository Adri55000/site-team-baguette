"use strict";

/* =========================================================
   ÉTAT GLOBAL (source de vérité côté client)
========================================================= */

const currentIndicesState = {};


/* =========================================================
   UTILITAIRES
========================================================= */

/**
 * Récupère le slug du restream depuis l'URL
 * Ex: /restream/<slug>/indices
 */
function getRestreamSlug() {
    const parts = window.location.pathname.split("/");
    return parts[2];
}

/**
 * Retourne la section HTML correspondant à une catégorie
 */
function getCategorySection(category) {
    return document.querySelector(
        `.restream-indices-category[data-category="${category}"]`
    );
}

/**
 * Convertit des items [["a","b"], ["c","d"]] en lignes "a | b"
 */
function itemsToLines(items) {
    return items.map(row => row.join(" | "));
}

/**
 * Met à jour l'affichage d'une catégorie
 */
function updateCategoryView(category, lines) {
    const section = getCategorySection(category);
    if (!section) return;

    const tableWrapper = section.querySelector(".restream-indices-table");
    if (!tableWrapper) return;

    const tbody = tableWrapper.querySelector("tbody");
    const isOneColumn = tableWrapper.classList.contains("one-column");

    tbody.innerHTML = "";

    if (lines.length === 0) {
        const tr = document.createElement("tr");
        const td = document.createElement("td");

        td.colSpan = isOneColumn ? 1 : 2;
        td.textContent = "—";
        td.className = "restream-indices-empty";

        tr.appendChild(td);
        tbody.appendChild(tr);
        return;
    }

    lines.forEach(line => {
        const tr = document.createElement("tr");

        if (isOneColumn) {
            const td = document.createElement("td");
            td.textContent = line;
            tr.appendChild(td);
        } else {
            const parts = line.split("|").map(p => p.trim());

            const td1 = document.createElement("td");
            const td2 = document.createElement("td");

            td1.textContent = parts[0] || "";
            td2.textContent = parts[1] || "";

            tr.appendChild(td1);
            tr.appendChild(td2);
        }

        tbody.appendChild(tr);
    });
}


/* =========================================================
   DOM READY
========================================================= */

document.addEventListener("DOMContentLoaded", () => {

    /* ---------- OUVERTURE DU MODE ÉDITION ---------- */

    document.querySelectorAll(".edit-btn").forEach(button => {
        button.addEventListener("click", () => {
            const category = button.dataset.category;
            const section = getCategorySection(category);
            if (!section) return;

            const form = section.querySelector(".edit-form");
            if (!form) return;

            const textarea = form.querySelector("textarea");

            // Si l'état est déjà connu via SSE, on le recharge
            if (currentIndicesState[category]) {
                textarea.value = itemsToLines(currentIndicesState[category]).join("\n");
            }

            form.classList.remove("hidden");
        });
    });


    /* ---------- ANNULATION ÉDITION ---------- */

    document.querySelectorAll(".cancel-btn").forEach(button => {
        button.addEventListener("click", () => {
            const form = button.closest(".edit-form");
            if (form) {
                form.classList.add("hidden");
            }
        });
    });


    /* ---------- SAUVEGARDE ÉDITION ---------- */

    document.querySelectorAll(".edit-form").forEach(form => {
        form.addEventListener("submit", async (e) => {
            e.preventDefault();

            const category = form.dataset.category;
            const textarea = form.querySelector("textarea");
            const slug = getRestreamSlug();

            const lines = textarea.value
                .split("\n")
                .map(l => l.trim())
                .filter(Boolean);

            try {
                const res = await fetch(
                    `/restream/${slug}/indices/update-category`,
                    {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ category, lines })
                    }
                );

                if (!res.ok) {
                    throw new Error("Erreur serveur");
                }

                // La mise à jour visuelle se fera via le SSE
                form.classList.add("hidden");

            } catch (err) {
                console.error(err);
                alert("Impossible d'enregistrer les indices.");
            }
        });
    });


    /* ---------- RESET GLOBAL ---------- */

    const resetBtn = document.getElementById("reset-all-btn");
    if (resetBtn) {
        resetBtn.addEventListener("click", async () => {
            if (!confirm("Réinitialiser tous les indices ?")) return;

            const slug = getRestreamSlug();

            try {
                const res = await fetch(
                    `/restream/${slug}/indices/reset-all`,
                    { method: "POST" }
                );

                if (!res.ok) {
                    throw new Error("Erreur reset");
                }

            } catch (err) {
                console.error(err);
                alert("Impossible de réinitialiser les indices.");
            }
        });
    }


    /* ---------- SSE ---------- */

    initSSE();
});


/* =========================================================
   SERVER-SENT EVENTS
========================================================= */

function initSSE() {
    const slug = getRestreamSlug();
    const source = new EventSource(`/restream/${slug}/indices/stream`);

    source.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);

            for (const key in data.categories) {
                const items = data.categories[key].items || [];

                // Mise à jour de la source de vérité
                currentIndicesState[key] = items;

                const lines = itemsToLines(items);
                updateCategoryView(key, lines);

                // Si le formulaire de cette catégorie est ouvert, on resynchronise
                const form = document.querySelector(
                    `.edit-form[data-category="${key}"]:not(.hidden)`
                );

                if (form) {
                    const textarea = form.querySelector("textarea");
                    textarea.value = lines.join("\n");
                }
            }

        } catch (err) {
            console.error("Erreur SSE :", err);
        }
    };

    source.onerror = () => {
        console.warn("SSE déconnecté — reconnexion automatique par le navigateur");
    };
}
