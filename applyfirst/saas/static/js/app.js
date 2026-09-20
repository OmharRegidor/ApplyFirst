// ApplyFirst progressive enhancement. Every flow works without this file.
// CSP-safe: loaded with <script src defer>, no inline handlers, never builds HTML from strings,
// no dynamic code, and reads or writes text with textContent only.
(() => {
  "use strict";
  const live = (msg) => {
    const el = document.getElementById("live");
    if (el) { el.textContent = ""; setTimeout(() => { el.textContent = msg; }, 60); }
  };
  const label = (btn) => btn.querySelector(":scope > span:not(.visually-hidden)");
  const hasClipboard = !!(navigator.clipboard && window.isSecureContext);
  const canCopy = hasClipboard ||
    !!(document.queryCommandSupported && document.queryCommandSupported("copy"));

  async function copyText(text) {
    if (hasClipboard) {
      try { await navigator.clipboard.writeText(text); return true; } catch (_) { /* fall through */ }
    }
    const ta = document.createElement("textarea");  // old in-app browsers
    ta.value = text; ta.setAttribute("readonly", ""); ta.className = "visually-hidden";
    document.body.appendChild(ta); ta.select();
    let ok = false;
    try { ok = document.execCommand("copy"); } catch (_) { ok = false; }
    ta.remove();
    return ok;
  }

  // Copy buttons: data-copy="#preview-letter" copies that element's text, data-copy-url copies the page link.
  document.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-copy], [data-copy-url]");
    if (!btn) return;
    let text = location.href;
    if (btn.hasAttribute("data-copy")) {
      const src = document.querySelector(btn.getAttribute("data-copy"));
      if (!src) return;
      text = src.textContent;
    }
    if (!(await copyText(text))) return;   // the text stays selectable by hand
    const isUrl = btn.hasAttribute("data-copy-url");
    const span = label(btn);
    if (span) {
      if (!btn.dataset.label) btn.dataset.label = span.textContent;
      span.textContent = isUrl ? "Link copied" : "Copied";
      setTimeout(() => { span.textContent = btn.dataset.label; }, 4000);
    }
    live(isUrl ? "Link copied" : "Copied to clipboard");
  });

  // Bring a form field into view with its label, then focus it (links in the profile alert, blocked saves).
  const goTo = (field) => {
    const lbl = document.querySelector(`label[for="${field.id}"]`);
    (lbl || field).scrollIntoView({ block: "start" });
    field.focus({ preventScroll: true });
  };
  document.addEventListener("click", (e) => {
    const a = e.target.closest("#form-error a[href^='#f-']");
    const field = a && document.getElementById(a.getAttribute("href").slice(1));
    if (!field) return;
    e.preventDefault();
    goTo(field);
  });

  // The browser cuts a paste that would pass maxlength without a word. Say so by the field
  // (its hidden "<id>-cut" note). Counted like the server: newlines as one character.
  document.addEventListener("paste", (e) => {
    const el = e.target;
    const note = el && el.id && el.maxLength > 0 ? document.getElementById(`${el.id}-cut`) : null;
    if (!note) return;
    const text = ((e.clipboardData && e.clipboardData.getData("text")) || "").replace(/\r\n?/g, "\n");
    const next = el.value.length - (el.selectionEnd - el.selectionStart) + text.length;
    note.hidden = next <= el.maxLength;
    if (!note.hidden) live(note.textContent.trim());
  });

  // One submit per click, with a busy state. Submit buttons carry no name or value, so disabling is safe.
  document.addEventListener("submit", (e) => {
    // Browsers only enforce maxlength on text typed in this visit, so a saved value already over
    // the cap would post, bounce back and lose every other edit. Stop here and point at it instead.
    // Counted in characters (code points) like the server, not in UTF-16 units like maxLength.
    const capped = [...e.target.querySelectorAll("input[maxlength], textarea[maxlength]")];
    const over = capped.filter((f) => [...f.value].length > f.maxLength);
    if (over.length) {
      e.preventDefault();
      const box = e.target.querySelector("#form-error");
      // A field fixed since the page loaded drops its flag, its tie to the alert and its alert line.
      // Blank ones keep theirs. maxlength stops a fixed field from growing past its cap again.
      capped.filter((f) => !over.includes(f) && f.value.trim()).forEach((f) => {
        f.removeAttribute("aria-invalid");
        const ids = (f.getAttribute("aria-describedby") || "").split(" ").filter((id) => id && id !== "form-error");
        if (ids.length) f.setAttribute("aria-describedby", ids.join(" ")); else f.removeAttribute("aria-describedby");
        const a = box && box.querySelector(`a[href="#${f.id}"]`);
        if (a) a.closest("p").remove();   // removed, not hidden, so the next line's top margin goes too
      });
      over.forEach((f) => f.setAttribute("aria-invalid", "true"));
      if (box) {
        // Same as on load: bring the alert into view and focus it, so the reason is read and seen.
        // It now lists only what is still too long, and each line links to its field.
        (box.closest(".alert") || box).scrollIntoView({ block: "start" });
        box.focus({ preventScroll: true });
      } else {
        goTo(over[0]);
        live("Some of your text is too long. Shorten it, then save again.");
      }
      return;
    }
    const btn = e.submitter || e.target.querySelector("button[type=submit], button:not([type])");
    if (!btn || btn.disabled) return;
    btn.disabled = true;
    btn.dataset.state = "busy";
    const span = label(btn);
    if (!span || !btn.classList.contains("btn")) return;
    btn.dataset.label = span.textContent;
    span.textContent = btn.dataset.busy || "Saving";
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    const path = document.createElementNS(ns, "path");
    for (const [k, v] of [["class", "icon btn__spin"], ["width", "16"], ["height", "16"], ["viewBox", "0 0 24 24"],
      ["fill", "none"], ["stroke", "currentColor"], ["stroke-width", "2"], ["stroke-linecap", "round"],
      ["stroke-linejoin", "round"], ["aria-hidden", "true"], ["focusable", "false"]]) svg.setAttribute(k, v);
    path.setAttribute("d", "M21 12a9 9 0 1 1-6.219-8.56");
    svg.appendChild(path);
    btn.insertBefore(svg, btn.firstChild);
  });

  // Re-enable buttons when the page comes back from the back/forward cache.
  window.addEventListener("pageshow", (e) => {
    if (!e.persisted) return;
    document.querySelectorAll("button[data-state=busy]").forEach((btn) => {
      btn.disabled = false;
      delete btn.dataset.state;
      const spin = btn.querySelector(".btn__spin");
      if (spin) spin.remove();
      const span = label(btn);
      if (span && btn.dataset.label) span.textContent = btn.dataset.label;
    });
  });

  // Copy buttons ship hidden, so they only appear when copying can work.
  if (canCopy) document.querySelectorAll("[hidden][data-copy], [hidden][data-copy-url]").forEach((b) => { b.hidden = false; });

  // Move focus to a page-level message (profile error, Gmail retry note) so keyboard and screen reader users land on it.
  const note = document.querySelector("[role=alert][tabindex='-1']");
  if (note) note.focus();
})();
