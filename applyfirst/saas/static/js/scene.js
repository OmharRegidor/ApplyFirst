/* Agad hero scene. A stream of job posts drifts across the light field, one lights up as a match
   and flies into the inbox that is actually drawn on the page beside it. Then it does it again.

   It paints into #hero-bg with source-over on a transparent bitmap, so on the light hero it only
   ever ADDS soft blue ink over the aura painted by hero.css. Two colours, both hard-capped, and a
   white wash sits above it, so no state it can reach pushes the hero copy under AA.

   It loops, so WCAG 2.2.2 applies and a pause control is mandatory. This file injects it rather
   than the template carrying it, because with JavaScript off there is no motion to pause and a
   dead button would be worse than no button. The control stops the CSS aura too, by setting
   data-scene="paused" on the hero, or it would not honestly be a pause.

   CSP-safe: classic script, same origin, no dynamic code, no network, no storage, no worker. */
(function () {
  "use strict";

  var cv = document.getElementById("hero-bg");
  if (!cv) return;
  var hero = cv.closest(".hero");
  if (!hero) return;
  var ctx = cv.getContext("2d");
  if (!ctx) return;

  /* ---- palette. Action blue for the outlines, navy for the title bar. Both capped. ---- */
  var BLU = "11,107,199", NVY = "11,37,69";
  var CAP = 0.22, CAP_NVY = 0.16;
  var cache = {};
  function ink(base, a, top) {
    var q = a < 0 ? 0 : (a > top ? top : a);
    q = ((q * 200) | 0) / 200;                    /* quantised, so the string table stays bounded */
    var k = base + q;
    return cache[k] || (cache[k] = "rgba(" + base + "," + q + ")");
  }
  function blu(a) { return ink(BLU, a, CAP); }
  function nvy(a) { return ink(NVY, a, CAP_NVY); }

  /* ---- one cycle, milliseconds. The story repeats rather than stopping. ---- */
  var CYCLE = 11000;
  var T_SWEEP = 1500, T_SWEEP_END = 2900, T_LOCK = 3400, T_FLY = 4800, T_RING = 5600;
  var STILL_AT = 4200;                            /* the pose the reduced-motion frame freezes on */

  var mq = matchMedia("(prefers-reduced-motion: reduce)");
  var conn = navigator.connection;
  var lite = mq.matches || navigator.deviceMemory <= 2 ||
    (conn && (conn.saveData || /2g/.test(conn.effectiveType || "")));

  /* deterministic, so the still frame is identical for every visitor */
  var rs = 20260922;
  function rnd() { rs = (rs * 1664525 + 1013904223) >>> 0; return rs / 4294967296; }

  var W = 0, H = 0, dpr = 1, lanes = 0, cards = [], match = null, matchIdx = 0;
  var tx = 0, ty = 0, scan = null, SCANW = 0;
  var clock = 0, locked = false, raf = 0, last = 0, next = 0, ema = 0;
  var userPaused = false, btn = null;
  var STEP = 1000 / 30, DX = 16.87, DY = 2.07;

  var hasRR = typeof ctx.roundRect === "function";
  function rr(x, y, w, h, r) {
    if (hasRR) { ctx.roundRect(x, y, w, h, r); return; }
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }
  function par(c) { return 0.5 + (c.a - 0.05) / 0.08 * 0.8; }
  function lay(c) { var g = H / lanes; c.y = c.lane * g + g * 0.5 + (c.seed - 0.5) * g * 0.42; }

  /* ---- the target is the real inbox drawn on the page, so the flight means something ---- */
  function aim() {
    var hb = hero.getBoundingClientRect();
    var el = hero.querySelector(".inbox") || hero.querySelector(".arrival__stage");
    if (el) {
      var r = el.getBoundingClientRect();
      tx = r.left - hb.left + r.width * 0.5;
      ty = r.top - hb.top + (r.height * 0.5 > 90 ? 90 : r.height * 0.5);
    } else { tx = W * 0.78; ty = H * 0.72; }
  }

  /* a different card each time round, always one that is on screen and clear of the copy */
  function pick() {
    var best = null, i, c;
    for (i = 0; i < cards.length; i++) {
      c = cards[(matchIdx + i) % cards.length];
      if (c.x > W * 0.14 && c.x < W * 0.82 && c.y > H * 0.1 && c.y < H * 0.72) { best = c; break; }
    }
    matchIdx = (matchIdx + 3) % Math.max(1, cards.length);
    match = best || cards[0];
    locked = false;
  }

  function build() {
    lanes = Math.max(3, Math.round(H / 118));
    var n = Math.round(W * H / 26000);
    if (navigator.hardwareConcurrency && navigator.hardwareConcurrency <= 4) n = Math.round(n * 0.7);
    n = Math.max(10, Math.min(28, n));
    rs = 20260922;
    cards.length = 0;
    var perLane = Math.ceil(n / lanes), i, c;
    for (i = 0; i < n; i++) {
      c = { lane: i % lanes, a: 0.05 + rnd() * 0.08, w: 96 + rnd() * 52, h: 58 + rnd() * 31,
            x: 0, y: 0, seed: rnd(), bars: rnd() < 0.5 ? 2 : 3, px: 0, py: 0, cx: 0, cy: 0 };
      c.x = -120 + ((W + 240) / perLane) * (Math.floor(i / lanes) + rnd() * 0.6);
      lay(c);
      cards.push(c);
    }
    matchIdx = 0;
    pick();
    SCANW = Math.max(120, W * 0.26);
    scan = ctx.createLinearGradient(0, 0, SCANW, 0);
    scan.addColorStop(0, "rgba(" + BLU + ",0)");
    scan.addColorStop(0.5, "rgba(" + BLU + ",0.07)");
    scan.addColorStop(1, "rgba(" + BLU + ",0)");
    aim();
  }

  function size() {
    var r = hero.getBoundingClientRect();
    W = Math.round(r.width); H = Math.round(r.height);
    if (W < 2 || H < 2) return false;
    dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    while (W * dpr * H * dpr > 1600000 && dpr > 1) dpr -= 0.1;    /* 1.6 megapixel ceiling */
    cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr);
    cv.style.width = W + "px"; cv.style.height = H + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    build();
    return true;
  }

  /* ---- drawing is pure: it reads state and paints, so the still frame reuses it exactly ---- */
  function card(c, a, sc) {
    var w = c.w * sc, h = c.h * sc, x = c.x - w / 2, y = c.y - h / 2;
    ctx.beginPath(); rr(x, y, w, h, 10 * sc);
    ctx.fillStyle = blu(a * 0.16); ctx.fill();
    ctx.strokeStyle = blu(a); ctx.lineWidth = 1; ctx.stroke();
    var bx = x + 12 * sc, by = y + 15 * sc, bw = w - 24 * sc, i;
    ctx.fillStyle = nvy(a * 0.8);
    ctx.fillRect(bx, by, bw * (0.5 + c.seed * 0.3), 4 * sc);      /* the job title */
    ctx.fillStyle = blu(a * 0.5);
    for (i = 0; i < c.bars; i++) {
      ctx.fillRect(bx, by + (13 + i * 9) * sc, bw * (0.88 - i * 0.2 - c.seed * 0.1), 3 * sc);
    }
  }

  function bez(p, a, b, c2) { var q = 1 - p; return q * q * a + 2 * q * p * b + p * p * c2; }

  function draw() {
    ctx.clearRect(0, 0, W, H);
    var flying = clock >= T_LOCK && clock < T_RING;
    var sx = -9999, i, c, d, a;
    if (clock >= T_SWEEP && clock < T_SWEEP_END) {
      sx = -SCANW + (W + SCANW * 2) * ((clock - T_SWEEP) / (T_SWEEP_END - T_SWEEP));
    }

    for (i = 0; i < cards.length; i++) {
      c = cards[i];
      if (c === match && flying) continue;               /* the flight below draws it instead */
      a = c.a;
      if (sx > -9000) {
        d = Math.abs(c.x - sx);
        if (d < SCANW * 0.5) a += 0.05 * (1 - d / (SCANW * 0.5));
      }
      if (c === match && clock >= T_SWEEP_END && clock < T_LOCK) {
        a += (CAP - c.a) * ((clock - T_SWEEP_END) / (T_LOCK - T_SWEEP_END));
      }
      card(c, a, 1);
    }

    if (sx > -9000) {
      ctx.save(); ctx.translate(sx - SCANW / 2, 0);
      ctx.fillStyle = scan; ctx.fillRect(0, 0, SCANW, H);
      ctx.restore();
    }

    if (flying) {
      var p = Math.min(1, (clock - T_LOCK) / (T_FLY - T_LOCK));
      var e = p * p * (3 - 2 * p);
      var ox = match.x, oy = match.y;
      match.x = bez(e, match.px, match.cx, tx);
      match.y = bez(e, match.py, match.cy, ty);
      card(match, CAP * (1 - e * 0.25), 1 - e * 0.58);
      match.x = ox; match.y = oy;
    }

    if (clock >= T_FLY && clock < T_RING) {               /* it landed: one ring per cycle */
      var q = (clock - T_FLY) / (T_RING - T_FLY);
      ctx.beginPath(); ctx.arc(tx, ty, 8 + q * 52, 0, 6.2831853);
      ctx.strokeStyle = blu((1 - q) * 0.20); ctx.lineWidth = 2; ctx.stroke();
    }
  }

  function advance(dt) {
    var was = clock;
    clock = (clock + dt * 1000) % CYCLE;
    if (clock < was) pick();                             /* new cycle, new match */
    if (!locked && clock >= T_LOCK && clock < T_RING) {
      locked = true;
      match.px = match.x; match.py = match.y;
      match.cx = (match.x + tx) * 0.5 + (ty - match.y) * 0.16;
      match.cy = Math.min(match.y, ty) - Math.abs(tx - match.x) * 0.12;
    }
    for (var i = 0; i < cards.length; i++) {
      var c = cards[i];
      if (c === match && locked && clock < T_RING) continue;
      var k = par(c) * dt;
      c.x += DX * k; c.y += DY * k;
      if (c.x - c.w / 2 > W + 30) { c.x = -c.w / 2 - rnd() * 90; c.seed = rnd(); lay(c); }
    }
  }

  function still() {                                     /* pose, paint one frame, never loop */
    clock = 0; locked = false;
    var steps = Math.round(STILL_AT / 1000 * 30);
    for (var i = 0; i < steps; i++) advance(1 / 30);
    draw();
  }

  function stop() { if (raf) { cancelAnimationFrame(raf); raf = 0; } }

  function frame(ts) {
    raf = requestAnimationFrame(frame);
    if (ts < next) return;
    var dt = Math.min((ts - last) / 1000, 0.05);
    last = ts; next = ts + STEP;
    var t0 = performance.now();
    advance(dt);
    draw();
    var cost = performance.now() - t0;
    ema = ema ? ema * 0.85 + cost * 0.15 : cost;
    if (ema > 14) { stop(); still(); }                   /* too slow for this phone: settle now */
  }

  function go() {
    if (raf || userPaused || lite) return;
    last = performance.now(); next = 0;
    raf = requestAnimationFrame(frame);
  }

  /* ---- the pause control, required because this loops (WCAG 2.2.2) ---- */
  function label() {
    btn.setAttribute("aria-pressed", userPaused ? "true" : "false");
    btn.setAttribute("aria-label", userPaused ? "Play background motion" : "Pause background motion");
    btn.title = userPaused ? "Play background motion" : "Pause background motion";
  }
  function control() {
    btn = document.createElement("button");
    btn.type = "button";
    btn.className = "hero__pause";
    label();
    btn.addEventListener("click", function () {
      userPaused = !userPaused;
      if (userPaused) { stop(); hero.setAttribute("data-scene", "paused"); }
      else { hero.removeAttribute("data-scene"); go(); }
      label();
    });
    hero.appendChild(btn);
  }

  if (!size()) return;
  if (lite) {
    still();
  } else {
    control();
    if ("IntersectionObserver" in window) {
      new IntersectionObserver(function (es) {
        if (es[0].isIntersecting) { go(); } else { stop(); }
      }, { threshold: 0 }).observe(hero);
    } else { go(); }
    document.addEventListener("visibilitychange", function () {
      if (document.hidden) { stop(); } else { go(); }
    });
    if (mq.addEventListener) mq.addEventListener("change", function () {
      if (mq.matches) { stop(); still(); }
    });
  }

  /* resize: debounced, with an 8px deadband so the iOS URL bar cannot thrash it */
  if ("ResizeObserver" in window) {
    var pw = W, ph = H, tmr = 0;
    new ResizeObserver(function () {
      var r = hero.getBoundingClientRect();
      if (Math.abs(r.width - pw) < 8 && Math.abs(r.height - ph) < 8) return;
      pw = r.width; ph = r.height;
      clearTimeout(tmr);
      tmr = setTimeout(function () {
        var running = !!raf;
        stop();
        if (!size()) return;
        if (lite || userPaused) { still(); } else if (running) { ema = 0; go(); }
      }, 160);
    }).observe(hero);
  }
}());
