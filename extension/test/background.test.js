// Service worker tests: runs background.js in a sandbox with a fake chrome.storage.session.
"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const ROOT = path.join(__dirname, "..");
const SITE_SENDER = { id: "ext-id", url: "https://www.onlinejobs.ph/jobseekers/job/Dev-1234567#agad=x" };
const LOGIN_SENDER = { id: "ext-id", url: "https://www.onlinejobs.ph/login" };

function boot() {
  const data = {};
  const session = {
    async get(keys) {
      if (keys === null) return { ...data };
      return keys in data ? { [keys]: data[keys] } : {};
    },
    async set(items) { Object.assign(data, items); },
    async remove(keys) { for (const k of [].concat(keys)) delete data[k]; },
  };
  let listener = null;
  const sandbox = {
    chrome: {
      runtime: { id: "ext-id", onMessage: { addListener: (fn) => { listener = fn; } } },
      storage: { session },
    },
    TextDecoder, atob, Date, URL,
  };
  sandbox.globalThis = sandbox;
  sandbox.self = sandbox;
  sandbox.importScripts = (rel) => vm.runInContext(fs.readFileSync(path.join(ROOT, rel), "utf8"), sandbox);
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(path.join(ROOT, "background.js"), "utf8"), sandbox);
  const call = (msg, sender = SITE_SENDER) => new Promise((resolve) => {
    const kept = listener(msg, sender, (r) => resolve(JSON.parse(JSON.stringify(r)))); // sandbox objects are another realm
    if (!kept) resolve("ignored");
  });
  return { data, call };
}

test("saves by job id and loads it back", async () => {
  const { data, call } = boot();
  assert.deepEqual(await call({ type: "agad:save", j: "1234567", s: "Hi", m: "Body" }), { ok: true });
  assert.deepEqual(Object.keys(data), ["agad:job:1234567"]);
  assert.equal(typeof data["agad:job:1234567"].savedAt, "number");
  assert.deepEqual(await call({ type: "agad:load", j: "1234567" }), { s: "Hi", m: "Body" });
  assert.equal(await call({ type: "agad:load", j: "999" }), null);
});

test("rejects bad saves and bad job ids", async () => {
  const { data, call } = boot();
  assert.deepEqual(await call({ type: "agad:save", j: "12a", s: "Hi", m: "" }), { ok: false });
  assert.deepEqual(await call({ type: "agad:save", j: "1", s: "", m: "" }), { ok: false });
  assert.deepEqual(await call({ type: "agad:save", j: "1", s: "x".repeat(201), m: "" }), { ok: false });
  assert.equal(await call({ type: "agad:load", j: "../x" }), null);
  assert.equal(Object.keys(data).length, 0);
});

test("ignores messages from other extensions, other sites and unknown types", async () => {
  const { data, call } = boot();
  const msg = { type: "agad:save", j: "1", s: "Hi", m: "" };
  assert.equal(await call(msg, { id: "other", url: SITE_SENDER.url }), "ignored");
  assert.equal(await call(msg, { id: "ext-id", url: "https://evil.example/jobseekers/job/Dev-1" }), "ignored");
  assert.equal(await call(msg, { id: "ext-id", url: "https://www.onlinejobs.ph.evil.example/" }), "ignored");
  assert.equal(await call(msg, { id: "ext-id" }), "ignored");
  assert.equal(await call({ type: "agad:nope" }), "ignored");
  assert.equal(Object.keys(data).length, 0);
});

test("drops entries older than 24 hours and keeps at most 50", async () => {
  const { data, call } = boot();
  const old = Date.now() - 25 * 60 * 60 * 1000;
  data["agad:job:1"] = { s: "old", m: "", savedAt: old };
  assert.equal(await call({ type: "agad:load", j: "1" }), null);
  assert.equal("agad:job:1" in data, false);
  for (let i = 0; i < 55; i++) data[`agad:job:${100 + i}`] = { s: "x", m: "", savedAt: Date.now() - (60 - i) * 1000 };
  data["agad:job:2"] = { s: "old", m: "", savedAt: old };
  await call({ type: "agad:save", j: "7", s: "new", m: "" }, LOGIN_SENDER);
  const keys = Object.keys(data).filter((k) => k.startsWith("agad:job:"));
  assert.equal(keys.length, 50);
  assert.ok(keys.includes("agad:job:7"));
  assert.ok(!keys.includes("agad:job:2"));
  assert.ok(!keys.includes("agad:job:100"));
});

test("saves only for the job on the sending page, any job from a page without one", async () => {
  const { data, call } = boot();
  assert.deepEqual(await call({ type: "agad:save", j: "999", s: "Hi", m: "" }), { ok: false });
  assert.equal(Object.keys(data).length, 0);
  assert.deepEqual(await call({ type: "agad:save", j: "999", s: "Hi", m: "" }, LOGIN_SENDER), { ok: true });
  assert.deepEqual(Object.keys(data), ["agad:job:999"]);
});

test("a hashchange save never overwrites a same-job save under 10 minutes old", async () => {
  const { data, call } = boot();
  const key = "agad:job:1234567";
  await call({ type: "agad:save", j: "1234567", s: "Mine", m: "Body" });
  assert.deepEqual(await call({ type: "agad:save", j: "1234567", s: "Theirs", m: "X", keepRecent: true }),
    { ok: true, kept: true });
  assert.equal(data[key].s, "Mine");
  data[key].savedAt = Date.now() - 11 * 60 * 1000;
  assert.deepEqual(await call({ type: "agad:save", j: "1234567", s: "Later", m: "Y", keepRecent: true }), { ok: true });
  assert.equal(data[key].s, "Later");
  assert.deepEqual(await call({ type: "agad:save", j: "1234567", s: "Email", m: "Z" }), { ok: true }); // page load overwrites
  assert.equal(data[key].s, "Email");
});
