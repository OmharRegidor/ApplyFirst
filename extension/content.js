// Agad Apply Fill content script, runs on https://www.onlinejobs.ph/* only.
// 1. Reads #agad=<payload> from the Apply link, hands it to the service worker, removes it from the address bar.
// 2. On a job page, loads the saved Subject and Message for that job.
// 3. When the Apply pop-up opens, fills only empty boxes the first time, then offers Refill.
// It never clicks, submits or sends anything, and writes page text only through .value and textContent.
(() => {
  "use strict";
  const P = globalThis.AgadPayload;
  if (!P || globalThis.__agadApplyFill) return;
  globalThis.__agadApplyFill = true;

  const NOTICE_MS = 3000;
  const FIND_MS = 8000;
  const COPY_FLASH_MS = 1500;
  const DIALOG_SEL = '[role="dialog"], [role="alertdialog"], dialog[open], .modal.show, .modal.in, .modal[style*="display: block"]';
  const SUBJECT_RE = /subject/i;
  const MESSAGE_RE = /message|letter|cover|body|content/i;
  const NOT_SUBJECT_RE = /salary|rate|price|email|phone|url|link|search|name/i;
  const APPLY_RE = /apply/i;

  const state = {
    saved: null, loading: Promise.resolve(), opens: 0, dialog: null, handled: false, busy: false, findTimer: 0,
  };

  // ---------- messaging ----------
  async function send(msg) {
    try { return (await chrome.runtime.sendMessage(msg)) ?? null; } catch (_) { return null; }
  }

  // ---------- intake: save, strip, load ----------
  // A payload for a different job than the one on screen is stripped but never saved.
  // fromHash: the fragment arrived by hashchange (a link on the page itself), so the service worker
  // keeps a same-job entry saved in the last 10 minutes instead of overwriting it.
  function intake(fromHash) {
    const raw = P.readFragment(location.hash);
    let saving = Promise.resolve();
    if (raw !== null) {
      const data = P.decodePayload(raw);
      if (data && P.jobMatchesPage(data.j, location.pathname)) {
        saving = send({ type: "agad:save", j: data.j, s: data.s, m: data.m, keepRecent: fromHash });
      }
      history.replaceState(history.state, "", P.stripFragment(location.href));
    }
    const j = P.jobIdFromPath(location.pathname);
    state.opens = 0;
    state.loading = !j ? Promise.resolve() : saving
      .then(() => send({ type: "agad:load", j }))
      .then((r) => { state.saved = r && typeof r.s === "string" && typeof r.m === "string" ? r : null; });
  }

  // ---------- finding the pop-up and its boxes ----------
  const isVisible = (el) => el.isConnected &&
    (el.checkVisibility ? el.checkVisibility({ checkVisibilityCSS: true }) : el.getClientRects().length > 0);
  const usable = (el) => isVisible(el) && !el.disabled && !el.readOnly;
  const describe = (el) => [el.name, el.id, el.placeholder, el.getAttribute("aria-label"),
    ...Array.from(el.labels || [], (l) => l.textContent)].filter(Boolean).join(" ");

  function pick(list, re, skipRe) {
    const named = list.find((el) => re.test(describe(el)));
    if (named) return named;
    const rest = skipRe ? list.filter((el) => !skipRe.test(describe(el))) : list;
    return rest.length === 1 ? rest[0] : null;
  }

  function findFields(dialog) {
    const inputs = Array.from(dialog.querySelectorAll('input[type="text"], input:not([type])')).filter(usable);
    const areas = Array.from(dialog.querySelectorAll("textarea")).filter(usable);
    return { subject: pick(inputs, SUBJECT_RE, NOT_SUBJECT_RE), message: pick(areas, MESSAGE_RE) };
  }

  const findDialog = () => Array.from(document.querySelectorAll(DIALOG_SEL))
    .find((d) => isVisible(d) && d.querySelector("textarea")) || null;

  // ---------- filling ----------
  function put(el, text) {
    el.value = text;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  // Fills each box that has a box and saved text. With onlyEmpty, a box the owner already typed in is left
  // alone and listed in skipped. With only, just those labels are filled.
  function fill(fields, saved, onlyEmpty, only) {
    const done = [], skipped = [];
    for (const [label, el, text] of [["Subject", fields.subject, saved.s], ["Message", fields.message, saved.m]]) {
      if (!el || !text || (only && !only.includes(label))) continue;
      if (onlyEmpty && el.value.trim() !== "") { skipped.push(label); continue; }
      put(el, text);
      done.push(label);
    }
    return { done, skipped };
  }

  // Runs on every page change while a pop-up is open, until its boxes are found once.
  async function handle(dialog) {
    if (state.busy) return;
    state.busy = true;
    const first = state.opens === 1;
    await state.loading;
    state.busy = false;
    if (state.dialog !== dialog) { schedule(); return; } // a newer pop-up was skipped while we waited
    if (state.handled) return;
    const fields = findFields(dialog);
    if (!fields.subject && !fields.message) { if (!state.findTimer) armFindTimer(); return; }
    state.handled = true;
    clearTimeout(state.findTimer);
    state.findTimer = 0;
    const saved = state.saved;
    if (!saved) {
      UI.notice({ tone: "none", msg: "No saved text for this job",
        sub: "Open the job from your Agad email to bring it over.", ms: NOTICE_MS });
      return;
    }
    const { done, skipped } = first ? fill(fields, saved, true) : { done: [], skipped: [] };
    const text = P.fillNotice(done, skipped);
    if (!text.refill) {
      UI.notice({ tone: "ok", msg: text.msg, ms: NOTICE_MS });
    } else {
      // After a partial first fill, Refill touches only the skipped box, so the box just filled is not reset.
      const only = done.length ? skipped : null;
      UI.notice({ tone: "ok", msg: text.msg, sub: text.sub,
        action: { label: "Refill", done: "Refilled", run: () => fill(findFields(dialog), saved, false, only).done.length > 0 },
        until: dialog });
    }
    const lost = (saved.s && !fields.subject) || (saved.m && !fields.message);
    if (lost) UI.copyPanel(saved);
  }

  function armFindTimer() {
    clearTimeout(state.findTimer);
    state.handled = false;
    state.findTimer = setTimeout(async () => {
      state.findTimer = 0;
      await state.loading;
      if (!state.saved || state.handled) return;
      UI.notice({ tone: "warn", msg: "Fields not found, copy below" });
      UI.copyPanel(state.saved);
    }, FIND_MS);
  }

  // ---------- watching the page ----------
  let scheduled = false;
  function check() {
    scheduled = false;
    if (state.dialog && !isVisible(state.dialog)) {
      state.dialog = null;
      clearTimeout(state.findTimer); // so "Fields not found" never shows after the pop-up closed
      state.findTimer = 0;
      UI.closeTied();
    }
    if (!state.dialog) {
      state.dialog = findDialog();
      if (!state.dialog) return;
      state.opens += 1;
      state.handled = false;
    }
    if (!state.handled) handle(state.dialog);
  }
  const schedule = () => { if (!scheduled) { scheduled = true; setTimeout(check, 60); } };

  document.addEventListener("click", (e) => {
    if (!e.isTrusted || state.dialog) return; // clicks inside an open pop-up (Send, Submit Application) are ignored
    const target = e.target instanceof Element ? e.target.closest('button, a, [role="button"], input[type="submit"], input[type="button"]') : null;
    if (target && APPLY_RE.test(target.textContent || target.value || "")) armFindTimer();
  }, true);

  // ---------- UI: notice and copy panel, inside a closed Shadow DOM ----------
  const UI = (() => {
    let root = null, wrap = null, noticeBox = null, panelBox = null, tiedTo = null;
    const CSS = `
      :host { all: initial; }
      .agad { display: flex; flex-direction: column; gap: 8px; color: #0B2545;
        font: 13px/1.45 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
      .box { position: relative; background: #EEF7FD; border: 1px solid #BFE3F8; border-radius: 8px; overflow: hidden;
        box-shadow: 0 1px 2px rgba(11, 37, 69, 0.10), 0 8px 24px rgba(11, 37, 69, 0.16);
        animation: agad-in 0.22s cubic-bezier(0.16, 1, 0.3, 1) both; }
      .row { display: flex; align-items: flex-start; gap: 10px; padding: 10px 8px 10px 12px; }
      .dot { flex: 0 0 auto; width: 8px; height: 8px; border-radius: 50%; margin-top: 6px; }
      .dot.ok { background: #1F8A4C; } .dot.warn { background: #C98A12; } .dot.none { background: #7A8794; }
      .text { flex: 1 1 auto; min-width: 0; overflow-wrap: anywhere; }
      .src { display: block; font-size: 11px; color: #3E5670; letter-spacing: 0.02em; }
      .msg { display: block; font-weight: 600; font-size: 13.5px; text-wrap: pretty; }
      .sub { display: block; color: #3E5670; margin-top: 2px; text-wrap: pretty; }
      button { font: inherit; cursor: pointer; touch-action: manipulation; -webkit-tap-highlight-color: transparent; }
      .close { flex: 0 0 auto; width: 28px; height: 28px; margin: -4px 0 0; padding: 0; border: 0; background: transparent;
        color: #3E5670; border-radius: 6px; font-size: 18px; line-height: 1; }
      .close:hover { background: #BFE3F8; color: #0B2545; }
      .close:focus-visible, .btn:focus-visible { outline: 2px solid #0B6BC7; outline-offset: 2px; }
      .actions { display: flex; gap: 8px; padding: 0 12px 12px 30px; }
      .btn { font: 600 13px/1 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; background: #0B6BC7; color: #FFFFFF;
        border: 0; border-radius: 6px; padding: 9px 16px; min-height: 34px; transition: background-color 0.15s ease; }
      .btn:hover { background: #095AA8; }
      .btn.done { background: #1A7F45; } /* mockup #1F8A4C darkened: white text needs 4.5:1 */
      .btn.fail { background: #FFFFFF; color: #A3341F; box-shadow: inset 0 0 0 1px #E8B4A8; }
      .timer { position: absolute; left: 0; right: 0; bottom: 0; height: 3px; background: #BFE3F8; }
      .timer i { display: block; height: 100%; background: #0B6BC7; transform-origin: left center;
        animation: agad-drain var(--ms, 3s) linear forwards; }
      .copy { padding: 10px 12px 12px; display: flex; flex-direction: column; gap: 10px; }
      .copy-head { display: flex; justify-content: space-between; align-items: center; margin: 0 -4px -4px 0; }
      .copy-head b { font-size: 13px; font-weight: 600; }
      .item { display: flex; flex-direction: column; gap: 6px; }
      .k { font-size: 11px; color: #3E5670; }
      .preview { background: #FFFFFF; border: 1px solid #BFE3F8; border-radius: 6px; padding: 6px 8px; }
      .clip { overflow: hidden; overflow-wrap: anywhere; display: -webkit-box; -webkit-box-orient: vertical; }
      .one .clip { -webkit-line-clamp: 1; } .two .clip { -webkit-line-clamp: 2; }
      .item .btn { align-self: flex-start; }
      @keyframes agad-in { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
      @keyframes agad-drain { from { transform: scaleX(1); } to { transform: scaleX(0); } }
      @media (prefers-reduced-motion: reduce) {
        .box { animation: none; }
        .timer i { animation: none; transform: scaleX(0.5); }
      }`;

    function el(tag, cls, text) {
      const n = document.createElement(tag);
      if (cls) n.className = cls;
      if (text != null) n.textContent = text;
      return n;
    }

    function button(cls, text, onClick, ariaLabel) {
      const b = el("button", cls, text);
      b.type = "button";
      if (ariaLabel) b.setAttribute("aria-label", ariaLabel);
      b.addEventListener("click", onClick);
      return b;
    }

    function mount() {
      if (wrap && wrap.isConnected) return;
      const host = document.createElement("agad-apply-fill");
      for (const [k, v] of [["position", "fixed"], ["left", "16px"], ["bottom", "16px"], ["z-index", "2147483647"],
        ["width", "280px"], ["max-width", "calc(100vw - 32px)"], ["display", "block"]]) host.style.setProperty(k, v, "important");
      root = host.attachShadow({ mode: "closed" });
      try {
        const sheet = new CSSStyleSheet();
        sheet.replaceSync(CSS);
        root.adoptedStyleSheets = [sheet];
      } catch (_) {
        root.appendChild(el("style", null, CSS));
      }
      wrap = el("div", "agad");
      wrap.setAttribute("aria-live", "polite");
      root.appendChild(wrap);
      document.documentElement.appendChild(host);
    }

    const drop = (box) => { if (box) box.remove(); };

    // Auto-dismiss after ms, paused while the pointer is over the box.
    function autoDismiss(box, ms) {
      const bar = el("div", "timer");
      const fillBar = el("i");
      fillBar.style.setProperty("--ms", `${ms}ms`);
      bar.appendChild(fillBar);
      box.appendChild(bar);
      let left = ms, started = Date.now(), t = setTimeout(() => drop(box), left);
      box.addEventListener("pointerenter", () => {
        clearTimeout(t);
        left -= Date.now() - started;
        fillBar.style.animationPlayState = "paused";
      });
      box.addEventListener("pointerleave", () => {
        started = Date.now();
        t = setTimeout(() => drop(box), Math.max(left, 600));
        fillBar.style.animationPlayState = "running";
      });
    }

    function notice({ tone, msg, sub, action, ms, until }) {
      mount();
      drop(noticeBox);
      const box = el("div", "box");
      box.setAttribute("role", "status");
      const row = el("div", "row");
      const dot = el("span", `dot ${tone}`);
      dot.setAttribute("aria-hidden", "true");
      const text = el("div", "text");
      const src = el("span", "src", "Agad apply fill");
      src.translate = false;
      text.append(src, el("span", "msg", msg));
      if (sub) text.appendChild(el("span", "sub", sub));
      row.append(dot, text, button("close", "×", () => drop(box), "Close notice"));
      box.appendChild(row);
      if (action) {
        const act = el("div", "actions");
        const b = button("btn", action.label, () => {
          if (b.classList.contains("done")) return;
          if (!action.run()) return;
          b.textContent = action.done;
          b.classList.add("done");
          setTimeout(() => drop(box), 900);
        });
        act.appendChild(b);
        box.appendChild(act);
      }
      if (ms) autoDismiss(box, ms);
      wrap.prepend(box);
      noticeBox = box;
      tiedTo = until ? box : null;
    }

    function copyItem(label, value, lines) {
      const item = el("div", "item");
      const preview = el("div", `preview ${lines}`);
      preview.appendChild(el("span", "clip", value));
      item.append(el("span", "k", label), preview);
      const idle = `Copy ${label}`;
      let reset = 0;
      const b = button("btn", idle, async () => {
        let ok = true;
        try { await navigator.clipboard.writeText(value); } catch (_) { ok = false; }
        clearTimeout(reset);
        b.classList.remove("done", "fail");
        b.textContent = ok ? "Copied" : "Copy failed";
        b.classList.add(ok ? "done" : "fail");
        reset = setTimeout(() => { b.textContent = idle; b.classList.remove("done", "fail"); }, COPY_FLASH_MS);
      });
      item.appendChild(b);
      return item;
    }

    function copyPanel(saved) {
      mount();
      drop(panelBox);
      const box = el("div", "box");
      const inner = el("div", "copy");
      const head = el("div", "copy-head");
      head.append(el("b", null, "Your saved text"), button("close", "×", () => drop(box), "Close saved text"));
      inner.appendChild(head);
      if (saved.s) inner.appendChild(copyItem("Subject", saved.s, "one"));
      if (saved.m) inner.appendChild(copyItem("Message", saved.m, "two"));
      box.appendChild(inner);
      wrap.appendChild(box);
      panelBox = box;
    }

    // Removes a notice that only makes sense while its pop-up is open (the Refill offer).
    function closeTied() { if (tiedTo) { drop(tiedTo); tiedTo = null; } }

    return { notice, copyPanel, closeTied };
  })();

  // ---------- start ----------
  intake(false);
  window.addEventListener("hashchange", () => { if (P.readFragment(location.hash) !== null) intake(true); });
  new MutationObserver(schedule).observe(document.documentElement, {
    childList: true, subtree: true, attributes: true, attributeFilter: ["class", "style", "open", "hidden", "aria-hidden"],
  });
  schedule();
})();
