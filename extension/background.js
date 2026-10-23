// Agad Apply Fill service worker. The only place that touches chrome.storage.session.
// Content scripts cannot read session storage at its default (trusted-only) access level,
// and page scripts never can, so the text for each job lives here and is handed out on request.
"use strict";
importScripts("lib/payload.js");

const SITE = "https://www.onlinejobs.ph/";
const PREFIX = "agad:job:";
const MAX_AGE_MS = 24 * 60 * 60 * 1000;
const MAX_ENTRIES = 50;
const RECENT_MS = 10 * 60 * 1000;
const store = chrome.storage.session;

const keyFor = (j) => PREFIX + j;
const isFresh = (entry, now) =>
  !!entry && typeof entry.savedAt === "number" && now - entry.savedAt < MAX_AGE_MS;

// Drops entries older than 24 hours, then the oldest ones beyond 50.
async function prune(now) {
  const all = await store.get(null);
  const entries = Object.entries(all).filter(([k]) => k.startsWith(PREFIX));
  const stale = entries.filter(([, v]) => !isFresh(v, now)).map(([k]) => k);
  const fresh = entries.filter(([, v]) => isFresh(v, now)).sort((a, b) => b[1].savedAt - a[1].savedAt);
  const extra = fresh.slice(MAX_ENTRIES).map(([k]) => k);
  if (stale.length + extra.length) await store.remove(stale.concat(extra));
}

const pathOf = (url) => { try { return new URL(url).pathname; } catch (_) { return null; } };

// Saves only for the job on the sending page (any job from a page without a job number).
// keepRecent (set when the text arrived by an in-page hashchange) never overwrites a save under 10 minutes old.
async function save(msg, sender) {
  const clean = AgadPayload.validate({ v: 1, j: msg.j, s: msg.s, m: msg.m });
  const path = pathOf(sender.url);
  if (!clean || path === null || !AgadPayload.jobMatchesPage(clean.j, path)) return { ok: false }; // fails closed
  const key = keyFor(clean.j);
  const now = Date.now();
  if (msg.keepRecent === true) {
    const prev = (await store.get(key))[key];
    if (prev && typeof prev.savedAt === "number" && now - prev.savedAt < RECENT_MS) return { ok: true, kept: true };
  }
  await store.set({ [key]: { s: clean.s, m: clean.m, savedAt: now } });
  await prune(now);
  return { ok: true };
}

async function load(msg) {
  if (typeof msg.j !== "string" || !/^\d{1,12}$/.test(msg.j)) return null;
  const key = keyFor(msg.j);
  const entry = (await store.get(key))[key];
  if (!isFresh(entry, Date.now())) {
    if (entry) await store.remove(key);
    return null;
  }
  return { s: entry.s, m: entry.m };
}

const HANDLERS = { "agad:save": save, "agad:load": load };

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  const handler = msg && HANDLERS[msg.type];
  const trusted = sender.id === chrome.runtime.id &&
    typeof sender.url === "string" && sender.url.startsWith(SITE);
  if (!handler || !trusted) return false;
  handler(msg, sender).then(sendResponse, () => sendResponse(msg.type === "agad:save" ? { ok: false } : null));
  return true; // keeps the channel open for the async reply
});
