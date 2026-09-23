// Agad reveal, every page. Parser-blocking in the head so the start state is in place before
// the first paint, then one IntersectionObserver once the DOM is parsed. CSP-safe: classic
// script, no inline code, no dynamic code, no network, no storage.
// The contract: the reveal rules in app.css hide a target ONLY while <html data-rv> is there,
// and this file is the only thing that sets it. No IntersectionObserver, reduced motion, Data
// Saver, a small device, a thrown error, or a parse that takes over 3s, and the attribute is
// simply absent, which means the page is complete and fully visible.
(() => {
  "use strict";
  const d = document, root = d.documentElement, nav = navigator, c = nav.connection;
  const mq = matchMedia("(prefers-reduced-motion: reduce)");
  if (!("IntersectionObserver" in window) || mq.matches) return;
  if (nav.deviceMemory <= 2 || (c && (c.saveData || /2g/.test(c.effectiveType || "")))) return;

  // Must match the start-state rule in app.css, selector for selector (test R-1).
  const TARGETS = ".intro, .route > li, .facts > li, .mail, .faq__list details," +
    " .gmail__copy, .gmail__visual, .gmail__foot, .honest, .behind__note, .closing__grid > *," +
    " .dash__grid > *, .footer__grid > *";
  const SKIP = ".status, .mailcard, .preview, .gconf, .arrives";
  const DRAW = ".arrival__stage";

  root.dataset.rv = "on";
  let armed = false;
  const off = () => { if (!armed) root.removeAttribute("data-rv"); };
  setTimeout(off, 3000);                     // parsing took too long: show everything, plainly

  const start = () => {
    if (!root.dataset.rv) return;            // the watchdog already gave up
    try {
      const io = new IntersectionObserver((entries) => {
        entries.forEach((e) => {
          if (!e.isIntersecting) return;
          const t = e.target;                // one shot: it never hides again
          t.dataset[t.matches(DRAW) ? "rvDraw" : "rvItem"] = "in";
          io.unobserve(t);
        });
      }, { rootMargin: "0px 0px -10% 0px", threshold: 0 });
      d.querySelectorAll(TARGETS + "," + DRAW).forEach((el) => { if (!el.closest(SKIP)) io.observe(el); });
      // Focus inside a target not yet seen shows it, or the focus ring would be invisible.
      d.addEventListener("focusin", (e) => {
        for (let t = e.target; t && (t = t.closest(TARGETS)); t = t.parentElement)
          if (!t.closest(SKIP)) { t.dataset.rvItem = "in"; io.unobserve(t); }
      });
      armed = true;
    } catch (_) { root.removeAttribute("data-rv"); }
  };
  if (d.readyState === "loading") d.addEventListener("DOMContentLoaded", start, { once: true });
  else start();

  // Reduced motion switched on mid-visit: drop the layer, nothing is left half faded.
  if (mq.addEventListener) mq.addEventListener("change", () => {
    if (mq.matches) root.removeAttribute("data-rv");
  });
})();
