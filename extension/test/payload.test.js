// Run with: node --test extension/test/   (Node's built-in runner, nothing to install)
"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const fs = require("node:fs");
const P = require("../lib/payload.js");

const vectors = JSON.parse(fs.readFileSync(path.join(__dirname, "vectors.json"), "utf8"));
const enc = (obj) => Buffer.from(typeof obj === "string" ? obj : JSON.stringify(obj), "utf8").toString("base64url");
const ok = { v: 1, j: "1234567", s: "Subject", m: "Message" };

test("vectors file has the four agreed cases", () => {
  assert.ok(vectors.length >= 4);
  assert.ok(vectors.some((c) => c.m.length === P.MAX_MESSAGE));
});

for (const c of vectors) {
  test(`vector decodes: ${c.name}`, () => {
    assert.equal(enc({ v: 1, j: c.j, s: c.s, m: c.m }), c.fragment);
    assert.match(c.fragment, /^[A-Za-z0-9_-]+$/);
    assert.deepEqual(P.decodePayload(c.fragment), { j: c.j, s: c.s, m: c.m });
    assert.equal(P.jobIdFromPath(new URL(c.url).pathname), c.j);
    assert.equal(c.link, `${c.url}#agad=${c.fragment}`);
    assert.equal(P.readFragment(new URL(c.link).hash), c.fragment);
  });
}

test("exposes the agreed constants", () => {
  assert.equal(P.FRAGMENT_KEY, "agad");
  assert.equal(P.MAX_SUBJECT, 200);
  assert.equal(P.MAX_MESSAGE, 5000);
  assert.equal(globalThis.AgadPayload, P);
});

test("decodePayload returns null for every bad payload", () => {
  const good = enc(ok);
  const bad = {
    "truncated": good.slice(0, -3),
    "tampered": good.slice(0, 10) + "A" + good.slice(11),
    "non-base64 characters": "abc$def+/==",
    "length that is 1 mod 4": "AAAAA",
    "empty": "",
    "invalid utf-8": Buffer.from([0x7b, 0xff, 0xfe, 0x7d]).toString("base64url"),
    "not json": enc("hello"),
    "json array": enc("[1,2]"),
    "json null": enc("null"),
    "json string": enc('"x"'),
    "v is 2": enc({ ...ok, v: 2 }),
    "v is string": enc({ ...ok, v: "1" }),
    "j has letters": enc({ ...ok, j: "12a" }),
    "j too long": enc({ ...ok, j: "1234567890123" }),
    "j empty": enc({ ...ok, j: "" }),
    "j is a number": enc({ ...ok, j: 1234567 }),
    "s over 200": enc({ ...ok, s: "x".repeat(201) }),
    "m over 5000": enc({ ...ok, m: "x".repeat(5001) }),
    "s not a string": enc({ ...ok, s: 5 }),
    "m missing": enc({ v: 1, j: "1", s: "x" }),
    "both empty": enc({ ...ok, s: "", m: "" }),
    "extra key": enc({ ...ok, q: [] }),
    "huge fragment": "A".repeat(50000),
    "not a string": 42,
  };
  for (const [name, value] of Object.entries(bad)) {
    assert.equal(P.decodePayload(value), null, name);
  }
});

test("decodePayload accepts the caps exactly and one empty text", () => {
  assert.deepEqual(P.decodePayload(enc({ ...ok, s: "s".repeat(200), m: "" })), { j: ok.j, s: "s".repeat(200), m: "" });
  assert.deepEqual(P.decodePayload(enc({ ...ok, s: "", m: "m".repeat(5000) })), { j: ok.j, s: "", m: "m".repeat(5000) });
  // caps count UTF-16 units: 2500 emoji = 5000 units passes, 2501 fails
  assert.notEqual(P.decodePayload(enc({ ...ok, m: "😀".repeat(2500) })), null);
  assert.equal(P.decodePayload(enc({ ...ok, m: "😀".repeat(2501) })), null);
});

test("validate keeps only j, s, m and rejects non-objects", () => {
  assert.deepEqual(P.validate(ok), { j: "1234567", s: "Subject", m: "Message" });
  for (const v of [null, undefined, "x", 1, [], [ok]]) assert.equal(P.validate(v), null);
});

test("jobIdFromPath reads the trailing job number like the Python scraper", () => {
  assert.equal(P.jobIdFromPath("/jobseekers/job/Senior-Dev-1234567"), "1234567");
  assert.equal(P.jobIdFromPath("/jobseekers/job/Senior-Dev-1234567/"), "1234567");
  assert.equal(P.jobIdFromPath("/login"), null);
  assert.equal(P.jobIdFromPath("/jobseekers/job/1234567"), null);
  assert.equal(P.jobIdFromPath(""), null);
  assert.equal(P.jobIdFromPath(undefined), null);
});

test("readFragment finds agad= only when it is our marker", () => {
  assert.equal(P.readFragment("#agad=abc_-1"), "abc_-1");
  assert.equal(P.readFragment("#agad="), "");
  assert.equal(P.readFragment("#agad=bad$chars"), "bad$chars");
  for (const h of ["", "#", "#agadx=abc", "#x=1&agad=abc", "agad=abc", "#AGAD=abc", "#top", null, undefined]) {
    assert.equal(P.readFragment(h), null, String(h));
  }
});

test("stripFragment keeps path and query and drops the hash", () => {
  const base = "https://www.onlinejobs.ph/jobseekers/job/Dev-12?ref=mail&x=1";
  assert.equal(P.stripFragment(base + "#agad=abc"), base);
  assert.equal(P.stripFragment(base + "#"), base);
  assert.equal(P.stripFragment(base), base);
  assert.equal(P.stripFragment("https://www.onlinejobs.ph/login#agad=a#b"), "https://www.onlinejobs.ph/login");
});

test("jobMatchesPage: job pages accept only their own number, other pages accept any", () => {
  assert.equal(P.jobMatchesPage("1234567", "/jobseekers/job/Dev-1234567"), true);
  assert.equal(P.jobMatchesPage("999", "/jobseekers/job/Dev-1234567"), false);
  assert.equal(P.jobMatchesPage("12345", "/jobseekers/job/Dev-1234567"), false);
  assert.equal(P.jobMatchesPage("999", "/login"), true);
  assert.equal(P.jobMatchesPage("999", "/"), true);
});

test("fillNotice offers Refill for a box skipped because it had text", () => {
  assert.deepEqual(P.fillNotice(["Subject", "Message"], []),
    { msg: "Subject and Message filled. Review, then Send.", sub: null, refill: false });
  const partial = P.fillNotice(["Subject"], ["Message"]);
  assert.equal(partial.refill, true);
  assert.match(partial.msg, /^Subject filled\. Your Message box already had text/);
  assert.equal(partial.sub, "Refill puts the saved Message in that box.");
  const none = P.fillNotice([], ["Subject", "Message"]);
  assert.equal(none.refill, true);
  assert.equal(none.msg, "Saved text for this job is ready.");
  assert.deepEqual(P.fillNotice([], []), none);
  for (const t of [partial, none]) assert.ok(!/\u2014/.test(t.msg + t.sub)); // no em-dashes in user-facing text
});
