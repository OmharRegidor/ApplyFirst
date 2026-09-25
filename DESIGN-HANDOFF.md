# Design handoff — take Agad from considered to finished

Paste this whole file into a fresh Claude Code session opened in `C:\Users\regid\Desktop\applyfirst`.
Part 1 is the ask. Everything after it is the reference material that stops you rebuilding what is
already there or breaking a test you did not know existed.

Last brought up to date on 2026-09-23 after commit `8be4f45` (the scroll-story pass), and on
2026-09-25 for the sign-up journey redesign (built, not yet committed), which gives login,
onboarding, the dashboard and the sign-in failed page their own look in `journey.css`.

---

## 1. The ask

Agad is a real product about to go into a small beta. The homepage has had two design passes. It has
a light hero with a live background, three kinds of scroll arrival, four scroll-driven moments that
each say something true about the product, layered depth, and sections that hand off to each other
instead of stacking. It works, it is fast, and it passes every gate.

**The owner has not yet looked at it on a real phone.** Before designing anything new, ask whether
they have, and what they felt. Their reaction outranks everything in part 8.

If they want to go further, the remaining surface is smaller and quieter than before.

- **The letter and the inbox are still static pictures.** They are the most important objects on the
  page and the only big ones that do not yet reward attention.
- **Desktop pointer interactions are unexplored.** Hover states are functional and nothing more.
- **The legal pages have had the least attention of anything on the site.**
- **Everything should still feel calm.** Premium is restraint plus precision, not more effects. If a
  moment does not say something, cut it. Two passes in, the right move may be to cut rather than add.

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

All of it shipped and verified. Treat it as a floor to build on, not a draft to replace.

**The light hero, homepage only.** A white field fading into the page colour, reaching the very top
of the page and swallowing the header. Three moving layers, back to front. Two soft aura blobs (sky
and action blue) drifting on different clocks, pure CSS transforms. A canvas of faint job posts
drifting past, one of which lights up as a match and flies a bezier into the inbox mock rendered
beside it, on an **11 second loop**. A white wash above both, which is the contrast guarantee. Lives
in `applyfirst/saas/static/css/hero.css` and `applyfirst/saas/static/js/scene.js`, switched on by an
`is-home` body class. **A dark cinematic hero was built earlier and the owner rejected it. Do not
rebuild it.**

**The pause control.** Because the background loops, WCAG 2.2.2 requires a way to stop it.
`scene.js` injects the button (never the template, so with JavaScript off there is no dead button)
and it stops the CSS aura as well as the canvas by setting `data-scene="paused"` on the hero.

**Three kinds of scroll arrival, every page.** `applyfirst/saas/static/js/reveal.js` plus a block at
the end of `app.css`. One IntersectionObserver stamps `data-rv-item="in"`. Headings rise 12px
(`rv-in`), reading text only fades (`rv-fade`), and objects settle up from slightly smaller on a long
soft curve (`rv-settle`, `--ease-land`). Keyboard focus inside a target that has not arrived yet
reveals it at once, so a focus ring is never drawn invisibly.

**Four scroll-driven moments, homepage only.** Pure CSS, no JavaScript per frame.
1. **The slots** (in `app.css`). The 15 application slots fill one by one as you read the section
   about the 15-application limit, then the three early ones pop. The room filled while you read and
   you were already inside.
2. **The ruler** (in `story.css`). The 9:02 to 9:12 timing line in the hero draws itself once, dot 1
   to dot 2 only, because the third step is the reader's. A ring pulses where the email lands, then
   the inbox's new row lights, then the opened letter lifts 14px into place. Triggered when
   `reveal.js` marks `.arrival__stage` with `data-rv-draw`.
3. **The route** (in `story.css`). In How it works, the line between the three steps fills as you
   read down them and each step lights as the line reaches it. On a phone each step's timeline is
   inset to a 2px line 60% down the screen with pixel ranges, so it is in sync on any screen height.
4. **The spotlight** (in `story.css`). The labelled example email lights one part at a time, exactly
   while that part crosses a line across the middle of the screen.

**Depth and light.** Layered, navy-tinted shadow tokens (`--shadow-sheet`, `--shadow-raised`,
`--shadow-arrival`) with one light source straight above. A thin lit edge on the top of the hero
letter, and on nothing else. Each white section casts a faint shade onto the grey one below it. Soft
radial sky glows on the dark Gmail band, the closing band and the footer.

**FAQ and footer.** Roomier FAQ rows, the chevron in a small disc that tints on hover and when open,
answers that fade in when opened, footer links that ease their colour.

**Gradient calls to action.** One gradient per view on `.btn--primary`, on the homepage, privacy
and terms. The sign-up journey (login, onboarding, the dashboard, the sign-in failed page) uses a
flat solid `#0B6BC7` primary instead (owner, 2026-09-24). `journey.css` sets
`background-image: none` on `.btn--primary`, and the frozen Activate morph starts from that flat
blue. The sky gradient and sheen from the rejected dark hero were removed with it.

**The type.** On the homepage, privacy and terms, the device's own font, so SF on Apple, Roboto on
Android, Segoe on Windows, downloading nothing. One `font-size-adjust` line evens out their
x-heights. Every width cap on a heading is in `em`, never `ch`. The sign-up journey adds a
self-hosted Inter subset for Android and Windows (`static/fonts/inter-4.1-latin-wght.woff2`,
28 KB, declared only in `journey.css`, never preloaded). Apple devices match `-apple-system` first
and download nothing. A metric-matched fallback face ("Inter Agad Fallback", local Segoe UI or
Roboto) keeps the swap to about 0.2 percent of a line's width, and the journey body sets
`font-size-adjust: none` so Inter renders at its nominal size.

---

## 4. Hard constraints. Every one of these is enforced

Breaking any of these fails the build or ships a broken page. Read the real files, do not trust this
summary alone.

**4.1 The Content Security Policy is frozen.** Set in `applyfirst/saas/app.py` around line 229.

```
default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:;
form-action 'self'; base-uri 'none'; frame-ancestors 'none'
```

So there is no inline `<script>`, no `on*` attributes, no eval, no WASM, no CDN for anything, no
`blob:` URLs. Canvas 2D is fine. A `data:` URI in a CSS background is fine. Self-hosted files under
`/static` are fine. Do not loosen it. Pytest only checks `default-src 'self'`, so a loosened policy
would pass, which is exactly why it must not be touched.

**4.2 No build step, no Node, no package manager.** Hand-written CSS and classic JavaScript served
from `applyfirst/saas/static/`. Nothing we write is compiled, bundled or minified. Two vendored
files are generated by hand-run scripts, never on deploy: the trimmed Basecoat stylesheet
(`static/vendor/basecoat-1.0.2-agad.css`, minified upstream by Tailwind, rebuilt only by
`tools/basecoat/trim.py`) and the Inter subset (`tools/fonts/build_inter.py`). Never edit either
output by hand. Change the script and run it again. The tests pin both by sha256.

**4.3 No `<style>` blocks in templates.** Enforced by `tests/test_saas_template_guards.py`.

**4.4 The public pages must not name the onboarding motion files.** Test M-2 in
`tests/test_saas_motion.py` renders `/`, `/login`, `/privacy` and `/terms` and fails if the HTML
contains any of `motion.css`, `vt.js`, `motion.js` or `canvas-confetti`. Any new file you add must
have a name that contains none of those substrings. `hero.css`, `story.css`, `reveal.js` and
`scene.js` are safe. A file called `home-motion.css` would fail, because it contains `motion.css`.

**4.5 The head order is locked.** Test M-1 requires, on the five signed-in pages, this order.

```
css/app.css  →  css/motion.css  →  js/vt.js  →  js/motion.js
```

and no `<script>` may appear before `motion.css`. The head in `base.html` puts `{% block page_css %}`
and the parser-blocking `reveal.js` **after** `motion_head`, which is what keeps that true. On the
homepage the order is `app.css → hero.css → story.css → reveal.js`, and a test pins that too. If you
add a head tag, put it after `motion_head` and re-run the tests.

**4.6 Several files are full.** Measured with the tests' own helper (gzip 9, CRLF normalised).

| file | gzip | cap | spare |
|---|---|---|---|
| `css/motion.css` | 2,818 | 2,850 | 32 |
| `js/vt.js` | 1,868 | 1,900 | 32 |
| `motion.css` + `vt.js` | 4,686 | 4,700 | **14** |
| `js/reveal.js` | 1,377 | 1,400 | **23** |
| `css/story.css` | 3,552 | 3,700 | 148 |
| `hero.css` + `scene.js` + `story.css` | 10,469 | 11,000 | 531 |

Do not edit `motion.css`, `vt.js` or `motion.js`, not even a comment. Build in new files instead. Trim
`reveal.js` before you add to it.

**4.7 No purple, ever.** `tests/test_saas_palette.py` scans every CSS file under `static/` (the
vendored Basecoat in `static/vendor` included), every template and every JS file, and rejects any
colour whose hue is between 230 and 345 at 8 percent saturation or more, plus the words purple,
violet, indigo, lavender, lilac, magenta, fuchsia, orchid, plum, blueviolet, rebeccapurple and
slateblue. Compute the hue of every stop you invent before you write it. The brand is navy `#0B2545`,
deep navy `#081A30`, action blue `#0B6BC7`, sky `#38AEEA`, page `#F3F6FA`. Blue through cyan through
teal is the whole available range and it is enough. An `oklch()` colour is converted to sRGB and
judged by the same hue test, never by its own hue (the brand blues sit at OKLCH hue 236 to 255),
and `color-mix()` is allowed in exactly three forms. They are a variable or `currentcolor` faded
towards `transparent`, the `@supports` probe `color-mix(in lab, red, red)`, and two greys defined
in the same file.

**4.8 `app.js` must not do motion work.** A test fails if it contains the words `pagereveal`,
`view-transition` or `confetti`. New behaviour goes in a new file.

**4.9 Never use `url_for` in a template.** It emits absolute URLs and breaks behind the proxy. Use
the `static_url()` Jinja global for assets and literal paths like `/privacy` for links.

**4.10 Content must never depend on JavaScript to be visible.** The reveal layer hides elements
**only** while `<html data-rv>` is present, and `reveal.js` is the only thing that sets it. It also
removes it on any bail, including no IntersectionObserver, reduced motion, Data Saver, a 2g
connection, a device reporting 2GB of memory or less, a thrown error, and a parse that takes over
three seconds. With JavaScript off there is no attribute and nothing is hidden. The `TARGETS` list in
`reveal.js` and the start-state rule in `app.css` must match selector for selector (test R-1).
Anything that should play once without ever being hidden goes in the separate `DRAW` list and is
marked `data-rv-draw`, never `data-rv-item`. The CSP forbids the usual inline head script that most
reveal libraries rely on.

**4.11 Accessibility is not optional.** `prefers-reduced-motion: reduce` must produce a genuinely
static result, not a faster one. AA contrast throughout, which is 4.5 to 1 for body text and 3 to 1
for large text and the visible edge of a control. WCAG 2.2.2 says anything that moves by itself for
more than five seconds needs a way to stop it. The hero loops, so it has the pause control, and a
test fails if the control goes or stops only half the motion. **Anything new that moves by itself
must either finish inside 5,000ms or be stopped by that same control.** `tests/test_saas_story.py`
fails any `story.css` moment that runs past 5,000ms.

**4.12 Nothing in the hero may be hidden, and nothing there may fade.** The headline is the Largest
Contentful Paint candidate, so nothing inside `.hero` may be a reveal target. The letter's lift is
transform only and is declared **without** the reveal gate, with the gate changing only its timing.
Changing an element's `animation-name` restarts it, so gating the whole animation meant that losing
`data-rv` swapped in `app.css`'s fading `arrive` and the letter blinked out. A test pins this.

**4.13 `motion.css` owns three token names.** It defines `--ease-settle`, `--ease-exit` and
`--ease-spring` and wins on the signed-in pages. Never give a token in `app.css` one of those names.
A test fails if any `app.css` token is redefined by `motion.css`. That is why the settle curve in
`app.css` is called `--ease-land`.

**4.14 The gates.** 1,283 pytest tests and a 607-check smoke script must stay green.

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
applyfirst/saas/templates/home.html     the homepage, hero at the top, 7 sections below
applyfirst/saas/templates/_ui.html      the macro library and the owner switches
applyfirst/saas/templates/_icons.html   inlined SVG icons
applyfirst/saas/static/css/app.css      everything, ~71 KB, layered reset/tokens/base/components/screens
applyfirst/saas/static/css/hero.css     the light hero, homepage only, final `hero` layer
applyfirst/saas/static/css/story.css    the ruler, route and spotlight, homepage only, final `story` layer
applyfirst/saas/static/css/motion.css   onboarding only. DO NOT EDIT
applyfirst/saas/static/css/journey.css  the sign-up journey look, seven templates only, `journey` layer
applyfirst/saas/static/vendor/basecoat-1.0.2-agad.css  trimmed Basecoat, rebuilt only by tools/basecoat/trim.py
applyfirst/saas/static/js/app.js        form behaviour, no motion
applyfirst/saas/static/js/reveal.js     the scroll reveal layer and the draw trigger, every page
applyfirst/saas/static/js/scene.js      the hero canvas and its pause control, homepage only
applyfirst/saas/static/js/vt.js         onboarding view transitions. DO NOT EDIT
applyfirst/saas/static/js/motion.js     onboarding motion. DO NOT EDIT
tests/test_saas_hero.py                 guards for the hero, the scene, the pause control, the gradient and the font
tests/test_saas_reveal.py               guards for the reveal layer and the slots surprise
tests/test_saas_story.py                guards for the story moments, the arrivals, the glows and the focus reveal
tests/test_saas_motion.py               the onboarding motion contract, head order and byte budgets
tests/test_saas_palette.py              the no-purple guard, every static/**/*.css
tests/test_saas_journey.py              the journey layer, scope, frozen values, contrast and page checks
tests/test_saas_basecoat.py             the vendored Basecoat pins and trimmed-content checks
```

Design tokens are at the top of `app.css` in the `tokens` layer. Use them. Do not invent a parallel
colour or spacing system.

---

## 6. Locked decisions, do not relitigate

- Sky blue and dark blue only. Zero purple.
- **The homepage hero is light.** A dark one was built and rejected. The only dark bands on the
  homepage are the Gmail section and the footer.
- The inbox mock and the opened letter stay **bright white**. The promise is an email landing in
  Gmail and Gmail's inbox is white. A frosted-glass inbox is a picture of something that is not Gmail.
- The Continue with Google button is Google's own branding and may not be restyled by a single pixel.
- The device's own font stays on the homepage, privacy and terms. Do not add a webfont there. The
  sign-up journey alone serves the Inter subset to Android and Windows (owner, 2026-09-24); Apple
  devices keep SF.
- The animated background is drawn in the browser. No video files. The audience is on mobile data.
- Sign-up copy stays invite-only while Google review is pending, and pricing stays hidden.
- The hero headline must remain a Largest Contentful Paint candidate, so nothing inside `.hero` may
  be a reveal target.

---

## 7. What premium means on this product

Worth saying plainly, because premium is often read as "add more".

- **Precision beats abundance.** One perfectly timed moment on a page beats five adequate ones.
- **Motion should explain something.** The hero scene is a job post flying into an inbox. The slots
  are the room filling while you read. The ruler says the email lands before you open it. That is the
  bar. A thing that merely moves is decoration and should be cut.
- **The page should feel built, not assembled.** Consistent optical spacing, considered edges, light
  that falls the same way everywhere, and type that sits on a real scale.
- **Nothing may make the page feel slower.** On a mid-range Android on 4G, a premium page is one that
  paints immediately and never stutters. If a choice trades speed for polish, it is the wrong choice.
- **Restraint reads as confidence.** A cheap page shouts. Aim for the feeling of a product that does
  not need to.

---

## 8. Where the opportunities are

The first nine ideas from the previous brief, and what became of them.

| # | Idea | Status |
|---|---|---|
| 1 | Different arrivals for different content | **Done.** rise, fade, settle |
| 2 | Two or three more scroll-driven moments | **Done.** ruler, route, spotlight |
| 3 | Section hand-offs | **Done.** shade under white sections, glows, lit edges |
| 4 | The 9:02 to 9:12 timeline moves | **Done.** the ruler draws once |
| 5 | The letter and inbox reward attention | **Open.** only the letter's lift so far |
| 6 | Depth and layering | **Done.** layered shadow tokens, one light source |
| 7 | FAQ, footer and legal pages | **FAQ and footer done. Legal pages open.** |
| 8 | Desktop pointer interactions | **Open.** |
| 9 | Animated numbers | **Cut on purpose.** a counting "15" says less than the slots already do |

Also cut on purpose, so nobody re-proposes them without a new reason: parallax, mouse tilt on cards,
and a card shadow that grows as the card lands (it repaints every frame on a cheap phone).

Ideas a reviewer raised and the owner has not ruled on. Take them or argue with them.

- The three section glows sit in three different places (footer top-left, Gmail band top-right,
  closing band behind the call to action). A stricter reading of "one light source" would move them.
- The layered shadows are about 1.5 times darker at the edge than the old ones. Worth checking on the
  signed-in pages that also use `--shadow-raised`, like the sign-in sheet.

---

## 9. Anti-goals

Things that would make it worse, listed so nobody has to find out the expensive way.

- Scroll hijacking, scroll jacking, smooth-scroll overrides, or anything that delays a swipe.
- Parallax so heavy it drops frames on a phone.
- A loading screen, a splash, or a skeleton on a page that already paints fast.
- Animating `width`, `height`, `top`, `left`, `background` or `box-shadow`. Transform and opacity
  only. A test fails any other property in a `story.css` or reveal keyframe.
- `backdrop-filter` over the live canvas. It forces a full backdrop readback every frame, which is
  the difference between 60fps and 25fps on a mid-range Android.
- Anything that makes text harder to read at any point in an animation.
- Effects that only work with JavaScript and leave a hole without it.
- More than one primary call to action in a view.
- Copy that implies Agad applies for people, guarantees a job, or promises income.
- Em dashes in user-facing copy. The house style is plain full stops.

---

## 10. How to verify, including the traps

**Run the app locally in every state.** Run it in your own PowerShell window, not as a background
task, because Claude Code reaps background shells when memory is low.

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
Hide the scrollbar before you measure.

```js
document.head.insertAdjacentHTML('beforeend',
  '<style>html{scrollbar-width:none}html::-webkit-scrollbar{display:none}</style>');
```

**Trap two, `ch` units.** `1ch` is glyph-derived and swings 26 percent between the fonts different
platforms serve. Use `em`, which is font-size-derived and identical everywhere.

**Trap three, IntersectionObserver in a test.** Scrolling the page inside a single `page.evaluate`
with `setTimeout` between steps does not yield real animation frames, so the observer never fires.
Drive scrolling with `requestAnimationFrame` between steps.

**Trap four, `overflow: hidden` silently kills a view timeline.** It makes the box a scroll
container, and a view timeline follows the nearest one. The example email card had it, so every
part tracked a card that never scrolls and the spotlight sat frozen on one part. The first
screenshot showed exactly that and was misread as working. The fix is `overflow: clip`. **Never
judge a scroll-driven effect from one screenshot.** Sample it at many scroll positions.

**Trap five, specificity beats a section's own background.** A shade rule at (0,3,0) that set
`background-image` matched the Gmail band and erased its glow, while the contrast test still passed
because it read the declared alphas, not the cascade. A test now checks every glowing section is
excluded from the shade.

**Trap six, an observer can skip a thin element.** A reload that restores the scroll position below
the timing ruler never saw it intersect, and everything waiting on it waited forever. Trigger on the
whole picture, not its thinnest part.

**Trap seven, percent-based animation ranges depend on screen height.** Two stacked steps in sync on
a 390px phone drifted on a tablet. Inset each step's view timeline to a thin line and use pixel
ranges.

**Trap eight, the browser tools.** The Playwright MCP `browser_run_code_unsafe` sandbox has no
`setTimeout`, so use `page.waitForTimeout()`. If the MCP browser fails to launch, a plain
`browser_navigate` restarts it. Fresh `browser.newContext()` windows are signed out. The browser
writes a `.playwright-mcp/` folder into the repo root, so delete it before committing.

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

**Compute contrast, do not trust it.** The hero has three layers painting into it. `tests/test_saas_hero.py`
reads the alphas out of the real files, composites them the way a browser does, and fails under AA.
`tests/test_saas_story.py` does the same for the section glows, reading each section's real ground
colour from `app.css`. If you add a layer, extend those tests rather than working around them.

**Check the states nobody looks at.** JavaScript off, `prefers-reduced-motion: reduce`, Windows high
contrast (`forced-colors: active`), print preview, a 320 pixel viewport, a Facebook in-app browser
user agent, a low-memory phone (`navigator.deviceMemory` of 2), a page whose scripts take over three
seconds, and a reload that lands halfway down. All are handled today and all are easy to break.

**Prove your guards bite.** Break each new test on purpose, confirm it turns red, then restore the
file byte for byte from a backup. Never use `git checkout` or `git stash` for this while work is
uncommitted. A test that cannot fail is worse than no test, because it reads like coverage.

**Get it reviewed.** In the last pass, five independent review lenses plus one skeptic per finding
plus a mutation pass found 13 real defects the author had missed, including the frozen spotlight.
It is worth repeating for any visual pass.

---

## 11. Before you finish

- Both gates green, and say the numbers.
- Screenshot the homepage at 360, 390 and 1280, and at least one signed-in page.
- Say what you cut and why. The cut list is the most useful part of a design pass.
- Give the gzipped byte cost of everything you added, and add or extend a budget test for it,
  modelled on the ones in `tests/test_saas_motion.py` and `tests/test_saas_story.py`.
- Nothing is committed automatically. The owner commits. A privacy hook blocks any command whose text
  contains `.env`, `key` or `credentials`, which includes the words keyboard and keyframes, so keep
  those out of commit messages.
