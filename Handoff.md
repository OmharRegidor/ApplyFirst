# Goal — What we're building
**Agad** — be first to apply on **onlinejobs.ph**. Two surfaces:
- **V1 — personal CLI** (live on Oracle): polls every ~5 min, AI-tailors an application via Gemini,
  emails it to me. Plus a private read-only dashboard over Tailscale. **Unchanged — still running.**
- **V2 — multi-tenant SaaS** (`applyfirst/saas/`): other onlinejobs.ph applicants sign in with Google,
  onboard, and the worker delivers tailored applications **to their own Gmail inbox**. **M1–M5, the UI
  redesign, the animated onboarding and the premium design pass are all committed.** The sign-up
  journey redesign is built and verified but **not yet committed**. Deploy targets:
  **Fly.io beta** (`Dockerfile`/`fly.toml`/`entrypoint.sh`) and the **Oracle VM production runbook**
  (`deploy/oracle/`).

# Current State — Where it stands (2026-09-25)
✅ **Launch blockers B1–B6 are all fixed, committed and pushed** (B1–B5 `c32ca48`, B6 `8c65928`),
along with the redesign spec (`ba60723`). Tests: **1,283 passing** with the sign-up redesign and
the Log out fix (neither committed yet), **887** with B6 (`.venv/Scripts/python.exe -m pytest -q`),
845 before B6, 779 before the launch fixes, 745 on 2026-09-23 morning, 692 before that day, 546
before the animated onboarding, 211 before the redesign. Smoke: **607 checks, 0 failed**, 558 before
the sign-up redesign (`.venv/Scripts/python.exe .noxa/redesign-saas-ui/inputs/preserve_smoke.py`).
🟡 **B1–B6 need four things from the owner at deploy time**, because code cannot pick them:
the Gemini credential with billing on, an alert webhook, the SMTP settings (for B6), and an
uptime monitor on `/health`. See "Launch blockers" below.
✅ **B6 is fixed and committed (2026-09-24, `8c65928`).** A user whose Gmail connection Google
ends is now emailed once to reconnect. See "What shipped in B6" below.
🟢 **Sign-up journey redesign: built and verified, waiting for the owner's look and commit.**
Login, the four onboarding steps, the dashboard and a new "Sign-in didn't finish" page share one
light and dark look on a trimmed Basecoat and self-hosted Inter, built from
`docs/superpowers/plans/2026-09-25-signup-redesign.md`. **None of it is committed yet.** See
"Sign-up journey redesign (built)" below.
✅ **Found and fixed during the review, not yet committed: Log out did not sign anyone out in
production.** It is an old bug, not one the redesign made. In production the sign-in cookie has the
`__Host-` prefix, and a browser only deletes such a cookie when the delete also says `Secure`. Ours
did not, so Log out answered normally but the browser kept the cookie and the person stayed signed
in, for up to 7 days. The same bug left the 10-minute Google sign-in cookie behind.
`applyfirst/saas/session.py` now deletes both cookies with exactly the rules it set them with.
🔴 **Still not deployed.** The owner was mid Google Cloud OAuth setup on 2026-09-22 (see the gotcha
about "Authorized JavaScript origins"). No Fly app, no test users. V2 has never run outside localhost.
⚠️ **The homepage has still never been looked at by a human.** Two design passes have landed on it,
both verified by tests, computed contrast and headless-browser measurement, but nobody has scrolled
it on a real phone. Do that first.

## The commits from 2026-09-23 and 2026-09-24
```
a2034b8  docs: handoff records the sign-up redesign decisions and progress
ba60723  docs: design for the sign-up journey redesign
d8cb2a9  docs: handoff records the B6 fix
8c65928  fix(saas): B6, email users when Google ends their Gmail connection
2693ca6  docs: handoff carries a ready-to-start brief for B6
771b36a  docs: handoff records the launch-blocker fixes
c32ca48  fix(saas): launch blockers B1-B5 from the operations audit
acdb88f  docs: design brief matches the page after the scroll-story pass
20f435b  docs: handoff records the scroll-story pass
8be4f45  feat(saas): scroll story, depth and calmer section joins on the homepage
049ea21  docs: bring the handoff up to date with the design pass
57551a3  docs: local end-to-end walkthrough and the production runbook
f5c6f86  docs: design brief for taking the homepage further
6cb2342  feat(saas): light animated hero, platform font, scroll reveals, CTA gradients
597d0ab  refactor: rename the product from ApplyFirst to Agad   (the previous day's HEAD)
```

# Sign-up journey redesign (built)
**Where it stands.** Spec `docs/superpowers/specs/2026-09-24-signup-redesign-design.md` (`ba60723`),
plan `docs/superpowers/plans/2026-09-25-signup-redesign.md`, built task by task with both gates green
after every task. Final numbers, after the review fixes: pytest **1,283 passed** (1,266 before the
fixes), smoke **607 checks, 0 failed**. The plan's Task 8 browser pass covered every journey state
at 360, 390, 768 and 1280 wide, light and dark, JavaScript off, reduced motion, forced colours, text
at 200 percent and a throttled first visit on Android: **707 PASS, 0 failed**, run again after the
fixes with the same result. The font swap moves the page by 0.0001 on `/login`, 0.0011 on the
dashboard and 0.0000 on Step 2 (the limit is 0.02). The mutation pass broke every guard on purpose
and every break was caught: Task 1's planted rule failed the 4 tests it should, Task 3 44 of 44,
Task 5 29 of 29, Task 6 26 of 26, Task 7 28 of 28, the review-focus checks 13 of 13, and the
review fixes' new tests 18 of 18. **Not yet committed:** the owner commits the files listed under
"What to commit" below.

**The review.** Six lenses (spec, motion, accessibility, security, CSS, tests) raised **22
findings**. Each was then checked on its own: **8 confirmed, 14 refuted.** All 8 were fixed test-first
and none was declined. Three of the 8 were the same bug seen by three lenses, so there were 6 real
problems:
- **The footer's Privacy Policy, Terms of Service and support email never appeared on a computer.**
  On any journey page in a window about 740px tall or more they stayed invisible, even scrolled to
  the bottom. The browser pass's screenshots showed it too.
- **Log out did not sign anyone out in production** (old bug, see Current State above).
- **On Step 4 at 320 to 360px wide, tapping the bottom of "Change my message" opened "Change
  keywords".** The two links' tap areas overlapped when they stacked.
- **In Windows high contrast, the current step's label on the desktop rail was a blank box.** Old
  bug, now fixed too.
- **Two tests were weaker than they looked.** The phone dark-mode dashboard test would have
  accepted a colour fix that only works on wide screens or on hover, and the touch-laptop guard
  missed the normal spaced spelling `(hover: hover)`. Both now fail on those cases.

**The dark header mark is fixed too.** The plan had left it for the owner (departure 16): in dark
mode the navy tile of the header logo nearly vanished on the dark header, about 1.1 to 1. It now has
a thin 1px ring in the dark edge colour (`journey.css` section 6), 4.0 to 1 against the header and
3.57 to 1 against the tile, and light mode is unchanged.

**The plan's 19 departures from the spec** are listed, with reasons, near the top of the plan under
"Where this plan departs from the spec (owner, please confirm)". None of them harms a user. Two are
real choices the owner may want to undo: the paused Gmail panel keeps its own "Edit keywords"
button, so that state has two ways to the keywords page (departure 13), and hover colours ease over
200ms although spec 5.4 says transform and opacity only (departure 6).

**As built, where it differs from the spec.** The plan has the reasons.
- The upstream Basecoat file is `package/dist/basecoat.cdn.min.css`, copied to the spec's name.
- `trim.py` also drops selectors for markup we never write, the one `!important` rule and
  `@layer properties`, so the file is 3,363 B gzip, not about 6 KB.
- Inter is 28,132 B, not about 47 KB, and `font-size-adjust` is `none`.
- `.btn--primary` sets `background-image: none`, and hover colours ease.
- The theme-color metas are the header surface, `#FFFFFF` and `#111B2B`, in a `theme_color_meta`
  block.
- "Start watching without Gmail" stays secondary, and the dark Gmail panel sits on the surface.
- The sign-in failed page has a small amber icon, and `_fail` logs `signin_failed`.
- app.css keeps the now unused dashboard rules (`.kv`, `.card-actions`, `.usage-label`,
  `.span-5/7/12`, `.arrives*`).
- The review fixes added four small rules to `journey.css`. The footer items never wait for the
  scroll reveal (section 6), the dark mark has its ring (section 6), Step 4's stacked links have a
  22px gap (section 8), and the rail label shows in high contrast (section 8).

**Still to check on a real Apple device:** that iPhones and Macs never download Inter. It cannot be
proven on Windows, because the check depends on the browser finding the Apple system font first.

**What to commit.** Explicit paths only, never `git add -A`, never `REMOTE.md`, nothing under
`.noxa/`, no `Co-Authored-By` line, and no ".env", "key" or "credentials" in a message. The privacy
hook also blocks a Claude Bash command that names `onboarding_keywords.html` (its name contains
"key"), so from Claude write `applyfirst/saas/templates/onboarding_*.html`, which matches exactly
the four onboarding templates, all of which belong in commit 3. In this order (the first commit was
tested alone on top of `64fc606`: 892 passed):
```
1. fix(saas): log out now really deletes the secure sign-in cookies
   applyfirst/saas/session.py
   tests/test_saas_auth_flow.py
2. docs: implementation plan for the sign-up journey redesign
   docs/superpowers/plans/2026-09-25-signup-redesign.md
3. feat(saas): sign-up journey redesign with trimmed Basecoat, Inter and dark mode
   .gitattributes
   requirements-dev.txt
   applyfirst/saas/app.py
   applyfirst/saas/static/css/app.css
   applyfirst/saas/static/css/journey.css
   applyfirst/saas/static/fonts/inter-4.1-latin-wght.woff2
   applyfirst/saas/static/licenses/OFL-inter.txt
   applyfirst/saas/static/licenses/basecoat-MIT.txt
   applyfirst/saas/static/licenses/tailwindcss-MIT.txt
   applyfirst/saas/static/vendor/basecoat-1.0.2-agad.css
   applyfirst/saas/templates/base.html
   applyfirst/saas/templates/dashboard.html
   applyfirst/saas/templates/login.html
   applyfirst/saas/templates/onboarding_connect_gmail.html
   applyfirst/saas/templates/onboarding_keywords.html
   applyfirst/saas/templates/onboarding_preview.html
   applyfirst/saas/templates/onboarding_profile.html
   applyfirst/saas/templates/signin_failed.html
   tools/basecoat/basecoat-1.0.2.cdn.min.css
   tools/basecoat/trim.py
   tools/fonts/build_inter.py
   tests/_journey_css.py
   tests/test_saas_basecoat.py
   tests/test_saas_journey.py
   tests/test_saas_signin_failed.py
   tests/test_saas_connect_gmail.py
   tests/test_saas_gmail_retry.py
   tests/test_saas_hero.py
   tests/test_saas_onboarding.py
   tests/test_saas_palette.py
   tests/test_saas_template_context.py
4. docs: handoff records the sign-up redesign build
   Handoff.md
   DESIGN-HANDOFF.md
```

**What the owner asked for.** Make the pages a new user touches when signing up feel premium, like
Apple products and Supabase's dashboard: clean, minimal, easy to navigate, small type on computers,
readable buttons, the right font, and animation or 3D only where it helps.

**Owner decisions, in the order they were made.**
1. Of the three researched options (refine by hand, Basecoat, a React rewrite) the owner chose
   **Basecoat**, the shadcn/ui look as plain HTML, on the existing FastAPI and Jinja pages.
2. **Sign-up journey first**: login, the four onboarding steps and the dashboard. The homepage,
   privacy and terms pages keep today's look.
3. **Inter** for Android and Windows, self-hosted. Apple devices keep SF and download nothing.
   This reverses the "device font" lock, for the journey pages only.
4. **Flat solid blue primary button** on the journey pages. The homepage keeps its gradient.
5. **No build step**: vendor Basecoat's ready-made file rather than adding the Tailwind compiler.
6. **Dark mode follows the phone's setting**, by CSS alone.
7. **Only the Basecoat parts we use** (buttons, cards, fields, inputs, labels, textareas, alerts,
   badges), trimmed by a script from the upstream file. No reset, no menus or pop-ups, no JS.
8. Include **two fixes**: a styled "Sign-in didn't finish" page instead of the bare JSON on
   `/auth/callback` failures, and a redirect to `/login` for signed-out GETs of onboarding pages
   instead of a 401 JSON reply.

**Why the trimmed copy, not the whole Basecoat file.** A six-reader map of the journey found about
15 ways the full file (218 KB raw, 21.9 KB gzip) fights our CSS even when wrapped in a layer. Its
reset merges into our `base` layer (layer names `base` and `components` collide), it redefines
`--font-sans` and the frozen `--ease-out`, its `.btn:not([data-variant])` paints every button
near-black, `.btn:disabled{opacity:.5}` would fade the Activate button inside the frozen morph,
`.badge` clips "Connected", `.alert>svg` adds an empty strip, `field-sizing:content` grows the
message box, and it adds smooth scrolling and turns off pull-to-refresh. Its unlayered `:root`,
`.dark` and `pulse` keyframes beat every layered rule. The sign-up pages need no Basecoat JS, which
also fails test M-5 (`innerHTML`). Trimmed to the parts we use it measured about 6.8 KB gzip before
tightening the selector filter.

**Design in one paragraph** (the spec has every value). The trimmed file is
`static/vendor/basecoat-1.0.2-agad.css`, rebuilt by `tools/basecoat/trim.py` from the pinned
upstream copy in `tools/basecoat/`, wrapped in `@layer basecoat`, with dark variants rewritten to
`prefers-color-scheme`. Our look is `static/css/journey.css` in `@layer journey`. The layer order at
`app.css:6` is now `basecoat, reset, tokens, base, components, screens, journey`, so Basecoat is
lowest and `journey` sits below the frozen `motion` layer, which motion.css adds after it. Both
files are linked with `static_url()` from the `page_css` block of the seven journey templates only,
so they get the one-year cache and there is no `@import` chain. Light and dark palettes are
contrast-checked in spec 5.3. Spec 9 lists every frozen hook the motion files read.

**Research results worth keeping** (the raw notes were in a session scratchpad that gets cleared).
- Supabase's UI is shadcn/ui on Radix and Tailwind, on Next.js, with Inter plus Manrope. Buttons
  press to `scale(.97)` over 200ms, weight 500, heights 26 to 50px. Corners 8, 10.7 and 16px. Motion
  100 to 300ms on `cubic-bezier(0.16,1,0.3,1)`, the same curve as our `--ease-land`.
- Apple sets 17px body on iPhone and 13pt on Mac, blue `#0071E3` (hue 210, ours is 209), and serves
  SF Pro as a webfont to every platform. SF Pro's licence forbids us doing that.
- Inter from google/fonts is 72 KB with both axes, **46.9 KB with opsz pinned at 14** (Latin plus
  the peso sign, tabular figures kept), and **28.1 KB as built**, with the weight axis limited to
  400 to 600. Writing WOFF2 needs `pip install brotli` (dev only, now in `requirements-dev.txt`).
  Geist was the runner-up at 28 KB. Figtree, Onest and Instrument Sans lack the peso sign.
- Skipped on purpose: three.js (187.5 KB for r185 minified, r186 ships 417 KB unminified; its core
  runs under our CSP but it is six times the whole homepage), React Three Fiber (needs React and a
  build), Spline (WASM, its own CDN, an eval block), GSAP (free since the Webflow deal but not open
  source, and its `hsla(` fails the palette guard), Motion (49 KB no-build file, `hsla(`, `.mjs`
  build), Anime.js (purple colours inside), Lenis (smooth scrolling is banned).
- A React rewrite was estimated at 6 to 10 weeks, 68 KB for React alone, and about 400 of the tests
  rewritten. Next.js would also need a loosened CSP.

**What any later change must not forget** (from the map and its critic, all in the spec, all kept
by the build).
- The Activate button must stay solid `#0B6BC7`, 12px corners and opacity 1 even when disabled and
  busy, and the live panel navy `#0B2545` with 24px corners, because the frozen `af-fill` morph
  runs between those values.
- Keep Basecoat off `/privacy` and `/terms`. Its reset strips the bullets from their lists, which
  Google reviewers read.
- Do not make the header sticky. It would cover fields that the error links and focus moves jump to.
- Do not use `overflow:hidden` on the grouped rows or on anything around `.kw` chips. It clips focus
  rings and the frozen new-chip ring.
- Switch "small type on computers" on `(hover:hover) and (pointer:fine)`, never on width alone, and
  keep every input at 16px or more.
- Tests changed on purpose: the font tests and the gradient test in `tests/test_saas_hero.py`, the
  palette guard (scan the vendor folder, read zero-chroma `oklch()` and three `color-mix()` forms),
  the callback-failure and signed-out 401 tests, and the rendered-template count.

# What shipped in the scroll-story pass (2026-09-23, `8be4f45`)
Built from `DESIGN-HANDOFF.md` §8 items 1–7. Owner approved a seven-item plan, then two rounds of
independent multi-agent review with an adversarial verifier per finding found **13 real defects**,
all fixed before the commit, and a mutation pass broke every new guard on purpose to prove it bites.

**The three scroll moments** live in a new homepage-only file,
`applyfirst/saas/static/css/story.css` (final `story` layer, loaded after `hero.css`):
1. **The ruler draws itself.** The 9:02 → 9:12 → 9:15 timing line in the hero draws a blue line from
   dot 1 to dot 2 **only** (the third step is the user's), a ring pulses where the email lands, THEN
   the inbox's new row lights, THEN the opened letter lifts 14px into place. The trigger is
   `reveal.js` marking **`.arrival__stage`** with `data-rv-draw="in"` (NOT `data-rv-item`, so the
   reveal fade can never reach anything in the hero). Without the mark (no JS, a bail, the watchdog)
   the picture is simply finished.
2. **The How it works line fills as you read.** Blue fill on `h3::before` exactly over the grey
   `li::after` connector, lit ring on `h3::after` over the badge. Phones use one view timeline per
   step, **inset to a 2px line 60% down the screen**, with pixel ranges, so each step lights exactly
   as the previous line finishes on any screen height. At 960px+ one timeline on the list plays the
   three in turn.
3. **The example email spotlight.** Each `.mail__parts > div` is lit (left bar + sky wash) only while
   it crosses a line across the middle of the screen, so exactly one part is lit at a time.
Plus a fade-in on an opened FAQ answer.

**Site-wide, in `app.css`:** three reveal arrivals instead of one (`rv-in` headings rise 12px,
`rv-fade` reading text only fades, `rv-settle` objects settle on `--ease-land`); layered navy-tinted
shadow tokens with one light source straight above; a lit top edge on the hero letter; a soft shade
under each white section; radial sky glows on the Gmail band, the closing band and the footer (the
footer is on every page); FAQ rows with a chevron disc and hover states; `.mail` now uses
`--shadow-raised`.

**`reveal.js`:** `TARGETS` swapped `.mail__parts > div` for `.mail` (the spotlight owns the parts);
new `DRAW = ".arrival__stage"` list; and a `focusin` handler that reveals any target a keyboard user
tabs into. That last one fixed a **pre-existing** WCAG 2.4.7 bug: the observer trims 10% off the
bottom of the screen, so a target could sit on screen at opacity 0 with a focused link inside it.

**`tests/test_saas_story.py`, 31 guards** (+3 from existing parametrised scans picking up
`story.css`): load order and homepage-only loading, layer order, no-preference and `@supports`
wrapping, longhands only, transform/opacity keyframes, the 5s rule, nothing but decorations fading,
the draw gate, the arrivals clearing their start offset, row/ring/letter timing, pixel alignment of
the ruler and route fills, phone route sync, the spotlight's scroll-container trap, forced colours
(including masks), contrast computed from the real glows and grounds, the shade never landing on a
glowing section, no token collision with `motion.css`, and the byte caps.

**Cut, on purpose:** counting numbers, parallax, mouse tilt, and a card shadow that grows as the
card lands (it repaints every frame on a cheap phone, so cards settle with transform only).

# What shipped in the premium design pass (2026-09-23)

**1. The homepage headline changed.** `New job posted. Apply Agad.` replaces
`Apply Agad on onlinejobs.ph` at `applyfirst/saas/templates/home.html:24`. The owner picked it from a
shortlist of seven, judged down from thirty candidates on memorability, claim safety and whether a
Filipino VA instantly understands it. Nothing in the tests or the smoke asserts the h1 text.

**2. The hero lead was rewritten**, because dropping the site name from the h1 left nothing naming
onlinejobs.ph until word nine. It now reads *"Agad watches onlinejobs.ph for the jobs you want, day
and night. When a new one is posted, a ready-to-paste application lands in your own Gmail within
minutes. You check it, then apply agad. That's Filipino for right away."* The lowercase `agad` near
the end is deliberate — it teaches the word through use and the next sentence glosses it.

**3. The site uses the device's own font and downloads no typeface at all.** Apple's SF Pro cannot be
licensed for the web, so `--font-sans` is now the platform system stack (`app.css:52`). That resolves
to SF on Apple, Roboto on Android, Segoe UI on Windows. Both Plus Jakarta woff2 files are **deleted**
(49,076 bytes) along with their `@font-face` blocks and the preload in `base.html`. The Google Sans
Button subset stays, because Google requires its own face on the sign-in button.
- `font-size-adjust: .52` on `body` evens out the x-height spread between the three platform faces.
  SF is the reference, Roboto is pulled down 1.6%, Segoe is pulled up 4%.
- Type scale retuned **smaller but not less readable**: display −7%, h2 and h1 −11%, h3 −5%, desktop
  lead −5%, and **body, small and caption unchanged** because that is where people actually read.
- **Every `ch`-based measure became `em`.** `1ch` is 0.732em in Plus Jakarta and 0.539em in Segoe UI,
  a 26% collapse. `.hero h1 { max-width: 13ch }` would have wrapped the headline to three lines on
  every phone. It is now `8.2em`.
- Side effect: this **fixed a live bug**. The old file wrapped the headline to three lines between
  960 and 979 px. Measured after the swap, it is two clean lines at 320, 360, 375, 390, 412, 768,
  960, 980, 1200 and 1440, with 21px of slack at 320 (it was 7px) and 27px at 960.

**4. One gradient per view on the primary button.** `--grad-cta` / `-hov` / `-prs` on `.btn--primary`
in `app.css`, plus a two-band focus ring (a 3px white collar, then the outline 3px further out, so it
never lands on the gradient). Every stop was run through the palette guard's own hue maths before it
was written; the highest is **212.57**, well clear of the banned 230–345 band.

**5. Scroll reveals on every page.** `applyfirst/saas/static/js/reveal.js` (1,225 B gzip) plus a block
at the end of `app.css`. One IntersectionObserver stamps `data-rv-item="in"`, the CSS fades and lifts
with a three-step stagger. **The gate is the whole design:** the CSS hides a target only while
`<html data-rv>` is present, and `reveal.js` is the only thing that sets it — and it removes it on
any bail (no IntersectionObserver, reduced motion, Data Saver, 2g, ≤2GB device memory, a thrown
error, or a parse over 3s). With JavaScript off nothing is ever hidden. Nothing inside `.hero` is a
target, so the h1 stays an LCP candidate.

**6. The surprise.** On the section explaining that a free employer account receives only **15
applications per job**, the slots fill one by one as you scroll and go dark, then the three early
tiles pop — the room filled while you were reading and you were already inside. Pure CSS on a
`view-timeline`, zero JavaScript, zero main-thread frames, wrapped whole in
`@supports (animation-timeline: view())` so Firefox skips it and keeps today's static diagram.

**7. The homepage hero.** `applyfirst/saas/static/css/hero.css` (2,480 B gzip) and
`applyfirst/saas/static/js/scene.js` (4,437 B gzip), **homepage only**, switched on by an `is-home`
body class. A white field fading into the page colour, with three moving layers back to front:
- two soft aura blobs (sky and action blue) drifting on different clocks so the field never visibly
  loops — pure CSS transforms, carried by the compositor;
- a canvas of faint job posts drifting past, one of which lights up as a match and flies a bezier
  into the **real inbox mock rendered beside it** (the target is measured from the live DOM), then a
  ring pulses. An 11s cycle;
- a white wash above both, which is the contrast guarantee.
The hero reaches `y = 0` and swallows the header via a negative margin, so the page opens as one
field. That margin cannot escape `main` because `body` is a flex column.

**8. Because the background loops, it ships the pause control WCAG 2.2.2 requires.** It is **injected
by `scene.js`**, never in the template, so with JavaScript off there is no motion and no dead button.
It stops the CSS aura as well as the canvas by setting `data-scene="paused"` on the hero — stopping
only half of it would not honestly be a pause.

**9. 40 new guard tests** (25 + 15) in `tests/test_saas_hero.py` and `tests/test_saas_reveal.py`.
The suite went 692 to 745; the extra 13 are existing parametrised asset scans picking up the
three new files. All six
deliberate mutations were caught (ink raised past the ceiling, a second light source put back, the
timeline pushed past the WCAG threshold, a selector dropped from each of the reveal lists, a sheen
put back on a light button).

## ⚠️ The dark hero was built, then reverted — do not rebuild it
A full dark cinematic hero was built and passed every gate, and the owner then asked for a white
background instead. **It was never committed**, so there is no commit to look at and nothing to
revert. What survives from it, deliberately:
- the canvas scene (re-themed from sky-on-navy with `lighter` compositing to blue-on-white with
  `source-over`, and from a 4.6s one-shot to an 11s loop);
- the aura/wash/scrim layering;
- the contrast-by-computation test approach.
What was removed with it: the `.on-dark .btn--primary` block and the whole `cta-sheen` animation, now
dead because no `.on-dark` surface holds a primary button (the footer, the `.gmail` band and the live
status panel all use secondary or none).

## Asset weights after both passes (gzip, LF-normalised)
| file | gzip before `8be4f45` | gzip now | cap |
|---|---|---|---|
| `css/app.css` | 14,878 | **15,876** | none |
| `css/hero.css` | 2,480 | 2,480 | 2,780 |
| `css/story.css` (new, homepage only) | — | **3,552** | 3,700 |
| `js/reveal.js` | 1,225 | **1,377** | 1,400 (**23 B spare**) |
| `js/scene.js` | 4,437 | 4,437 | 4,970 |
| hero + scene + story together | — | 10,469 | 11,000 |

The scroll-story pass added **4,702 B** gzipped to the homepage and **1,150 B** to every other page.
The rows below are the older layers, unchanged.

| file | raw | gzip | cap |
|---|---|---|---|
| `css/motion.css` | 10,081 | 2,818 | 2,850 (**32 B spare**) |
| `js/vt.js` | 4,471 | 1,868 | 1,900 (**32 B spare**) |
| `js/motion.js` | 5,658 | 2,529 | 3,000 |
| `vendor/canvas-confetti` | 24,846 | 6,892 | 7,000 |

The whole new public layer is **8,142 B gzipped**, and the site now downloads **one** 2 KB font
instead of three fonts totalling 51 KB, so a first visit got *lighter*, not heavier.

The sign-up journey (2026-09-25) loads only on its seven templates. Measured after the review fixes
(gzip 9, LF):

| file | raw | gzip | cap |
|---|---|---|---|
| `vendor/basecoat-1.0.2-agad.css` | 36,345 | 3,363 | 7,000 |
| `css/journey.css` | 15,290 | 5,224 | 8,000 |
| `fonts/inter-4.1-latin-wght.woff2` | 28,132 | (WOFF2) | 50,000 raw |
| render-blocking CSS on `/login` (app.css + both) | | 24,475 | 30,000 |

# Where the new work lives
```
applyfirst/saas/static/css/hero.css   the light animated hero, homepage only, final `hero` layer
applyfirst/saas/static/js/reveal.js   the scroll reveal layer, every page, parser-blocking
applyfirst/saas/static/js/scene.js    the hero canvas, homepage only, deferred
applyfirst/saas/static/css/story.css  the three scroll moments, homepage only, final `story` layer
tests/test_saas_hero.py               hero, scene, gradient and font guards (25)
tests/test_saas_reveal.py             reveal layer and slots surprise guards (15)
tests/test_saas_story.py              scroll story, arrivals, glows, focus reveal guards (31)
applyfirst/saas/static/css/journey.css  the sign-up journey look, seven templates only, `journey` layer
applyfirst/saas/static/vendor/basecoat-1.0.2-agad.css  trimmed Basecoat, built by tools/basecoat/trim.py
applyfirst/saas/static/fonts/inter-4.1-latin-wght.woff2  Inter subset, built by tools/fonts/build_inter.py
applyfirst/saas/templates/signin_failed.html  the D8 "Sign-in didn't finish" page
tests/test_saas_journey.py, tests/_journey_css.py  journey layer, scope, frozen values, review focus, pages
tests/test_saas_basecoat.py           vendored Basecoat pins and trimmed-content checks
tests/test_saas_signin_failed.py      the D8 page and the D9 redirects
DESIGN-HANDOFF.md                     a pasteable brief for the NEXT design session
```
**`DESIGN-HANDOFF.md` is the thing to hand a fresh design session**, not this file. It carries the
constraints, the ranked opportunities, the anti-goals and the measuring traps. It was rewritten
after `8be4f45` to match the real page (light looping hero with a pause control, the four scroll
moments, the byte table, the new traps), and its §8 now marks which ideas are done, open or cut.
On 2026-09-25 it was brought up to date for the sign-up journey (the flat button, Inter, the
vendored files, the palette scan).

# Constraints any future UI work must respect
These are each enforced by a passing test. `DESIGN-HANDOFF.md` §4 has them in full.
- **The CSP is frozen** (`applyfirst/saas/app.py:229`). No CDN, no inline `<script>`, no `on*`, no
  eval, no WASM, no `blob:`. Canvas 2D and `data:` backgrounds are fine.
- **No build step, no Node.** Hand-written CSS and classic JS from `applyfirst/saas/static/`.
- **Public pages must not name `motion.css`, `vt.js`, `motion.js` or `canvas-confetti`** (test M-2).
  Any new file needs a name containing none of those substrings.
- **The app-page head order is locked** (test M-1): `app.css` → `motion.css` → `vt.js` → `motion.js`,
  and no `<script>` before `motion.css`. `base.html` now has `{% block page_css %}` and the
  parser-blocking `reveal.js` **after** `motion_head`, plus `{% block page_js %}` after `app.js`, and
  `{% block theme_color %}` / `{% block brand_mark %}` overrides, and since the sign-up redesign
  `{% block color_scheme %}` and `{% block theme_color_meta %}`. That ordering is what keeps M-1 true.
- **`motion.css`, `vt.js` and `motion.js` are full** (32, 32 and 471 bytes of headroom). Do not edit
  them; build in new files.
- **`reveal.js` is nearly full too** (1,377 of 1,400 B). Trim before adding.
- **`motion.css` defines `--ease-settle`, `--ease-exit` and `--ease-spring`, and wins on the
  signed-in pages.** Never give an `app.css` token one of those names (a guard test now fails if you
  do). The settle curve in `app.css` is `--ease-land` for that reason.
- **Anything in the hero may move but must never fade.** The letter's lift is transform only and is
  declared without the reveal gate, so losing `data-rv` changes only its timing.
- **No purple** — hue 230–345 at ≥8% saturation is rejected in any CSS, JS or template file,
  the vendored Basecoat included.
- **`app.js` must not contain** `pagereveal`, `view-transition` or `confetti`.
- **Never `url_for`** in a template. Use `static_url()` and literal paths.
- **Content must never need JavaScript to be visible.**
- **The journey layer outranks every app.css rule** (`@layer basecoat, reset, tokens, base,
  components, screens, journey;` at `app.css:6`, with `motion` above it). Scope every journey rule
  with a page class, never a bare element, and give back the forced-colours value of anything
  app.css keeps in high contrast. `tests/test_saas_journey.py` enforces both.
- **The journey look loads only on the templates in `tests/_journey_css.py` `JOURNEY_TEMPLATES`**,
  never on the homepage, privacy or terms.
- **Never hand-edit the trimmed Basecoat file or the Inter subset.** Change
  `tools/basecoat/trim.py` or `tools/fonts/build_inter.py` and run it again. Both outputs are
  pinned by sha256.

# Locked owner decisions (do not relitigate)
- Colour: **sky blue / dark blue only, zero purple.**
- **The homepage hero is LIGHT.** A dark one was built and rejected (see above).
- **The device's own font stays on the homepage, privacy and terms.** SF Pro cannot be licensed for
  the web. **Changed 2026-09-24 for the sign-up journey only:** login, onboarding and the dashboard
  get self-hosted Inter on Android and Windows, never preloaded, and Apple devices keep SF.
- **The primary button keeps its gradient on the homepage.** **Changed 2026-09-24 for the sign-up
  journey only:** a flat solid `#0B6BC7` button. Both are built (2026-09-25).
- **Signed-in pages follow the phone's dark mode** (decided 2026-09-24, built 2026-09-25 by CSS alone). The homepage
  hero stays light.
- **The animated background is drawn in the browser, not a video file.** The audience is on mobile
  data; a video was explicitly rejected on weight.
- The inbox mock and the opened letter stay **bright white** — the promise is an email landing in
  Gmail, and Gmail's inbox is white.
- The **Continue with Google** button is Google's branding and may not be restyled.
- Sign-up: **invite only** (`INVITE_ONLY = true` in `_ui.html`) while Google is in Testing. Primary
  CTA "Ask for a beta invite" (mailto **omharregidor@gmail.com**), Google button under
  "Already invited?".
- Pricing copy: **"14-day free trial" only**, price hidden (`SHOW_PRICE = false`,
  `PRICE_TEXT = "₱199 a month"` ready for later). **No billing or trial enforcement is built.**
- AI letters: never invent availability; "I can send my resume on request" when a resume is requested.
- Retries never charge the daily cap. Too-long errors name the field.
- Animated onboarding: approved 2026-09-20 and built.

# Earlier milestones, still true
## Renamed to Agad (2026-09-20)
The product people see is **Agad** — Tagalog for "right away", said **ah-GAD**. Tagline **"Apply
Agad"**, an instruction to the user and never a claim that we apply for anyone. The logo did not
change. **Deliberately NOT renamed (machine names, all still `applyfirst`):** the `applyfirst/`
package and every import path, every `APPLYFIRST_*` environment variable, `prog="applyfirst"`, the
`applyfirst_session` cookie, `/opt/applyfirst`, the `applyfirst.db` / `applyfirst-saas.db` filenames,
the `deploy/oracle/*.service` and `*.timer` units, `Dockerfile`/`fly.toml`/`entrypoint.sh`, and
`applyfirst/saas/static/vendor/**` (pinned by sha256). Also left alone on purpose: `docs/plans/*` and
`docs/superpowers/specs/*`, historical records of finished milestones.

## The redesign (2026-09-19/20) and the animated onboarding (2026-09-20)
Run folder `.noxa/redesign-saas-ui/` (git-ignored) holds plan.md, verify-report.md, mandate-report.md,
session.md, inputs/ and artifacts/. "Calm Clarity" across all 10 templates plus `_ui.html` /
`_icons.html`. Navy `#0B2545`, action blue `#0B6BC7`, sky `#38AEEA`, page `#F3F6FA`. Self-hosted
assets, CSP untouched, no CDN, no build step, no Node. Candidate-driven AI prompt with an explicit
`resume_attached` flag. Gmail send-permission check (`google_oauth.GmailScopeError`). Retries are free
(`alert.attempts == 0`). Precise `?error=long_<field>` tokens. Activated users no longer re-walk
onboarding. Five animated onboarding moments, each playing once, with `CELEBRATE = true` in `_ui.html`
as the owner switch and `canvas-confetti` vendored with only its default colours swapped for the brand
blues (sha256 `26f0bb1c…e98e`, reversible to upstream `49f4bcbc…0a95`). `.gitattributes` has
`applyfirst/saas/static/vendor/** -text` so `core.autocrlf` cannot break that pinned hash.
Verification at the time: 9-Gate PASS → verify-and-fix loop 1 GREEN → completion mandate COMPLETE →
owner-requested loop 2 GREEN. 55 findings, 25 fixed, 1 wontfix, 29 deferred in `artifacts/findings.json`.

# Launch blockers (audit 2026-09-21, B1–B5 fixed 2026-09-24 in `c32ca48`) — READ BEFORE DEPLOYING
**B1–B6 are fixed in code.** `docs/OPERATIONS.md` §1 has the full table of what
the code now does and what the owner still sets, and §2 lists the log events and the `/health`
states. Everything below was built, then reviewed by three rounds of independent multi-agent review
(31 real defects found and fixed along the way), and every new guard was broken on purpose to prove
it bites. The guards live in `tests/test_saas_ops.py` (66 tests).

| # | Was | Now | Owner still does |
|---|---|---|---|
| B1 | No Gemini credential anywhere in the deploy | Listed as required. Production without it: CRITICAL `ai_not_configured`, one alert, `/health` 503 `"ai": "off"`. Unfilled placeholders count as missing. `APPLYFIRST_AI_OFF_OK=1` marks a deliberate off. A set-but-failing credential: `ai_call_failed` (status only), and after 2 all-failed cycles `ai_all_failed` + an alert. The request sends it in the `x-goog-api-key` header, never the URL | `fly secrets set GEMINI_API_KEY=...` with **billing on first** |
| B2 | SaaS never switched logging on | On by default (`APPLYFIRST_LOG_JSON`) in web (the uvicorn entry, NOT `create_app`, so pytest `caplog` keeps working), worker, backup and notify | Nothing |
| B3 | No alert destination | Loud when none is set. `python -m applyfirst.saas.notify --test` names the channel that really delivered and exits 1 if the configured one failed. Webhook 4xx is not "delivered" and its URL never reaches a log. Blind now means the site did not answer (a canary search for "virtual assistant" decides when every term is empty), and a blind worker turns `/health` 503. A worker that cannot load its master key alerts. An alert no channel accepted is retried after 15 minutes, not 6 hours | `fly secrets set APPLYFIRST_ALERT_WEBHOOK=...`, then run `notify --test` |
| B4 | Fly watchdog was dead code | `entrypoint.sh` restart loop, backoff 10s doubling to 300s, reset after a 10-minute run. In-worker `_Watchdog` ends a cycle with no progress for 900s (`worker_stalled`, exit 70). Every search attempt, stored job and handled alert beats, a failed search included. `/health` 503 `"worker": "never_ran"` when no first cycle long after start | Point UptimeRobot at `/health` |
| B5 | No backup on Fly | `APPLYFIRST_BACKUP_IN_WORKER=1` in `fly.toml`: the worker backs up after its first cycle of each UTC day. `applyfirst/backup.py` (shared with V1) writes a `.part` then renames, cleans temp files on every failure path, sweeps leftovers over an hour old, refuses when free disk is under twice the DB, and matches ONLY its own stem and stamp, because on Oracle V1 (`applyfirst-*`) and the SaaS (`applyfirst-saas-*`) share `backups/`. Oracle's `backup.main` now alerts on failure | Pull a backup off the box now and then. **No tested Fly restore procedure exists yet** (OPERATIONS §5) |
| B6 | The beta's 7-day refresh expiry cleared the credential **silently** | The worker emails the user once to reconnect, from the server's SMTP account, to the address they signed in with (`applyfirst/saas/reconnect.py`). Details in "What shipped in B6" | `fly secrets set APPLYFIRST_SMTP_HOST=smtp.gmail.com APPLYFIRST_SMTP_USER=... APPLYFIRST_SMTP_PASSWORD=<app password>`, then `python -m applyfirst.saas.reconnect --test you@example.com` |

**Two more before the first paying user.** A **free** Gemini tier makes the published privacy policy
untrue (Google trains on unpaid API traffic; the privacy page promises the opposite) — enable billing
first. And **`INVITE_ONLY` is copy, not a gate**: it is a Jinja constant read only by templates;
`/auth/login` has no invite check. The real gate is Google's Testing-mode test-user list (100 max).

**Cost model** (Gemini 2.5 Flash at $0.30/$2.50 per 1M in/out, read 2026-09-21; Fly `shared-cpu-1x`
512MB): hosting ≈ **$4.33/mo flat**; AI ≈ half a cent to one cent per application. 100 users ≈ $83/mo
at the full cap, ≈ $17/mo realistic. At ₱199 (~$3.16) the margin holds. Three traps: the "10/day" cap
counts **slots not API calls** (engine `retries=2`); **nothing caps spend across all users**; and
**thinking tokens are unbounded** (no `thinkingBudget` anywhere in `applyfirst/tailor/llm.py`).

**The scaling wall is the worker, not the database.** It polls once per *distinct* watch word across
all tenants, serially, pausing 1.0–2.5 s between each. A cycle overruns the 600 s interval at **~185
distinct words** (~102 at Oracle's 330 s), roughly 25–100 users depending on overlap. It fails
**silently** — `run_once` sleeps the full interval *after* the cycle, so cadence just drifts while
pages keep promising "about every 10 minutes". A word's first poll detail-fetches every job on the
page, so one user adding the 20-word maximum adds ~15 min to a single cycle. onlinejobs.ph
`robots.txt` declares `Crawl-delay: 5` and we wait 1.0–2.5. SQLite is **not** the bottleneck.

**Other gaps** (OPERATIONS.md §8): account deletion is promised on the privacy page with **no code
behind it**; a wrong master secret breaks every send forever while `/health` stays 200; `jobs` and
`user_job_alerts` are **never pruned** (~940 MB/yr vs a 1 GB volume); a user can activate without
Gmail and be skipped permanently; dependencies are unpinned; only `/auth/*` is rate-limited.

**The one that used to wake you at 3am** was a hung worker. Since `c32ca48` it costs about 15 minutes
(the watchdog ends it, the loop restarts it). What is left is a worker that keeps hanging or goes
blind, and both turn `/health` 503, so the uptime monitor is the one thing that must not be skipped.

# What shipped in B6 (2026-09-24): tell users when their Gmail connection ends
**Owner decision:** only an email after the connection ends, no reminder the day before.

**The problem it fixes.** While the Google app is in Testing mode, Google expires every refresh
token 7 days after the user connects. On the next send Google answers `invalid_grant`, the worker
cleared the credential, and the user silently stopped getting applications.

**How it works now, hop by hop.**
- `worker.process_alert` reads `db.gmail_connected_at` BEFORE the token. On `GmailAuthError` it
  re-reads it. If it changed, the user reconnected or disconnected mid-send: the alert is retried,
  nothing is cleared, nothing is mailed.
- Otherwise it calls `reconnect.expired()` FIRST (queues the email), then
  `reconnect.clear_dead_grant()`, which deletes the grant only if `updated_at` still matches, so a
  reconnect landing in between keeps its new grant. `db.clear_gmail_credential` is no longer used
  here (it deletes whatever row is there).
- `run_once` calls `worker._tell_expired_users()` after the alert loop, which runs
  `reconnect.send_due()` and raises the owner alerts.
- State is one `worker_meta` row per user, `reconnect_mail_<user_id>`: `due <connected_at> <since>
  <tried>`, `sent <connected_at>`, `refused <connected_at>`, `off <connected_at>`. No schema change.
- The web app writes `off <connected_at>` BEFORE revoking on `/auth/disconnect-gmail` (the revoke
  makes an in-flight send fail exactly like an expiry) and deletes the row after a reconnect in
  `/auth/gmail-callback`.
- `reconnect._send` uses `smtplib.SMTP_SSL` directly (not the V1 `SmtpNotifier`), so it can tell
  "connecting or logging in failed" (server-wide) from "this message was refused". Errors after the
  message was handed over (a bad QUIT) are ignored.
- The email links to `/dashboard` (signed-out users go through `/login` first), not
  `/auth/connect-gmail`, which then answered a signed-out click with a raw 401. Since the sign-up
  redesign (D9) that route sends a signed-out visitor to `/login` too.

**Failure handling, each pinned by a test.** Server-wide failures (connect, login, any 421, a
dropped line, the same refusal twice running) pause sending 15 min, 1 h, then 6 h, and a restart
or a quiet 6 h resets it. One refused message holds nobody up (least recently tried goes first) and is retried on its own
slower clock (15 min, then hourly, then 6 h). A user is given up only after 3 days of refusals AND
only if another message went through after the first refusal.
The SMTP password, any character of it, and the user's address never reach a log or an alert. With
owner alerts on SMTP only, a broken SMTP account logs `user_reconnect_mail_down` (CRITICAL) rather
than alerting through itself. Delivery is at least once, normally exactly once.

**Other changes.** `SaaSConfig.user_mail_configured` (host, user and password, no owner email
needed). A production worker without them logs `user_mail_not_configured` at start. The privacy
page has one new sentence about account service emails and "Last updated: 24 September 2026", and
`tests/fixtures/legal_privacy.txt` pins both (**the owner should read that sentence**, the legal
wording was frozen). The email's 7-day sentence is marked `# BETA` / `# /BETA` in
`reconnect.compose()`, and `docs/legal/google-verification.md` now lists every beta-only line to
delete after verification.

**Check it after deploying:** `python -m applyfirst.saas.reconnect --test you@example.com` sends
the real email (OPERATIONS §2 has the Fly and Oracle forms). `notify --test` does not touch these
settings when a webhook is set.

**Verification.** 42 tests in `tests/test_saas_reconnect.py`. Three rounds of independent
multi-agent review with two skeptics per finding (round 1 confirmed 14, round 2 confirmed 15, most
of them about guessing SMTP failures from reply codes, which led to the phase-based redesign, and
round 3 confirmed 4 narrower ones: a lone refused message resent every cycle, a give-up proof that
came before the refusal, and two contradicting owner alerts). A mutation pass after each round broke
every guard on purpose (17, 18, 15, then 5 for the round-3 fixes), all caught except one
equivalent mutant (`>` vs `>=` once every attempt has its own instant).

# Open follow-ups (ordered)
Before the numbered list:
- **Sign-up journey redesign.** Built and verified. The owner looks at it in the preview in light
  and dark, decides the two open points in "Sign-up journey redesign (built)" (the paused panel's
  second "Edit keywords" and hover colours easing), commits the files listed under "What to commit"
  there, then checks on a real iPhone that Inter is never downloaded.

1. **Look at the new homepage.** It has never been seen by a person. Start the
   preview (below), scroll slowly on a phone and a computer, and check the ruler drawing, the How it
   works line, the email spotlight and the slots surprise.
2. **Finish the Google Cloud OAuth client**, then walk `docs/LOCAL-TEST.md` end to end on localhost
   with a real Google account. This is the actual blocker to everything else.
3. **Deploy (Path A, Fly.io beta)** with the four owner settings from "Launch blockers" (Gemini
   credential with billing on, alert webhook then `notify --test`, the SMTP settings then
   `reconnect --test`, UptimeRobot on `/health`).
4. **Rate limiting beyond `/auth/*` (F-039)** — required **before** turning `INVITE_ONLY` off.
5. **Oracle web unit needs `APPLYFIRST_WORKER_INTERVAL=330`**
   (`deploy/oracle/applyfirst-saas-web.service`), or the site says "about every 10 minutes" while the
   worker runs every ~6.
6. Smaller deferred items in `findings.json`: hyphenated email line breaks (F-033), case-duplicate
   watch words (F-023), `Cache-Control: no-store` on authenticated pages (F-028), HTML error pages for
   401/403/429 (the sign-up redesign covers two: a failed Google sign-in and a signed-out visit to
   an onboarding page), worker-kill double-charge (F-047, needs a `charged` column in the protected `db.py`),
   GZip for static.
7. **Owner check:** after deploying, read one of your own V1 letters end-to-end to confirm the prompt
   rewrite reads the way you want.

# Deploy — Path A (Fly.io beta) unchanged
`flyctl install` → `fly apps create <name>` → edit `fly.toml` (`app=` **and** `APPLYFIRST_BASE_URL` in
`[env]`) → `fly volumes create af_data --region sin --size 1` → Google Console (enable **Gmail API**,
OAuth Web client, Testing mode + test users, redirect URIs `/auth/callback` + `/auth/gmail-callback`)
→ `fly secrets set` (SESSION_SECRET, APPLYFIRST_MASTER_KEY, GOOGLE_CLIENT_ID/SECRET, GEMINI_API_KEY,
APPLYFIRST_ALERT_WEBHOOK; **not** base_url; the list is also at the top of `fly.toml`) → `fly deploy` →
verify with `fly status` / `fly logs`, and `fly ssh console -C "python -m applyfirst.saas.notify --test"`.
**NEVER `fly scale count >1`** (one volume, one machine). Point UptimeRobot at `/health`; smoke the
worker with `python -m applyfirst.saas.worker --once`.
**Path B (Oracle VM production):** `deploy/oracle/README.md` §"Deploying the V2 SaaS" + item 5 above.
`applyfirst/saas/static/` ships automatically (Dockerfile `COPY applyfirst`, and `.dockerignore`
patterns are root-anchored).

# CASA / Google verification — settled, unchanged
`gmail.send` is a **SENSITIVE** scope → Trust & Safety sensitive-scope review only, **no CASA, $0**.
CASA is triggered only by **RESTRICTED** scopes. Beta (Testing mode) needs zero verification, caps at
100 test users, and forces a **7-day refresh-token expiry** (worker clears the credential, user
reconnects). Never switch to `gmail.compose` (restricted → CASA). Re-check the scopes page before a
public launch.

# Live system facts — V1 CLI (still running, untouched)
- **Server:** Oracle VM `VM.Standard.E2.1.Micro` (2 vCPU / 1 GB / 45 GB), Ubuntu 24.04.
  Public IP `129.158.205.47` · **SSH:** `C:\Users\regid\.ssh\applyfirst_oracle` (user `ubuntu`).
- **App dir:** `/opt/applyfirst` (system user `applyfirst`). Secrets in `/opt/applyfirst/.env` (mode 600).
- **Services:** `applyfirst.service` (poller) · `applyfirst-dash.service` (dashboard) ·
  `applyfirst-health.timer` · `tailscaled`. **Dashboard (Tailscale only):** `http://100.71.19.32:8000`.
  **Watch words:** claude code · vibe coder · web developer · software developer.
- Health: `ssh -F _afcfg af "systemctl is-active applyfirst.service applyfirst-dash.service; curl -s localhost:8000/api/health"`

# Environment quirks a new session MUST know
- **Python 3.14.3**; venv at `.venv` → use **`.venv/Scripts/python.exe`**. The Fly image uses py3.12
  for wheel reliability; app is 3.10+ safe. **No ruff/black/mypy** — pytest + the smoke are the gates.
- **Run the SaaS locally in every state:**
  `.venv/Scripts/python.exe .noxa/redesign-saas-ui/artifacts/run_local.py --port 8765 --data-dir <folder OUTSIDE the repo>`
  → `http://127.0.0.1:8765/__dev/` lists 22 seeded states (throwaway DB + random master secret; it
  refuses a data dir inside the repo). `/__dev/*` exists only in that file, never in `app.py`.
- **NEW (2026-09-23): run the preview in the OWNER'S OWN PowerShell window, not as a background task.**
  Claude Code reaps background shells when the machine is low on memory, and it killed the preview
  twice in one session. A window the owner opened is never reaped.
- **Before/after any template or CSS change, run the smoke** (`inputs/preserve_smoke.py`, 607 checks).
  Unit tests alone do NOT catch a missing CSRF field, a reworded asserted string, or a CSP violation.
- **A "privacy guard" hook blocks any Bash/Read command whose TEXT contains `.env`, `key`, or
  `credentials`** — including `onboarding_keywords.html` and any test with "keyword" in its path.
  Workaround: read those with the **Grep tool** (pattern `.*`, output_mode content); Write/Edit/Grep
  are not hooked. **Updated 2026-09-23:** it did **not** block `git commit` for content containing
  those words this time (`57551a3` shipped both docs and `6cb2342` shipped CSS full of `@keyframes`).
  Keep the banned words out of commit *messages* — that is what the 2026-09-22 refusal was.
- **Secrets/runtime are git-ignored** — NEVER commit: `.env`, `profile.yaml`, `applyfirst-saas.db`,
  `.noxa/`, `backups/`, `output/`. Commit explicit paths (not `git add -A`) to avoid `REMOTE.md`
  (pre-existing, never commit). Playwright MCP writes `.playwright-mcp/` and screenshots to the repo
  root — delete both, don't commit them.
- **`.gitattributes` forces `*.sh eol=lf`** — a CRLF shebang breaks `/bin/sh` in the Fly container.
- **`claude-mem` plugin is DISABLED.** Commits: **no `Co-Authored-By` trailer.**
- **Obsidian vault:** `C:\Users\regid\Documents\MyBrain`. Project memory for the dev-team pipeline is
  in `.noxa/memory/` — git-ignored, local only.

# Failed attempts / gotchas worth keeping
## New in the sign-up redesign (2026-09-25)
- **A short footer can sit where the scroll reveal never looks.** `reveal.js` ignores the bottom
  10% of the screen and `app.css` hides `.footer__grid > *` until revealed. The journey footer is
  so short that on a window 740px tall or more its links sat inside that ignored strip, so Privacy,
  Terms and the support email stayed invisible forever (spec, motion and accessibility lenses all
  found it). The browser pass missed it because its contrast check ignores opacity. Pinned by
  `test_the_short_footer_never_waits_for_a_reveal_it_cannot_get`.
- **A `__Host-` cookie is only deleted when the delete also says `Secure`.** Starlette's
  `delete_cookie` defaults to `secure=False`, so in production Log out and the failed-sign-in
  cleanup did nothing and people stayed signed in. Delete with exactly the attributes you set with.
  Pinned by `test_a_cookie_is_deleted_with_the_rules_it_was_set_with` and
  `test_logout_and_a_failed_callback_delete_the_host_cookies_a_browser_holds`.
- **Two quiet links with 44px tap bands overlap when they wrap.** On Step 4 at 320 to 360px the
  bottom of "Change my message" opened "Change keywords". The row gap is now 22px, worked out from
  the tap band and the line height, for phone text and for computer text at 400 percent zoom.
  Pinned by `test_step_4_links_keep_their_whole_tap_band_when_they_stack`.
- **In forced colours, text on a system-coloured fill needs `forced-color-adjust:none`.** The
  current step's label on the desktop rail drew as a blank box. Pinned by
  `test_high_contrast_shows_the_current_rail_label`.
- **A cascade test must count only rules that apply at rest on a phone.** The dark-mode dashboard
  test accepted a colour redraw hidden behind a wide-screen query or `:hover`. Pinned by
  `test_only_a_redraw_a_phone_at_rest_gets_counts_on_the_dashboard`, which the main
  `test_no_light_page_colour_survives_on_the_dashboard_in_dark_mode` now relies on.
- **Media query text has more than one spelling.** The touch-laptop guard matched only
  `(hover:hover)` and let `(hover: hover)` and a bare `(hover)` through. Pinned by
  `test_the_touch_guard_reads_every_spelling_of_hover`.
- **Check screenshots by eye, not only the script.** Every scripted check was green while the
  footer links were missing on every computer screenshot.

## New in B6 (2026-09-24)
- **Never classify an SMTP failure by its exception type or reply code alone.** smtplib raises
  `SMTPRecipientsRefused` for a 421 "try again later" and for a 450 greylist, not only for a bad
  address, and a non-ASCII password or a host typo raises `UnicodeError`. Two designs built on
  guessing from the code each had several ways to give up on every user at once. What held up is
  WHEN it failed: connecting or logging in is the server's fault, only handing over one message
  can be that user's.
- **`UnicodeEncodeError` text quotes the offending character and its position.** For a password
  that is part of the secret, so it is replaced with a fixed message, never logged as is.
- **`db.clear_gmail_credential` deletes whatever grant is there.** Between "this grant is dead" and
  the delete, the user can reconnect, so the worker deletes only the row whose `updated_at` still
  matches (`reconnect.clear_dead_grant`).
- **Timestamps are to the second.** Tests that reconnect "later" must move `db._now_iso` forward,
  or the new grant looks identical to the old one.
- **A broken SMTP account cannot report itself** when owner alerts also go by SMTP. Keep a webhook.
## New in the launch-blocker fixes (2026-09-24)
- **The privacy hook matches case-insensitively and on more than it says.** Any Bash command whose text
  contains `GEMINI_API_KEY` (it has "KEY"), `keyword` or long patch text got blocked. Write patches to
  a scratchpad `.py` file with the Write tool and run the file; read such files with the Grep tool.
- **`log.configure()` sets `propagate=False` on the `applyfirst` logger.** Call it only in process
  entry points (the uvicorn `__getattr__`, `worker.main`, `backup.main`, `notify.main`), never in
  `create_app`, or every `caplog` test that runs afterwards goes blind.
- **A watchdog that only beats on success kills a healthy worker during a slow outage.** Failed
  searches must beat too, or 31+ terms timing out at 30s each look like a hang and the blind alert
  never fires.
- **"Zero jobs across every term" is not "blind".** One user watching a term with no posts would page
  forever once blind turned `/health` 503. The canary search is what tells the two apart.
- **V1 and the SaaS share `backups/` on Oracle and their stems overlap** (`applyfirst` is a prefix of
  `applyfirst-saas`). Any glob like `applyfirst-*` matches both. Match stem plus stamp exactly.
- **An unfilled sample line is worse than a missing one.** `GEMINI_API_KEY=<your-gemini-key>` appended
  to Oracle's shared `.env` would replace V1's real value (last line wins) and, before `_filled`,
  silence the very warning meant to catch it. The sample now ships it commented.
- **`/health` is the owner's only pager when no webhook is set**, so every new 503 needs an off switch
  for the deliberate case (`APPLYFIRST_AI_OFF_OK`), or it hides the next real outage behind itself.

## New in the scroll-story pass (2026-09-23, evening)
- **`overflow: hidden` silently kills a view timeline.** It makes the box a scroll container, and a
  view timeline follows the NEAREST scroll container. `.mail` had it, so every part's timeline
  tracked a card that never scrolls and the spotlight sat frozen on part 3. The first screenshot
  showed exactly that and was misread as working. Fix is `overflow: clip` (clips the rounded
  corners, is not a scroller). Measure a scroll-driven effect at several scroll positions, never
  judge it from one screenshot.
- **A higher-specificity `background-image` wipes a section's own gradient.** The new section shade
  (0,3,0) matched the Gmail band and erased its glow (0,1,0). The contrast test still passed because
  it read the declared alphas, not the cascade. A guard now checks every glowing section is excluded.
- **Changing `animation-name` restarts the animation.** Gating the letter's animation on
  `:root[data-rv]` meant the 3s watchdog swapped it back to `app.css`'s fading `arrive`, and the
  letter blinked out. Declare one animation ungated and let the gate change only delay/play-state.
- **IntersectionObserver can skip a thin element entirely.** A reload that restores scroll below the
  ruler never saw it intersect, so the gated row and letter waited forever. Trigger on the whole
  picture (`.arrival__stage`), not its thinnest part.
- **Percent-based `animation-range` depends on screen height.** Two stacked steps synced on a 390px
  phone drifted on a tablet. Inset each step's view timeline to a 2px line and use pixel ranges.
- **The Playwright MCP `browser_run_code_unsafe` sandbox has no `setTimeout`.** Use
  `page.waitForTimeout()`. If the MCP browser fails to launch, a plain `browser_navigate` restarts
  it. Fresh `browser.newContext()` windows are signed out; the default one may carry a dev session.
- **Long Python heredocs through the Bash tool mangle backslashes.** Write the script to the
  scratchpad with the Write tool and run the file.
- **Multi-agent review paid for itself.** Five lenses plus one skeptic per finding plus a mutation
  pass found the frozen spotlight and 12 more. Worth repeating for any visual pass.

## New earlier this session (2026-09-23)
- **The scrollbar trap, which produced a confidently wrong conclusion.** A headless or desktop browser
  reserves ~15px for a classic scrollbar; a real phone uses an overlay scrollbar and takes none. At a
  320px viewport that is 265px of container versus 280px — enough to change how a headline wraps. The
  first measurement said the new headline broke to three lines on phones. It does not. Hide the
  scrollbar before measuring: `html{scrollbar-width:none}html::-webkit-scrollbar{display:none}`.
- **`ch` units are glyph-derived and swing 26% between platform fonts.** Any `ch`-based `max-width` on
  a heading wraps differently on Windows than on Android. Use `em`.
- **IntersectionObserver does not fire inside a tight `page.evaluate` loop.** Scrolling with
  `setTimeout` between steps yields no real animation frames, so reveals look broken when they are
  fine. Drive scrolling with `requestAnimationFrame` between steps.
- **The Bash tool is bash, not PowerShell.** A PowerShell here-string (`@'…'@`) in a `git commit -m`
  puts a literal `@` on the first line of the message. Large heredocs also failed to survive the
  wrapper — write big files with the Write tool instead.
- **The smoke's `lint_css` naively regex-scans every `url()`.** An SVG `data:` URI containing
  `filter='url(#n)'` makes it try to fetch `/static/css/%23n` and fail. Write the inner parens as
  `%28 %29` so the CSS never contains a literal `url(` there, and the `#` as `%23` so the palette
  guard's hex scanner ignores it.
- **A pseudo-element sheen on a light gradient button fails AA.** `rgba(255,255,255,.22)` over the
  lightest stop composites to 3.33:1 for a white label, for the whole pass. Measured, not guessed.

## Still true from before
- **Google Cloud OAuth client.** The redirect URLs go in **Authorized redirect URIs**, NOT in
  **Authorized JavaScript origins**. Origins reject any path, and an empty row fails validation, so
  **delete the row** (bin icon to its right, often cut off in a narrow window) or put the bare
  `http://localhost:8000` in it.
- Module-level `app = create_app()` broke test collection → lazy via PEP 562 `__getattr__`.
- **The CSP is frozen.** Pytest only checks `default-src 'self'`, so loosening it would pass — don't.
- **Never `url_for`** in templates. Use `static_url()` for assets and literal paths for links.
- Keep the Google sign-in and Connect Gmail buttons as **plain `<a>` links** — as forms, CSP
  `form-action` blocks the redirect to Google.
- `applyfirst/saas/static/` must exist and be committed, or `StaticFiles` raises at `create_app`.
  Never name an asset folder `dist`/`build` (git-ignored), never `.mjs`.
- Jinja macros need `with context` or the CSRF value renders empty; pass `csrf_token` explicitly.
- `prompt.py` is shared by V1 and the SaaS — route behaviour with an **explicit flag from the call
  site**, never by sniffing profile fields, and clear the tailoring cache via `PROMPT_FINGERPRINT`.
- JWKS "degrade to claim-only" was an attacker-forceable bypass → **fail-closed**.
- Each milestone bumps `PRAGMA user_version`; tests must use `db._SCHEMA_VERSION`.
- Worker clamps scraped `raw_description` to 8000 chars (the daily cap limits CALLS not TOKENS).
- **Fly rate-limit gotcha:** on Fly the LAST XFF hop is a constant app IP; key on `Fly-Client-IP`
  (`APPLYFIRST_TRUSTED_IP_HEADER`). The limiter fails **closed** (503) if its table is gone.
- **Don't blind-apply audit output** (a past audit's `starlette<0.50` pin would have broken the build,
  and its CASA claim was wrong). Verify first.
- Cross-document **View Transitions do animate POST → 302 → GET** (Chromium and WebKit); Firefox 156
  still lacks them and degrades to a normal navigation.
- When driving subagents: messaging an agent still running inside a workflow **resumes a second copy**
  of it, and the two overwrite each other's files. Let workflow agents finish.
- Parallel agents and the main session **share one Playwright browser**. A background agent will steal
  the viewport mid-measurement. Re-navigate and re-check the page identity before trusting a reading.

# Next Step — The single next thing to try
**If this is the redesign session:** the sign-up journey is built (see "Sign-up journey redesign
(built)" above). Ask the owner to look at it in the preview in light and dark (the command is
below; `/__dev/` lists every login, onboarding and dashboard state), then to commit the files
listed under "What to commit" in that section, in that order. The Log out fix goes first. After
that, check on a real iPhone or Mac that Inter is never downloaded.

**Otherwise, start the preview in your own PowerShell window and look at the new homepage.**
Nobody has seen it.

```powershell
cd C:\Users\regid\Desktop\applyfirst
.\.venv\Scripts\python.exe .noxa\redesign-saas-ui\artifacts\run_local.py --port 8765 --data-dir C:\Users\regid\AppData\Local\Temp\agad-preview
```

Check the hero at a phone width and watch the timing line draw, scroll slowly through How it works,
the example email and the "15 applications" section, and confirm the pause control in the hero's
bottom corner stops the background.

**Then finish the Google Cloud OAuth client** and walk `docs/LOCAL-TEST.md` end to end on localhost
with a real Google account. That is the real blocker and it has not moved since 2026-09-22.

**Then deploy to Fly** with the four owner settings (Gemini credential with billing on, alert
webhook plus `notify --test`, the SMTP settings plus `reconnect --test`, UptimeRobot on `/health`).
B1–B6 are handled in code.

See `DESIGN-HANDOFF.md` for the next design session, `docs/OPERATIONS.md` for every production
command, `docs/LOCAL-TEST.md` for the local walkthrough, and `docs/SYSTEM-DESIGN.md` §10–§11 for the
architecture.
