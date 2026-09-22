# Design handoff — make Agad feel premium, and make scrolling it a pleasure

Paste this whole file into a fresh Claude Code session opened in `C:\Users\regid\Desktop\applyfirst`.
Part 1 is the ask. Everything after it is the reference material that stops you rebuilding what is
already there or breaking a test you did not know existed.

---

## 1. The ask

Agad is a real product about to go into a small beta. The homepage already has a dark cinematic
hero with a live canvas scene, scroll reveals on every page, gradient buttons and one scroll-driven
surprise. It works, it is fast, and it passes every gate.

It is not yet **premium**.

Take it there. Specifically.

- **Raise the craft floor across the whole page, not just the hero.** Everything below the hero is
  still a competent light page with one generic fade-up reveal. It should feel considered at every
  scroll position, the way a well-funded product does.
- **Give me more moments that surprise someone while they scroll.** There is exactly one right now,
  the application slots filling. I want several, each earning its place, each tied to something true
  about the product rather than decoration for its own sake.
- **Make depth, light and material do real work.** The page is flat. Elevation, layering, the way
  light falls on the one important card, the way a section hands off to the next.
- **Keep it calm.** Premium is restraint plus precision, not more effects. If a moment does not say
  something, cut it.

Read part 4 before you write a line. The constraints there are unusual and several of them are
enforced by tests that will fail the build.

---

## 2. What the product is

Agad watches **onlinejobs.ph** for job posts matching the watch words a user saves. When a matching
job appears it writes a tailored application letter with AI and emails it to that user's own Gmail,
usually within minutes. The user reads it, copies it, and applies **themselves**.

- Agad never applies on anyone's behalf, never contacts an employer, never logs into anyone's
  onlinejobs.ph account. The homepage says so out loud and every piece of copy has to stay true to it.
- The audience is **Filipino virtual assistants and remote workers**, mostly on mid-range Android
  phones, often on mobile data. Every kilobyte and every dropped frame is a real cost to a real person.
- The name is **Agad**, Tagalog for "right away", said ah-GAD. The tagline **Apply Agad** is an
  instruction to the reader, never a claim that Agad applies for them.
- It is invite-only beta with a 14-day free trial. Price is written but hidden.
- The reason the product exists is that a free employer account on onlinejobs.ph can only receive
  **15 applications per job**, so good jobs fill while you sleep. Being early is the whole value.

---

## 3. What already exists, so you do not rebuild it

Recently shipped and verified. Treat all of it as a floor to build on, not a draft to replace.

**The dark hero, homepage only.** A navy band that runs to the very top of the page and swallows the
site header, with one sky radial glow, a grain tile to stop banding on cheap panels, and a scrim.
Everything below it stays light. Lives in `applyfirst/saas/static/css/hero.css`, switched on by a
`is-home` body class so no other page is touched.

**The live hero scene.** `applyfirst/saas/static/js/scene.js` paints a canvas behind the headline.
Faint job posts drift past, a light sweep crosses, one post lights up as a match and flies along a
bezier into the inbox mock that is actually rendered on the page beside it, then a ring pulses and
every card eases to a stop. It runs **once** and finishes at 4,600ms. That is deliberate and it is
load-bearing, see part 4.

**Scroll reveals, every page.** `applyfirst/saas/static/js/reveal.js` plus a block at the end of
`app.css`. One IntersectionObserver stamps `data-rv-item="in"` on a fixed selector list, and the CSS
fades and lifts them in with a three-step stagger. It is a single generic move and it is the most
obvious thing to make better.

**The one surprise.** The 15 application slots fill in one by one as you read the section that
explains the 15-application limit, then the three early ones pop, because the room filled while you
were reading and you were already inside. Pure CSS on a view timeline, no JavaScript, no scroll
listener. This is the standard to beat.

**Gradient calls to action.** One gradient per view on `.btn--primary`, a separate brighter sky
gradient with a navy label on the dark hero, and a white sheen that passes once on the dark hero only.

**The type.** The site uses the device's own font, so SF on Apple, Roboto on Android, Segoe on
Windows, downloading nothing. One `font-size-adjust` line compensates for the fact that those three
look different sizes at the same pixel value. Headings came down 5 to 11 percent, reading text did not
move.

---

## 4. Hard constraints. Every one of these is enforced

Breaking any of these fails the build or ships a broken page. Read the real files, do not trust this
summary alone.

**4.1 The Content Security Policy is frozen.** Set in `applyfirst/saas/app.py` around line 223.

```
default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:;
form-action 'self'; base-uri 'none'; frame-ancestors 'none'
```

So there is no inline `<script>`, no `on*` attributes, no eval, no WASM, no CDN for anything, no
`blob:` URLs. Canvas 2D is fine. A `data:` URI in a CSS background is fine. Self-hosted files under
`/static` are fine. Do not loosen it. Pytest only checks `default-src 'self'`, so a loosened policy
would pass, which is exactly why it must not be touched.

**4.2 No build step, no Node, no package manager.** Hand-written CSS and classic JavaScript served
from `applyfirst/saas/static/`. Nothing is compiled, bundled or minified.

**4.3 No `<style>` blocks in templates.** Enforced by `tests/test_saas_template_guards.py`.

**4.4 The public pages must not name the onboarding motion files.** Test M-2 in
`tests/test_saas_motion.py` renders `/`, `/login`, `/privacy` and `/terms` and fails if the HTML
contains any of `motion.css`, `vt.js`, `motion.js` or `canvas-confetti`. Any new file you add must
have a name that contains none of those substrings. `hero.css`, `reveal.js` and `scene.js` are safe.
A file called `home-motion.css` would fail, because it contains `motion.css`.

**4.5 The head order is locked.** Test M-1 requires, on the five signed-in pages, this order.

```
css/app.css  →  css/motion.css  →  js/vt.js  →  js/motion.js
```

and no `<script>` may appear before `motion.css`. The current head in `base.html` puts
`{% block page_css %}` and the parser-blocking `reveal.js` **after** `motion_head`, which is what
keeps that true. If you add a head tag, put it after that point and re-run the test.

**4.6 The existing motion files are full.** Measured just now with the test's own helper.
`motion.css` is 2,818 bytes of 2,850 gzipped, `vt.js` is 1,868 of 1,900, and the pair together is
4,686 of 4,700. That is **fourteen bytes of headroom**. Adding so much as a comment to either will
fail test M-3. Do not edit `motion.css`, `vt.js` or `motion.js`. Build in new files instead.

**4.7 No purple, ever.** `tests/test_saas_palette.py` scans every CSS and JS file and rejects any
colour whose hue is between 230 and 345 at 8 percent saturation or more, plus the words purple,
violet, indigo, lavender, lilac, magenta, fuchsia, orchid, plum, blueviolet, rebeccapurple and
slateblue. Compute the hue of every stop you invent before you write it. The brand is navy `#0B2545`,
deep navy `#081A30`, action blue `#0B6BC7`, sky `#38AEEA`, page `#F3F6FA`. Blue through cyan through
teal is the whole available range and it is enough.

**4.8 `app.js` must not do motion work.** A test fails if it contains the words `pagereveal`,
`view-transition` or `confetti`. New behaviour goes in a new file.

**4.9 Never use `url_for` in a template.** It emits absolute URLs and breaks behind the proxy. Use
the `static_url()` Jinja global for assets and literal paths like `/privacy` for links.

**4.10 Content must never depend on JavaScript to be visible.** This is the one that will bite you.
The reveal layer hides elements **only** while `<html data-rv>` is present, and `reveal.js` is the
only thing that sets it. It also removes it on any bail, including no IntersectionObserver, reduced
motion, Data Saver, a 2g connection, a device reporting 2GB of memory or less, a thrown error, and a
parse that takes over three seconds. With JavaScript off there is no attribute and nothing is hidden.
Whatever you build, keep that property, and note that the CSP forbids the usual inline head script
that most reveal libraries rely on.

**4.11 Accessibility is not optional.** `prefers-reduced-motion: reduce` must produce a genuinely
static result, not a faster one. AA contrast throughout, which is 4.5 to 1 for body text and 3 to 1
for large text and the visible edge of a control. WCAG 2.2.2 says moving content that runs past five
seconds needs a way to stop it, which is exactly why the hero scene is a 4,600ms one-shot and has no
pause button. **If you make it loop, or push its timeline past 5,000ms, you have just made a pause
control mandatory**, and a test in `tests/test_saas_hero.py` will fail to tell you so.

**4.12 The gates.** 744 pytest tests and a 555-check smoke script must stay green.

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe .noxa\redesign-saas-ui\inputs\preserve_smoke.py
```

Unit tests alone do not catch a missing CSRF field, a reworded asserted string or a CSP violation.
Run both, every time.

---

## 5. Where everything lives

```
applyfirst/saas/templates/base.html     the shared shell and the head contract
applyfirst/saas/templates/home.html     the homepage, hero at the top, 10 sections below
applyfirst/saas/templates/_ui.html      the macro library and the owner switches
applyfirst/saas/templates/_icons.html   inlined SVG icons
applyfirst/saas/static/css/app.css      everything, ~70 KB, layered reset/tokens/base/components/screens
applyfirst/saas/static/css/hero.css     the dark hero, homepage only, wins via a final `hero` layer
applyfirst/saas/static/css/motion.css   onboarding only. DO NOT EDIT, 32 bytes of headroom
applyfirst/saas/static/js/app.js        form behaviour, no motion
applyfirst/saas/static/js/reveal.js     the scroll reveal layer, every page
applyfirst/saas/static/js/scene.js      the hero canvas, homepage only
applyfirst/saas/static/js/vt.js         onboarding view transitions. DO NOT EDIT
applyfirst/saas/static/js/motion.js     onboarding motion. DO NOT EDIT
tests/test_saas_hero.py                 guards for the hero, the scene, the gradient and the font
tests/test_saas_reveal.py               guards for the reveal layer and the slots surprise
tests/test_saas_motion.py               the onboarding motion contract, head order and byte budgets
tests/test_saas_palette.py              the no-purple guard
```

Design tokens are at the top of `app.css` in the `tokens` layer. Use them. Do not invent a parallel
colour or spacing system.

---

## 6. Locked decisions, do not relitigate

- Sky blue and dark blue only. Zero purple.
- The dark band is the homepage hero only. Every other page and every other section stays light.
- The inbox mock and the opened letter stay **bright white**, even on the dark hero. The promise is
  an email landing in Gmail and Gmail's inbox is white. A frosted-glass inbox is a picture of
  something that is not Gmail.
- The Continue with Google button is Google's own branding and may not be restyled by a single pixel.
- The device's own font stays. Do not add a webfont.
- No video files. The audience is on mobile data.
- Sign-up copy stays invite-only while Google review is pending, and pricing stays hidden.
- The hero headline must remain a Largest Contentful Paint candidate, so nothing inside `.hero` may
  be a reveal target.

---

## 7. What premium means on this product

Worth saying plainly, because premium is often read as "add more".

- **Precision beats abundance.** One perfectly timed moment on a page beats five adequate ones.
- **Motion should explain something.** The hero scene is a job post flying into an inbox. The slots
  surprise is the room filling while you read. That is the bar. A thing that merely moves is decoration
  and should be cut.
- **The page should feel built, not assembled.** Consistent optical spacing, considered edges, light
  that falls the same way everywhere, and type that sits on a real scale.
- **Nothing may make the page feel slower.** On a mid-range Android on 4G, a premium page is one that
  paints immediately and never stutters. If a choice trades speed for polish, it is the wrong choice.
- **Restraint reads as confidence.** A cheap page shouts. Aim for the feeling of a product that does
  not need to.

---

## 8. Where the opportunities are, roughly ranked

These are observations, not instructions. Take the ones you agree with and argue with the rest.

1. **The reveal is one generic move.** Every element fades up 16 pixels with a three-step stagger.
   Different kinds of content deserve different arrivals, and some deserve none.
2. **There is only one scroll-driven moment.** Scroll-driven CSS animations cost no main-thread
   frames and are supported in Chrome, Edge and Safari 26, with a clean skip in Firefox. The slots
   effect proves the pattern works here. There is room for two or three more.
3. **The hand-off between sections is a hard edge.** The dark hero ends in a lit hairline, which is
   good, but the light sections below simply stack. Section transitions are an untouched surface.
4. **The 9:02 to 9:12 timeline in the hero is static.** It is the clearest statement of the product
   promise on the page and it does not move.
5. **The letter and the inbox are static pictures.** The most important object on the page could
   reward attention.
6. **Nothing has depth.** Shadows are single-layer and flat. There is no parallax, no layering, no
   sense that the page has a z-axis.
7. **The FAQ, the footer and the legal pages have had the least attention.**
8. **Desktop pointer interactions are unexplored.** Hover states are functional and nothing more.
9. **Numbers do not animate.** "15 applications" and the timing figures are the product's argument.

---

## 9. Anti-goals

Things that would make it worse, listed so nobody has to find out the expensive way.

- Scroll hijacking, scroll jacking, smooth-scroll overrides, or anything that delays a swipe.
- Parallax so heavy it drops frames on a phone.
- A loading screen, a splash, or a skeleton on a page that already paints fast.
- Animating `width`, `height`, `top` or `left`. Transform and opacity only.
- `backdrop-filter` over the live canvas. It forces a full backdrop readback every frame, which is
  the difference between 60fps and 25fps on a mid-range Android.
- Anything that makes text harder to read at any point in an animation.
- Effects that only work with JavaScript and leave a hole without it.
- More than one primary call to action in a view.
- Copy that implies Agad applies for people, guarantees a job, or promises income.
- Em dashes in user-facing copy. The house style is plain full stops.

---

## 10. How to verify, including the traps

**Run the app locally in every state.**

```powershell
.venv\Scripts\python.exe .noxa\redesign-saas-ui\artifacts\run_local.py --port 8765 --data-dir C:\Users\regid\AppData\Local\Temp\agad-preview
```

Then open `http://127.0.0.1:8765/__dev/` for a clickable list of 22 seeded states, including every
onboarding step, the dashboard variants and the error pages. The data directory must be outside the
repo and the runner refuses one inside it. Those `/__dev/` routes exist only in that file and never
in `app.py`.

**Trap one, the scrollbar.** A headless or desktop browser reserves about 15 pixels for a classic
scrollbar. A real phone uses an overlay scrollbar and takes none. At a 320 pixel viewport that is the
difference between 265 and 280 pixels of container, which is enough to change how a headline wraps.
Measuring the phone layout in a desktop browser without accounting for it produces confident wrong
answers. Hide the scrollbar before you measure.

```js
document.head.insertAdjacentHTML('beforeend',
  '<style>html{scrollbar-width:none}html::-webkit-scrollbar{display:none}</style>');
```

**Trap two, `ch` units.** `1ch` is glyph-derived and swings 26 percent between the fonts different
platforms serve. Any `ch`-based `max-width` on a heading will wrap differently on Windows than on
Android. Use `em`, which is font-size-derived and identical everywhere.

**Trap three, IntersectionObserver in a test.** Scrolling the page inside a single `page.evaluate`
with `setTimeout` between steps does not yield real animation frames, so the observer never fires and
everything looks broken when it is not. Drive scrolling with `requestAnimationFrame` between steps.

**Measure line breaks properly** rather than eyeballing a screenshot. A Range over the text node
returns one client rect per line box.

```js
const r = document.createRange(), node = el.firstChild, lines = [];
let cur = null;
for (let i = 0; i < node.length; i++) {
  r.setStart(node, i); r.setEnd(node, i + 1);
  const rect = r.getClientRects()[0]; if (!rect) continue;
  const top = Math.round(rect.top);
  if (!cur || cur.top !== top) { cur = { top, text: '', right: 0, left: rect.left }; lines.push(cur); }
  cur.text += node.data[i];
  cur.right = Math.max(cur.right, rect.right);
  cur.left = Math.min(cur.left, rect.left);
}
```

**Compute contrast, do not trust it.** The hero has three layers painting into it, a CSS glow, a
canvas and a scrim. An earlier draft of this work stacked two glows plus the canvas and pushed the
hero lead to 3.78 against a 4.5 requirement, and no test could see it. `tests/test_saas_hero.py` now
reads the alphas out of the real files, composites them the way a browser does, and fails if the
result drops under AA. If you add a layer, extend that test rather than working around it.

**Check the states nobody looks at.** JavaScript off, `prefers-reduced-motion: reduce`, Windows high
contrast (`forced-colors: active`), print preview, a 320 pixel viewport, and a Facebook in-app browser
user agent. All six are already handled and all six are easy to break.

**Prove your guards bite.** Break each new test on purpose, confirm it turns red, then revert. A test
that cannot fail is worse than no test, because it reads like coverage.

---

## 11. Before you finish

- Both gates green, and say the numbers.
- Screenshot the homepage at 360, 390 and 1280, and at least one signed-in page.
- Say what you cut and why. The cut list is the most useful part of a design pass.
- Give the gzipped byte cost of everything you added, and add a budget test for it modelled on the
  one in `tests/test_saas_motion.py`.
- Nothing is committed automatically. The owner commits, and note that a privacy hook in this repo
  blocks a commit whose staged content or message contains certain words, so keep those out of both.
