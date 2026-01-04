/* DEV Tracker interactions (with SSE)
 * - multi-root init
 * - POST updates per slot (only if can_edit)
 * - SSE stream receives full session JSON (participants[]) and updates UI
 * - avoids feedback loops (SSE apply never triggers POST)
 */

(() => {
  const GLOBAL_CATALOG = window.TRACKER_CATALOG || {};
  const STREAM_URL = window.TRACKER_STREAM_URL || null;

  const roots = document.querySelectorAll("[data-tracker-root]");
  if (!roots.length) return;

  // slot -> api
  const instancesBySlot = new Map();

  roots.forEach((root) => {
    const api = initTracker(root);
    if (api && typeof api.slot === "number") {
      instancesBySlot.set(api.slot, api);
    }
  });

  // One SSE connection for the whole page (session-wide)
  if (STREAM_URL) {
    try {
      const es = new EventSource(STREAM_URL);

      es.onmessage = (e) => {
        try {
          const session = JSON.parse(e.data);
          applySessionFromSse(session);
        } catch (err) {
          console.warn("[tracker] SSE parse error", err);
        }
      };

      es.onerror = () => {
        // EventSource auto-reconnects; keep it quiet
        // console.warn("[tracker] SSE error");
      };
    } catch (err) {
      console.warn("[tracker] SSE init failed", err);
    }
  }

  function applySessionFromSse(session) {
    if (!session || !Array.isArray(session.participants)) return;

    for (const p of session.participants) {
      const slot = Number(p?.slot);
      if (!Number.isFinite(slot)) continue;
      const api = instancesBySlot.get(slot);
      if (!api) continue;
      api.applyRemoteParticipant(p);
    }
  }

  function initTracker(root) {
    // ----- Per-root config from template -----
    const USE_STORAGE =
      root.dataset.trackerUseStorage
        ? root.dataset.trackerUseStorage !== "false"
        : (window.TRACKER_USE_STORAGE !== false);

    const STORAGE_KEY =
      root.dataset.trackerStorageKey ||
      (() => {
        const slot = Number(root.dataset.slot || 0);
        return slot ? `tb_tracker_preview_state_v1_slot${slot}` : "tb_tracker_preview_state_v1";
      })();

    const UPDATE_URL = root.dataset.trackerUpdateUrl || window.TRACKER_UPDATE_URL || null;

    // NEW: permissions (read-only mode for non editors)
    const CAN_EDIT =
      root.dataset.trackerCanEdit
        ? root.dataset.trackerCanEdit !== "false"
        : false;

    // State: prefer per-root JSON
    let baseState = null;
    if (root.dataset.trackerState) {
      try {
        baseState = JSON.parse(root.dataset.trackerState);
      } catch (e) {
        console.warn("[tracker] invalid data-tracker-state JSON", e);
      }
    }
    if (!baseState) baseState = window.TRACKER_STATE || {};

    const slot = Number(baseState?.slot || root.dataset.slot || 0) || 0;

    const catalog = GLOBAL_CATALOG;
    const itemsById = new Map((catalog.items || []).map((it) => [it.id, it]));

    let state = JSON.parse(JSON.stringify(baseState));

    // Standalone only: allow localStorage restore (per root)
    if (USE_STORAGE) {
      try {
        const saved = localStorage.getItem(STORAGE_KEY);
        if (saved) state = JSON.parse(saved);
      } catch {
        // ignore
      }
    }

    function getItemMeta(itemId) {
      return itemsById.get(itemId) || null;
    }

    function clamp(n, min, max) {
      return Math.max(min, Math.min(max, n));
    }

    function saveLocal() {
      if (!USE_STORAGE) return;
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
      } catch {
        // ignore
      }
    }

    // ----- Server save (session mode) -----
    let _serverSaveTimer = null;
    let _inflight = false;
    let _needsAnother = false;

    // When applying SSE updates, we must not POST back (avoid loops)
    let _suppressNetworkSaves = false;

    function scheduleServerSave() {
      if (!UPDATE_URL) return;
      if (!CAN_EDIT) return; // NEW: viewers never POST
      if (_suppressNetworkSaves) return;

      if (_serverSaveTimer) clearTimeout(_serverSaveTimer);
      _serverSaveTimer = setTimeout(() => {
        void flushServerSave();
      }, 200);
    }

    async function flushServerSave() {
      if (!UPDATE_URL) return;
      if (!CAN_EDIT) return; // NEW: viewers never POST
      if (_suppressNetworkSaves) return;

      if (_inflight) {
        _needsAnother = true;
        return;
      }

      _inflight = true;
      _needsAnother = false;

      try {
        const res = await fetch(UPDATE_URL, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ participant: state }),
        });

        if (!res.ok) {
          const txt = await res.text().catch(() => "");
          console.warn("[tracker] server save failed", res.status, txt);
        }
      } catch (e) {
        console.warn("[tracker] server save error", e);
      } finally {
        _inflight = false;
        if (_needsAnother) {
          _needsAnother = false;
          void flushServerSave();
        }
      }
    }

    // ----- Asset helpers -----
    function buildAssetUrl(itemMeta, level) {
      const dir = catalog.asset_dir || "";
      const base = itemMeta.asset_base || "";
      return `/static/${dir}/${base}${level}.png`;
    }

    // ----- Render helpers -----
    function renderItemSimple(itemId) {
      const itemMeta = getItemMeta(itemId);
      if (!itemMeta) return;

      const level = state.items?.[itemId] ?? 0;

      const nodes = root.querySelectorAll(
        `[data-item-id="${CSS.escape(itemId)}"] img`
      );
      nodes.forEach((img) => {
        img.src = buildAssetUrl(itemMeta, level);
      });

      const wrappers = root.querySelectorAll(
        `[data-item-id="${CSS.escape(itemId)}"][data-level]`
      );
      wrappers.forEach((w) => (w.dataset.level = String(level)));
    }

    function renderCounter(itemId) {
      const value = Number(state.items?.[itemId] ?? 0);
      const iconLevel = value > 0 ? 1 : 0;

      const wrappers = root.querySelectorAll(
        `[data-item-id="${CSS.escape(itemId)}"] .tracker-counter`
      );

      wrappers.forEach((w) => {
        w.dataset.value = String(value);
        w.dataset.iconLevel = String(iconLevel);

        const overlay = w.querySelector(".tracker-overlay");
        if (overlay) overlay.textContent = String(value);

        const img = w.querySelector("img");
        if (img) {
          const itemMeta = getItemMeta(itemId);
          if (itemMeta) img.src = buildAssetUrl(itemMeta, iconLevel);
        }
      });
    }

    function renderWallet(itemId) {
      const level = Number(state.items?.[itemId] ?? 1);

      const wrappers = root.querySelectorAll(
        `[data-item-id="${CSS.escape(itemId)}"] .tracker-wallet`
      );

      wrappers.forEach((w) => {
        w.dataset.level = String(level);

        const img = w.querySelector("img");
        if (img) {
          const itemMeta = getItemMeta(itemId);
          if (itemMeta) img.src = buildAssetUrl(itemMeta, level);
        }

        const overlay = w.querySelector(".tracker-overlay");
        if (overlay) {
          const bonus = Number(state.wallet_bonus ?? 0);
          overlay.textContent = bonus > 0 ? `+${bonus}` : "+0";
        }
      });
    }

    function cycleWalletBonus(delta) {
      const walletMeta = getItemMeta("wallet");
      const values =
        walletMeta &&
        Array.isArray(walletMeta.wallet_bonus_values) &&
        walletMeta.wallet_bonus_values.length
          ? walletMeta.wallet_bonus_values
          : [0, 300, 600, 900];

      const cur = Number(state.wallet_bonus ?? 0);
      let idx = values.indexOf(cur);
      if (idx === -1) idx = 0;

      idx = clamp(idx + delta, 0, values.length - 1);
      state.wallet_bonus = values[idx];

      renderWallet("wallet");
    }

    function renderDungeon(code) {
      const v = Number(state.dungeons?.[code] ?? 0);
      const el = root.querySelector(`[data-dungeon="${CSS.escape(code)}"]`);
      if (!el) return;

      el.dataset.dungeonState = String(v);

      el.classList.remove(
        "tracker-dungeon--off",
        "tracker-dungeon--todo",
        "tracker-dungeon--done"
      );
      if (v === 0) el.classList.add("tracker-dungeon--off");
      else if (v === 1) el.classList.add("tracker-dungeon--todo");
      else el.classList.add("tracker-dungeon--done");
    }

    function renderComposite(compositeId) {
      const flags = state[compositeId] || {};
      const group = root.querySelector(
        `[data-composite-id="${CSS.escape(compositeId)}"]`
      );
      if (!group) return;

      const overlays = group.querySelectorAll(
        ".tracker-composite-overlay[data-overlay-key]"
      );

      overlays.forEach((img) => {
        const key = img.dataset.overlayKey;
        const on = !!flags[key];
        img.classList.toggle("is-on", on);
      });
    }

    function renderAll() {
      if (state.items) {
        for (const [itemId, itemMeta] of itemsById.entries()) {
          if (itemMeta.kind === "composite") continue;
          if (itemMeta.kind === "counter") renderCounter(itemId);
          else if (itemMeta.kind === "wallet") renderWallet(itemId);
          else renderItemSimple(itemId);
        }
      }

      if (state.dungeons) {
        Object.keys(state.dungeons).forEach(renderDungeon);
      }

      renderComposite("tablets");
      renderComposite("triforces");
    }

    // ----- Update logic -----
    function cycleLevel(itemId, delta) {
      const meta = getItemMeta(itemId);
      if (!meta) return;

      const levels =
        Array.isArray(meta.level_values) && meta.level_values.length > 0
          ? meta.level_values
          : [0, 1];

      const curVal = Number(state.items?.[itemId] ?? levels[0]);
      let idx = levels.indexOf(curVal);
      if (idx === -1) idx = 0;

      idx = clamp(idx + delta, 0, levels.length - 1);
      const nextVal = levels[idx];

      state.items[itemId] = nextVal;

      if (meta.kind === "wallet") renderWallet(itemId);
      else renderItemSimple(itemId);
    }

    function updateCounter(itemId, delta) {
      const meta = getItemMeta(itemId);
      if (!meta) return;

      const step = Number(meta.counter_step ?? 1);
      const minV = Number(meta.counter_min ?? 0);
      const maxV = Number(meta.counter_max ?? 999999);

      let cur = Number(state.items?.[itemId] ?? 0);
      cur = cur + delta * step;
      cur = clamp(cur, minV, maxV);

      state.items[itemId] = cur;
      renderCounter(itemId);
    }

    function cycleDungeon(code, delta) {
      let cur = Number(state.dungeons?.[code] ?? 0);
      cur = clamp(cur + delta, 0, 2);
      state.dungeons[code] = cur;
      renderDungeon(code);
    }

    function toggleCompositeKey(compositeId, key, forceValue = null) {
      const obj = state[compositeId] || {};
      const next = forceValue === null ? !obj[key] : !!forceValue;
      obj[key] = next;
      state[compositeId] = obj;
      renderComposite(compositeId);
    }

    // ============================================================
    // PIXEL-PERFECT COMPOSITES
    // ============================================================
    const ALPHA_THRESHOLD = 20;

    const compositeHitCache = new Map();
    const compositeLoadPromises = new Map();

    function getCompositeElement(compositeId) {
      return root.querySelector(
        `[data-kind="composite"][data-composite-id="${CSS.escape(compositeId)}"]`
      );
    }

    function getCompositeOverlayImgs(compositeId) {
      const comp = getCompositeElement(compositeId);
      if (!comp) return [];
      const compositeBox = comp.querySelector(".tracker-composite");
      if (!compositeBox) return [];
      return Array.from(
        compositeBox.querySelectorAll(
          `.tracker-composite-overlay[data-overlay-key]`
        )
      );
    }

    function getCompositeOverlayOrder(compositeId) {
      const meta = getItemMeta(compositeId);
      if (meta && meta.overlays) return Object.keys(meta.overlays);
      const imgs = getCompositeOverlayImgs(compositeId);
      return imgs.map((img) => img.dataset.overlayKey).filter(Boolean);
    }

    function loadImageDataFromUrl(url) {
      return new Promise((resolve, reject) => {
        const img = new Image();
        img.onload = () => {
          const w = img.naturalWidth;
          const h = img.naturalHeight;
          const canvas = document.createElement("canvas");
          canvas.width = w;
          canvas.height = h;
          const ctx = canvas.getContext("2d", { willReadFrequently: true });
          ctx.drawImage(img, 0, 0);
          const imageData = ctx.getImageData(0, 0, w, h);
          resolve({ w, h, data: imageData.data });
        };
        img.onerror = () => reject(new Error(`Failed to load image: ${url}`));
        img.src = url;
      });
    }

    function ensureCompositeHitCache(compositeId) {
      if (compositeLoadPromises.has(compositeId)) {
        return compositeLoadPromises.get(compositeId);
      }

      const promise = (async () => {
        const overlays = getCompositeOverlayImgs(compositeId);
        const map = new Map();

        await Promise.all(
          overlays.map(async (imgEl) => {
            const key = imgEl.dataset.overlayKey;
            const src = imgEl.currentSrc || imgEl.src;
            if (!key || !src) return;
            const entry = await loadImageDataFromUrl(src);
            map.set(key, entry);
          })
        );

        compositeHitCache.set(compositeId, map);
      })().catch((err) => {
        console.warn(`[tracker] composite cache failed for ${compositeId}`, err);
      });

      compositeLoadPromises.set(compositeId, promise);
      return promise;
    }

    function getLocalPointInElement(ev, el) {
      const rect = el.getBoundingClientRect();
      const x = ev.clientX - rect.left;
      const y = ev.clientY - rect.top;
      return { x, y, w: rect.width, h: rect.height };
    }

    function mapToImageCoordsContain(local, imgW, imgH) {
      const scale = Math.min(local.w / imgW, local.h / imgH);
      const drawW = imgW * scale;
      const drawH = imgH * scale;
      const offX = (local.w - drawW) / 2;
      const offY = (local.h - drawH) / 2;

      const inX = local.x - offX;
      const inY = local.y - offY;

      if (inX < 0 || inY < 0 || inX > drawW || inY > drawH) return null;

      const ix = inX / scale;
      const iy = inY / scale;

      const px = clamp(Math.floor(ix), 0, imgW - 1);
      const py = clamp(Math.floor(iy), 0, imgH - 1);

      return { px, py };
    }

    function alphaAt(entry, px, py) {
      const idx = (py * entry.w + px) * 4 + 3;
      return entry.data[idx] || 0;
    }

    function pixelPerfectCompositeToggle(ev, delta) {
      const compositeRoot = ev.target.closest(
        `[data-kind="composite"][data-composite-id]`
      );
      if (!compositeRoot) return false;

      const compositeId = compositeRoot.dataset.compositeId;
      const compositeBox = compositeRoot.querySelector(".tracker-composite");
      if (!compositeId || !compositeBox) return false;

      const cacheMap = compositeHitCache.get(compositeId);
      if (!cacheMap || cacheMap.size === 0) return false;

      const local = getLocalPointInElement(ev, compositeBox);
      const order = getCompositeOverlayOrder(compositeId);

      for (const key of order) {
        const entry = cacheMap.get(key);
        if (!entry) continue;

        const mapped = mapToImageCoordsContain(local, entry.w, entry.h);
        if (!mapped) continue;

        const a = alphaAt(entry, mapped.px, mapped.py);
        if (a > ALPHA_THRESHOLD) {
          if (delta < 0) toggleCompositeKey(compositeId, key, false);
          else toggleCompositeKey(compositeId, key, null);
          return true;
        }
      }
      return false;
    }

    ["tablets", "triforces"].forEach((cid) => {
      const el = getCompositeElement(cid);
      if (!el) return;
      ensureCompositeHitCache(cid);
    });

    // ----- Event routing -----
    function handleInteraction(ev, delta) {
      const walletBonus = ev.target.closest(".tracker-wallet .tracker-overlay");
      if (walletBonus) {
        cycleWalletBonus(delta);
        return true;
      }

      if (ev.target.closest(`[data-kind="composite"][data-composite-id]`)) {
        const changed = pixelPerfectCompositeToggle(ev, delta);
        return !!changed;
      }

      const dungeon = ev.target.closest("[data-dungeon]");
      if (dungeon) {
        const code = dungeon.dataset.dungeon;
        cycleDungeon(code, delta);
        return true;
      }

      const item = ev.target.closest("[data-item-id]");
      if (!item) return false;

      const itemId = item.dataset.itemId;
      const kind = item.dataset.kind || "cycle";
      const meta = getItemMeta(itemId);

      if (kind === "counter" || meta?.kind === "counter") {
        updateCounter(itemId, delta);
        return true;
      }

      if (kind === "wallet" || meta?.kind === "wallet") {
        cycleLevel(itemId, delta);
        return true;
      }

      cycleLevel(itemId, delta);
      return true;
    }

    function afterChangePersist() {
      saveLocal();
      scheduleServerSave();
    }

    // NEW: bind interactions only for editors
    if (CAN_EDIT) {
      root.addEventListener("click", (ev) => {
        const changed = handleInteraction(ev, +1);
        if (changed) afterChangePersist();
      });

      root.addEventListener("contextmenu", (ev) => {
        ev.preventDefault();
        const changed = handleInteraction(ev, -1);
        if (changed) afterChangePersist();
      });
    } else {
      // read-only mode (viewers)
      root.classList.add("is-readonly");
      // prevent browser menu on right click (clean UX)
      root.addEventListener("contextmenu", (ev) => ev.preventDefault());
    }

    // --- Public API for SSE apply ---
    function applyRemoteParticipant(participant) {
      if (!participant || typeof participant !== "object") return;
      // Avoid overwriting wrong slot
      const remoteSlot = Number(participant.slot);
      if (slot && remoteSlot && remoteSlot !== slot) return;

      _suppressNetworkSaves = true;
      try {
        state = JSON.parse(JSON.stringify(participant));
        renderAll();
        // Keep localStorage in sync (even in read-only, helps refresh keep last seen state)
        saveLocal();
      } finally {
        _suppressNetworkSaves = false;
      }
    }

    renderAll();

    return { slot, applyRemoteParticipant };
  }
})();
