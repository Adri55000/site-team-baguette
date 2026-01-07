(() => {
  const root = document.querySelector(".interview-ranking");
  if (!root) return;

  const POLL_MS = 2000;

  // Recommandé : passer l'URL depuis le template:
  // <div class="interview-ranking" data-url="..."></div>
  const dataUrl = root.dataset.url;
  if (!dataUrl) {
    // Pas d'URL => on ne fait rien (évite erreurs en boucle)
    return;
  }

  let timerId = null;
  let lastSignature = "";
  let isFetching = false;

  function escapeHtml(s) {
    return String(s ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function normalizeRow(row) {
    return {
      name: String(row?.name ?? ""),
      twitch: String(row?.twitch ?? ""),
      status: String(row?.status ?? ""),
      time: String(row?.time ?? ""),
    };
  }

  function signatureFor(payload) {
    try {
      return JSON.stringify(payload);
    } catch {
      return "";
    }
  }

  function resultLabel(r) {
    if (r.status === "done") return r.time || "DONE";
    if (r.status === "dnf") return "DNF";
    if (r.status === "dq") return "DQ";
    if (r.status === "in_progress") return "En cours";
    return (r.status || "").toUpperCase();
  }

  function render(payload) {
    const top = Array.isArray(payload?.top) ? payload.top.map(normalizeRow) : [];

    const headerHtml = `
      <div class="interview-row interview-row--head">
        <div class="col-rank">#</div>
        <div class="col-name">Coureur</div>
        <div class="col-twitch">Twitch</div>
        <div class="col-time">Résultat</div>
      </div>
    `;

    const rowsHtml = top
      .map((r, idx) => {
        const rank = idx + 1;
        return `
          <div class="interview-row">
            <div class="col-rank">${rank}</div>
            <div class="col-name">${escapeHtml(r.name)}</div>
            <div class="col-twitch">${escapeHtml(r.twitch)}</div>
            <div class="col-time">${escapeHtml(resultLabel(r))}</div>
          </div>
        `;
      })
      .join("");

    root.innerHTML = headerHtml + rowsHtml;
  }

  async function tick() {
    if (isFetching) return;
    isFetching = true;

    try {
      const res = await fetch(dataUrl, { cache: "no-store" });

      // Même si ce n'est pas 200, on tente de lire le JSON,
      // mais on ne casse pas l'overlay si ça échoue.
      const data = await res.json();

      if (!data || data.ok !== true) {
        return; // best effort : on garde l'affichage précédent
      }

      const sig = signatureFor(data);
      if (sig && sig === lastSignature) return;
      lastSignature = sig;

      render(data);
    } catch (_) {
      // silence : overlay ne doit pas spam / casser
    } finally {
      isFetching = false;
    }
  }

  tick();
  timerId = window.setInterval(tick, POLL_MS);

  window.addEventListener("beforeunload", () => {
    if (timerId) window.clearInterval(timerId);
  });
})();
