// ApplyFirst motion, after load. Deferred, the 5 app pages only. Spec: onboarding-motion.md section 6.
// Taps only arm one-shot flags for vt.js: never preventDefault, never wait for an animation. CSP-safe.
(() => {
  "use strict";
  const d = document, root = d.documentElement, nav = navigator;
  const arm = (k, v) => { try { sessionStorage.setItem(k, (v || "") + "|" + Date.now()); } catch (_) { /* blocked */ } };
  const label = (el) => el.querySelector(":scope > span:not(.visually-hidden)");

  // Connect Gmail: say where we are going, and arm the arrival on the page Google sends you back to.
  d.addEventListener("click", (e) => {
    const a = e.target.closest && e.target.closest('a[href="/auth/connect-gmail"]');
    if (!a || e.button || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    arm("af:gmail");
    const s = label(a);
    if (s && !a.dataset.label) { a.dataset.label = s.textContent; s.textContent = "Opening Google's page"; a.dataset.state = "busy"; }
  });
  addEventListener("pageshow", (e) => {                     // back from Google through the back/forward cache
    if (e.persisted) d.querySelectorAll("a[data-label]").forEach((a) => { const s = label(a); if (s) s.textContent = a.dataset.label; delete a.dataset.label; delete a.dataset.state; });
  });

  // Submits, capture phase: flags only.
  d.addEventListener("submit", (e) => {
    const f = e.target, action = f.getAttribute("action");
    if (action === "/onboarding/activate") {
      arm("af:act");
      if (root.dataset.motion !== "off" && f.querySelector(".btn--primary") && nav.vibrate) { try { nav.vibrate(12); } catch (_) { /* none */ } }
    } else if (action === "/onboarding/keywords" && f.elements.keyword) {
      const k = f.elements.keyword.value.trim().toLowerCase();
      if (k) arm("af:kw", k.slice(0, 60));
    }
  }, true);

  // Reduced motion switched on mid-way: jump every running animation to its end.
  const mq = matchMedia("(prefers-reduced-motion: reduce)");
  if (mq.addEventListener) mq.addEventListener("change", () => {
    if (!mq.matches) return;
    root.dataset.motion = "off";
    d.getAnimations().forEach((x) => { try { x.finish(); } catch (_) { x.cancel(); } });
  });

  // A struggling main thread in the first 3 s (Chromium): the rest of this tab gets the lite tier.
  const PO = window.PerformanceObserver;
  if (PO && PO.supportedEntryTypes && PO.supportedEntryTypes.includes("long-animation-frame")) {
    let blocked = 0;
    const po = new PO((list) => {
      list.getEntries().forEach((x) => { blocked += x.blockingDuration; });
      if (blocked > 200) { arm("af:motion", "lite"); po.disconnect(); }
    });
    po.observe({ type: "long-animation-frame", buffered: true });
    setTimeout(() => po.disconnect(), 3000);
  }

  // The one celebration: warm the file on Step 4, fire it once on the first live dashboard view.
  const c = nav.connection;
  const ok = root.dataset.motion === "full" && !(c && (c.saveData || /2g/.test(c.effectiveType || "")));
  const form = d.querySelector("form[data-burst-src]");
  if (form && ok) { const l = d.createElement("link"); l.rel = "prefetch"; l.href = form.dataset.burstSrc; d.head.appendChild(l); }
  const panel = d.querySelector(".status--live[data-fresh][data-burst-src]");
  if (!panel || !ok) return;

  const burst = (t0) => {
    if (!window.confetti || performance.now() - t0 > 2500) return;         // late is worse than never
    const r = panel.getBoundingClientRect(), p = panel.querySelector(".live i").getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio || 1, 3);
    const cv = d.createElement("canvas");
    cv.className = "burst";
    cv.setAttribute("aria-hidden", "true");
    cv.width = Math.round(r.width * dpr);                                  // device pixels: crisp on 2x and 3x
    cv.height = Math.round(r.height * dpr);
    panel.appendChild(cv);
    // create() on our own canvas, useWorker false. The library's default call needs a blob: Worker (blocked).
    const fire = window.confetti.create(cv, { resize: false, useWorker: false, disableForReducedMotion: true });
    const done = () => cv.remove();
    // One shot. Always pass colors: brand blues only, no white (it would blur into the white heading).
    fire({ particleCount: 48, angle: 5, spread: 80, startVelocity: 30 * dpr, ticks: 120, decay: 0.91,
      origin: { x: (p.left + p.width / 2 - r.left) / r.width, y: (p.top + p.height / 2 - r.top) / r.height },
      colors: ["#38AEEA", "#86CBF2", "#0B6BC7"], shapes: ["square", "circle"],
      scalar: 0.8 * dpr, gravity: 1.15 * dpr, disableForReducedMotion: true }).then(done, done);
    addEventListener("pagehide", () => { fire.reset(); done(); }, { once: true });
  };
  // vt.js sets the arrival flags at pagereveal, which can come after this deferred file has run.
  const peak = () => {
    if (!/activated/.test(root.dataset.arrive || "")) return;
    const t0 = +root.dataset.t0 || 0;
    const load = () => {
      if (!getComputedStyle(root).getPropertyValue("--ease-exit")) return;  // motion.css missing: no canvas in the flow
      if (window.confetti) return burst(t0);
      const s = d.createElement("script");
      s.src = panel.dataset.burstSrc;
      s.onload = () => burst(t0);                                          // a property set here, not an inline handler
      d.head.appendChild(s);
    };
    const idle = window.requestIdleCallback || ((f) => setTimeout(f, 0));
    setTimeout(() => idle(load, { timeout: 150 }), Math.max(0, 880 - (performance.now() - t0)));
  };
  if (root.dataset.t0) peak(); else d.addEventListener("af:arrive", peak, { once: true });
})();
