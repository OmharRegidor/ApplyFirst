// Agad Apply Fill: pure helpers (link payload, page check, notice wording). No chrome.*, no DOM, no imports.
// Loaded as a classic script by Chrome (content script and service worker) and by `node --test`.
//
// Link format (shared with applyfirst/notify/compose.py build_apply_link):
//   <job url>#agad=<base64url(utf8(JSON.stringify({v:1,j,s,m}))) without "=" padding>
(function (root) {
  "use strict";

  const FRAGMENT_KEY = "agad";
  const MAX_SUBJECT = 200;
  const MAX_MESSAGE = 5000;
  // Worst case: every message unit JSON-escaped to 6 chars, then base64 grows it by 4/3.
  const MAX_ENCODED = Math.ceil(((MAX_SUBJECT + MAX_MESSAGE) * 6 + 64) * 4 / 3);
  const MARKER = "#" + FRAGMENT_KEY + "=";
  const B64URL_RE = /^[A-Za-z0-9_-]+$/;
  const JOB_ID_RE = /^\d{1,12}$/;
  const PATH_ID_RE = /-(\d+)\/?$/; // same rule as Python _ID_RE in applyfirst/sources/onlinejobsph.py
  const KEYS = ["v", "j", "s", "m"];

  // The raw text after "#agad=" when the hash is our marker, otherwise null.
  // An empty or malformed payload still returns a string, so the caller knows to strip it.
  function readFragment(hash) {
    if (typeof hash !== "string" || !hash.startsWith(MARKER)) return null;
    return hash.slice(MARKER.length);
  }

  function decodePayload(b64url) {
    if (typeof b64url !== "string" || b64url.length > MAX_ENCODED) return null;
    if (!B64URL_RE.test(b64url) || b64url.length % 4 === 1) return null;
    try {
      const b64 = b64url.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((b64url.length + 3) % 4);
      const bin = atob(b64);
      const bytes = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
      const text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
      return validate(JSON.parse(text));
    } catch (_) {
      return null;
    }
  }

  // Accepts only {v:1, j, s, m} with nothing extra, digits-only j, and both texts within caps.
  function validate(obj) {
    if (!obj || typeof obj !== "object" || Array.isArray(obj)) return null;
    const keys = Object.keys(obj);
    if (keys.length !== KEYS.length || !KEYS.every((k) => keys.includes(k))) return null;
    const { v, j, s, m } = obj;
    if (v !== 1 || typeof j !== "string" || !JOB_ID_RE.test(j)) return null;
    if (typeof s !== "string" || typeof m !== "string") return null;
    if (s.length > MAX_SUBJECT || m.length > MAX_MESSAGE) return null;
    if (s.length === 0 && m.length === 0) return null;
    return { j, s, m };
  }

  function jobIdFromPath(pathname) {
    if (typeof pathname !== "string") return null;
    const match = PATH_ID_RE.exec(pathname);
    return match ? match[1] : null;
  }

  // A payload may only save for the job on screen. Pages without a job number (the login page) accept any j.
  function jobMatchesPage(j, pathname) {
    const onPage = jobIdFromPath(pathname);
    return onPage === null || onPage === j;
  }

  // Wording for the notice when the pop-up's boxes are found. filled and skipped are box labels
  // ("Subject", "Message"). Nothing filled: offer Refill for both. Some skipped (they already had text):
  // offer Refill for just those. Otherwise a plain "filled" notice.
  function fillNotice(filled, skipped) {
    const list = (labels) => labels.join(" and ");
    if (!filled.length) {
      return { msg: "Saved text for this job is ready.", sub: "Refill replaces what is in the boxes now.", refill: true };
    }
    if (!skipped.length) return { msg: `${list(filled)} filled. Review, then Send.`, sub: null, refill: false };
    // Only two boxes exist, so here exactly one was filled and one was skipped.
    return {
      msg: `${list(filled)} filled. Your ${list(skipped)} box already had text, so it was left alone.`,
      sub: `Refill puts the saved ${list(skipped)} in that box.`,
      refill: true,
    };
  }

  function stripFragment(href) {
    const at = String(href).indexOf("#");
    return at === -1 ? String(href) : String(href).slice(0, at);
  }

  const api = Object.freeze({
    FRAGMENT_KEY, MAX_SUBJECT, MAX_MESSAGE,
    readFragment, decodePayload, validate, jobIdFromPath, jobMatchesPage, fillNotice, stripFragment,
  });
  root.AgadPayload = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : self);
