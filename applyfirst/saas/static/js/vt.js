// Agad page-transition glue, before first paint. CSP-safe. Spec: onboarding-motion.md section 5.
(() => {
  "use strict";
  const d = document, root = d.documentElement, nav = navigator, now = Date.now;
  const S = (() => { try { return sessionStorage; } catch (_) { return null; } })();
  const get = (k) => { try { return S.getItem(k); } catch (_) { return null; } };
  const put = (k, v) => { try { S.setItem(k, v); } catch (_) { /* blocked */ } };
  const del = (k) => { try { S.removeItem(k); } catch (_) { /* blocked */ } };
  const peek = (k, ms) => { const v = get(k), i = v ? v.lastIndexOf("|") : -1; return i > -1 && now() - v.slice(i + 1) < ms ? v.slice(0, i) : null; };
  const take = (k, ms) => { const v = peek(k, ms); del(k); return v; };
  const mem = nav.deviceMemory, c = nav.connection;
  const tier = matchMedia("(prefers-reduced-motion: reduce)").matches ? "off"
    : mem <= 2 || (c && c.saveData) || peek("af:motion", 864e5) === "lite" ? "lite" : "full";
  root.dataset.motion = tier;
  const step = parseInt(root.dataset.step, 10);
  const seen = (el) => { if (!el) return false; const r = el.getBoundingClientRect(); return r.bottom > 0 && r.top < innerHeight; };
  const low = (t) => (t || "").trim().toLowerCase();
  const name = (t) => { let h = 2166136261; for (const ch of low(t)) h = Math.imul(h ^ ch.codePointAt(0), 16777619); return "kw-" + (h >>> 0).toString(36); };
  const chips = () => d.querySelectorAll("[data-vt-kw]");
  const trav = (a) => !!a && a.navigationType === "traverse";
  // Names last one transition: cleared before naming and on every reveal, back/forward cache included.
  const unname = () => { delete root.dataset.vt; chips().forEach((el) => { el.style.viewTransitionName = ""; }); };

  // Old page, before capture: name only what is on screen now. Back/forward names nothing.
  addEventListener("pageswap", (e) => {
    unname();
    const o = { s: step, t: [], k: [], at: now() };
    if (e.viewTransition && !trav(e.activation)) {
      const q = (s) => seen(d.querySelector(s)), add = peek("af:kw", 60000), cap = tier === "full" && scrollY <= 120 ? 8 : 0;
      if (q(".site-header")) o.t.push("head");
      if (peek("af:act", 60000) !== null) { if (tier === "full" && q(".activate .btn--primary")) o.t.push("act"); } else if (q(".stepper__marker")) o.t.push("rail");
      chips().forEach((el) => {
        const n = name(el.dataset.vtKw);
        if (seen(el) && !o.k.includes(n) && (low(el.dataset.vtKw) === add || (el.classList.contains("kw") && o.k.length < cap))) { el.style.viewTransitionName = n; o.k.push(n); }
      });
      root.dataset.vt = o.t.join(" ");
    }
    put("af:vt", JSON.stringify(o));
  });

  // New page: arrival flags only add emphasis.
  const arrive = () => {
    const a = [], kw = take("af:kw", 60000);
    if (take("af:gmail", 600000) !== null) a.push("gmail");
    if (take("af:act", 60000) !== null && step === 0) a.push("activated");
    else if (step === 0 && S) root.dataset.still = "";
    root.dataset.arrive = a.join(" ");
    root.dataset.t0 = Math.round(performance.now());
    if (kw !== null) {
      const mark = () => chips().forEach((el) => { if (el.classList.contains("kw") && low(el.dataset.vtKw) === kw) el.dataset.new = ""; });
      if (d.readyState === "loading") d.addEventListener("DOMContentLoaded", mark, { once: true }); else mark();
    }
    d.dispatchEvent(new Event("af:arrive"));                     // motion.js may have run before this
    return kw;
  };
  if (!("onpagereveal" in window)) { arrive(); return; }
  addEventListener("pagereveal", (e) => {
    unname();
    d.querySelectorAll("[data-new]").forEach((el) => { delete el.dataset.new; });
    const kw = arrive(), vt = e.viewTransition, a = root.dataset.arrive.includes("activated"), nv = window.navigation;
    let o = null;
    try { o = JSON.parse(get("af:vt")); } catch (_) { /* none */ }
    del("af:vt");
    if (!vt) return;
    if (mem <= 1) return vt.skipTransition();
    if (!o || now() - o.at > 10000) return;
    if (!trav(nv && nv.activation)) {
      root.dataset.vt = o.t.filter((t) => t !== "act" || a).join(" ");
      const want = new Set(o.k);
      if (kw !== null) want.add(name(kw));
      chips().forEach((el) => { const n = name(el.dataset.vtKw); if (want.delete(n)) el.style.viewTransitionName = n; });
    }
    if (vt.types && o.s >= 0 && step >= 0) vt.types.add(a ? "activate" : o.s === step ? "same" : o.s > step ? "back" : "forward");
  });
})();
