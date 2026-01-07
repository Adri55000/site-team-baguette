// static/js/api/match_results_racetime.js
(function () {
  function setFeedback(el, kind, message) {
    // kind: "info" | "error"
    el.className = kind === "error" ? "admin-warning" : "admin-info";
    el.textContent = message;
  }

  document.addEventListener("DOMContentLoaded", () => {
    const toolbar = document.getElementById("racetime-toolbar");
    const btn = document.getElementById("racetime-prefill-btn");
    const feedback = document.getElementById("racetime-feedback");

    if (!toolbar || !btn) return;

    btn.addEventListener("click", async () => {
      const prefillUrl = (toolbar.dataset.prefillUrl || "").trim();
      const racetimeRoom = (toolbar.dataset.racetimeRoom || "").trim();

      if (feedback) setFeedback(feedback, "info", "Chargement des résultats depuis racetime…");
      btn.disabled = true;

      try {
        if (!prefillUrl) {
          // Template not wired (defensive)
          const msg =
            "Le pré-remplissage racetime est prêt côté UI, mais le backend n’est pas encore branché.";
          if (feedback) setFeedback(feedback, "info", msg);
          console.warn("[racetime] prefill not connected yet", { racetimeRoom });
          return;
        }

        const res = await fetch(prefillUrl, {
          headers: { Accept: "application/json" },
          credentials: "same-origin",
        });

        // Try to parse JSON even on non-2xx to extract {error}
        let data = null;
        try {
          data = await res.json();
        } catch (_) {
          // ignore
        }

        if (!res.ok) {
          const msg = (data && data.error) ? data.error : `Erreur HTTP ${res.status}`;
          throw new Error(msg);
        }

        if (!data || data.ok !== true) {
          const msg = (data && data.error) ? data.error : "Réponse invalide.";
          throw new Error(msg);
        }

        if (!Array.isArray(data.results)) {
          throw new Error("Réponse invalide (results manquant).");
        }

        // Fill inputs
        for (const r of data.results) {
          if (!r || typeof r.team_id === "undefined") continue;
          const input = document.querySelector(`input[name="result_${r.team_id}"]`);
          if (input) input.value = String(r.raw || "").toUpperCase();
        }

        // Optional: show meta hints (missing users / empty results)
        const missingTeams = data.meta && data.meta.missing_users_by_team
          ? Object.keys(data.meta.missing_users_by_team)
          : [];
        const emptyTeams = data.meta && Array.isArray(data.meta.empty_results)
          ? data.meta.empty_results
          : [];

        if (missingTeams.length || emptyTeams.length) {
          const parts = ["Champs pré-remplis depuis racetime (non enregistré)."];
          if (missingTeams.length) parts.push("Attention : correspondance incomplète pour certaines équipes.");
          if (emptyTeams.length) parts.push("Attention : certains temps sont indisponibles.");
          if (feedback) setFeedback(feedback, "info", parts.join(" "));
        } else {
          if (feedback) setFeedback(feedback, "info", "Champs pré-remplis depuis racetime (non enregistré).");
        }
      } catch (e) {
        const msg = (e && e.message) ? e.message : "Impossible de récupérer les résultats depuis racetime.";
        if (feedback) setFeedback(feedback, "error", msg);
        console.error("[racetime] prefill error", e);
      } finally {
        btn.disabled = false;
      }
    });
  });
})();
