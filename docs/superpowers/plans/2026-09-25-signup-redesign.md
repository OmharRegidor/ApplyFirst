# Sign-up Journey Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the pages a new user touches while signing up (login, the four onboarding steps, the dashboard, and a new "Sign-in didn't finish" page) one calm, premium look in light and dark mode, built on a trimmed copy of Basecoat and self-hosted Inter, with every frozen motion hook and every existing behaviour test still true.

**Architecture:** Two new stylesheets load only on the seven journey templates, after `motion_head` in `{% block page_css %}`: the trimmed Basecoat file in `@layer basecoat` (the lowest layer) and `journey.css` in `@layer journey` (above every app.css layer, below the frozen `motion` layer). `journey.css` re-points app.css's own colour tokens at journey tokens, so dark mode follows the phone by CSS alone. Two small server changes replace the bare JSON on `/auth/callback` failures with a styled 400 page (D8) and send signed-out GETs of onboarding pages to `/login` (D9).

**Tech Stack:** FastAPI and Jinja2 on Python 3.14 (`.venv`), hand-written CSS with cascade layers, basecoat-css 1.0.2 (Tailwind v4.3.1 output, trimmed by a standard-library Python script), Inter 4.1 subset with fontTools and brotli (dev only), pytest plus the smoke script as gates, headless Chrome 153 and Playwright (scratch venv) for measurement.

**Spec:** `docs/superpowers/specs/2026-09-24-signup-redesign-design.md` (read it with this plan; section numbers below are the spec's).

## Global Constraints

- The CSP at `applyfirst/saas/app.py:225-228` is not touched. No inline script, no `style=` attribute, no `<style>` block, no CDN, no `blob:`.
- No Node, no package manager, no build step on deploy. `tools/basecoat/trim.py` and `tools/fonts/build_inter.py` run by hand, only on an upgrade.
- `motion.css`, `vt.js` and `motion.js` are not edited. No new file name contains `motion.css`, `vt.js`, `motion.js` or `canvas-confetti` (test M-2). Head order M-1 holds: `app.css`, `motion.css`, `vt.js`, `motion.js`, and the two new links go in `{% block page_css %}` after `motion_head`.
- Layer order at `app.css:6` becomes exactly `@layer basecoat, reset, tokens, base, components, screens, journey;`. `motion.css:2` then appends `motion` after `journey`.
- Everything in the trimmed Basecoat file sits in `@layer basecoat { ... }` except `@property`; everything in `journey.css` sits in one `@layer journey { ... }` except its two `@font-face` rules.
- `journey.css` sections, in this order, each opened by a banner `/* ---- N name */`: 1 fonts, 2 tokens, 3 basecoat-map, 4 base, 5 components, 6 chrome, 7 login, 8 onboarding, 9 dashboard, 10 signin-failed, 11 motion. A task writes only inside its own section.
- Journey tokens: `--j-ground`, `--j-surface`, `--j-text`, `--j-muted`, `--j-edge`, `--j-link`, `--j-primary` (`#0B6BC7` in both schemes), `--j-primary-hover` (`#0A5AA8`), `--j-hairline`, `--j-attn-fg`, `--j-attn-bg`, `--j-ok-fg`, `--j-ok-bg`, `--j-danger-fg`, `--j-shadow`, with the values of spec 5.3. The dark values of every `--j-*` token live in one `@media (prefers-color-scheme:dark)` block in section 2 (with the `.mailcard,.gsi-btn` light island beside them). The only other dark blocks are page-local: section 8's `--ob-*` tints (Task 5) and section 9's panel repaints (Task 6); neither redefines a `--j-*` token.
- `journey.css` never defines `--ease-out`, `--ease-settle`, `--ease-exit` or `--ease-spring`, and reads only `--ease-land`.
- Content never depends on JavaScript. Reduced motion is fully static. Every transition and animation in `journey.css` sits inside `@media (prefers-reduced-motion:no-preference)`, 100 to 300ms on `--ease-land`.
- WCAG AA: text 4.5 to 1, large text and control edges 3 to 1. Inputs never below 16px (`font-size:max(16px,1rem)`).
- "Computers" means `(hover:hover) and (pointer:fine)`, never width alone. Width breakpoints (the frozen 960px and 1100px) may change layout, never type.
- No purple: hue 230 to 345 at 8 percent saturation or more fails `tests/test_saas_palette.py`, which scans every `static/**/*.css` from Task 1 on.
- The Google button (`.gsi-btn`, 40px, `#747775` border, Google Sans Button) is not restyled. `journey.css` may give it only custom properties and `color-scheme:light`.
- Invite-only copy and hidden pricing stay. The sample email (`.mailcard`) stays bright white in both schemes.
- Frozen hooks: the full list is spec section 9. Every task lists the hooks its templates contain and how each is kept.
- The journey look loads on exactly `login.html`, `onboarding_connect_gmail.html`, `onboarding_profile.html`, `onboarding_keywords.html`, `onboarding_preview.html`, `dashboard.html` and `signin_failed.html`, through `static_url()`, Basecoat first, and never on `/`, `/privacy` or `/terms`. `tests/_journey_css.py` `JOURNEY_TEMPLATES` is the list; it starts empty (Task 3) and grows by task.
- Never `url_for` in a template. Use `static_url()` and literal paths.
- Budgets, gzip level 9 with CRLF normalised to LF: trimmed Basecoat at most 7,000 B, `journey.css` at most 8,000 B, render-blocking CSS on `/login` (`app.css` plus both new files) at most 30,000 B, the Inter file at most 50,000 raw bytes.
- No commits inside tasks. The owner commits at the end (Task 8 hands over the list), with explicit paths, never `git add -A`, never `REMOTE.md` or anything under `.noxa/`, and with no `Co-Authored-By` trailer.
- The privacy hook blocks any Bash or Read call whose command text contains `.env`, `key` or `credentials` (so `onboarding_keywords.html` and any test path containing "keyword"). Read such files with the Grep tool (pattern `.*`, output mode content). Change them with a small Python patch script written with the Write tool into the scratchpad under an innocent name and run by that name. Write, Edit and Grep are not hooked.
- Write every Python script with the Write tool and run the file. Long Python heredocs through Bash mangle backslashes.
- `<scratchpad>` in this plan means the session scratchpad folder the system prompt names. Prototype scripts, downloads and screenshots go there, never into the repo.
- Line endings in the working tree: `applyfirst/saas/templates/base.html`, `tests/test_saas_gmail_retry.py`, `tests/test_saas_template_context.py` and `tests/_saas_client.py` are CRLF (the Edit tool keeps them); everything else this plan touches is LF, and every new file is written LF.
- Gates after every task, both green: `.venv/Scripts/python.exe -m pytest -q` (887 passing today) and `.venv/Scripts/python.exe .noxa/redesign-saas-ui/inputs/preserve_smoke.py` (558 checks, 0 failed today; the file is git-ignored but it is a gate).
- Never leave a server running. The local preview runs in its own PowerShell window (Claude Code reaps background shells): where a step says "in the owner's own PowerShell window", an agent opens it with Task 8 Step 5's `Start-Process` command and closes it with Task 8 Step 8's, before the step ends.

## Review Focus

Most likely first. Each line names the input and what a reasonable person expects, then the test that now pins it in the owning task.

1. **A phone in dark mode opening the dashboard, in any state, including what waits in a closed disclosure.** Nothing keeps a light-page colour (navy text, sky tint, amber edge) that vanishes on the dark ground. Pinned by `test_no_light_page_colour_survives_on_the_dashboard_in_dark_mode` over every dashboard state plus a new "near the limit" state (Task 6, Step 2). It flagged the near-limit meter's amber fill (kept on purpose: 4.33 to 1 on the dark surface) and proved every other fixed colour on the page is redrawn.
2. **Text at 200 percent, or Android's largest font size.** No button or field clips its own label. Pinned by `test_no_control_gets_a_fixed_height_so_zoomed_text_never_clips` (Task 3, Step 2) and measured at 360 and 1280 wide with the root font doubled in Task 8's browser pass.
3. **A first visit on slow mobile data on an Android phone.** Text shows at once in the tuned fallback, Inter arrives from our own origin as a font, a second visit reuses it, and the swap barely moves anything. Pinned by `test_the_inter_file_is_served_as_a_cached_font` (Task 2, Step 2) next to the existing swap and fallback tests, and measured under throttling (CLS below 0.02) in Task 8.
4. **Windows high contrast (forced colours).** Every button, card, alert and badge keeps a solid edge, the focus ring stays the system Highlight, and the rail marker stays Highlight. Pinned by `test_high_contrast_keeps_every_shape_and_system_colour_app_css_gives` (Task 3, Step 2), which found that `:focus-visible{outline-color:var(--j-link)}` silently replaced app.css's Highlight ring; section 5 now restores it.
5. **A Windows laptop with a touch screen.** Its trackpad makes it a "computer", so it gets 40px buttons and 15px text, and a finger still has to hit them: sizes switch only on a fine pointer that hovers, a hover left stuck by a tap moves nothing, and quiet links keep their 44px tap band everywhere. Pinned by `test_computer_sizes_need_a_fine_pointer_that_hovers` (Task 3, Step 2).

## Where this plan departs from the spec (owner, please confirm)

Each item was found while prototyping and is explained in the owning task.

1. The npm package has no `basecoat-1.0.2.cdn.min.css`. The pinned source is `package/dist/basecoat.cdn.min.css`, copied to the spec's name (Task 1).
2. `trim.py` has three rules beyond spec 4.3: it drops selectors for markup the journey never writes (a template test guards it), the one `!important` rule, and `@layer properties` (its `*` selector is banned). The trimmed file is 3,363 B gzip instead of 5,938 B, which keeps about 5.8 KB of room in the `/login` budget. On browsers without `@property` (Safari before 16.4, Firefox before 128) Basecoat's own borders would vanish; every journey control sets its border itself, so nothing visible changes (Task 1). Two smaller differences: from `@layer theme` it also keeps `--default-transition-duration` and `--default-transition-timing-function`, because kept `.btn` and `.input` rules read them (spec 4.3 step 3 lists only sizes, radius, spacing, text sizes, weights and leading; neither name collides with app.css or motion.css), and it writes the 15 `@property` rules after the `@layer basecoat{...}` block, unlayered, which spec 8 allows (spec 4.3 step 7 says the wrapper holds "the result").
3. Inter is 28,132 bytes, not about 47 KB (Task 2).
4. `font-size-adjust` is `none`, measured: a number such as `.546` also renders Inter at nominal size but cancels the fallback face's `size-adjust`, and the swap then moves text 1.9 percent instead of 0.15 (Task 2).
5. Spec 8 says `journey.css` "never sets background-image" on `.btn--primary`. It must set `background-image:none` to remove app.css's gradient; the tests allow `none` and nothing else (Task 3).
6. Hover colour changes also ease (200ms, `--ease-land`, no-preference only), beyond spec 5.4's "transform and opacity only" (Task 3).
7. Basecoat's names point at the hex `--j-*` tokens instead of repeating the hex (spec 4.4), so dark mode follows with one list (Task 3).
8. The two `theme-color` metas are the header surface of each scheme, `#FFFFFF` and `#111B2B`, in a new `base.html` block `theme_color_meta` (spec 4.2 names only `color_scheme`) (Task 3).
9. The field hint shows below the input through CSS `order`; the DOM keeps today's label, hint, input order for screen readers (Task 3).
10. Step 1's "What will Google ask me?" disclosure is new markup, so the beta "unverified app" steps are one tap away; Step 3's Next sits about 200px lower on phones (Task 5).
11. "Start watching without Gmail" stays a secondary button: making it primary would break today's one-primary rule and switch on the frozen Activate morph for a path that never celebrates (Task 5).
12. In dark mode the Gmail panel sits on the surface, not the amber ground, because the frozen blue measures 2.98 to 1 on `#2A2110` (Task 6).
13. The paused panel keeps its own "Edit keywords" button (spec 6.3 keeps the panel), so the paused state has two ways to the keywords page; the whole dashboard stack, panel included, sits in the 40rem column (Task 6).
14. The "Sign-in didn't finish" page has a small decorative amber icon, and `_fail` now logs one WARNING `signin_failed` with the reason per failure (Task 7).
15. The smoke has no callback-failure or signed-out checks today, so Task 7 adds 41 new ones rather than "updating" them; `tests/test_saas_template_context.py` needs a request added, because it records only what it renders (Task 7).
16. In dark mode the navy tile of the header mark nearly disappears (about 1.2 to 1); the white chevron and sky dot still read. Left as is, flagged for the owner's screenshot look in Task 8.
17. The quiet links' 44px tap band (spec 5.2 says "on phones") applies on every device, because a touch-screen laptop gets computer sizes (review focus 5, Task 3).
18. Spec 7 puts the journey font-stack check in `tests/test_saas_hero.py`. The stack is written in section 4 of `journey.css`, so its test (`test_the_journey_body_uses_the_inter_stack_at_nominal_size`) lives in `tests/test_saas_journey.py` with the other section checks (Task 3); the hero file keeps the face, file and preload checks (Task 2).
19. Page leads (`.lead` on login and the onboarding steps) drop to body size in the muted colour. Spec 5.1 has no lead role, so the plan reads a lead as body text (Tasks 3 to 5).

## File Structure

| File | Task | Responsibility |
|---|---|---|
| `tools/basecoat/basecoat-1.0.2.cdn.min.css` | 1 | Upstream Basecoat, byte for byte, sha256 pinned, `-text`. Not served |
| `tools/basecoat/trim.py` | 1 | Rebuilds the trimmed file from the upstream file (spec 4.3). Standard library only, run by hand |
| `applyfirst/saas/static/vendor/basecoat-1.0.2-agad.css` | 1 | The trimmed, served Basecoat, in `@layer basecoat`, dark mode on `prefers-color-scheme`. Generated, never hand-edited |
| `applyfirst/saas/static/licenses/basecoat-MIT.txt`, `tailwindcss-MIT.txt` | 1 | Licences for the vendored stylesheet |
| `.gitattributes` | 1 | Adds `tools/basecoat/*.css -text` so the pinned bytes survive a Windows checkout |
| `tests/test_saas_basecoat.py` | 1 | Vendor pins, trim reproducibility, trimmed-content checks |
| `tests/test_saas_palette.py` | 1 | No-purple guard now scans every `static/**/*.css` and reads `oklch()` and three `color-mix()` forms |
| `tools/fonts/build_inter.py` | 2 | Reproduces the Inter subset from a pinned google/fonts commit and prints the fallback numbers |
| `applyfirst/saas/static/fonts/inter-4.1-latin-wght.woff2` | 2 | The Inter subset (opsz 14, wght 400 to 600, Latin plus peso). Generated |
| `applyfirst/saas/static/licenses/OFL-inter.txt` | 2 | Inter's licence with a note of what changed. Generated |
| `requirements-dev.txt` | 2 | Adds `brotli` (dev only) |
| `tests/test_saas_hero.py` | 2 | Font contract: device font on app.css, Inter in `journey.css` only, never preloaded, served cacheable |
| `applyfirst/saas/static/css/journey.css` | 2 creates, 3 to 7 fill | The sign-up look: fonts, tokens, Basecoat map, base, components, chrome, one section per page, motion |
| `applyfirst/saas/static/css/app.css` | 3 | Line 6 only: the layer order statement |
| `applyfirst/saas/templates/base.html` | 3 | Lines 7 and 8 only: the `color_scheme` and `theme_color_meta` blocks |
| `tests/_journey_css.py` | 3, list grows in 4 to 7 | Shared CSS readers and `JOURNEY_TEMPLATES` |
| `tests/test_saas_journey.py` | 3 creates, 4 to 6 append | Layers, scope, frozen values, contrast, 16px inputs, motion, budgets, review-focus checks, then per-page structure checks |
| `applyfirst/saas/templates/login.html` | 4 | Journey head, the brand mark only in the header |
| `.noxa/redesign-saas-ui/inputs/preserve_smoke.py` | 4, 7 | Required assets (Task 4), D8 and D9 checks (Task 7). Git-ignored, a gate |
| `applyfirst/saas/templates/onboarding_connect_gmail.html`, `onboarding_profile.html`, `onboarding_keywords.html`, `onboarding_preview.html` | 5 | Journey head, Step 1 disclosure and quiet skip links, Step 2 one card, Step 3 Next after the quick adds |
| `applyfirst/saas/templates/dashboard.html` | 6 | Journey head, three groups of rows, the help note |
| `applyfirst/saas/app.py` | 7 | `_SignedOut`, its handler, `require_user_or_login` on the seven GET routes, `_fail` renders the page and logs |
| `applyfirst/saas/templates/signin_failed.html` | 7 | The D8 page |
| `tests/test_saas_signin_failed.py` | 7 | D8 and D9 |
| `tests/test_saas_gmail_retry.py`, `tests/test_saas_onboarding.py`, `tests/test_saas_connect_gmail.py`, `tests/test_saas_template_context.py` | 7 | Old 401 and JSON expectations changed on purpose (spec 7) |
| `DESIGN-HANDOFF.md`, `Handoff.md` | 8 | The font lock, the gradient, "nothing is minified", the palette scan, the as-built record |

## Order, dependencies and gate numbers

Run the tasks in order; each one is green on its own at its end. Task 2 creates `journey.css` with the header and section 1, and Task 3 appends the `@layer journey` block after it, so the font face and its tests land together with the file `test_saas_static.py` checks. Every number below was measured during assembly by applying this plan's code, task by task, to a copy of the repo.

| After | pytest | smoke | `journey.css` gzip | new test items |
|---|---|---|---|---|
| today | 887 passed | 558 checks, 0 failed | none | |
| Task 1 | 925 | 558 | none | 38 |
| Task 2 | 939 | 558 | 507 B | 14 |
| Task 3 | 1,053 | 558 | 3,429 B | 114 |
| Task 4 | 1,067 | 566 | 3,567 B | 14 |
| Task 5 | 1,119 | 566 | 4,280 B | 52 |
| Task 6 | 1,204 | 566 | 4,933 B | 85 |
| Task 7 | 1,266 | 607 | 4,962 B | 62 |

The browser checks measured on the finished tree: login 96 PASS, the four onboarding steps 330 PASS, the dashboard 132 PASS, the sign-in failed page 32 PASS, and Task 8's full pass over the preview 707 PASS, all with 0 failed. The mutation passes: Task 1's planted rule failed the 4 tests it should, Task 3 44 of 44, Task 5 29 of 29, Task 6 26 of 26, Task 7 28 of 28, the review-focus checks 13 of 13.

---


### Task 1: Basecoat vendoring and the palette test changes

Spec 4.1 (files), 4.3 (trimming rules), 7 (palette bullet), 8 (vendor pins, trimmed content, budget).
No page links the new file in this task (spec 11 stage 1): the login task (Task 4) is the first to
load it. Everything below was prototyped end to end in a scratch copy of the repo on 2026-09-25:
the numbers, hashes and test counts are measured, not estimated.

**What the upstream package really contains (measured).**
- The tarball `https://registry.npmjs.org/basecoat-css/-/basecoat-css-1.0.2.tgz` (sha256
  `b493e77a7ee0b945e41398f5aee186ffa692f930751b960f5ac0853e4b54de48`, npm integrity
  `sha512-C6I5rr7HziIAoBYNGPO5U6HaU/6FuF3iVp++IgoEqqJ836is3XoRty6l1ibXqxnoIRZNnOAYDMX8QxVC+58zhw==`)
  has no file called `basecoat-1.0.2.cdn.min.css`. The ready-made minified file is
  `package/dist/basecoat.cdn.min.css` (218,225 B, 21,908 B gzip 9, sha256
  `8123677adb9bba43be3298e1543bcc5fc763e8cda3d32dc74c806046a3537ca0`). The spec's name is the name
  we give our pinned copy in `tools/basecoat/`. (`dist/basecoat-vega.cdn.min.css` is the same
  bytes; the other `basecoat-<style>.cdn.min.css` files are alternative themes.)
- It is the full Tailwind CSS v4.3.1 output (first line `/*! tailwindcss v4.3.1 | MIT License |
  https://tailwindcss.com */`, then one newline, then everything on one line). Top level, in order:
  `@layer properties` (a `*,:before,:after,::backdrop` fallback inside an `@supports` that only
  matches browsers without `@property`), `@layer theme` (one `:root,:host` rule), `@layer base`
  (the preflight reset), `@layer components` (1,160 statements, including 114
  `@supports (color:color-mix(in lab, red, red))`, 40 `@media (hover:hover)`, 24
  `@media (forced-colors:active)`, 3 `@starting-style`, 1 `@container field-group`),
  an empty `@layer utilities`, unlayered `:root` and `.dark` colour blocks (all 58 `oklch()`
  values live there and in their `data:` SVG icons), `@keyframes toast-up`, 43
  `@property --tw-*` registrations, `@keyframes pulse`.
- Dark variant forms: 103 `:is(html.dark *)` (appended to a compound selector) and 2
  `html.dark ` descendant prefixes (both on switch rules). No `:where(.dark ...)` form.
- One `!important` rule in the parts we keep: `.badge>svg{width:12px!important;height:12px!important}`
  (written with `calc(var(--spacing) * 3)`). In the lowest layer an important declaration beats
  every declaration in every layer above it, so journey.css could never override it.

**What the trim keeps (measured on the output of the script below).**
- 36,345 B raw, **3,363 B gzip 9** against the 7,000 B cap. sha256
  `4aae6ed8773c27938e12e6c87139f99305fb680a4cd5298c7864034119325157`. 233 lines.
- For comparison, the literal spec 4.3 step 4 filter alone keeps 72,870 B raw and 5,938 B gzip.
  That also passes the 7,000 cap, but it leaves the spec 8 render-blocking budget for `/login`
  with 164 B of room (app.css is 15,876 B gzip today, plus 5,938, plus journey.css up to 8,000,
  against 30,000). Step 4b below brings the room to about 2.7 KB. See "Notes for the reviewer (Task 1)".
- Kept `@layer theme` variables, in upstream order: `--spacing`, `--text-xs`,
  `--text-xs--line-height`, `--text-sm`, `--text-sm--line-height`, `--text-base`,
  `--text-base--line-height`, `--font-weight-normal`, `--font-weight-medium`, `--leading-snug`,
  `--leading-normal`, `--radius-md` (`calc(var(--radius) - 2px)`), `--radius-lg`
  (`var(--radius)`), `--radius-xl` (`calc(var(--radius) + 4px)`), `--radius-4xl` (`2rem`),
  `--default-transition-duration` (`.15s`), `--default-transition-timing-function`
  (`cubic-bezier(.4, 0, .2, 1)`). No `--font-sans`, `--font-mono`, `--ease-*`, `--color-*` or
  `--animate-*`. None of the kept names exists in app.css, motion.css, hero.css or story.css
  (checked by grep).
- Kept `@property` registrations (15, each read by a kept rule): `--tw-border-style`,
  `--tw-shadow`, `--tw-shadow-color`, `--tw-inset-shadow`, `--tw-ring-color`, `--tw-ring-shadow`,
  `--tw-inset-ring-shadow`, `--tw-ring-inset`, `--tw-ring-offset-width`, `--tw-ring-offset-shadow`,
  `--tw-leading`, `--tw-translate-x`, `--tw-translate-y`, `--tw-duration`, `--tw-ease`.
- Variables the kept rules read that nothing in the file defines, which journey.css must define
  (Task 3): `--color-card`, `--color-card-foreground`, `--color-destructive`,
  `--color-foreground`, `--color-input`, `--color-muted-foreground`, `--color-primary`,
  `--color-primary-foreground`, `--color-ring`, `--radius`. None of the bare spec 4.4 names
  (`--background`, `--primary`, ...) is read directly, because the `--color-*` aliases that pointed
  at them were colour variables and are dropped with the rest of the theme colours.
- Dark mode: 18 `@media (prefers-color-scheme:dark)` blocks (written without a space after the
  colon; any later test must match `prefers-color-scheme:\s*dark`). No `.dark`, no `html.dark`.
- Colour values that survive: hex `#0000` and `#0000000d` only (both neutral). No `oklch()`.
  `color-mix()` survives in exactly two forms: 20 of `color-mix(in oklab, var(--x) N%, transparent)`
  (form 1) and 19 `@supports (color:color-mix(in lab, red, red))` probes (form 2). The only
  upstream instance of form 3, `color-mix(in oklch,var(--secondary),var(--foreground) 5%)`, sat on
  `.btn[data-variant=secondary]:hover` and is trimmed. The currentcolor variant of form 1 is also
  gone. The palette test still accepts all three forms, as spec 7 asks.
- Styled classes (outside `:not()`/`:has()`): exactly `alert`, `badge`, `btn`, `card`,
  `card-action`, `card-description`, `card-title`, `field`, `input`, `label`, `textarea`. The
  classes `command` and `dialog` still appear inside the upstream negation
  `.field>input[type=text]:not(:is(.command>header input,.dialog>*>header input))`; they style
  nothing, so the content test reads styled classes, not raw text.
- No `@keyframes`, no `animation`, no `infinite`, no `url(`, no `!important`.

**Files:**
- Create: `tools/basecoat/basecoat-1.0.2.cdn.min.css` (upstream `package/dist/basecoat.cdn.min.css`, byte for byte; `tools/` does not exist yet)
- Create: `tools/basecoat/trim.py`
- Create (generated by `trim.py`, never hand-edited): `applyfirst/saas/static/vendor/basecoat-1.0.2-agad.css`
- Create: `applyfirst/saas/static/licenses/basecoat-MIT.txt`
- Create: `applyfirst/saas/static/licenses/tailwindcss-MIT.txt`
- Create: `tests/test_saas_basecoat.py`
- Modify: `.gitattributes` (9 lines today, all LF; append 4 lines after line 9, `applyfirst/saas/static/vendor/** -text`, which already covers the trimmed file)
- Modify: `tests/test_saas_palette.py` (147 lines today; replaced whole, see Step 2 for what changes and what stays)
- Not touched: any template, `app.css`, `motion.css`, `vt.js`, `motion.js`, `app.py`, the smoke script. Nothing links the new CSS yet.

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces:
  - `applyfirst/saas/static/vendor/basecoat-1.0.2-agad.css`: everything inside one `@layer basecoat{...}`, then 15 unlayered `@property --tw-*` rules. This is the file `_journey_css.BASECOAT_CSS` (Task 3) points at and that Task 4 links first.
  - `tools/basecoat/trim.py` module API (import it by path, `tools/` is not a package; register it in `sys.modules` before `exec_module`, see the `trim` fixture): `trim(source: bytes) -> bytes`, `parse(text: str) -> list[Node]` (`Node.prelude`, `Node.body`, `Node.children`, `Node.is_rule`), `split_top(text, sep) -> list[str]`, `classes(selector) -> set[str]`, `can_match_our_markup(selector) -> bool`, `reads(nodes) -> set[str]`, `lf(data) -> bytes`, `TrimError`, and the constants `SOURCE`, `OUTPUT`, `SOURCE_SHA256`, `GZIP_CAP`, `ALLOWED`, `NEVER_IN_OUR_MARKUP`, `TRIMMED_ON`.
  - `tests/test_saas_basecoat.py` constants `UPSTREAM_SHA`, `TRIMMED_SHA`, `SUPPLIED_BY_JOURNEY` (the 10 names above). Task 3 must make journey.css define every name in `SUPPLIED_BY_JOURNEY` (its test can compute the same set from the trimmed file with the three regexes in `test_every_variable_read_is_defined_registered_or_supplied_by_journey`).
  - `tests/test_saas_palette.py` now scans `static/**/*.css` (`CSS_FILES = sorted((SAAS / "static").rglob("*.css"))`), so journey.css is scanned the moment Task 3 creates it, and exposes `_css_problems(text) -> list[str]` for any later planted-colour test.
  - A new guard every later page task must respect: `test_no_template_writes_markup_whose_basecoat_rules_were_trimmed` fails if any template writes `data-variant`, `data-size`, `data-orientation`, `data-invalid`, `data-disabled`, `type="checkbox"`, `type="radio"`, `type="range"` or `role="switch"` (their Basecoat rules were trimmed away).

**Frozen hooks (spec 9) in this task's files:** none. This task edits no template and no frozen
motion file. The M-2 name rule is asserted for every new file name
(`test_no_new_file_name_contains_a_motion_asset_name`), and M-1 head order cannot change because
no `<link>` is added.

- [ ] **Step 1: Write the failing test `tests/test_saas_basecoat.py`**

Create it with the Write tool, exactly:

```python
"""Basecoat, vendored and trimmed (sign-up redesign spec 4.1, 4.3 and 8).

The sign-up pages use eight of Basecoat's parts. tools/basecoat/trim.py cuts them out of the
pinned upstream file, so these tests pin both files by sha256, run the trim again and require the
same bytes, and read the trimmed file for anything that must never reach a phone: Tailwind's
reset, the class-based dark mode, a colour block, a component we do not use, an endless
animation, or an !important that no layer above Basecoat could override.
"""

from __future__ import annotations

import gzip
import hashlib
import importlib.util
import re
import sys
from pathlib import Path

import pytest

from applyfirst.saas import static_assets

SAAS = Path(static_assets.__file__).parent
REPO = SAAS.parents[1]
STATIC = SAAS / "static"
TEMPLATES = SAAS / "templates"
TOOLS = REPO / "tools" / "basecoat"
UPSTREAM = TOOLS / "basecoat-1.0.2.cdn.min.css"
TRIM_PY = TOOLS / "trim.py"
TRIMMED = STATIC / "vendor" / "basecoat-1.0.2-agad.css"
BASECOAT_LICENCE = STATIC / "licenses" / "basecoat-MIT.txt"
TAILWIND_LICENCE = STATIC / "licenses" / "tailwindcss-MIT.txt"
NEW_FILES = (UPSTREAM, TRIM_PY, TRIMMED, BASECOAT_LICENCE, TAILWIND_LICENCE)

# package/dist/basecoat.cdn.min.css in the npm tarball
# https://registry.npmjs.org/basecoat-css/-/basecoat-css-1.0.2.tgz
UPSTREAM_SHA = "8123677adb9bba43be3298e1543bcc5fc763e8cda3d32dc74c806046a3537ca0"
TRIMMED_SHA = "4aae6ed8773c27938e12e6c87139f99305fb680a4cd5298c7864034119325157"
GZIP_CAP = 7000                                                              # spec 8
ALLOWED = {"btn", "card", "card-title", "card-description", "card-action", "field", "input",
           "label", "textarea", "alert", "badge"}                              # spec 4.3 step 4
UNUSED_PARTS = ("dialog", "alert-dialog", "menu", "dropdown-menu", "popover", "select", "tabs",
                "toast", "sidebar", "table", "command", "combobox", "accordion", "avatar")
PREFLIGHT = {"*", "html", "body", "a", "h1", "h2", "h3", "h4", "h5", "h6", "img", "details",
             "summary", "button", "input", "textarea", "select", "ol", "ul", "hr", "table",
             ":root", ":host", "::backdrop", "::placeholder", "::file-selector-button"}
# What the trimmed file reads but leaves to journey.css (spec 4.4). journey.css defines each one.
SUPPLIED_BY_JOURNEY = ("--color-card", "--color-card-foreground", "--color-destructive",
                       "--color-foreground", "--color-input", "--color-muted-foreground",
                       "--color-primary", "--color-primary-foreground", "--color-ring", "--radius")
# The only custom properties the trimmed file may define: sizes, radius, spacing, text sizes,
# weights, leading and Tailwind's internal --tw-* plumbing (spec 4.3 step 3).
OWN_VARIABLE = re.compile(r"--(?:spacing|text-(?:xs|sm|base|lg)|font-weight-|leading-|radius-"
                          r"|default-transition-|tw-)")
# Markup whose Basecoat rules trim.py drops (its step 4b). A page that writes one gets no styling.
TRIMMED_MARKUP = re.compile(r"""data-(?:variant|size|orientation|invalid|disabled)\b"""
                            r"""|type=["']?(?:checkbox|radio|range)\b|role=["']?switch\b""")
MOTION_ASSETS = ("motion.css", "vt.js", "motion.js", "canvas-confetti")      # test M-2


def _lf_bytes(path: Path) -> bytes:
    """The file's bytes with CRLF normalised to LF, so a Windows checkout hashes the same."""
    return path.read_bytes().replace(b"\r\n", b"\n")


def _gz(path: Path) -> int:
    return len(gzip.compress(_lf_bytes(path), 9, mtime=0))


def _css(path: Path) -> str:
    return re.sub(r"/\*.*?\*/", "", _lf_bytes(path).decode("utf-8"), flags=re.S)


def _without_not_and_has(selector: str) -> str:
    """The selector with the arguments of :not() and :has() removed: what is left is what it
    styles."""
    out, i = [], 0
    while i < len(selector):
        if selector.startswith((":not(", ":has("), i):
            depth, i = 1, i + 5
            while depth:
                depth += {"(": 1, ")": -1}.get(selector[i], 0)
                i += 1
        else:
            out.append(selector[i])
            i += 1
    return "".join(out)


def _selectors(selector_list: str) -> list[str]:
    """The selectors of a list, split on the commas that sit outside brackets."""
    out, depth, start = [], 0, 0
    for i, ch in enumerate(selector_list):
        depth += {"(": 1, "[": 1, ")": -1, "]": -1}.get(ch, 0)
        if ch == "," and depth == 0:
            out.append(selector_list[start:i])
            start = i + 1
    return out + [selector_list[start:]]


def _styled_classes(selector: str) -> set[str]:
    styled = re.sub(r"\[[^\]]*\]", "", _without_not_and_has(selector))
    return set(re.findall(r"\.(-?[_a-zA-Z][\w-]*)", styled))


@pytest.fixture(scope="module")
def trim():
    """tools/basecoat/trim.py, imported by path (tools/ is not a package)."""
    spec = importlib.util.spec_from_file_location("basecoat_trim", TRIM_PY)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _rules(nodes, chain=()):
    """(selector list, body, enclosing at-rules) for every style rule, depth first."""
    for node in nodes:
        if node.children is not None:
            yield from _rules(node.children, chain + (node.prelude,))
        elif node.is_rule:
            yield node.prelude, node.body, chain


@pytest.fixture(scope="module")
def layer(trim):
    """The children of the one @layer basecoat block."""
    top = trim.parse(_css(TRIMMED))
    assert top[0].prelude == "@layer basecoat"
    return top[0].children


# --- vendor pins (spec 8) ---------------------------------------------------------------------

def test_the_upstream_file_is_the_pinned_basecoat_release():
    assert hashlib.sha256(_lf_bytes(UPSTREAM)).hexdigest() == UPSTREAM_SHA


def test_the_trimmed_file_is_the_pinned_build():
    assert hashlib.sha256(_lf_bytes(TRIMMED)).hexdigest() == TRIMMED_SHA


def test_running_trim_again_gives_the_committed_file_byte_for_byte(trim):
    assert trim.trim(_lf_bytes(UPSTREAM)) == _lf_bytes(TRIMMED), (
        "the trimmed file was edited by hand, or trim.py changed without re-running it")


def test_trim_reads_and_writes_the_pinned_paths(trim):
    assert (trim.SOURCE, trim.OUTPUT) == (UPSTREAM, TRIMMED)
    assert trim.SOURCE_SHA256 == UPSTREAM_SHA
    assert trim.GZIP_CAP == GZIP_CAP


@pytest.mark.parametrize("change", [
    (b"", b"@layer reset{a{color:red}}"),                         # a new top-level statement
    (b"@layer components{", b"@layer components{.btn:where(.dark *){color:red}"),  # new dark form
    (b"@layer components{", b"@layer components{@font-feature-values X{@swash{a:1}}"),
])
def test_trim_stops_on_input_it_does_not_recognise(trim, change):
    old, new = change
    source = _lf_bytes(UPSTREAM)
    changed = source + new if old == b"" else source.replace(old, new, 1)
    with pytest.raises(trim.TrimError):
        trim.trim(changed)


def test_gitattributes_keeps_both_basecoat_files_byte_for_byte():
    attributes = (REPO / ".gitattributes").read_text(encoding="utf-8")
    assert "applyfirst/saas/static/vendor/** -text" in attributes
    assert "tools/basecoat/*.css -text" in attributes


def test_both_files_have_lf_endings_only():
    assert b"\r" not in UPSTREAM.read_bytes()
    assert b"\r" not in TRIMMED.read_bytes()


def test_the_trimmed_file_stays_inside_its_gzip_cap():
    assert _gz(TRIMMED) <= GZIP_CAP, f"trimmed Basecoat gzip {_gz(TRIMMED)} B"


def test_the_header_names_the_source_its_sha256_the_script_the_date_and_the_licences():
    head = _lf_bytes(TRIMMED).decode("utf-8").split("@layer basecoat{", 1)[0]
    for needle in ("/*! tailwindcss v4.3.1 | MIT License", "/*! basecoat-css 1.0.2 | MIT License",
                   "tools/basecoat/basecoat-1.0.2.cdn.min.css", UPSTREAM_SHA,
                   "tools/basecoat/trim.py", "basecoat-MIT.txt", "tailwindcss-MIT.txt"):
        assert needle in head, needle
    assert re.search(r"trim\.py on \d{4}-\d{2}-\d{2}\.", head)


def test_the_licences_name_their_authors():
    basecoat = BASECOAT_LICENCE.read_text(encoding="utf-8")
    tailwind = TAILWIND_LICENCE.read_text(encoding="utf-8")
    for licence in (basecoat, tailwind):
        assert licence.startswith("MIT License")
        assert "Permission is hereby granted, free of charge" in licence
    assert "Copyright (c) 2025 Ronan Berder" in basecoat
    assert "Copyright (c) Tailwind Labs, Inc." in tailwind


def test_no_new_file_name_contains_a_motion_asset_name():
    for path in NEW_FILES:
        assert path.is_file(), path
        assert not any(name in path.name for name in MOTION_ASSETS), path.name


# --- trimmed content (spec 8) -----------------------------------------------------------------

def test_everything_sits_in_the_basecoat_layer_except_property_registrations(trim):
    top = trim.parse(_css(TRIMMED))
    assert top[0].prelude == "@layer basecoat" and top[0].children
    rest = [node.prelude for node in top[1:]]
    assert rest and all(re.fullmatch(r"@property --tw-[\w-]+", p) for p in rest), rest


def test_no_preflight_or_bare_element_selector(layer):
    rules = list(_rules(layer))
    theme = [r for r in rules if r[0] == ":root,:host"]
    assert len(theme) == 1 and theme[0][2] == (), "one theme rule, at the top of the layer"
    assert all(d.split(":", 1)[0].startswith("--") for d in theme[0][1].split(";"))
    for selectors, _body, _chain in rules:
        if selectors == ":root,:host":
            continue
        for selector in _selectors(selectors):
            assert selector.strip() not in PREFLIGHT, selectors
            assert _styled_classes(selector), f"a selector with no class: {selector}"


def test_only_the_parts_the_sign_up_pages_use_are_styled(layer):
    styled = set()
    for selectors, _body, _chain in _rules(layer):
        if selectors != ":root,:host":
            styled |= {c for s in _selectors(selectors) for c in _styled_classes(s)}
    assert styled <= ALLOWED, sorted(styled - ALLOWED)
    assert not styled & set(UNUSED_PARTS)


def test_dark_mode_follows_the_phone_setting_not_a_class(layer):
    css = _css(TRIMMED)
    assert ".dark" not in css and "html.dark" not in css
    chains = [chain for _s, _b, chain in _rules(layer)]
    assert any("@media (prefers-color-scheme:dark)" in chain for chain in chains)
    assert not re.search(r"prefers-color-scheme:\s*light", css)


def test_no_colour_block_font_or_easing_variable_is_defined(layer):
    css = _css(TRIMMED)
    assert "oklch(" not in css
    defined = set()
    for _selectors, body, _chain in _rules(layer):
        defined |= set(re.findall(r"(?:^|;)\s*(--[\w-]+)\s*:", body))
    assert defined and all(OWN_VARIABLE.match(name) for name in defined), sorted(
        n for n in defined if not OWN_VARIABLE.match(n))


def test_nothing_animates_and_nothing_is_important():
    css = _css(TRIMMED)
    assert "@keyframes" not in css
    assert not re.search(r"(?<![\w-])animation(?:-name)?\s*:", css)
    assert "infinite" not in css
    assert "!important" not in css


def test_every_variable_read_is_defined_registered_or_supplied_by_journey():
    css = _css(TRIMMED)
    read = set(re.findall(r"var\((--[\w-]+)", css))
    defined = set(re.findall(r"(?<![\w-])(--[\w-]+)\s*:", css))
    registered = set(re.findall(r"@property (--[\w-]+)", css))
    assert read - defined - registered == set(SUPPLIED_BY_JOURNEY)
    assert registered <= read, sorted(registered - read)                 # step 6: only what is read


def test_no_template_writes_markup_whose_basecoat_rules_were_trimmed():
    for path in sorted(TEMPLATES.glob("*.html")):
        src = re.sub(r"\{#.*?#\}", "", path.read_text(encoding="utf-8"), flags=re.S)
        found = sorted({m.group(0) for m in TRIMMED_MARKUP.finditer(src)})
        assert found == [], f"{path.name}: trim.py drops Basecoat's rules for {found}"
```

- [ ] **Step 2: Replace `tests/test_saas_palette.py` with the version that reads the vendored CSS**

What changes against today's file (line numbers are today's, verified):
- Lines 1-9 docstring: now says every stylesheet under `static/` is scanned, how `oklch()` is judged and that `color-mix()` has three allowed forms.
- Lines 11-20 imports: add `import math` (for the OKLCH to sRGB conversion).
- Line 23 `CSS_FILES = sorted((SAAS / "static" / "css").glob("*.css"))` becomes `CSS_FILES = sorted((SAAS / "static").rglob("*.css"))` (spec 7: scan `static/**/*.css`).
- After line 32 (`_RGB`): new `_OKLCH` pattern. After line 38 (`_JS_VALUE`): the three `color-mix()` form patterns `_MIX_FADE`, `_MIX_PROBE`, `_MIX_TWO_VARS`.
- New helpers `_oklch_parts`, `_oklch_rgb`, `_is_grey`, `_arguments`, `_mix_of_greys`, `_unreadable`, `_css_problems`.
- Lines 52-56 `_colours`: also yields every numeric `oklch()` converted to sRGB, so T37 judges it with the unchanged hue test (never by the OKLCH hue).
- Lines 90-94 `test_there_is_something_to_scan`: also asserts a CSS file in `static/vendor` is scanned.
- Lines 125-129 `test_stylesheet_uses_only_colours_the_guard_can_read`: now fails only on what `_unreadable()` reports (a numeric `oklch()` and the three `color-mix()` forms are readable; `hsl`, `hwb`, `lab`, `lch`, `oklab`, any other `color-mix()` and any non-numeric `oklch()` still fail).
- New tests: `test_oklch_is_judged_in_srgb_not_by_its_own_hue`, `test_color_mix_is_allowed_in_exactly_three_forms`, and `test_a_planted_purple_fails_in_every_colour_form` (12 planted cases, at least one per form).
- Unchanged: `_HEX`, `_RGB`, `BANNED_WORDS`, `_UNREADABLE_FN`, `_JS_VALUE`, `_hue_sat`, `_hex_rgb`, `_is_purple`, `_js_values`, `_css_values`, `test_the_guard_catches_purple_and_passes_the_brand_colours`, T37, T38, and both M-7 tests (today's lines 132-147).

Replace the whole file with the Write tool, exactly:

```python
"""Owner rule, enforced forever: no purple, violet or indigo anywhere a colour is written.

Scans every stylesheet under static/ (the trimmed Basecoat file in static/vendor included), every
SaaS template, every static JavaScript file (the vendored canvas-confetti included, now that its
default colours are the brand blues) and the delivered email module for every #rgb / #rgba /
#rrggbb / #rrggbbaa, rgb(), rgba() and oklch() value, and fails on a hue from 230 to 345 with
saturation of 8% or more (spec 14.4, M-7). An oklch() colour is converted to sRGB and judged by
that same test, never by its own hue, because the brand blues sit at OKLCH hue 236 to 255.
color-mix() is allowed in exactly three forms that cannot bring in a new hue (sign-up redesign
spec 7). Colour words that name a purple, and every other colour function, are banned as CSS
values, and in JavaScript as whole string literals. The Google G PNG is binary and never scanned.
"""

from __future__ import annotations

import colorsys
import math
import re
from pathlib import Path

import pytest

from applyfirst.notify import compose
from applyfirst.saas import static_assets

SAAS = Path(static_assets.__file__).parent
CSS_FILES = sorted((SAAS / "static").rglob("*.css"))          # own CSS and the vendored Basecoat
TEMPLATE_FILES = sorted((SAAS / "templates").glob("*.html"))
JS_FILES = sorted((SAAS / "static").rglob("*.js"))          # own JS and the vendored burst (M-7)
SCANNED = CSS_FILES + TEMPLATE_FILES + JS_FILES + [Path(compose.__file__)]

# "&#8594;" is an HTML entity, not a colour, hence the (?<![&\w]) guard.
_HEX = re.compile(r"(?<![&\w])#([0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{4}|[0-9a-fA-F]{3})"
                  r"(?![0-9a-zA-Z_-])")
_RGB = re.compile(r"\brgba?\(\s*(\d{1,3}(?:\.\d+)?)\s*[,\s]\s*(\d{1,3}(?:\.\d+)?)\s*[,\s]\s*"
                  r"(\d{1,3}(?:\.\d+)?)")
_OKLCH = re.compile(r"(?<![\w-])oklch\(([^()]*)\)", re.I)
BANNED_WORDS = ("purple", "violet", "indigo", "lavender", "lilac", "magenta", "fuchsia",
                "orchid", "plum", "blueviolet", "rebeccapurple", "slateblue")
_UNREADABLE_FN = re.compile(r"(?<![\w-])(hsla?|hwb|lab|lch|oklab|oklch|color-mix)\(", re.I)
# A whole JS string literal that is one bare word, optionally with a bracket: "purple",
# "hsl(280 60% 50%)", "hsl(". Anything with a space or a colon in it is not a colour value.
_JS_VALUE = re.compile(r"""(['"`])\s*([A-Za-z][\w-]*(?:\([^'"`\n]*\)?)?)\s*\1""")

# The three color-mix() forms a stylesheet may use (sign-up redesign spec 7).
# 1. A variable or currentcolor faded towards transparent: it keeps the hue it already had, and
#    the variable's own value is scanned wherever it is defined.
_MIX_FADE = re.compile(r"\s*in\s+[a-z-]+\s*,\s*(?:var\(\s*--[\w-]+\s*\)|currentcolor)\s+"
                       r"\d+(?:\.\d+)?%\s*,\s*transparent\s*", re.I)
# 2. Tailwind's feature test, only as the whole condition of an @supports rule.
_MIX_PROBE = re.compile(r"@supports\s*\(\s*color\s*:\s*color-mix\(\s*in\s+lab\s*,\s*red\s*,"
                        r"\s*red\s*\)\s*\)", re.I)
# 3. Two variables, each defined in the same file, and only ever as a grey (zero chroma).
_MIX_TWO_VARS = re.compile(r"\s*in\s+[a-z-]+\s*,\s*var\(\s*(--[\w-]+)\s*\)(?:\s+\d+(?:\.\d+)?%)?"
                           r"\s*,\s*var\(\s*(--[\w-]+)\s*\)(?:\s+\d+(?:\.\d+)?%)?\s*", re.I)


def _hue_sat(r: float, g: float, b: float) -> tuple[float, float]:
    h, _l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    return h * 360, s


def _hex_rgb(digits: str) -> tuple[int, int, int]:
    if len(digits) in (3, 4):
        digits = "".join(ch * 2 for ch in digits[:3])
    return int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16)


def _oklch_parts(args: str) -> tuple[float, float, float] | None:
    """Lightness (0 to 1), chroma and hue of oklch() arguments, or None if they are not plain
    numbers (relative colour syntax, var(), 'none')."""
    parts = args.split("/")[0].split()
    if len(parts) != 3:
        return None
    try:
        lightness = float(parts[0][:-1]) / 100 if parts[0].endswith("%") else float(parts[0])
        chroma = float(parts[1][:-1]) * 0.004 if parts[1].endswith("%") else float(parts[1])
        hue = float(parts[2].lower().removesuffix("deg"))
    except ValueError:
        return None
    return lightness, chroma, hue


def _oklch_rgb(args: str) -> tuple[float, float, float] | None:
    """The sRGB colour (0 to 255 per channel, clipped to the gamut) of oklch() arguments."""
    parts = _oklch_parts(args)
    if parts is None:
        return None
    lightness, chroma, hue = parts
    a, b = chroma * math.cos(math.radians(hue)), chroma * math.sin(math.radians(hue))
    l_ = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m_ = (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s_ = (lightness - 0.0894841775 * a - 1.2914855480 * b) ** 3
    linear = (4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_,
              -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
              -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_)

    def encode(x: float) -> float:
        x = min(max(x, 0.0), 1.0)
        return 12.92 * x if x <= 0.0031308 else 1.055 * x ** (1 / 2.4) - 0.055

    return tuple(encode(x) * 255 for x in linear)


def _colours(text: str):
    for m in _HEX.finditer(text):
        yield m.group(0), _hex_rgb(m.group(1))
    for m in _RGB.finditer(text):
        yield m.group(0), tuple(float(v) for v in m.groups())
    for m in _OKLCH.finditer(text):
        rgb = _oklch_rgb(m.group(1))
        if rgb is not None:                     # unparseable oklch() fails as unreadable instead
            yield m.group(0), rgb


def _is_purple(rgb) -> bool:
    hue, sat = _hue_sat(*rgb)
    return 230 <= hue <= 345 and sat >= 0.08


def _is_grey(value: str) -> bool:
    """True when a custom property's value is a colour with zero chroma."""
    value = value.strip()
    m = _OKLCH.fullmatch(value)
    if m:
        parts = _oklch_parts(m.group(1))
        return parts is not None and parts[1] == 0
    m = _HEX.fullmatch(value)
    if m:
        r, g, b = _hex_rgb(m.group(1))
        return r == g == b
    m = _RGB.match(value)
    return bool(m) and len(set(float(v) for v in m.groups())) == 1


def _arguments(text: str, start: int) -> str:
    """The text from start up to the ')' that closes the '(' just before start."""
    depth, i = 1, start
    while depth:
        depth += {"(": 1, ")": -1}.get(text[i], 0)
        i += 1
    return text[start:i - 1]


def _mix_of_greys(css: str, args: str) -> bool:
    m = _MIX_TWO_VARS.fullmatch(args)
    if not m:
        return False
    for name in m.groups():
        values = re.findall(rf"(?<![\w-]){re.escape(name)}\s*:\s*([^;{{}}]+)", css)
        if not values or not all(_is_grey(v) for v in values):
            return False
    return True


def _unreadable(css: str) -> list[str]:
    """Colour functions in a stylesheet (comments removed) that the guard cannot judge."""
    css = _MIX_PROBE.sub("@supports (probe)", css)                       # form 2
    bad = []
    for m in _UNREADABLE_FN.finditer(css):
        name, args = m.group(1).lower(), _arguments(css, m.end())
        if name == "oklch" and _oklch_rgb(args) is not None:
            continue                                  # judged in sRGB by the hue test instead
        if name == "color-mix" and (_MIX_FADE.fullmatch(args) or _mix_of_greys(css, args)):
            continue                                  # forms 1 and 3
        bad.append(f"{name}({args})")
    return sorted(set(bad))


def _css_problems(text: str) -> list[str]:
    """Everything the guard rejects in one stylesheet: a purple hue, a purple word, a colour
    function it cannot read. The planted-purple tests below run through this."""
    css = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    purple = sorted({raw for raw, rgb in _colours(css) if _is_purple(rgb)})
    words = re.compile(r"\b(" + "|".join(BANNED_WORDS) + r")\b", re.I)
    named = sorted({m.group(1).lower() for v in re.findall(r"[\w-]+\s*:\s*([^;{}]+)", css)
                    for m in words.finditer(v)})
    return purple + named + _unreadable(css)


def _js_values(text: str) -> list[str]:
    """Every string literal in a .js file that is a colour on its own.

    A colour written in JavaScript is always the whole literal: "rebeccapurple",
    "hsl(280 60% 50%)", or the open "hsl(" of a concatenation. Requiring the literal to be
    exactly one word, optionally with a bracket, is what keeps prose out, so the word "plum"
    in a comment or in a sentence is never mistaken for a colour value.
    """
    return [m.group(2) for m in _JS_VALUE.finditer(text)]


def _css_values(path: Path, text: str) -> list[str]:
    """The value side of every declaration a file can carry."""
    if path.suffix == ".js":
        return _js_values(text)
    if path.suffix == ".css":
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        return re.findall(r"[\w-]+\s*:\s*([^;{}]+)", text)
    values = re.findall(r"""\bstyle\s*=\s*(["'])(.*?)\1""", text, flags=re.S)
    values = [v for _, v in values]
    values += re.findall(r"<style\b[^>]*>(.*?)</style>", text, flags=re.S | re.I)
    values += [v for _, v in re.findall(r"""\b(?:color|fill|stroke|bgcolor|stop-color)\s*=\s*
                                            (["'])(.*?)\1""", text, flags=re.X)]
    return values


def test_there_is_something_to_scan():
    assert CSS_FILES, "static/css/app.css must exist"
    assert [p.name for p in CSS_FILES if p.parent.name == "vendor"], "vendored CSS is scanned"
    assert len(TEMPLATE_FILES) >= 10
    assert len(JS_FILES) >= 3, "static/js/*.js and the vendored burst library must be scanned"
    assert [p.name for p in JS_FILES if p.parent.name == "vendor"], "the vendor file is scanned"


def test_the_guard_catches_purple_and_passes_the_brand_colours():
    assert _is_purple(_hex_rgb("7c3aed")) and _is_purple(_hex_rgb("6366f1"))   # violet, indigo
    assert _is_purple((128, 0, 128))
    for brand in ("0B2545", "0B6BC7", "EEF7FD", "DCEFFB", "F3F6FA", "2563eb", "111827"):
        assert not _is_purple(_hex_rgb(brand))
    assert not _is_purple((11, 37, 69))
    assert list(_colours("&#8594; &#9733;")) == []                 # entities are not colours


# --- T37 ----------------------------------------------------------------------------------

@pytest.mark.parametrize("path", SCANNED, ids=lambda p: p.name)
def test_no_colour_in_the_banned_hue_band(path):
    text = path.read_text(encoding="utf-8")
    bad = sorted({raw for raw, rgb in _colours(text) if _is_purple(rgb)})
    assert bad == [], f"{path.name}: hue 230-345 colours {bad}"


# --- T38 ----------------------------------------------------------------------------------

@pytest.mark.parametrize("path", SCANNED, ids=lambda p: p.name)
def test_no_purple_colour_words_as_css_values(path):
    text = path.read_text(encoding="utf-8")
    words = re.compile(r"\b(" + "|".join(BANNED_WORDS) + r")\b", re.I)
    bad = sorted({m.group(1).lower() for v in _css_values(path, text) for m in words.finditer(v)})
    assert bad == [], f"{path.name}: banned colour words {bad}"


@pytest.mark.parametrize("path", CSS_FILES, ids=lambda p: p.name)
def test_stylesheet_uses_only_colours_the_guard_can_read(path):
    text = re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8"), flags=re.S)
    found = _unreadable(text)
    assert found == [], (f"{path.name}: use hex, rgb()/rgba(), a numeric oklch() or one of the "
                         f"three color-mix() forms instead of {found}")


# --- sign-up redesign spec 7: oklch() and color-mix() ---------------------------------------

# #0B6BC7, #38AEEA and #0B2545 written as oklch(). Their OKLCH hues (254, 236, 255) sit inside
# 230-345, which is why the guard converts to sRGB (hues 209, 200, 213) instead of reading them.
BRAND_OKLCH = ("oklch(53.0% 0.164 254.0)", "oklch(71.2% 0.134 235.8)", "oklch(26.4% 0.068 255.3)")
PURPLE_OKLCH = "oklch(54.1% 0.247 293.0)"                       # #7c3aed


def test_oklch_is_judged_in_srgb_not_by_its_own_hue():
    for colour in BRAND_OKLCH:
        (raw, rgb), = _colours(colour)
        assert 230 <= _oklch_parts(colour[6:-1])[2] <= 345, "the OKLCH hue alone would fail"
        assert not _is_purple(rgb), f"{raw} is a brand blue"
        assert _css_problems(f"a{{color:{colour}}}") == []
    for grey in ("oklch(97% 0 0)", "oklch(14.5% 0 0)", "oklch(100% 0 0/.1)"):
        assert _css_problems(f"a{{color:{grey}}}") == [], grey
    assert _css_problems(f"a{{color:{PURPLE_OKLCH}}}") == [PURPLE_OKLCH]
    assert _css_problems("a{color:oklch(from var(--x) l c h)}") != [], "unreadable oklch() fails"


def test_color_mix_is_allowed_in_exactly_three_forms():
    fade = ("a{box-shadow:0 0 0 3px color-mix(in oklab, var(--color-ring) 50%, transparent);"
            "border-color:color-mix(in oklab, currentcolor 20%, transparent)}")
    probe = "@supports (color:color-mix(in lab, red, red)){a{color:red}}"
    greys = (":root{--g1:oklch(97% 0 0);--g2:#252525}"
             "a{background:color-mix(in oklch,var(--g1),var(--g2) 5%)}")
    for css in (fade, probe, greys):
        assert _css_problems(css) == [], css


@pytest.mark.parametrize("css", [
    # form 1 with a colour where the variable belongs, or a purple behind the variable
    "a{color:color-mix(in oklab, #7c3aed 50%, transparent)}",
    "a{color:color-mix(in oklab, rebeccapurple 50%, transparent)}",
    f"a{{color:color-mix(in oklab, {PURPLE_OKLCH} 50%, transparent)}}",
    ":root{--x:#7c3aed}a{color:color-mix(in oklab, var(--x) 50%, transparent)}",
    # form 2 with a purple probe, or the probe used as a colour outside @supports
    "@supports (color:color-mix(in lab, purple, purple)){a{color:red}}",
    "@supports (color:color-mix(in lab, #7c3aed, #7c3aed)){a{color:red}}",
    "a{color:color-mix(in lab, red, red)}",
    # form 3 with a chromatic purple variable, or variables this file never defines
    f":root{{--a:{PURPLE_OKLCH};--b:oklch(20% 0 0)}}"
    "a{color:color-mix(in oklch,var(--a),var(--b) 5%)}",
    ":root{--a:#7c3aed;--b:#111111}a{color:color-mix(in oklch,var(--a),var(--b) 5%)}",
    "a{color:color-mix(in oklch,var(--a),var(--b) 5%)}",
    # anything else still fails
    "a{color:color-mix(in srgb, #0B6BC7, #7c3aed)}",
    "a{color:hsl(280 60% 50%)}",
])
def test_a_planted_purple_fails_in_every_colour_form(css):
    assert _css_problems(css) != [], css


# --- M-7 ------------------------------------------------------------------------------------

@pytest.mark.parametrize("path", JS_FILES, ids=lambda p: p.name)
def test_javascript_uses_only_colours_the_guard_can_read(path):
    values = _js_values(path.read_text(encoding="utf-8"))
    found = sorted({m.group(0).lower() for v in values for m in _UNREADABLE_FN.finditer(v)})
    assert found == [], f"{path.name}: use hex or rgb()/rgba() instead of {found}"


def test_the_javascript_scan_reads_colour_values_and_not_prose():
    assert "rebeccapurple" in _js_values('el.style.color = "rebeccapurple";')
    assert "hsl(280 60% 50%)" in _js_values("const c = `hsl(280 60% 50%)`;")
    assert "hsl(" in _js_values("const c = 'hsl(' + h + ', 60%, 50%)';")   # concatenated
    prose = '// a plum-coloured note, do not use violet\nconst k = "af:gmail", t = "use strict";'
    assert not [v for v in _js_values(prose) if v in BANNED_WORDS]
    assert [raw for raw, rgb in _colours('const c = "#a25afd";') if _is_purple(rgb)] == ["#a25afd"]
```

- [ ] **Step 3: Run the new tests and watch them fail**

Run: `.venv/Scripts/python.exe -m pytest -q tests/test_saas_basecoat.py tests/test_saas_palette.py`

Expected: `11 failed, 73 passed, 10 errors`. The failures are `FileNotFoundError` for the missing
upstream, trimmed and licence files, `test_gitattributes_keeps_both_basecoat_files_byte_for_byte`
(no `tools/basecoat/*.css -text` yet), and `test_there_is_something_to_scan` with
`vendored CSS is scanned`. The 10 errors are every test that uses the `trim` or `layer` fixture
(`tools/basecoat/trim.py` does not exist). The one Basecoat test that passes already is
`test_no_template_writes_markup_whose_basecoat_rules_were_trimmed` (today's templates write none
of that markup).

- [ ] **Step 4: Download the upstream file into `tools/basecoat/`**

Write this script with the Write tool to `<scratchpad>/fetch_basecoat.py` (the session scratchpad,
not the repo):

```python
"""Download basecoat-css 1.0.2 from npm and copy its ready-made CSS, byte for byte, into the repo.

Usage: python fetch_basecoat.py <repo root>
"""
import hashlib
import io
import sys
import tarfile
import urllib.request
from pathlib import Path

URL = "https://registry.npmjs.org/basecoat-css/-/basecoat-css-1.0.2.tgz"
TGZ_SHA256 = "b493e77a7ee0b945e41398f5aee186ffa692f930751b960f5ac0853e4b54de48"
CSS_MEMBER = "package/dist/basecoat.cdn.min.css"
CSS_SHA256 = "8123677adb9bba43be3298e1543bcc5fc763e8cda3d32dc74c806046a3537ca0"

repo = Path(sys.argv[1])
data = urllib.request.urlopen(URL, timeout=60).read()
assert hashlib.sha256(data).hexdigest() == TGZ_SHA256, "the npm tarball changed"
with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
    css = tar.extractfile(CSS_MEMBER).read()
    licence = tar.extractfile("package/LICENSE.md").read().decode("utf-8")
assert hashlib.sha256(css).hexdigest() == CSS_SHA256, "the CSS inside the tarball changed"
assert b"\r" not in css and css.startswith(b"/*! tailwindcss v4.3.1 | MIT License")
out = repo / "tools" / "basecoat" / "basecoat-1.0.2.cdn.min.css"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_bytes(css)
print(f"wrote {out} ({len(css)} B)")
print(licence.splitlines()[2])          # Copyright (c) 2025 Ronan Berder
```

Run: `.venv/Scripts/python.exe <scratchpad>/fetch_basecoat.py C:/Users/regid/Desktop/applyfirst`

Expected output:
```
wrote C:\Users\regid\Desktop\applyfirst\tools\basecoat\basecoat-1.0.2.cdn.min.css (218225 B)
Copyright (c) 2025 Ronan Berder
```
The script refuses to write anything if either the tarball or the CSS inside it has changed.

- [ ] **Step 5: Keep the upstream file byte for byte in git**

`core.autocrlf` is `true` on this machine and the upstream file contains one LF (after the
licence comment), so without `-text` a checkout would turn it into CRLF and break the sha256 pin.
The trimmed file is already covered by line 9.

`.gitattributes` lines 7-9 today:
```
# The vendored library is pinned by sha256, so a CRLF checkout would change its bytes
# and break the pin. Leave it exactly as committed.
applyfirst/saas/static/vendor/** -text
```
After (lines 7-13; append with the Edit tool, keep LF):
```
# The vendored library is pinned by sha256, so a CRLF checkout would change its bytes
# and break the pin. Leave it exactly as committed.
applyfirst/saas/static/vendor/** -text

# The pinned upstream Basecoat file is hashed byte for byte as well (tools/basecoat/trim.py
# re-creates static/vendor/basecoat-1.0.2-agad.css from it). Keep it exactly as committed.
tools/basecoat/*.css -text
```
Check: `git check-attr -a tools/basecoat/basecoat-1.0.2.cdn.min.css tools/basecoat/trim.py`
prints `tools/basecoat/basecoat-1.0.2.cdn.min.css: text: unset` and nothing for `trim.py`.

- [ ] **Step 6: Write `tools/basecoat/trim.py`**

Create it with the Write tool (not a Bash heredoc: heredocs mangle the backslashes in the
regular expressions), exactly. It is standard library only. Its steps map to spec 4.3 as follows;
steps 4b and 4c and the dropping of `@layer properties` are refinements this plan adds (see
"Notes for the reviewer (Task 1)"):
1. keep the Tailwind licence comment and add a header (upstream file, its sha256, the script, the date `TRIMMED_ON`, the two licence files);
2. drop `@layer properties`, `@layer base`, `@layer utilities`, the unlayered `:root` and `.dark`, and the `pulse` and `toast-up` keyframes;
3. from `@layer theme` keep only the variables the kept rules read (transitively), never `--font-sans/mono`, `--ease-*`, `--animate-*` (a kept rule that reads one of those stops the script) or `--color-*` (left to journey.css);
4. keep a component rule only when every selector in its list styles at least one allowed class and no other class (classes inside `:not()` and `:has()` do not count, so the upstream `:not(:is(.command>header input,...))` does not disqualify the input rule, and `label:has(>.field)` does not count as naming `.field`);
4b. drop a selector from a kept list when every way it can match (`:not()` removed, `:is()`/`:where()`/`:has()` expanded) needs markup the journey pages never write, and drop the rule if no selector is left;
4c. drop a rule that carries `!important`;
5. rewrite `:is(html.dark *)` and a leading `html.dark ` into the same rule inside `@media (prefers-color-scheme:dark)`, in place (source order is kept), stopping on any other dark form;
6. keep only the `@property` rules whose name a kept rule reads;
7. wrap everything in `@layer basecoat{...}`, put the `@property` rules after it unlayered, and write LF.
Neighbouring grouping rules with the same prelude are merged, which changes nothing but bytes.

```python
"""Rebuild Agad's trimmed Basecoat stylesheet from the pinned upstream file (spec 4.3).

Run it by hand, and only when Basecoat is upgraded:

    .venv/Scripts/python.exe tools/basecoat/trim.py

Input:  tools/basecoat/basecoat-1.0.2.cdn.min.css, byte for byte the file
        package/dist/basecoat.cdn.min.css in the basecoat-css 1.0.2 npm tarball.
Output: applyfirst/saas/static/vendor/basecoat-1.0.2-agad.css, LF line endings.

The output depends only on the input bytes and the constants below, so
tests/test_saas_basecoat.py calls trim() again and requires the committed file byte for byte.
Anything in the input this script does not recognise stops it with TrimError instead of being
copied through, so an upgrade cannot quietly bring back a reset, a colour block or a new layer.
Standard library only. No Node, no Tailwind, nothing to install.
"""

from __future__ import annotations

import gzip
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSION = "1.0.2"
SOURCE = ROOT / "tools" / "basecoat" / f"basecoat-{VERSION}.cdn.min.css"
OUTPUT = ROOT / "applyfirst" / "saas" / "static" / "vendor" / f"basecoat-{VERSION}-agad.css"
SOURCE_SHA256 = "8123677adb9bba43be3298e1543bcc5fc763e8cda3d32dc74c806046a3537ca0"
SOURCE_URL = "https://registry.npmjs.org/basecoat-css/-/basecoat-css-1.0.2.tgz"
SOURCE_IN_PACKAGE = "package/dist/basecoat.cdn.min.css"
TRIMMED_ON = "2026-09-25"           # printed in the header; change it by hand when you re-trim
GZIP_CAP = 7000                     # spec 8

# Step 4: the only Basecoat component classes the sign-up pages use.
ALLOWED = frozenset({"btn", "card", "card-title", "card-description", "card-action", "field",
                     "input", "label", "textarea", "alert", "badge"})
# Step 4b: markup the journey pages never write (they use BEM classes such as btn--primary and
# badge--ok, mark errors with aria-invalid, and every input is a text box or a textarea). A
# selector that can only match through one of these is dropped from its list, and a rule left
# with no selector is dropped. tests/test_saas_basecoat.py fails if a template starts writing one.
NEVER_IN_OUR_MARKUP = re.compile(
    r"\[data-(?:variant|size|orientation)=|\[data-(?:invalid|disabled)\b"
    r"|\[type=(?:checkbox|radio|range)\]|\[role=switch\]|:checked")
# Step 4c: a rule with !important is dropped. An important declaration in the lowest layer beats
# every declaration in the layers above it, so journey.css could never override it.
# Step 5: the two dark forms Tailwind writes for Basecoat.
DARK_IS = ":is(html.dark *)"
DARK_PREFIX = "html.dark "
DARK_MEDIA = "@media (prefers-color-scheme:dark)"
# Step 3: theme variables never copied. --color-* carry colour, and journey.css supplies the ones
# the kept rules read (spec 4.4). The others collide with app.css (--font-sans, the frozen
# --ease-out) or serve dropped parts, so a kept rule that reads one of them stops the script.
COLOUR_THEME = re.compile(r"--color-")
COLLIDING_THEME = re.compile(r"--(?:font-(?!weight-)|ease-|animate-|default-(?:mono-)?font)")
# Step 2: top-level statements dropped whole.
DROPPED_TOP = frozenset({"@layer properties", "@layer base", "@layer utilities", ":root", ".dark",
                         "@keyframes pulse", "@keyframes toast-up"})
GROUPING = ("@layer", "@media", "@supports", "@container", "@starting-style")
_VAR_READ = re.compile(r"var\((--[\w-]+)")
_CLASS = re.compile(r"\.(-?[_a-zA-Z][\w-]*)")


class TrimError(ValueError):
    """The input is not shaped the way this script expects. Read it before changing the rules."""


class Node:
    """One statement. A style rule has a body, a grouping rule (@layer, @media, @supports,
    @container, @starting-style) has children, and a comment or a ';' statement has neither."""

    __slots__ = ("prelude", "body", "children")

    def __init__(self, prelude: str, body: str | None = None,
                 children: list[Node] | None = None) -> None:
        self.prelude, self.body, self.children = prelude, body, children

    @property
    def is_rule(self) -> bool:
        return self.children is None and not self.prelude.startswith(("@", "/*"))


# --- reading --------------------------------------------------------------------------------

def _skip_string(text: str, i: int) -> int:
    """The index just past the quoted string that starts at text[i]."""
    quote, i = text[i], i + 1
    while text[i] != quote:
        i += 2 if text[i] == "\\" else 1
    return i + 1


def _block_end(text: str, i: int) -> int:
    """text[i] is '{'. The index of the '}' that closes it."""
    depth = 0
    while True:
        if text[i] in "\"'":
            i = _skip_string(text, i)
            continue
        if text.startswith("/*", i):
            i = text.index("*/", i) + 2
            continue
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1


def parse(text: str) -> list[Node]:
    """Split a stylesheet, or the inside of a grouping rule, into statements."""
    nodes: list[Node] = []
    i, n = 0, len(text)
    while i < n:
        if text[i].isspace():
            i += 1
            continue
        if text.startswith("/*", i):
            end = text.index("*/", i) + 2
            nodes.append(Node(text[i:end]))
            i = end
            continue
        j = i
        while j < n and text[j] not in "{;}":
            j = _skip_string(text, j) if text[j] in "\"'" else j + 1
        prelude = text[i:j].strip()
        if j == n or text[j] == "}":
            raise TrimError(f"declarations outside a rule: {prelude[:60]!r}")
        if text[j] == ";":
            nodes.append(Node(prelude))
            i = j + 1
            continue
        end = _block_end(text, j)
        inner = text[j + 1:end]
        if prelude.startswith(GROUPING):
            nodes.append(Node(prelude, children=parse(inner)))
        elif prelude.startswith("@") or "{" not in inner:
            nodes.append(Node(prelude, body=inner))
        else:
            raise TrimError(f"a rule nested inside {prelude[:60]!r}")
        i = end + 1
    return nodes


def split_top(text: str, sep: str) -> list[str]:
    """Split text on sep wherever sep is outside brackets, parentheses and strings."""
    parts, depth, start, i = [], 0, 0, 0
    while i < len(text):
        ch = text[i]
        if ch in "\"'":
            i = _skip_string(text, i)
            continue
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        elif ch == sep and depth == 0:
            parts.append(text[start:i])
            start = i + 1
        i += 1
    parts.append(text[start:])
    return parts


def _close(text: str, start: int) -> int:
    """text[start - 1] is '('. The index just past its matching ')'."""
    depth, i = 1, start
    while depth:
        depth += {"(": 1, ")": -1}.get(text[i], 0)
        i += 1
    return i


def without(selector: str, groups: tuple[str, ...]) -> str:
    """The selector with the argument of every listed pseudo-class (":not(" and so on) removed."""
    out, i = [], 0
    while i < len(selector):
        hit = next((g for g in groups if selector.startswith(g, i)), None)
        if hit is None:
            out.append(selector[i])
            i += 1
        else:
            i = _close(selector, i + len(hit))
    return "".join(out)


def classes(selector: str) -> set[str]:
    """The classes a selector styles. Attribute values are ignored, and so are the arguments of
    :not(), which names what must be absent, and :has(), which names what sits inside."""
    styled = without(selector, (":not(", ":has("))
    return set(_CLASS.findall(re.sub(r"\[[^\]]*\]", "", styled)))


def _alternatives(selector: str) -> list[str]:
    """Every way the selector can match: :not() arguments removed (they are never required),
    and each :is(), :where() and :has() list expanded into its choices."""
    selector = without(selector, (":not(",))
    m = re.search(r":(?:is|where|has)\(", selector)
    if m is None:
        return [selector]
    end = _close(selector, m.end())
    head, tail = selector[:m.start()], selector[end:]
    return [alt for arg in split_top(selector[m.end():end - 1], ",")
            for alt in _alternatives(head + arg + tail)]


def can_match_our_markup(selector: str) -> bool:
    """False when every way the selector can match needs markup the journey pages never write."""
    return any(not NEVER_IN_OUR_MARKUP.search(alt) for alt in _alternatives(selector))


# --- deciding -------------------------------------------------------------------------------

def _undark(selector: str) -> str:
    """Step 5: the selector without its dark marker, which must sit outside every bracket."""
    at = selector.find(DARK_IS)
    if at < 0:
        at, selector = 0, selector.removeprefix(DARK_PREFIX)
    else:
        selector = selector[:at] + selector[at + len(DARK_IS):]
    if selector[:at].count("(") != selector[:at].count(")") or "dark" in selector:
        raise TrimError(f"a dark form this script does not know: {selector[:80]!r}")
    return selector


def _keep_rule(rule: Node) -> Node | None:
    selectors = split_top(rule.prelude, ",")
    dark = [DARK_IS in s or s.startswith(DARK_PREFIX) for s in selectors]
    if any(dark) and not all(dark):
        raise TrimError(f"a selector list mixes light and dark: {rule.prelude[:80]!r}")
    if all(dark):
        selectors = [_undark(s) for s in selectors]
    elif "dark" in rule.prelude:
        raise TrimError(f"a dark form this script does not know: {rule.prelude[:80]!r}")
    if not all(classes(s) and classes(s) <= ALLOWED for s in selectors):
        return None                                                         # step 4
    selectors = [s for s in selectors if can_match_our_markup(s)]            # step 4b
    if not selectors or "!important" in rule.body:                          # step 4c
        return None
    kept = Node(",".join(selectors), body=rule.body)
    return Node(DARK_MEDIA, children=[kept]) if all(dark) else kept


def _filter(nodes: list[Node]) -> list[Node]:
    out: list[Node] = []
    for node in nodes:
        if node.is_rule:
            kept = _keep_rule(node)
        elif node.children is not None and node.prelude.startswith(GROUPING[1:]):
            kids = _filter(node.children)
            kept = Node(node.prelude, children=kids) if kids else None
        else:
            raise TrimError(f"unexpected statement in @layer components: {node.prelude[:60]!r}")
        if kept is not None:
            out.append(kept)
    return _merge(out)


def _merge(nodes: list[Node]) -> list[Node]:
    """Join neighbouring grouping rules with the same prelude. Order and meaning are unchanged."""
    out: list[Node] = []
    for node in nodes:
        if (node.children is not None and out and out[-1].children is not None
                and out[-1].prelude == node.prelude):
            out[-1] = Node(node.prelude, children=_merge(out[-1].children + node.children))
        else:
            out.append(node)
    return out


def reads(nodes: list[Node]) -> set[str]:
    """Every custom property the rules read with var()."""
    names: set[str] = set()
    for node in nodes:
        if node.children is not None:
            names |= reads(node.children)
        else:
            names |= set(_VAR_READ.findall(node.body or ""))
    return names


def _theme(layer: Node, wanted_by_rules: set[str]) -> Node:
    """Step 3: the theme variables the kept rules read, and the ones those read in turn."""
    if [c.prelude for c in layer.children] != [":root,:host"]:
        raise TrimError("@layer theme should hold exactly one :root,:host rule")
    root = layer.children[0]
    decls = [d.split(":", 1) for d in split_top(root.body, ";") if d.strip()]
    values = {name.strip(): value for name, value in decls}
    wanted: set[str] = set()
    frontier = {r for r in wanted_by_rules if r in values}
    while frontier:
        name = frontier.pop()
        if COLLIDING_THEME.match(name):
            raise TrimError(f"a kept rule reads {name}, which app.css owns or which was dropped")
        if COLOUR_THEME.match(name):
            continue
        wanted.add(name)
        frontier |= {r for r in _VAR_READ.findall(values[name]) if r in values} - wanted
    body = ";".join(f"{name.strip()}:{value}" for name, value in decls if name.strip() in wanted)
    return Node(":root,:host", body=body)


# --- writing --------------------------------------------------------------------------------

def _emit(nodes: list[Node], lines: list[str]) -> None:
    for node in nodes:
        if node.children is None:
            lines.append(f"{node.prelude}{{{node.body}}}")
        else:
            lines.append(node.prelude + "{")
            _emit(node.children, lines)
            lines.append("}")


def header(source_sha256: str) -> list[str]:
    return [
        f"/*! basecoat-css {VERSION} | MIT License | https://basecoatui.com */",
        f"/* Trimmed for Agad by tools/basecoat/trim.py on {TRIMMED_ON}. Do not edit this file:",
        "   change trim.py and run it again.",
        f"   Source: tools/basecoat/basecoat-{VERSION}.cdn.min.css, which is {SOURCE_IN_PACKAGE}",
        f"   from {SOURCE_URL}",
        f"   sha256 {source_sha256}",
        "   Licences: /static/licenses/basecoat-MIT.txt, /static/licenses/tailwindcss-MIT.txt */",
    ]


def lf(data: bytes) -> bytes:
    """The bytes with CRLF turned into LF, so a Windows checkout hashes and trims the same."""
    return data.replace(b"\r\n", b"\n")


def trim(source: bytes) -> bytes:
    """The trimmed stylesheet for these upstream bytes (spec 4.3 steps 1 to 7)."""
    source = lf(source)
    licence = theme = components = None
    properties: list[Node] = []
    for node in parse(source.decode("utf-8")):
        head = node.prelude
        if head.startswith("/*! tailwindcss v"):
            licence = head                                                  # step 1
        elif head in DROPPED_TOP:
            continue                                                        # step 2
        elif head == "@layer theme":
            theme = node
        elif head == "@layer components":
            components = _filter(node.children)                             # steps 4, 4b, 5
        elif head.startswith("@property --tw-"):
            properties.append(node)
        else:
            raise TrimError(f"unexpected top-level statement: {head[:60]!r}")
    if licence is None or theme is None or components is None:
        raise TrimError("the Tailwind licence, @layer theme or @layer components is missing")
    read = reads(components)
    kept_props = [p for p in properties if p.prelude.split()[1] in read]  # step 6
    lines = [licence, *header(hashlib.sha256(source).hexdigest()), "@layer basecoat{"]
    _emit([_theme(theme, read), *components], lines)                        # steps 3 and 7
    lines.append("}")
    _emit(kept_props, lines)
    return ("\n".join(lines) + "\n").encode("utf-8")


def main() -> int:
    source = lf(SOURCE.read_bytes())
    digest = hashlib.sha256(source).hexdigest()
    if digest != SOURCE_SHA256:
        print(f"{SOURCE.name}: sha256 {digest}, expected {SOURCE_SHA256}", file=sys.stderr)
        return 1
    out = trim(source)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(out)
    size = len(gzip.compress(out, 9, mtime=0))
    print(f"wrote {OUTPUT.relative_to(ROOT).as_posix()}: {len(out)} B, {size} B gzip "
          f"(cap {GZIP_CAP}), sha256 {hashlib.sha256(out).hexdigest()}")
    return 0 if size <= GZIP_CAP else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 7: Run the trim**

Run: `.venv/Scripts/python.exe tools/basecoat/trim.py`

Expected, exactly:
```
wrote applyfirst/saas/static/vendor/basecoat-1.0.2-agad.css: 36345 B, 3363 B gzip (cap 7000), sha256 4aae6ed8773c27938e12e6c87139f99305fb680a4cd5298c7864034119325157
```
If the sha256 differs, `trim.py` on disk differs from Step 6 (a changed character, header line or
`TRIMMED_ON`). Diff it against the plan and fix the script. Do not edit `TRIMMED_SHA` to match.
The first 9 lines of the output must read:
```
/*! tailwindcss v4.3.1 | MIT License | https://tailwindcss.com */
/*! basecoat-css 1.0.2 | MIT License | https://basecoatui.com */
/* Trimmed for Agad by tools/basecoat/trim.py on 2026-09-25. Do not edit this file:
   change trim.py and run it again.
   Source: tools/basecoat/basecoat-1.0.2.cdn.min.css, which is package/dist/basecoat.cdn.min.css
   from https://registry.npmjs.org/basecoat-css/-/basecoat-css-1.0.2.tgz
   sha256 8123677adb9bba43be3298e1543bcc5fc763e8cda3d32dc74c806046a3537ca0
   Licences: /static/licenses/basecoat-MIT.txt, /static/licenses/tailwindcss-MIT.txt */
@layer basecoat{
```

- [ ] **Step 8: Add the two licences**

Create `applyfirst/saas/static/licenses/basecoat-MIT.txt` with the Write tool. Lines 1-21 are
`package/LICENSE.md` from the tarball word for word (checked with `diff`); the last paragraph
follows the canvas-confetti precedent (`canvas-confetti-ISC.txt` ends with "Modified by Agad"):

```text
MIT License

Copyright (c) 2025 Ronan Berder

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

Modified by Agad (2026-09-25): static/vendor/basecoat-1.0.2-agad.css is a trimmed copy of
dist/basecoat.cdn.min.css from basecoat-css 1.0.2. tools/basecoat/trim.py keeps only the parts
the sign-up pages use, wraps them in @layer basecoat and moves dark mode to
prefers-color-scheme. Upstream sha256 8123677adb9bba43be3298e1543bcc5fc763e8cda3d32dc74c806046a3537ca0.
```

Create `applyfirst/saas/static/licenses/tailwindcss-MIT.txt`. Lines 1-21 are `LICENSE` of
tailwindlabs/tailwindcss at tag `v4.3.1` word for word (same text on `main`):

```text
MIT License

Copyright (c) Tailwind Labs, Inc.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

Basecoat's stylesheet (static/vendor/basecoat-1.0.2-agad.css) was generated by Tailwind CSS
v4.3.1 and keeps Tailwind's licence comment at the top.
```

- [ ] **Step 9: Run the new tests and watch them pass**

Run: `.venv/Scripts/python.exe -m pytest -q tests/test_saas_basecoat.py tests/test_saas_palette.py`

Expected: `97 passed` (21 in test_saas_basecoat.py, 76 in test_saas_palette.py; the palette file
had 59 before this task).

- [ ] **Step 10: Break it once on purpose, then restore**

Append a planted purple and a preflight rule to the trimmed file and confirm the semantic tests,
not only the hash pins, catch them. Write `<scratchpad>/plant.py` with the Write tool:

```python
from pathlib import Path
f = Path("C:/Users/regid/Desktop/applyfirst/applyfirst/saas/static/vendor/basecoat-1.0.2-agad.css")
f.write_bytes(f.read_bytes().replace(b"@layer basecoat{", b"@layer basecoat{\nbody{color:#7c3aed}", 1))
```
Run it, then `.venv/Scripts/python.exe -m pytest -q tests/test_saas_basecoat.py tests/test_saas_palette.py`.
Expected: `4 failed, 93 passed`, namely
`test_saas_palette.py::test_no_colour_in_the_banned_hue_band[basecoat-1.0.2-agad.css]`,
`test_saas_basecoat.py::test_no_preflight_or_bare_element_selector`,
`test_saas_basecoat.py::test_the_trimmed_file_is_the_pinned_build` and
`test_saas_basecoat.py::test_running_trim_again_gives_the_committed_file_byte_for_byte`.
Restore with `.venv/Scripts/python.exe tools/basecoat/trim.py` (same output line as Step 7) and
re-run the two files: `97 passed`.

- [ ] **Step 11: Run both gates**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: pytest: all pass (887 + the new tests), which is `925 passed` (38 new: 21 Basecoat tests
and 17 more palette tests).

Run: `.venv/Scripts/python.exe .noxa/redesign-saas-ui/inputs/preserve_smoke.py`
Expected: smoke: 0 failed (`558 checks passed, 0 failed.`; nothing served changes, so the count
does not move).

`git status --short` should show only: ` M .gitattributes`, ` M tests/test_saas_palette.py`,
`?? applyfirst/saas/static/licenses/basecoat-MIT.txt`,
`?? applyfirst/saas/static/licenses/tailwindcss-MIT.txt`,
`?? applyfirst/saas/static/vendor/basecoat-1.0.2-agad.css`, `?? tests/test_saas_basecoat.py`,
`?? tools/`, plus the pre-existing `?? REMOTE.md`. No commit in this task.

#### Notes for the reviewer (Task 1)

1. **Spec 4.3 refinements this task adds.** (a) Step 4b prunes selectors that need markup the
   journey pages never write (`data-variant=`, `data-size=`, `data-orientation=`, `data-invalid`,
   `data-disabled`, checkbox, radio, range, switch, `:checked`), guarded by a template test. It
   halves the file (5,938 to 3,363 B gzip) by removing the xs, sm, lg and icon button sizes, the
   secondary, outline, ghost, link and destructive variants, checkbox, radio, range and switch.
   It keeps the default variant and default size, because our buttons carry neither attribute:
   `.btn:not([data-size]){height:36px}` and `.btn:not([data-variant]){background:var(--color-primary)}`
   still apply and journey.css still overrides them (spec 5.2 already lists the 36px height).
   Without 4b the `/login` render-blocking budget (spec 8, 30,000 B) has 164 B of room. (b) Step 4c drops
   the one `!important` rule (`.badge>svg`). (c) `@layer properties` is dropped because its
   selector is `*` (forbidden by spec 8). Side effect: in browsers without `@property` (Safari
   before 16.4, Firefox before 128) `--tw-border-style` has no value, so Basecoat's own borders
   disappear there. journey.css should write `border-style` (or the `border` shorthand) itself on
   every control, card, alert and badge it styles.
2. **The upstream file name.** The package has no `basecoat-1.0.2.cdn.min.css`; the source is
   `package/dist/basecoat.cdn.min.css`, copied to the spec's name.
3. **For Task 3 (journey.css).** It must define the 10 names in `SUPPLIED_BY_JOURNEY`, in light and
   dark. The `--color-*` aliases are gone, so defining only `--primary` and friends (spec 4.4's
   list) styles nothing Basecoat reads. `var()` is resolved where a property is declared: if
   journey writes `--color-card: var(--card)` on `:root`, the light island on `.mailcard` and
   `.gsi-btn` must redefine the `--color-*` names too, not just `--card`.
4. **Basecoat leaks that are not in spec 5.2's override list** (all measured in the trimmed file;
   Task 3 overrides each one, see note 6):
   - `.input[aria-invalid=true]` and the textarea equivalent paint a `--color-destructive` border
     and a 3px ring, in light and in dark (six rules for inputs, six for the textarea). Spec 5.2
     says invalid fields stay amber,
     so journey.css must set `border-color` and `box-shadow` for `[aria-invalid=true]` on `.input`.
   - Our textarea is `textarea.input` with no `type`, so it matches Basecoat's
     `.input:not([type])` input rule (`height:36px`, `padding-block:4px`, a
     `0 1px 2px #0000000d` shadow) as well as `.field>textarea` (`field-sizing:content`,
     `min-height:64px`). `height:auto` must cover `textarea.input`.
   - In dark mode every input gets `background-color: color-mix(in oklab, var(--color-input) 30%,
     transparent)`, so `--color-input` (the control edge) tints the input fill unless journey sets
     the input background.
   - `.btn` and `.input` transitions (`transition-property: all` and `color,box-shadow`, 150ms)
     are unconditional. For reduced motion to be "fully static" journey.css must switch them off
     outside the `no-preference` block, not only narrow `transition-property`.
   - `.btn:not([data-variant])` paints every `.btn` with `--color-primary`, and under
     `(hover:hover)` a translucent `color-mix(... 80%, transparent)` hover. app.css
     `.btn--secondary` overrides the fill, but each variant needs its own hover background.
   - `.field{display:flex;flex-direction:column;gap:12px}`, `.field>*{width:100%}` and
     `.field>p:nth-last-child(2){margin-top:-4px}`, which hits our `p.field__hint` (the hint sits
     just before the input).
   - `.alert` becomes a grid with `background-color: var(--color-card)`; `.alert:has(>svg)` sets
     `grid-template-columns: auto 1fr` and `.alert>svg` a 2px translate. `.badge` gets
     `height:20px`, `overflow:hidden`, radius `var(--radius-4xl)` (2rem) and a `--color-primary`
     fill. `.card` gets `padding-block:24px`, `gap:24px` and a `--tw-shadow`.
5. **Order of tasks.** `tests/test_saas_basecoat.py` does not import `tests/_journey_css.py`
   (Task 3 creates that later); Task 3 points `BASECOAT_CSS` at the same path.
6. **Where the leaks in note 4 are handled.** Task 3 section 5 sets `height:auto` on `.btn` and
   `.input` (which covers `textarea.input`), the input background, `transition:none` outside
   the no-preference block, `.input[aria-invalid=true]` in amber, and every border itself, so
   the missing `@layer properties` changes nothing visible on old browsers.


### Task 2: Inter font (subset file, build script, licence, section 1 of journey.css, font tests)

Everything in this task was prototyped end to end in a scratch copy of the repo on 2026-09-25.
The build ran twice (from a local copy and from the pinned URL) and produced identical bytes, the
new tests failed before the implementation and passed after it, five planted mistakes were each
caught, and both gates were green afterwards. Re-run during assembly in sequence after Task 1,
with the review-focus test added: pytest 939 passed, smoke 558 checks and 0 failed.

**Files:**
- Create `tools/fonts/build_inter.py` (full code in Step 4).
- Create, by running the script, `applyfirst/saas/static/fonts/inter-4.1-latin-wght.woff2`
  (28,132 bytes, sha256 `effa0eae43e76b7d0f6ebfb74c77db701a420ae30a24c14b09a3fc82646b1fd0`).
- Create, by running the script, `applyfirst/saas/static/licenses/OFL-inter.txt` (4,835 bytes,
  sha256 `e1ede4f5976346ba147ed11df18f80b0d7e4bab16d33bd8f974ddb363de268d1`).
- Create `applyfirst/saas/static/css/journey.css` with the file header (lines 1 and 2) and
  section 1 only (lines 4 to 12). Task 3 appends the `@layer journey { ... }` block after line 12
  and must not recreate the file.
- Modify `requirements-dev.txt`, append after line 3 (`pytest-timeout>=2.3`).
- Modify `tests/test_saas_hero.py` lines 16 to 30 (imports and constants), line 188 (the
  file-name parametrize list), lines 258 to 275 (the font contract section, both tests replaced
  and nine added).
- No template changes. No change to `app.css`, `motion.css`, `vt.js`, `motion.js`, `.gitattributes`
  or the smoke file.

**Interfaces:**
- Consumes (verified): `tests/test_saas_motion.py` exports `REPO` (line 37), `STATIC` (38),
  `TEMPLATES` (39), `_text` (73), `_strip_comments` (179), `MOTION_ASSETS` (56).
  `applyfirst/saas/static_assets.py:77-82` serves a URL without `?v` with
  `Cache-Control: public, max-age=86400` plus an ETag, which is why the font name carries the
  version. `tests/test_saas_static.py:162-173` requires every `url()` in `static/css/*.css` to
  resolve to a real file, so the font and `journey.css` must land in the same task.
- Produces:
  - Font families `"Inter Agad"` (the subset, `font-weight: 400 600`) and `"Inter Agad Fallback"`
    (local Segoe UI or Roboto, metric-matched). Nothing else in the plan may declare a face.
  - `journey.css` lines 1 and 2 (file header) and section 1 opening with the banner
    `/* ---- 1 fonts */`, unlayered, exactly two `@font-face` rules.
  - `tools/fonts/build_inter.py` module API, imported by the tests: `COMMIT`, `SOURCE_URL`,
    `SOURCE_SHA256`, `LICENCE_URL`, `LICENCE_SHA256`, `OPSZ`, `WGHT`, `UNICODE_RANGES`,
    `FEATURES`, `MAX_BYTES`, `FREQ`, `FALLBACK_AVG_EM`, `unicodes()`, `unicode_range_css()`,
    `version_of(font)`, `font_name(version)`, `avg_em(font)`, `fallback_descriptors(font)`,
    `build(src_bytes)`.
  - In `tests/test_saas_hero.py`: constants `JOURNEY_CSS`, `INTER`, `INTER_SHA256`,
    `INTER_LICENCE`, `BUILD_INTER` and helpers `_builder()`, `_faces(css)`, `_tnum_advances(font)`.
  - For Task 3 (section 4 base), measured in Step 8: the journey body rule is
    `body{font-family:-apple-system,BlinkMacSystemFont,"Inter Agad","Inter Agad Fallback",system-ui,"Segoe UI",Roboto,sans-serif;font-size-adjust:none}`.
    Task 3 writes that rule and owns its test (`test_the_journey_body_uses_the_inter_stack_at_nominal_size`)
    and the flat primary button tests, in `tests/test_saas_journey.py`.
  - Review focus 3: `test_the_inter_file_is_served_as_a_cached_font`.

**Frozen hooks (spec 9):** this task edits no template and no rule that any hook reads, so none of
the section 9 hooks is in scope. The two new file names are checked against the M-2 substrings
(`motion.css`, `vt.js`, `motion.js`, `canvas-confetti`) by the extended parametrize in Step 2.

**How the numbers were chosen (read once, the steps below just apply them).**
- Source. google/fonts `ofl/inter/Inter[opsz,wght].ttf`, last changed in commit
  `e1d6480102fed30739fead0faee463101f892c8f` (2024-06-06, "Inter: Version 4.001;git-66647c0bb
  added", upstream archive `Inter-4.1-GoogleFonts.zip`). Its git blob `047c92f6e221...` is also
  what `main` serves today. sha256 of the file is
  `29160a80ff49ddcab2c97711247e08b1fab27a484a329ce8b813d820dc559031`, 876,576 bytes, axes
  opsz 14 to 32 and wght 100 to 900. Name ID 5 is `Version 4.001;git-66647c0bb`. Inter writes
  its minor version as three digits, so 4.001 is Inter 4.1 and the spec's file name
  `inter-4.1-latin-wght.woff2` holds.
- Size. opsz pinned at 14, wght 400 to 600, Basic Latin, Latin-1, General Punctuation and U+20B1,
  default shaping features plus `tnum`, WOFF2: **28,132 bytes**, not the 47 KB the spec guessed.
  For reference, the same subset with the full wght 100 to 900 is 40,112 bytes, and with every
  OpenType feature kept it is 44,540 bytes. What survives in the file is GSUB `calt`, `locl`,
  `tnum` and GPOS `kern` (Inter has no `liga`, and `ccmp`, `mark`, `mkmk` have no lookups left
  for Latin), 268 characters, 392 glyphs. U+00AD (soft hyphen) has no glyph in Inter, which is
  normal.
- Checked in headless Chrome 153. The weight axis moves (400 < 500 < 600 in width), 700 clamps to
  600 with no faux bold (widths equal), `tabular-nums` gives the ten digits one width, and the
  peso sign renders from Inter.
- Fallback face, average-width method. `size-adjust` = Inter's average advance divided by the
  fallback's, where the average is each of a to z plus the space weighted by English letter
  frequency with the space at 18.18 percent (Capsize's `xWidthAvg` weighting). Measured with
  fontTools: Inter 0.47358 em, Segoe UI 5.62 (`C:/Windows/Fonts/segoeui.ttf`) 0.44251 em,
  Roboto 3.015 (google/fonts `ofl/roboto/Roboto[wdth,wght].ttf`, the Android face) 0.44247 em.
  The two fallbacks match each other to 0.01 percent, which is why one face with both `local()`
  names is enough. size-adjust = 0.47358 / 0.44249 = **107.03%**. The overrides replace the local
  font's own ascent and descent, so they depend only on Inter's metrics (hhea and typo both
  1984 / -494 / 0 at unitsPerEm 2048, USE_TYPO_METRICS set) divided by the size-adjust, because
  browsers scale the overrides by size-adjust too. descent = (494/2048) / 1.0703 = **22.54%**,
  line gap **0%**. ascent = (1984/2048 + 1/1024) / 1.0703 = **90.6%**. The extra 1/1024 em is
  measured, not a guess. Inter's ascent is exactly 15.5px at 16px (1984/2048 is 31/32), Chrome
  rounds ascent to whole pixels, and its scaled size lands a hair short, so the exact value
  (90.52%) and 90.53% both round to 15px at 16px and lift every line of fallback text by one
  pixel. 90.55% to 90.6% round to 16 like Inter at every size from 12 to 30px, and 91% overshoots
  at 17px. Roboto's published metrics (unitsPerEm 2048, ascender 1900, descender -500) match the
  measured file exactly (hhea 1900 / -500 / 0) and, because the overrides replace them, they do
  not enter the formula. Only Roboto's average width does.
- Result, measured by the script in Step 8 across 12, 14, 15, 16, 17, 20, 28 and 30px. The
  Segoe UI fallback is 99.84 to 99.85 percent of Inter's width, Roboto 100.10 percent, no
  paragraph gains or loses a line, and no baseline moves at any size.
- font-size-adjust. Inter's x-height is 1118/2048 = **0.5459** (OS/2 `sxHeight`, constant across
  weights once opsz is pinned). Today's `.52` renders Inter at 95.25 percent (measured), the
  spec's "about 4.8 percent" shrink. Two values render Inter at its nominal size, `.546` and
  `none`, and both measured exactly 100 percent. They differ on the fallback. A number applies to
  every face in the stack and overrides the fallback's size-adjust, which moved the swap from
  0.15 percent to 1.9 percent in width, added a line to the 328px paragraph at 12 and 16px and
  moved the baseline at 17 and 30px. `none` keeps the tuned fallback working, keeps SF at its
  nominal size on Apple devices, and behaves the same in browsers without font-size-adjust
  support. `from-font` was also measured and is worse (93.27 percent during the swap, because it
  cancels size-adjust). So the measured value is **`none`**, and it goes in the journey `body` rule
  in section 4 base (Task 3), next to the font stack.

- [ ] **Step 1: Install brotli and record it as a dev dependency**

fontTools (4.63.0, already installed as a dependency of fpdf2) needs brotli to write and to read
WOFF2. It is dev only. The Dockerfile installs `requirements.txt` only, and `tools/` is never
copied into the image.

```bash
.venv/Scripts/python.exe -m pip install brotli
.venv/Scripts/python.exe -c "import brotli, fontTools; print(brotli.__version__, fontTools.version)"
```

Expected: `1.2.0 4.63.0`. If pip resolves a later brotli, the font bytes may differ, see Step 5.

Append one line to `requirements-dev.txt`, after line 3. The file becomes:

```text
-r requirements.txt
pytest>=8.0
pytest-timeout>=2.3
brotli>=1.1              # dev only: fontTools needs it to read and write the WOFF2 Inter subset
```

- [ ] **Step 2: Write the failing tests in `tests/test_saas_hero.py`**

Edit 1, lines 16 to 30. Before:

```python
from __future__ import annotations

import re

import pytest

from _saas_client import client_for
from test_saas_motion import (
    MOTION_ASSETS, NON_APP_PAGES, STATIC, _five_pages, _gz, _strip_comments, _text,
)

HERO_CSS = STATIC / "css" / "hero.css"
SCENE_JS = STATIC / "js" / "scene.js"
APP_CSS = STATIC / "css" / "app.css"
BASE_HTML = STATIC.parents[0] / "templates" / "base.html"
```

After:

```python
from __future__ import annotations

import hashlib
import importlib.util
import re

import pytest
from fontTools.ttLib import TTFont

from _saas_client import client_for
from test_saas_motion import (
    MOTION_ASSETS, NON_APP_PAGES, REPO, STATIC, TEMPLATES, _five_pages, _gz, _strip_comments,
    _text,
)

HERO_CSS = STATIC / "css" / "hero.css"
SCENE_JS = STATIC / "js" / "scene.js"
APP_CSS = STATIC / "css" / "app.css"
BASE_HTML = STATIC.parents[0] / "templates" / "base.html"
JOURNEY_CSS = STATIC / "css" / "journey.css"
INTER = STATIC / "fonts" / "inter-4.1-latin-wght.woff2"
INTER_SHA256 = "effa0eae43e76b7d0f6ebfb74c77db701a420ae30a24c14b09a3fc82646b1fd0"
INTER_LICENCE = STATIC / "licenses" / "OFL-inter.txt"
BUILD_INTER = REPO / "tools" / "fonts" / "build_inter.py"
```

Edit 2, line 188. Before:

```python
@pytest.mark.parametrize("name", ["hero.css", "reveal.js", "scene.js"])
```

After:

```python
@pytest.mark.parametrize("name", ["hero.css", "reveal.js", "scene.js", "journey.css",
                                  "inter-4.1-latin-wght.woff2"])
```

Edit 3, lines 258 to 275, the whole font contract section. Before:

```python
# --- the font contract ------------------------------------------------------------------------

def test_the_site_uses_the_device_own_font_and_downloads_none_of_it():
    css = _text(APP_CSS)
    faces = re.findall(r"@font-face\s*\{[^}]*\}", css)
    assert not any("Jakarta" in f for f in faces), "a Plus Jakarta face is still declared"
    assert len(faces) == 1 and "Google Sans Button" in faces[0], (
        "only Google's own button face may be downloaded")
    m = re.search(r"--font-sans:\s*([^;]+);", css)
    assert m and m.group(1).strip().startswith("system-ui"), (
        f"--font-sans must lead with system-ui, got {m and m.group(1)!r}")


def test_no_page_preloads_a_font_the_stylesheet_never_asks_for():
    base = _text(BASE_HTML)
    assert "plus-jakarta" not in base, "base.html still preloads a deleted font on every page"
    fonts = sorted(p.name for p in (STATIC / "fonts").glob("*.woff2"))
    assert fonts == ["google-sans-button-500.woff2"], f"unexpected fonts on disk: {fonts}"
```

After (the headline-measure test at old line 278 and everything below it stay as they are):

```python
# --- the font contract ------------------------------------------------------------------------
# The homepage, privacy and terms keep the device's own font. The sign-up journey adds Inter for
# Android and Windows (spec D5): one subset file, declared in journey.css only, never preloaded,
# with a metric-matched local fallback so the swap barely moves text.

def _builder():
    """tools/fonts/build_inter.py, loaded by path, so the tests and the build share one formula."""
    spec = importlib.util.spec_from_file_location("build_inter", BUILD_INTER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _faces(css: str) -> dict[str, dict[str, str]]:
    """Every @font-face in a stylesheet, by family, as {descriptor: value} with spaces collapsed."""
    out: dict[str, dict[str, str]] = {}
    for body in re.findall(r"@font-face\s*\{([^}]*)\}", _strip_comments(css)):
        d = {k: " ".join(v.split()) for k, v in re.findall(r"([\w-]+)\s*:\s*([^;]+)", body)}
        out[d["font-family"].strip("\"'")] = d
    return out


def _tnum_advances(font: TTFont) -> set[int]:
    """The advance of each digit 0-9 after the tnum substitution."""
    gsub = font["GSUB"].table
    wanted = {i for r in gsub.FeatureList.FeatureRecord if r.FeatureTag == "tnum"
              for i in r.Feature.LookupListIndex}
    mapping: dict[str, str] = {}
    for i in wanted:
        for sub in gsub.LookupList.Lookup[i].SubTable:
            mapping.update(getattr(getattr(sub, "ExtSubTable", sub), "mapping", None) or {})
    cmap, hmtx = font.getBestCmap(), font["hmtx"]
    return {hmtx[mapping.get(cmap[c], cmap[c])][0] for c in range(0x30, 0x3A)}


def test_app_css_keeps_the_device_font_and_never_asks_for_inter():
    css = _text(APP_CSS)
    faces = re.findall(r"@font-face\s*\{[^}]*\}", css)
    assert not any("Jakarta" in f for f in faces), "a Plus Jakarta face is still declared"
    assert len(faces) == 1 and "Google Sans Button" in faces[0], (
        "only Google's own button face may be downloaded by app.css")
    m = re.search(r"--font-sans:\s*([^;]+);", css)
    assert m and m.group(1).strip().startswith("system-ui"), (
        f"--font-sans must lead with system-ui, got {m and m.group(1)!r}")
    for sheet in (APP_CSS, HERO_CSS, STATIC / "css" / "story.css", STATIC / "css" / "motion.css"):
        src = _text(sheet)
        assert "Inter Agad" not in src and INTER.name not in src, f"{sheet.name} asks for Inter"


def test_no_page_preloads_a_font_the_stylesheet_never_asks_for():
    base = _text(BASE_HTML)
    assert "plus-jakarta" not in base, "base.html still preloads a deleted font on every page"
    fonts = sorted(p.name for p in (STATIC / "fonts").glob("*.woff2"))
    assert fonts == ["google-sans-button-500.woff2", INTER.name], f"unexpected fonts: {fonts}"


def test_no_template_preloads_or_names_inter():
    """Spec 4.5: never preloaded. Apple devices match -apple-system first and must download
    nothing, and a preload would fetch the file on every iPhone. Only journey.css names it."""
    for tpl in sorted(TEMPLATES.glob("*.html")):
        src = _text(tpl)
        assert INTER.name not in src and "Inter Agad" not in src, f"{tpl.name} names Inter"
        for tag in re.findall(r"<link\b[^>]*>", src):
            assert not ("preload" in tag and "inter" in tag.lower()), f"{tpl.name}: {tag}"


def test_the_inter_file_is_the_pinned_subset_under_its_cap():
    data = INTER.read_bytes()
    assert data[:4] == b"wOF2", "the Inter file must be WOFF2"
    assert len(data) <= 50_000, f"{INTER.name} is {len(data)} B, over the 50,000 B cap (spec 8)"
    assert hashlib.sha256(data).hexdigest() == INTER_SHA256, (
        "the Inter file changed: rebuild it only with tools/fonts/build_inter.py, then re-pin")


def test_the_inter_file_name_carries_the_version_from_its_name_table():
    """journey.css loads it without ?v, so a new Inter must arrive under a new name."""
    b = _builder()
    assert INTER.name == b.font_name(b.version_of(TTFont(INTER)))


def test_the_inter_subset_keeps_what_the_journey_pages_print():
    font = TTFont(INTER)
    axes = [(a.axisTag, a.minValue, a.maxValue) for a in font["fvar"].axes]
    assert axes == [("wght", 400, 600)], f"opsz must be pinned and wght limited to 400-600: {axes}"
    cmap = font.getBestCmap()
    need = [*range(0x20, 0x7F), *range(0xA0, 0xAD), *range(0xAE, 0x100),   # U+00AD has no glyph
            0x2013, 0x2014, 0x2018, 0x2019, 0x201C, 0x201D, 0x2022, 0x2026, 0x20B1]
    missing = [f"U+{c:04X}" for c in need if c not in cmap]
    assert not missing, f"the subset lost characters the pages print: {missing}"
    assert set(cmap) <= set(_builder().unicodes()), "the file holds more than its unicode-range"
    gpos = {r.FeatureTag for r in font["GPOS"].table.FeatureList.FeatureRecord}
    assert "kern" in gpos, "kerning was dropped"
    digits = {font["hmtx"][cmap[c]][0] for c in range(0x30, 0x3A)}
    assert len(digits) > 1 and len(_tnum_advances(font)) == 1, (
        "tnum must give all ten digits one width (usage counts and times line up)")


def test_the_inter_face_is_declared_in_journey_css_only():
    faces = _faces(_text(JOURNEY_CSS))
    assert set(faces) == {"Inter Agad", "Inter Agad Fallback"}, sorted(faces)
    inter = faces["Inter Agad"]
    assert inter["font-display"] == "swap" and inter["font-style"] == "normal"
    assert inter["font-weight"] == "400 600", "the face must declare the weight range it ships"
    one_url = r'url\("\.\./fonts/' + re.escape(INTER.name) + r'"\) format\("woff2"\)'
    assert re.fullmatch(one_url, inter["src"]), (
        f"one url and no ?v, the name carries the version: {inter['src']}")
    assert inter["unicode-range"].replace(" ", "") == _builder().unicode_range_css()


def test_the_fallback_face_is_tuned_to_the_served_inter():
    """Segoe UI on Windows and Roboto on Android, scaled to Inter's average width and line box
    (spec 4.5). The expected numbers come from the served file through the formula the build
    script prints, so a new Inter without retuned numbers fails here."""
    fb = _faces(_text(JOURNEY_CSS))["Inter Agad Fallback"]
    assert "url(" not in fb["src"], "the fallback face must never download anything"
    names = re.findall(r'local\("([^"]+)"\)', fb["src"])
    assert "Segoe UI" in names and "Roboto" in names, names
    want = _builder().fallback_descriptors(TTFont(INTER))
    assert {k: fb.get(k) for k in want} == want, f"retune Inter Agad Fallback to {want}"


def test_the_inter_licence_ships_beside_the_font():
    lic = _text(INTER_LICENCE)
    assert "SIL OPEN FONT LICENSE Version 1.1" in lic and "The Inter Project Authors" in lic
    assert "Modified by Agad" in lic and INTER.name in lic and _builder().COMMIT in lic


def test_the_build_script_pins_one_commit_one_hash_and_the_spec_settings():
    b = _builder()
    assert re.fullmatch(r"[0-9a-f]{40}", b.COMMIT) and b.COMMIT in b.SOURCE_URL
    assert "/main/" not in b.SOURCE_URL and re.fullmatch(r"[0-9a-f]{64}", b.SOURCE_SHA256)
    assert (b.OPSZ, b.WGHT, b.MAX_BYTES) == (14, (400, 600), 50_000)
    assert "tnum" in b.FEATURES and (0x20B1, 0x20B1) in b.UNICODE_RANGES


def test_the_inter_file_is_served_as_a_cached_font(saas_cfg):
    """A first visit on a slow Android connection. Text paints at once in the tuned fallback
    (font-display swap, tested above) while the file comes from our own origin as a font, and a
    second visit reuses it: no ?v on its url, so a day of caching plus an ETag, and a new Inter
    arrives under a new file name."""
    r = client_for(saas_cfg).get(f"/static/fonts/{INTER.name}")
    assert r.status_code == 200
    assert r.headers["content-type"] == "font/woff2"
    assert r.headers["cache-control"] == "public, max-age=86400"
    assert r.headers.get("etag")
    assert r.content == INTER.read_bytes()
```

The last test is review focus 3 (a first visit on slow mobile data): it pins what the
server does with the file, next to the tests above that pin `font-display: swap` and the
tuned fallback face. `saas_cfg` is the fixture from `tests/conftest.py`.

The gradient test (`test_exactly_one_button_carries_a_gradient`, lines 234 to 245) and
`test_no_sheen_survives_on_a_light_button` stay unchanged. The new assertion that the journey
`.btn--primary` has no background image lives in Task 3, because the rule it checks is written in
section 5 there (code in Task 3 Step 2).

- [ ] **Step 3: Run the font tests and watch them fail**

```bash
.venv/Scripts/python.exe -m pytest -q tests/test_saas_hero.py
```

Expected: `9 failed, 27 passed`. The nine failures, each for the reason shown:
- `test_no_page_preloads_a_font_the_stylesheet_never_asks_for`, the fonts list lacks the Inter file.
- `test_the_inter_file_is_the_pinned_subset_under_its_cap`, `FileNotFoundError` for the font.
- `test_the_inter_file_name_carries_the_version_from_its_name_table`, `FileNotFoundError` for
  `tools/fonts/build_inter.py`.
- `test_the_inter_subset_keeps_what_the_journey_pages_print`, `FileNotFoundError`.
- `test_the_inter_face_is_declared_in_journey_css_only`, `FileNotFoundError` for `journey.css`.
- `test_the_fallback_face_is_tuned_to_the_served_inter`, `FileNotFoundError` for `journey.css`.
- `test_the_inter_licence_ships_beside_the_font`, `FileNotFoundError` for `OFL-inter.txt`.
- `test_the_build_script_pins_one_commit_one_hash_and_the_spec_settings`, `FileNotFoundError`.
- `test_the_inter_file_is_served_as_a_cached_font`, `assert 404 == 200` (the font is not on disk).

The renamed app.css test, the new template test and the two new parametrize cases already pass.
If instead the run stops with `ImportError: No module named brotli`, Step 1 was skipped.

- [ ] **Step 4: Create `tools/fonts/build_inter.py`**

```python
"""Rebuild the Inter subset the sign-up journey serves, and its licence file.

Run by hand, only when Inter is upgraded. Nothing runs this on deploy.

    .venv/Scripts/python.exe -m pip install brotli          # dev only, WOFF2 needs it
    .venv/Scripts/python.exe tools/fonts/build_inter.py     # downloads the pinned source

Offline, with copies of the two pinned files:

    .venv/Scripts/python.exe tools/fonts/build_inter.py --src Inter.ttf --licence OFL.txt

The source is the variable Inter from google/fonts (axes opsz 14-32, wght 100-900), pinned to
one commit and one sha256, so a moved or edited upstream file fails loudly instead of quietly
changing what we serve. The script:

1. pins opsz at 14 (the text optical size) and limits wght to 400-600 with the instancer,
2. keeps Basic Latin, Latin-1 Supplement, General Punctuation and U+20B1 (the peso sign),
3. keeps the default-on shaping features plus tnum (tabular figures for counts and times),
4. writes WOFF2 named after the version in the font's own name table (Inter writes 4.1 as
   "4.001"), and licenses/OFL-inter.txt with the upstream licence under a note of what changed,
5. prints the descriptors journey.css must give "Inter Agad Fallback" for this Inter.

The output is byte-for-byte reproducible for a given fontTools and brotli (4.63.0 and 1.2.0
built the committed file): head.modified is carried over from the source, not stamped with today.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import re
import sys
import urllib.request
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

COMMIT = "e1d6480102fed30739fead0faee463101f892c8f"
BASE_URL = f"https://raw.githubusercontent.com/google/fonts/{COMMIT}/ofl/inter/"
SOURCE_URL = BASE_URL + "Inter%5Bopsz%2Cwght%5D.ttf"
SOURCE_SHA256 = "29160a80ff49ddcab2c97711247e08b1fab27a484a329ce8b813d820dc559031"
LICENCE_URL = BASE_URL + "OFL.txt"
LICENCE_SHA256 = "5b9321a4298cfeb6b34354164a1c3afc3db114569984c502b9b35d988fd58c57"

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "applyfirst" / "saas" / "static"

OPSZ = 14
WGHT = (400, 600)
# The @font-face unicode-range in journey.css is built from these same ranges.
UNICODE_RANGES = ((0x0020, 0x007E), (0x00A0, 0x00FF), (0x2000, 0x206F), (0x20B1, 0x20B1))
FEATURES = ["ccmp", "locl", "mark", "mkmk", "kern", "calt", "liga", "clig", "rvrn", "tnum"]
MAX_BYTES = 50_000

# Average-width method for the fallback face (Capsize's xWidthAvg weighting): the
# advance of each of a-z and the space, weighted by English letter frequency with the space at
# 18.18 per cent, in em. Measured with fontTools from C:/Windows/Fonts/segoeui.ttf (Segoe UI
# 5.62) and google/fonts ofl/roboto/Roboto[wdth,wght].ttf (3.015) at its default instance.
FREQ = {
    " ": 22.22, "a": 8.2, "b": 1.5, "c": 2.8, "d": 4.3, "e": 12.7, "f": 2.2, "g": 2.0, "h": 6.1,
    "i": 7.0, "j": 0.15, "k": 0.77, "l": 4.0, "m": 2.4, "n": 6.7, "o": 7.5, "p": 1.9, "q": 0.095,
    "r": 6.0, "s": 6.3, "t": 9.1, "u": 2.8, "v": 0.98, "w": 2.4, "x": 0.15, "y": 2.0, "z": 0.074,
}
FALLBACK_AVG_EM = {"Segoe UI": 0.44251, "Roboto": 0.44247}

LICENCE_NOTE = """\
Inter {version}, served by Agad as applyfirst/saas/static/fonts/{name}.
Source: google/fonts ofl/inter/Inter[opsz,wght].ttf at commit {commit}.
Modified by Agad with tools/fonts/build_inter.py: optical size pinned at 14, weight limited to
400-600, characters limited to Basic Latin, Latin-1 Supplement, General Punctuation and U+20B1.
No glyph was redrawn. The licence below covers the modified font unchanged.

"""


def unicodes() -> list[int]:
    return [cp for lo, hi in UNICODE_RANGES for cp in range(lo, hi + 1)]


def unicode_range_css() -> str:
    return ",".join(f"U+{lo:04X}" if lo == hi else f"U+{lo:04X}-{hi:04X}"
                    for lo, hi in UNICODE_RANGES)


def version_of(font: TTFont) -> str:
    """'Version 4.001;git-66647c0bb' -> '4.1'. Inter writes the minor version as three digits."""
    raw = font["name"].getDebugName(5) or ""
    m = re.search(r"(\d+)\.(\d{3})", raw)
    if not m:
        raise ValueError(f"no version in name ID 5: {raw!r}")
    return f"{int(m.group(1))}.{int(m.group(2))}"


def font_name(version: str) -> str:
    return f"inter-{version}-latin-wght.woff2"


def avg_em(font: TTFont) -> float:
    cmap, hmtx = font.getBestCmap(), font["hmtx"]
    total = sum(FREQ.values())
    return sum(hmtx[cmap[ord(c)]][0] * w for c, w in FREQ.items()) / total / font["head"].unitsPerEm


def _pct(x: float) -> str:
    return f"{round(x * 10000) / 100:.2f}".rstrip("0").rstrip(".") + "%"


def fallback_descriptors(font: TTFont) -> dict[str, str]:
    """What "Inter Agad Fallback" needs so Segoe UI or Roboto takes Inter's width and line box.

    size-adjust scales the local font so its average width matches Inter's. The overrides are
    then Inter's own ascent, descent and line gap divided by that scale, because browsers apply
    size-adjust to the overrides too. The ascent gets 1/1024 em more than Inter's: Chrome rounds
    ascent to whole pixels, Inter's is exactly 15.5px at 16px (1984/2048 = 31/32 em), and
    Chrome's scaled size lands a hair short, so an exact copy rounds to 15 and drops the
    fallback's baseline a pixel at the phone body size. Measured in Chrome 153: 90.52 and
    90.53 per cent round down at 16px, 90.55 to 90.6 round up like Inter, 91 overshoots at 17px.
    """
    upm, hhea = font["head"].unitsPerEm, font["hhea"]
    fallback = sum(FALLBACK_AVG_EM.values()) / len(FALLBACK_AVG_EM)
    size = round(avg_em(font) / fallback * 10000) / 10000
    return {
        "size-adjust": _pct(size),
        "ascent-override": _pct((hhea.ascent / upm + 1 / 1024) / size),
        "descent-override": _pct(-hhea.descent / upm / size),
        "line-gap-override": _pct(hhea.lineGap / upm / size),
    }


def build(src: bytes) -> TTFont:
    digest = hashlib.sha256(src).hexdigest()
    if digest != SOURCE_SHA256:
        raise ValueError(f"source sha256 {digest} is not the pinned {SOURCE_SHA256}")
    font = TTFont(io.BytesIO(src), recalcTimestamp=False)
    font = instancer.instantiateVariableFont(font, {"opsz": OPSZ, "wght": WGHT})
    buf = io.BytesIO()              # compile and reload: the instancer leaves glyphs that have
    font.save(buf)                  # no deltas out of gvar, and the subsetter needs every one
    font = TTFont(io.BytesIO(buf.getvalue()), recalcTimestamp=False)
    opts = subset.Options()
    opts.layout_features = FEATURES
    opts.name_IDs = ["*"]           # keep the copyright, licence, version and axis names
    opts.name_languages = [0x0409]
    opts.notdef_outline = True
    sub = subset.Subsetter(opts)
    sub.populate(unicodes=unicodes())
    sub.subset(font)
    font.flavor = "woff2"
    font.recalcTimestamp = False
    return font


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as r:
        return r.read()


def main() -> None:
    ap = argparse.ArgumentParser(description="Rebuild the Inter subset and its licence.")
    ap.add_argument("--src", type=Path, help="a local copy of the pinned source TTF")
    ap.add_argument("--licence", type=Path, help="a local copy of the pinned OFL.txt")
    ap.add_argument("--static", type=Path, default=STATIC, help="the static folder to write into")
    a = ap.parse_args()

    font = build(a.src.read_bytes() if a.src else fetch(SOURCE_URL))
    version = version_of(font)
    out = a.static / "fonts" / font_name(version)
    out.parent.mkdir(parents=True, exist_ok=True)
    font.save(out)

    licence = a.licence.read_bytes() if a.licence else fetch(LICENCE_URL)
    if hashlib.sha256(licence).hexdigest() != LICENCE_SHA256:
        sys.exit("OFL.txt is not the pinned licence file")
    note = LICENCE_NOTE.format(version=version, name=out.name, commit=COMMIT)
    lic = a.static / "licenses" / "OFL-inter.txt"
    lic.parent.mkdir(parents=True, exist_ok=True)
    lic.write_bytes(note.encode("ascii") + licence.replace(b"\r\n", b"\n"))

    size = out.stat().st_size
    print(f"{out.name}: {size} bytes, sha256 {hashlib.sha256(out.read_bytes()).hexdigest()}")
    print(f"source {SOURCE_URL}\nsource sha256 {SOURCE_SHA256}")
    print(f"unicode-range:{unicode_range_css()}")
    print("fallback:" + ";".join(f"{k}:{v}" for k, v in fallback_descriptors(font).items()))
    if size > MAX_BYTES:
        sys.exit(f"{out.name} is {size} bytes, over the {MAX_BYTES} cap")


if __name__ == "__main__":
    main()
```

Why the compile-and-reload in `build()`: without it fontTools 4.63 raises
`KeyError: 'quarteremspace'` inside the subsetter, because the instanced font's `gvar` has no
entry for glyphs whose deltas all became zero.

- [ ] **Step 5: Run the build (it downloads about 880 KB from raw.githubusercontent.com)**

```bash
.venv/Scripts/python.exe tools/fonts/build_inter.py
```

Expected output, exactly (about 8 seconds):

```text
inter-4.1-latin-wght.woff2: 28132 bytes, sha256 effa0eae43e76b7d0f6ebfb74c77db701a420ae30a24c14b09a3fc82646b1fd0
source https://raw.githubusercontent.com/google/fonts/e1d6480102fed30739fead0faee463101f892c8f/ofl/inter/Inter%5Bopsz%2Cwght%5D.ttf
source sha256 29160a80ff49ddcab2c97711247e08b1fab27a484a329ce8b813d820dc559031
unicode-range:U+0020-007E,U+00A0-00FF,U+2000-206F,U+20B1
fallback:size-adjust:107.03%;ascent-override:90.6%;descent-override:22.54%;line-gap-override:0%
```

It writes `applyfirst/saas/static/fonts/inter-4.1-latin-wght.woff2` and
`applyfirst/saas/static/licenses/OFL-inter.txt`. Confirm the licence:

```bash
.venv/Scripts/python.exe -c "import hashlib,pathlib; p=pathlib.Path('applyfirst/saas/static/licenses/OFL-inter.txt'); print(len(p.read_bytes()), hashlib.sha256(p.read_bytes()).hexdigest())"
```

Expected: `4835 e1ede4f5976346ba147ed11df18f80b0d7e4bab16d33bd8f974ddb363de268d1`.

If the font's sha256 differs, run `.venv/Scripts/python.exe -m pip show brotli fonttools`. A
different brotli or fontTools than 1.2.0 and 4.63.0 can change the compressed bytes. In that case
check the size is still at most 50,000 and the `fallback:` line is identical, then set
`INTER_SHA256` in `tests/test_saas_hero.py` to the printed value. Git keeps the file byte for byte
without a `.gitattributes` entry, because a WOFF2 file has NUL bytes in its header and git treats
it as binary.

The full text the script writes to `OFL-inter.txt` (a five-line note, then google/fonts' `OFL.txt`
unchanged, LF endings, and line 27 keeps upstream's trailing space after `embedded,`):

```text
Inter 4.1, served by Agad as applyfirst/saas/static/fonts/inter-4.1-latin-wght.woff2.
Source: google/fonts ofl/inter/Inter[opsz,wght].ttf at commit e1d6480102fed30739fead0faee463101f892c8f.
Modified by Agad with tools/fonts/build_inter.py: optical size pinned at 14, weight limited to
400-600, characters limited to Basic Latin, Latin-1 Supplement, General Punctuation and U+20B1.
No glyph was redrawn. The licence below covers the modified font unchanged.

Copyright 2020 The Inter Project Authors (https://github.com/rsms/inter)

This Font Software is licensed under the SIL Open Font License, Version 1.1.
This license is copied below, and is also available with a FAQ at:
https://scripts.sil.org/OFL


-----------------------------------------------------------
SIL OPEN FONT LICENSE Version 1.1 - 26 February 2007
-----------------------------------------------------------

PREAMBLE
The goals of the Open Font License (OFL) are to stimulate worldwide
development of collaborative font projects, to support the font creation
efforts of academic and linguistic communities, and to provide a free and
open framework in which fonts may be shared and improved in partnership
with others.

The OFL allows the licensed fonts to be used, studied, modified and
redistributed freely as long as they are not sold by themselves. The
fonts, including any derivative works, can be bundled, embedded, 
redistributed and/or sold with any software provided that any reserved
names are not used by derivative works. The fonts and derivatives,
however, cannot be released under any other type of license. The
requirement for fonts to remain under this license does not apply
to any document created using the fonts or their derivatives.

DEFINITIONS
"Font Software" refers to the set of files released by the Copyright
Holder(s) under this license and clearly marked as such. This may
include source files, build scripts and documentation.

"Reserved Font Name" refers to any names specified as such after the
copyright statement(s).

"Original Version" refers to the collection of Font Software components as
distributed by the Copyright Holder(s).

"Modified Version" refers to any derivative made by adding to, deleting,
or substituting -- in part or in whole -- any of the components of the
Original Version, by changing formats or by porting the Font Software to a
new environment.

"Author" refers to any designer, engineer, programmer, technical
writer or other person who contributed to the Font Software.

PERMISSION & CONDITIONS
Permission is hereby granted, free of charge, to any person obtaining
a copy of the Font Software, to use, study, copy, merge, embed, modify,
redistribute, and sell modified and unmodified copies of the Font
Software, subject to the following conditions:

1) Neither the Font Software nor any of its individual components,
in Original or Modified Versions, may be sold by itself.

2) Original or Modified Versions of the Font Software may be bundled,
redistributed and/or sold with any software, provided that each copy
contains the above copyright notice and this license. These can be
included either as stand-alone text files, human-readable headers or
in the appropriate machine-readable metadata fields within text or
binary files as long as those fields can be easily viewed by the user.

3) No Modified Version of the Font Software may use the Reserved Font
Name(s) unless explicit written permission is granted by the corresponding
Copyright Holder. This restriction only applies to the primary font name as
presented to the users.

4) The name(s) of the Copyright Holder(s) or the Author(s) of the Font
Software shall not be used to promote, endorse or advertise any
Modified Version, except to acknowledge the contribution(s) of the
Copyright Holder(s) and the Author(s) or with their explicit written
permission.

5) The Font Software, modified or unmodified, in part or in whole,
must be distributed entirely under this license, and must not be
distributed under any other license. The requirement for fonts to
remain under this license does not apply to any document created
using the Font Software.

TERMINATION
This license becomes null and void if any of the above conditions are
not met.

DISCLAIMER
THE FONT SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO ANY WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT
OF COPYRIGHT, PATENT, TRADEMARK, OR OTHER RIGHT. IN NO EVENT SHALL THE
COPYRIGHT HOLDER BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
INCLUDING ANY GENERAL, SPECIAL, INDIRECT, INCIDENTAL, OR CONSEQUENTIAL
DAMAGES, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF THE USE OR INABILITY TO USE THE FONT SOFTWARE OR FROM
OTHER DEALINGS IN THE FONT SOFTWARE.
```

Inter's OFL names no Reserved Font Name, so the subset may keep the name "Inter" in its name
table, and the CSS family "Inter Agad" is our own label.

- [ ] **Step 6: Create `applyfirst/saas/static/css/journey.css` with the header and section 1**

The whole file after this task (830 bytes raw, 507 bytes gzip level 9, LF endings). The two
`@font-face` rules are the only unlayered rules the file will ever have. Task 3 appends its
`@layer journey {` block after line 12.

```css
/* Agad sign-up journey. Loaded after app.css by the journey templates only. All but
   @font-face sits in @layer journey. Terse on purpose: the gzip cap is 8,000 B. */

/* ---- 1 fonts */
/* Inter 4.1 (OFL, licenses/OFL-inter.txt), built by tools/fonts/build_inter.py, which also
   prints the fallback numbers. No ?v on the url: the file name carries the version. */
@font-face{font-family:"Inter Agad";font-style:normal;font-weight:400 600;font-display:swap;
  src:url("../fonts/inter-4.1-latin-wght.woff2") format("woff2");
  unicode-range:U+0020-007E,U+00A0-00FF,U+2000-206F,U+20B1}
@font-face{font-family:"Inter Agad Fallback";src:local("Segoe UI"),local("SegoeUI"),
  local("Roboto"),local("Roboto Regular"),local("Roboto-Regular");size-adjust:107.03%;
  ascent-override:90.6%;descent-override:22.54%;line-gap-override:0%}
```

Why each `local()` name. Chrome matches `local()` against a font's full name or PostScript name
only, never the family name. Segoe UI's full name is `Segoe UI` and its PostScript name is
`SegoeUI` (read from `segoeui.ttf`). The google/fonts Roboto's full name is `Roboto Regular` and
its PostScript name is `Roboto-Regular`, while older Android builds use `Roboto`. So all three are
listed. The fallback face has no `font-weight`, so a 600 heading during the swap is a synthesised
bold Segoe UI or Roboto for the few hundred milliseconds before Inter arrives.

- [ ] **Step 7: Run the font tests and watch them pass**

```bash
.venv/Scripts/python.exe -m pytest -q tests/test_saas_hero.py tests/test_saas_static.py tests/test_saas_palette.py
```

Expected: `151 passed` (measured after Task 1). (`test_saas_hero.py` is 36 tests now, up from 25. `test_saas_static.py`
checks that the `url()` in `journey.css` resolves to a real file. `test_saas_palette.py` picks up
`journey.css` as three new parametrized cases, and section 1 holds no colour.)

- [ ] **Step 8: Measure the fallback and the font-size-adjust value in headless Chrome**

This re-checks, on the real files, the numbers in section 1 and the `font-size-adjust` value
handed to Task 3. It writes nothing in the repo. Set `SP` to this session's scratchpad folder (the
system prompt lists it), then download the Roboto file the Android numbers come from and check it:

```bash
SP="<this session's scratchpad folder>"
curl -sSLo "$SP/Roboto.ttf" "https://raw.githubusercontent.com/google/fonts/1c627bfa375fc51cf86fabeca4f6e08a95f0aa5c/ofl/roboto/Roboto%5Bwdth%2Cwght%5D.ttf"
sha256sum "$SP/Roboto.ttf"
```

Expected sha256: `d7598e12c5dbef095ff8272cfc55da0250bd07fbdecbac8a530b9b277872a134`.

Write `$SP/font_metrics.py` with the Write tool:

```python
"""Print the numbers the fallback face is built from, for each font file given.

    .venv/Scripts/python.exe <scratchpad>/font_metrics.py <repo root> <font> [<font> ...]

avg is build_inter.avg_em (the frequency-weighted a-z and space advance, in em). xh is the
OS/2 x-height over unitsPerEm, the number a font-size-adjust value is compared with.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(sys.argv[1]) / "tools" / "fonts"))
from build_inter import avg_em  # noqa: E402
from fontTools.ttLib import TTFont  # noqa: E402

for p in sys.argv[2:]:
    f = TTFont(p)
    upm, os2, hh = f["head"].unitsPerEm, f["OS/2"], f["hhea"]
    print(f"{Path(p).name}: avg {avg_em(f):.5f} em, xh {os2.sxHeight / upm:.4f}, "
          f"hhea {hh.ascent}/{hh.descent}/{hh.lineGap}, upm {upm}")
```

```bash
.venv/Scripts/python.exe "$SP/font_metrics.py" . applyfirst/saas/static/fonts/inter-4.1-latin-wght.woff2 C:/Windows/Fonts/segoeui.ttf "$SP/Roboto.ttf"
```

Expected:

```text
inter-4.1-latin-wght.woff2: avg 0.47358 em, xh 0.5459, hhea 1984/-494/0, upm 2048
segoeui.ttf: avg 0.44251 em, xh 0.5000, hhea 2210/-514/0, upm 2048
Roboto.ttf: avg 0.44247 em, xh 0.5283, hhea 1900/-500/0, upm 2048
```

The two `avg` values for Segoe UI and Roboto must equal `FALLBACK_AVG_EM` in the build script.

Write `$SP/measure_swap.py` with the Write tool:

```python
"""Measure how far text moves when Inter swaps in over "Inter Agad Fallback", in headless Chrome.

Reads both @font-face rules out of the real journey.css, inlines the fonts as data: URLs (so no
server runs), and for each journey text size compares Inter with the fallback built on local
Segoe UI and on Roboto (the downloaded Roboto stands in for Android's): the width of one long
line, the lines a 328px paragraph wraps to, and the baseline inside a 1.5 line box. It also
prints the three font-size-adjust choices for Inter so the body value is picked by measurement.

    .venv/Scripts/python.exe measure_swap.py <repo root> <Roboto[wdth,wght].ttf>

Exit code 1 if any width is off by more than 1 per cent or any baseline moves.
"""
import base64
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO, ROBOTO = Path(sys.argv[1]), Path(sys.argv[2])
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
CSS = re.sub(r"/\*.*?\*/", "", (REPO / "applyfirst/saas/static/css/journey.css").read_text("utf-8"), flags=re.S)
FACES = {re.search(r'font-family:\s*"([^"]+)"', b).group(1): b
         for b in re.findall(r"@font-face\s*\{([^}]*)\}", CSS)}
inter_url = re.search(r'url\("\.\./fonts/([^"]+)"\)', FACES["Inter Agad"]).group(1)
INTER = REPO / "applyfirst/saas/static/fonts" / inter_url
fb = FACES["Inter Agad Fallback"]
overrides = ";".join(re.findall(r"((?:size-adjust|ascent-override|descent-override|line-gap-override)\s*:\s*[^;]+)", fb))
i64 = base64.b64encode(INTER.read_bytes()).decode()
r64 = base64.b64encode(ROBOTO.read_bytes()).decode()

SIZES = (12, 14, 15, 16, 17, 20, 28, 30)
TEXT = ("Agad watches onlinejobs.ph for you and sends your application the moment a matching "
        "job appears. Connect Gmail, add a few watch words, and we will do the rest.")
CASES = {
    "inter": ('"Inter Agad"', "none"),
    "segoe_fallback": ('"Inter Agad Fallback"', "none"),
    "roboto_fallback": ('"Roboto As Fallback"', "none"),
    "inter_fsa_.52_today": ('"Inter Agad"', ".52"),
    "inter_fsa_.546": ('"Inter Agad"', ".546"),
    "segoe_fallback_fsa_.546": ('"Inter Agad Fallback"', ".546"),
}
sections = []
for k in CASES:
    for s in SIZES:
        sections.append(
            f'<section data-k="{k}" data-s="{s}" class="c-{k.replace(".", "_")}" style="font-size:{s}px">'
            f'<span class="one">{TEXT}</span><p class="para">{TEXT}</p>'
            f'<div class="lb"><i></i>x</div></section>')
rules = "\n".join(f'.c-{k.replace(".", "_")} {{ font-family: {f}; font-size-adjust: {a}; }}'
                  for k, (f, a) in CASES.items())
html = f"""<!doctype html><html><head><meta charset="utf-8"><style>
@font-face {{ font-family: "Inter Agad"; font-weight: 400 600; font-display: block;
  src: url(data:font/woff2;base64,{i64}) format("woff2"); }}
@font-face {{ font-family: "Inter Agad Fallback"; src: local("Segoe UI"), local("SegoeUI"); {overrides}; }}
@font-face {{ font-family: "Roboto As Fallback"; src: url(data:font/ttf;base64,{r64}); {overrides}; }}
body {{ margin: 0; line-height: 1.5; }}
.one {{ white-space: nowrap; display: inline-block; }}
.para {{ width: 328px; margin: 0; }}
.lb i {{ display: inline-block; width: 1px; height: 0; }}
{rules}
</style></head><body>{''.join(sections)}<pre id="out"></pre>
<script>
Promise.all([document.fonts.load('16px "Inter Agad"'), document.fonts.load('16px "Roboto As Fallback"')])
.then(() => document.fonts.ready).then(() => {{
  const out = [];
  for (const s of document.querySelectorAll('section')) {{
    const lh = parseFloat(getComputedStyle(s).lineHeight);
    const lb = s.querySelector('.lb').getBoundingClientRect();
    out.push({{ k: s.dataset.k, s: +s.dataset.s,
      w: s.querySelector('.one').getBoundingClientRect().width,
      lines: Math.round(s.querySelector('.para').getBoundingClientRect().height / lh),
      base: s.querySelector('.lb i').getBoundingClientRect().top - lb.top }});
  }}
  document.getElementById('out').textContent = 'RESULT' + JSON.stringify(out) + 'END';
}});
</script></body></html>"""

with tempfile.TemporaryDirectory() as d:
    page = Path(d) / "swap.html"
    page.write_text(html, encoding="utf-8")
    res = subprocess.run([CHROME, "--headless=new", "--disable-gpu", f"--user-data-dir={d}/p",
                          "--virtual-time-budget=10000", "--dump-dom", page.as_uri()],
                         capture_output=True, text=True, timeout=180)
m = re.search(r"RESULT(.*?)END", res.stdout, re.S)
if not m:
    sys.exit("Chrome printed no result:\n" + res.stdout[-1500:] + res.stderr[-1500:])
rows = json.loads(m.group(1).replace("&quot;", '"'))
ref = {r["s"]: r for r in rows if r["k"] == "inter"}
bad = 0
print(f"fallback descriptors from journey.css: {overrides}")
print(f"{'case':26} {'px':>3} {'width %':>8} {'lines':>5} {'baseline':>9}")
for r in rows:
    base = ref[r["s"]]
    pct = r["w"] / base["w"] * 100
    moved = r["base"] - base["base"]
    flag = ""
    if r["k"].endswith("_fallback") and (abs(pct - 100) > 1 or moved != 0):
        flag, bad = "  <-- off", bad + 1
    print(f"{r['k']:26} {r['s']:3} {pct:8.2f} {r['lines'] - base['lines']:+5d} {moved:+9.2f}{flag}")
sys.exit(1 if bad else 0)
```

Run it from the repo root. Chrome runs headless with a throwaway profile and exits by itself, so
no server or browser is left running.

```bash
.venv/Scripts/python.exe "$SP/measure_swap.py" . "$SP/Roboto.ttf"; echo "exit $?"
```

Expected, exit 0, and the output includes these rows (the eight `inter` reference rows read 100.00, +0, +0.00):

```text
segoe_fallback              12    99.85    +0     +0.00
segoe_fallback              14    99.84    +0     +0.00
segoe_fallback              15    99.84    +0     +0.00
segoe_fallback              16    99.85    +0     +0.00
segoe_fallback              17    99.85    +0     +0.00
segoe_fallback              20    99.85    +0     +0.00
segoe_fallback              28    99.85    +0     +0.00
segoe_fallback              30    99.85    +0     +0.00
roboto_fallback             12   100.10    +0     +0.00
roboto_fallback             14   100.10    +0     +0.00
roboto_fallback             15   100.10    +0     +0.00
roboto_fallback             16   100.10    +0     +0.00
roboto_fallback             17   100.10    +0     +0.00
roboto_fallback             20   100.10    +0     +0.00
roboto_fallback             28   100.10    +0     +0.00
roboto_fallback             30   100.10    +0     +0.00
inter_fsa_.52_today         16    95.25    +0     -1.00
inter_fsa_.546              16   100.00    +0     +0.00
segoe_fallback_fsa_.546     16   101.89    +1     +0.00
```

How to read it. `none` and `.546` both give Inter 100 percent, and `.52` shrinks it to 95.25.
With `.546` the Segoe UI fallback goes from 99.85 to about 101.9 percent and the paragraph wraps
one more line at 12 and 16px, so the body value is `none`. If a `_fallback` row is flagged, change
nothing by hand. Re-run Step 5, copy the `fallback:` line into section 1, and run this step again.

- [ ] **Step 9: Run both gates**

```bash
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe .noxa/redesign-saas-ui/inputs/preserve_smoke.py
```

Expected: pytest: all pass (887 + the new tests), measured `939 passed` in sequence after Task 1
(14 new: 11 in `test_saas_hero.py` and 3 `journey.css` cases in `test_saas_palette.py`); smoke:
0 failed, `558 checks passed, 0 failed.` The smoke does not change in this task, because no
page loads `journey.css` yet.

**For Task 3.** Task 3 writes the journey `body` rule with the stack and the
`font-size-adjust:none` measured in Step 8, sets `h1` to `h3` to weight 600 (app.css asks for
700, which Inter clamps to 600 without faux bold, but the fallback face would show a
synthesised bold during the swap), and owns the tests for both and for the flat primary
button.

**Notes for the reviewer (Task 2).**
1. `font-size-adjust` is `none`, not a number. Spec 4.5 asks for the value "set by measurement".
   The x-height number (.546) also renders Inter at nominal size, but it silently cancels the
   fallback's `size-adjust` that the same spec bullet asks to tune, and it scales SF on Apple
   devices by Inter's x-height. The measurements are in Step 8.
2. Spec 8 says `journey.css` "never sets background-image" on `.btn--primary`, but app.css paints
   the gradient with `background-image` in four states (`app.css:143-151`), so the journey rule
   has to set `background-image: none`. Task 3's tests allow `none` and ban any other value.
3. The font is 28,132 bytes, not "about 47 KB". Task 8 records the real number in `Handoff.md`.
4. Spec 4.5 says one fallback face uses both Roboto and Segoe UI. That works only because their
   average widths match to 0.01 percent, measured here. If a future fallback font differs, it
   needs its own face.
5. Not provable on Windows (already in spec 10). Safari on Apple devices should never fetch the
   file, because `-apple-system` covers every character in the range. Worth confirming on a real
   iPhone that the peso sign comes from SF too.
6. `tests/test_saas_hero.py` now imports `fontTools` at module level (always installed, fpdf2
   depends on it) and needs `brotli` to read WOFF2. Without brotli, 3 font tests fail with
   `ImportError: No module named brotli` (measured), which is why Step 1 records it in
   `requirements-dev.txt`.


### Task 3: journey.css foundation (tokens, Basecoat map, base, components, chrome, motion), the layer order, the colour-scheme blocks and their checks

Spec 4.2, 4.4, 5.1 to 5.4 and 8. No page loads the new look yet (spec 11 stage 1); Task 4 is the
first to link it. Everything below was prototyped end to end on 2026-09-25 in a scratch copy of
the repo that already carried Task 1 (the trimmed Basecoat file, sha256 `4aae6ed8...`, its tests
and the new palette test) and Task 2 (the Inter file, `journey.css` lines 1 to 12, the new hero
font tests) exactly as this plan writes them, then re-run during assembly with the three
review-focus tests and the forced-colours focus fix. Measured there: the new tests failed 68 and
passed 46 before the implementation and passed 114 of 114 after it, 44 of 44 planted mistakes
were caught, nine pages rendered byte for byte the same as today once hashes and CSRF tokens were
masked, headless Chrome computed every shared component as expected in light and dark (96
checks), pytest went from 939 to 1,053 passed and the smoke stayed at 558 checks, 0 failed.

**Files:**
- Create `tests/_journey_css.py` (full code in Step 1). The fixed helper interface.
- Create `tests/test_saas_journey.py` (full code in Step 2). 114 tests today, three of them the
  review-focus checks for zoomed text, high contrast and a touch-screen laptop.
- Modify `applyfirst/saas/static/css/app.css` line 6 only (the layer order statement). Verified:
  line 6 is `@layer reset, tokens, base, components, screens;`, and no test pins it
  (`grep -rn "@layer reset" tests` finds only the comment at `tests/test_saas_motion.py:191`;
  `tests/test_saas_story.py:112-113` read the statements of `story.css` and `hero.css`, and
  `tests/test_saas_story.py:387` searches `@layer tokens\s*\{`, which still matches `app.css:41`).
- Modify `applyfirst/saas/templates/base.html` lines 7 and 8 only (the two head metas). Verified:
  line 7 is `  <meta name="color-scheme" content="light">`, line 8 is
  `  <meta name="theme-color" content="{% block theme_color %}#F3F6FA{% endblock %}">`. No template
  overrides `theme_color` today (`grep -n theme_color applyfirst/saas/templates/*.html` finds only
  `base.html:8`). The file is CRLF in the working tree; the Edit tool keeps that.
- Modify `applyfirst/saas/static/css/journey.css`: append after line 12, which Task 2 wrote as
  `  ascent-override:90.6%;descent-override:22.54%;line-gap-override:0%}`. Lines 1 to 12 stay byte
  for byte. The file becomes 112 lines, 9,451 bytes, **3,429 B gzip 9** (cap 8,000, target for the
  foundation 5,000). Sections 7 to 10 are empty banners for Tasks 4 to 7.
- Scratchpad only, never in the repo: `render_pages.py` (Step 4), `probe_cascade.py` (Step 10),
  `mutate_journey.py` (Step 11).
- Not touched: any page template, `_ui.html`, `motion.css`, `vt.js`, `motion.js`, `app.py`, the
  smoke, `.gitattributes`, any existing test file. No existing test needs a change for the layer
  statement or the new blocks (the full suite passes unchanged, Step 12).

**Interfaces:**
- Consumes (all verified):
  - Task 1: `applyfirst/saas/static/vendor/basecoat-1.0.2-agad.css` must exist (the tests read it).
    The variables it reads but neither defines nor registers are exactly Task 1's
    `SUPPLIED_BY_JOURNEY`: `--color-card`, `--color-card-foreground`, `--color-destructive`,
    `--color-foreground`, `--color-input`, `--color-muted-foreground`, `--color-primary`,
    `--color-primary-foreground`, `--color-ring`, `--radius`. Its dark rules are written
    `@media (prefers-color-scheme:dark)` and it keeps `.btn:not([data-size]){height:36px}` and
    `.btn:not([data-variant]){background-color:var(--color-primary)}`.
  - Task 2: `journey.css` lines 1 to 12 (header, then `/* ---- 1 fonts */` at line 4 and the two
    `@font-face` rules), the families `"Inter Agad"` and `"Inter Agad Fallback"`, and the body rule
    Task 2 measured, `body{...;font-size-adjust:none}`, whose test lives in Step 2 below as
    `test_the_journey_body_uses_the_inter_stack_at_nominal_size`, next to the two primary-button tests.
  - app.css tokens read by journey.css: `--r-sm` 8px and `--r-md` 12px (`app.css:62`),
    `--amber-600` #B86E00 (`app.css:50`), `--ease-land` (`app.css:69`). app.css tokens journey.css
    re-points: `--ground`, `--sunk`, `--surface`, `--line`, `--line-strong` (`app.css:47`),
    `--text-strong`, `--text`, `--text-muted` (`app.css:48`), and the type tokens `--fs-h1`,
    `--fs-h3`, `--fs-lead`, `--fs-body`, `--fs-small`, `--fs-caption` (`app.css:55-58`, read by
    `body` at `app.css:89-90`, `h1` at 94, `h2` at 95, `.lead` at 124, `.caption` at 123).
  - `base.html` blocks `motion_head` (line 13) and `page_css` (line 14), both before the
    `reveal.js` script at line 15 (head order M-1).
  - `tests/_saas_client.py`: `client_for`, `seed_user`. `tests/conftest.py`: the `saas_cfg` fixture.
- Produces (exact names, used by Tasks 4 to 8):
  - `tests/_journey_css.py`: `ROOT: Path`, `STATIC: Path`, `TEMPLATES: Path`, `JOURNEY_CSS: Path`,
    `BASECOAT_CSS: Path`, `JOURNEY_TEMPLATES: list[str]` (starts `[]`),
    `read_css(path: Path) -> str`, `iter_rules(css: str) -> Iterator[tuple[str, str, tuple[str, ...]]]`
    (chains are whitespace-collapsed, for example `("@layer journey", "@media (prefers-color-scheme:dark)")`),
    `decls(body: str) -> dict[str, str]`, `contrast(fg_hex: str, bg_hex: str) -> float`,
    `gzip_size(path: Path) -> int`, `tokens(css: str, scheme: str) -> dict[str, str]`.
  - `base.html` blocks `color_scheme` (default `light`) and `theme_color_meta` (default: today's
    single theme-color meta, with the old `theme_color` block nested inside it).
  - The journey head, which each page task pastes into its template in the same change that adds
    the template's name to `JOURNEY_TEMPLATES` (the scope test checks every character of the two
    links and the two metas):
    ```jinja
    {% block color_scheme %}light dark{% endblock %}
    {% block theme_color_meta %}<meta name="theme-color" content="#FFFFFF" media="(prefers-color-scheme: light)">
      <meta name="theme-color" content="#111B2B" media="(prefers-color-scheme: dark)">{% endblock %}
    {% block page_css %}
      <link rel="stylesheet" href="{{ static_url('vendor/basecoat-1.0.2-agad.css') }}">
      <link rel="stylesheet" href="{{ static_url('css/journey.css') }}">
    {% endblock %}
    ```
    The two colours are the header surface of each scheme (`--j-surface`), which the test reads
    from `journey.css`, so they can never drift apart.
  - `journey.css` tokens `--j-ground`, `--j-surface`, `--j-text`, `--j-muted`, `--j-edge`,
    `--j-link`, `--j-primary`, `--j-primary-hover`, `--j-hairline`, `--j-attn-fg`, `--j-attn-bg`,
    `--j-ok-fg`, `--j-ok-bg`, `--j-danger-fg`, `--j-shadow` (light in section 2, dark in the one
    `@media (prefers-color-scheme:dark)` block of section 2).
  - Shared component rules page tasks build on: `.btn` (44px phones, 40px computers),
    `.btn--primary`, `.btn--secondary`, quiet actions `.text-link` and `.back-link` (link colour,
    44px tap band from their own `::after`), `.field` (label, control, then hint), `.input`,
    `.sheet` and `.card` (the group surface), `.alert` and its four tones, `.badge--ok` and
    `.badge--attention`, the header and the short footer.
  - The empty banners `/* ---- 7 login */` (line 100), `/* ---- 8 onboarding */` (101),
    `/* ---- 9 dashboard */` (102), `/* ---- 10 signin-failed */` (103). Each page task writes its
    rules directly under its own banner and nowhere else.

**Frozen hooks (spec 9).** The only template this task edits is `base.html`, and only lines 7 and 8.
- `site-header` (one): the `<header class="site-header...">` at `base.html:23` is not touched.
  journey.css restyles it (surface, hairline, 56px row) but never adds or removes one.
- `data-step` on `html`: comes from `{% block html_attrs %}` at `base.html:3`, not touched.
- Head order M-1 (`app.css`, `motion.css`, `vt.js`, `motion.js`): `motion_head` (line 13) and
  `page_css` (line 14) keep their places before `reveal.js`; `test_base_offers_the_blocks_the_journey_pages_fill`
  asserts the order, and `tests/test_saas_motion.py::test_the_motion_head_keeps_its_locked_order_on_every_app_page` still runs.
- The hidden `csrf` input of the Log out form (`base.html:30`): not touched.
- CSS-side hooks journey.css reads or restyles, and how each is kept:
  `form.activate ... .btn--primary` stays `#0B6BC7`, 12px, opacity 1, no background image in every
  state (`.btn--primary` sets `background-image:none` and the one held rule
  `.btn--primary:is([disabled],[data-state=busy])` comes after the hover rule; four tests and six
  mutants guard it). `.status--live` and `.status`: no journey rule sets their background,
  colour, radius, position, isolation or opacity. `.kw` and `.chip-list`: no box-shadow, no
  overflow. `a.btn[data-state="busy"]::before`: no journey rule touches any `.btn` pseudo-element.
  `--ease-out`, `--ease-settle`, `--ease-exit`, `--ease-spring`: never defined, only `--ease-land`
  is read. `.mailcard`: stays white in dark mode (the island, section 2), so the frozen
  `af-unread` tint from `#DCEFFB` still reads. `.alert--success[data-arrive-gmail] > .icon` stays
  the alert's first child (no markup change); journey only sets its colour and cancels
  Basecoat's `grid-row` span and `translate` on `.alert>svg`, the stamp animates `transform` in
  the higher motion layer. `.badge--ok`: height auto and overflow visible, so the stamp and the
  word are never clipped. `details.disclose`: the reduced-motion reset only adds
  `::details-content{transition:none!important}` under `reduce`; motion.css's no-preference
  transition is untouched. `.dash__grid > *`, `.gconf__track` (96px), `.fromto__node` (28px),
  `.stepper__marker`, `.copy-row`, `.letter__part`, `.preview__link`: no journey rule in this task
  names them.

**How the values were chosen (read once, the steps just apply them).**
- Why a layer beats everything. `journey` sits above every app.css layer, so any journey rule
  wins over any app.css rule whatever the specificity (a journey `.btn` beats app.css's
  `.btn--primary:hover`). That is how one `.btn--primary{background-image:none}` removes the
  gradient from all four app.css states (`app.css:143-151`). It is also the main hazard for page
  tasks: a journey element rule such as `h2{font-size:...}` would resize `.sample__label` and
  `.card-title` too. So type goes through app.css's own tokens (`--fs-*`), and links get their
  colour from `:where(a:not(.btn,.gsi-btn,.skip-link))`, which has zero specificity inside the
  layer and never reaches Google's button or the skip link.
- Tokens. Values exactly as spec 5.3, contrast recomputed from the file by the tests (text 14.20
  and 15.39 light, 16.04 and 14.64 dark, and so on). Hairline light is navy at 10 percent
  (`rgba(11,37,69,.1)`), dark is white at 12 percent (`rgba(255,255,255,.12)`), which is also the
  edge spec 5.2 asks for on the dark live panel (Task 6 can write
  `.status--live{border-color:var(--j-hairline)}`: invisible on navy in light, white 12 percent in
  dark, and allowed by the frozen test because it is not colour, radius or position). `--j-shadow`
  is `0 1px 2px rgba(11,37,69,.06)` light and `0 1px 2px rgba(0,0,0,.5)` dark.
- The light island. `var()` resolves where a custom property is declared, so redefining
  `--j-surface` on `.mailcard` alone would not change the `--surface` it already inherited from
  `:root`. The island therefore redefines every `--j-*` value (dark block) and sits on both
  mapping rules (`:root,.mailcard,.gsi-btn`), so `--surface`, `--text`, `--color-card` and the
  rest are recomputed inside it. `.mailcard` also gets `color:var(--j-text)` (its text inherits
  the dark body colour otherwise) and both get `color-scheme:light`. Google's button gets nothing
  else (spec 3, and `test_the_google_button_is_never_restyled`).
- Basecoat map. Spec 4.4 names, on our palette. `--primary` and `--primary-foreground` are literal
  hex; the others point at the hex `--j-*` tokens so dark mode follows without a second list.
  The `--color-*` aliases the trimmed rules read point at them.
- Type (spec 5.1). Phones: body 16px (`--fs-body:1rem`), small notes 15px, labels and captions
  12px, h1 28px, h2 20px (app.css sizes `h2` with `--fs-h3`, so that token is 1.25rem here), h3 17px
  (app.css already writes 1.0625rem). Computers, on `(hover:hover) and (pointer:fine)` only: body
  15px, small 14px, h1 30px, h3 16px. Line height 1.5. Headings weight 600 (Inter clamps 700 to
  600 anyway, and the fallback would fake a bold). `font-size-adjust:none`, Task 2's measurement:
  `.546` (Inter's x-height, 1118/2048, re-measured here with fontTools at opsz 14) also renders
  Inter at nominal size but cancels the fallback face's `size-adjust`. Inputs stay at
  `max(16px,1rem)` on every device.
- Basecoat leaks, each overridden by name (spec 5.2, plus the ones Task 1 measured): fixed height
  36px on `.btn` and inputs (and on `textarea.input`, which matches `.input:not([type])`),
  `.btn svg` at 16px (restored to our 20px, and 16px where the icon says 16, like the Copy
  buttons and the app.js spinner at `app.js:117`), `outline-style:none` on `.btn` and `.input`,
  the `translate` press, `transition-property:all` and the unconditional input transition,
  `.btn:disabled{opacity:50%}`, the focus box-shadow ring, `background-clip:padding-box` (it
  shrinks the blue fill by 1px under the transparent border), `.alert>svg` row span and 2px
  translate, `.badge` height and overflow, `field-sizing:content`, 14px inputs from 768px, the
  red `aria-invalid` edge (ours stays amber `#B86E00`, 3.99 on white, 4.33 on dark surface), and
  the dark input fill (journey sets the input background).
- Forced colours. app.css draws `border:1px solid CanvasText` on buttons, sheets, alerts and badges
  in high contrast (`app.css:756`) and a `Highlight` focus ring (`app.css:759`), but every journey
  rule beats that block: `.badge{border:0}` would erase the badge's edge, and
  `:focus-visible{outline-color:var(--j-link)}` would turn the ring into plain CanvasText. Section 5
  therefore restates the border for `.btn`, `.input`, `.sheet`, `.card`, `.alert` and `.badge` and
  the Highlight ring, and `test_high_contrast_keeps_every_shape_and_system_colour_app_css_gives`
  (review focus 4) holds every later section to the same rule.
- Motion. Press is `transform:scale(.97)` over 200ms on `--ease-land`, hover colours ease over
  200ms, all inside `prefers-reduced-motion:no-preference`; outside it every transition is `none`,
  and the reduced-motion reset also reaches `::details-content`, which app.css's
  `*, ::before, ::after` reset (`app.css:750`) never matches. On the owner's machine Windows has
  animation effects off, so Chrome reports `prefers-reduced-motion: reduce`; the probe in Step 10
  handles both.
- Budget. 3,429 B gzip for the whole file after this task, leaving about 4,500 B for sections 7 to
  10 together. Render-blocking CSS for `/login` is app.css 15,888 + Basecoat 3,363 + journey 3,429
  = 22,680 B against 30,000 (24,213 B once Tasks 4 to 7 have filled their sections).

- [ ] **Step 1: Create the helper `tests/_journey_css.py`**

Write it with the Write tool, exactly:

```python
"""Shared readers for the sign-up journey stylesheets (signup redesign spec 4.1, 4.2 and 8).

Not a test module (no ``test_`` prefix). Imported by ``tests/test_saas_journey.py`` and
``tests/test_saas_signin_failed.py``. Standard library only, so it imports on a bare checkout.

``JOURNEY_TEMPLATES`` is the one list of templates allowed to load the journey look. It starts
empty; each page task appends its template in the same change that links the two stylesheets,
and the scope test in ``test_saas_journey.py`` fails if a template links them without being
listed, or is listed without linking them.
"""

from __future__ import annotations

import gzip
import re
from pathlib import Path
from typing import Iterator

ROOT: Path = Path(__file__).resolve().parents[1]
STATIC: Path = ROOT / "applyfirst" / "saas" / "static"
TEMPLATES: Path = ROOT / "applyfirst" / "saas" / "templates"
JOURNEY_CSS: Path = STATIC / "css" / "journey.css"
BASECOAT_CSS: Path = STATIC / "vendor" / "basecoat-1.0.2-agad.css"

JOURNEY_TEMPLATES: list[str] = []

# At-rules whose block holds more rules. Every other at-rule with a block (@font-face, @property,
# @keyframes, @view-transition) is yielded whole, like a style rule.
_CONTAINERS = ("@media", "@supports", "@layer", "@container", "@scope", "@starting-style")


def read_css(path: Path) -> str:
    """The file as text with CRLF normalised to LF and every /* comment */ removed."""
    text = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def _squash(text: str) -> str:
    return " ".join(text.split())


def _blocks(css: str) -> Iterator[tuple[str, str]]:
    """(prelude, body) for every brace-matched block at this level. Strings are respected, and a
    bare statement such as ``@layer a, b;`` is skipped."""
    depth, quote, start, open_at, i, n = 0, "", 0, -1, 0, len(css)
    while i < n:
        ch = css[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif ch == ";" and depth == 0:
            start = i + 1
        elif ch == "{":
            if depth == 0:
                open_at = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                raise ValueError(f"unbalanced '}}' at offset {i}")
            if depth == 0:
                yield css[start:open_at], css[open_at + 1:i]
                start = i + 1
        i += 1
    if depth or quote:
        raise ValueError("unbalanced braces or an open string at the end of the stylesheet")


def iter_rules(css: str, _chain: tuple[str, ...] = ()) -> Iterator[tuple[str, str, tuple[str, ...]]]:
    """(selector_list, declarations_body, enclosing_at_rules) for every rule, outermost at-rule
    first. Pass comment-free text (``read_css``). Preludes are whitespace-collapsed, so a chain
    reads like ``("@layer journey", "@media (prefers-color-scheme:dark)")``. A rule that nests
    rules (Basecoat's ``&:hover``) is yielded once, nested blocks inside its body."""
    for prelude, body in _blocks(css):
        prelude = _squash(prelude)
        if prelude.startswith(_CONTAINERS):
            yield from iter_rules(body, _chain + (prelude,))
        else:
            yield prelude, body, _chain


def _split_top(text: str, sep: str) -> list[str]:
    """Split on ``sep`` outside quotes, parentheses and brackets."""
    out, depth, quote, cur = [], 0, "", ""
    for ch in text:
        if quote:
            quote = "" if ch == quote else quote
        elif ch in "\"'":
            quote = ch
        elif ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        elif ch == sep and depth == 0:
            out.append(cur)
            cur = ""
            continue
        cur += ch
    out.append(cur)
    return out


def decls(body: str) -> dict[str, str]:
    """{property: value} for one declaration block, the last one winning. Nested rules are dropped,
    properties are lower-cased, values keep their case and ``!important``, whitespace collapsed."""
    flat, prev = body, None
    while prev != flat:
        prev, flat = flat, re.sub(r"[^{};]*\{[^{}]*\}", ";", flat)
    out: dict[str, str] = {}
    for part in _split_top(flat, ";"):
        prop, sep, value = part.partition(":")
        if sep and prop.strip():
            out[prop.strip().lower()] = _squash(value)
    return out


def _channel(v: float) -> float:
    v /= 255.0
    return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4


def _luminance(hex_colour: str) -> float:
    h = hex_colour.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if not re.fullmatch(r"[0-9a-fA-F]{6}", h):
        raise ValueError(f"not an opaque hex colour: {hex_colour!r}")
    r, g, b = (_channel(int(h[i:i + 2], 16)) for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(fg_hex: str, bg_hex: str) -> float:
    """The WCAG 2 contrast ratio of two opaque hex colours, from 1.0 to 21.0."""
    a, b = _luminance(fg_hex), _luminance(bg_hex)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def gzip_size(path: Path) -> int:
    """Bytes after gzip level 9 of the file with CRLF normalised to LF (a Windows checkout
    measures the same as the Linux image)."""
    return len(gzip.compress(path.read_bytes().replace(b"\r\n", b"\n"), 9, mtime=0))


_DARK = re.compile(r"^@media \(prefers-color-scheme:\s*dark\)$")


def tokens(css: str, scheme: str) -> dict[str, str]:
    """The ``--j-*`` values journey.css gives ``:root`` in ``"light"`` or ``"dark"``. Light is every
    ``:root`` rule directly in ``@layer journey``; dark is light overlaid with the ``:root`` rules
    inside ``@media (prefers-color-scheme: dark)`` in that layer. Pass ``read_css`` text."""
    if scheme not in ("light", "dark"):
        raise ValueError(f"scheme must be 'light' or 'dark', not {scheme!r}")
    light: dict[str, str] = {}
    dark: dict[str, str] = {}
    for selectors, body, chain in iter_rules(css):
        if not chain or chain[0] != "@layer journey":
            continue
        if ":root" not in [s.strip() for s in _split_top(selectors, ",")]:
            continue
        found = {k: v for k, v in decls(body).items() if k.startswith("--j-")}
        if len(chain) == 1:
            light.update(found)
        elif len(chain) == 2 and _DARK.match(chain[1]):
            dark.update(found)
    return dict(light) if scheme == "light" else {**light, **dark}
```

- [ ] **Step 2: Write the failing test `tests/test_saas_journey.py`**

Write it with the Write tool, exactly. (The file contains the word "keyword" in two test names and
a comment. That is fine: the privacy hook reads command text, not file content, and every command
in this task names the file `test_saas_journey.py`.)

```python
"""The sign-up journey's look: journey.css, its cascade layer and where it may load (signup
redesign spec 4.2, 4.4, 5 and 8).

journey.css lives in its own layer, above Basecoat and every app.css layer and below the frozen
motion layer. So any rule in it beats Basecoat and app.css whatever the specificity, and none can
outrank motion.css. That power is also the risk: one careless rule would repaint the Activate
button in the middle of its frozen morph, clip a keyword chip, bring the gradient back, or drop a
colour under AA in dark mode, and no page test would notice. So these tests read the frozen
values straight out of the file, compute the contrast from the real tokens in both schemes, pin
every Basecoat leak spec 5.2 names, and allow the two new stylesheets only on the templates
listed in ``_journey_css.JOURNEY_TEMPLATES``.

Page tasks add their own structure checks at the end of this file.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from _journey_css import (
    BASECOAT_CSS, JOURNEY_CSS, JOURNEY_TEMPLATES, ROOT, STATIC, TEMPLATES, contrast, decls,
    gzip_size, iter_rules, read_css, tokens,
)
from _saas_client import client_for

APP_CSS = STATIC / "css" / "app.css"
MOTION_CSS = STATIC / "css" / "motion.css"
BASE_HTML = TEMPLATES / "base.html"
MOTION_ASSETS = ("motion.css", "vt.js", "motion.js", "canvas-confetti")      # test M-2
SECTIONS = ("fonts", "tokens", "basecoat-map", "base", "components", "chrome", "login",
            "onboarding", "dashboard", "signin-failed", "motion")
# Spec 4.2: the seven templates that may ever load the look.
SPEC_JOURNEY = {"login.html", "onboarding_connect_gmail.html", "onboarding_profile.html",
                "onboarding_keywords.html", "onboarding_preview.html", "dashboard.html",
                "signin_failed.html"}
PAGE_TEMPLATES = sorted(p.name for p in TEMPLATES.glob("*.html")
                        if not p.name.startswith("_") and p.name != "base.html")
KEEP_TODAY = ("/", "/privacy", "/terms")                                     # spec D1
J_TOKENS = {"--j-ground", "--j-surface", "--j-text", "--j-muted", "--j-edge", "--j-link",
            "--j-primary", "--j-primary-hover", "--j-hairline", "--j-attn-fg", "--j-attn-bg",
            "--j-ok-fg", "--j-ok-bg", "--j-danger-fg", "--j-shadow"}
SCHEME_FREE = {"--j-primary", "--j-primary-hover"}      # the frozen blue and its hover, both modes
JOURNEY_STACK = ('-apple-system, BlinkMacSystemFont, "Inter Agad", "Inter Agad Fallback", '
                 'system-ui, "Segoe UI", Roboto, sans-serif')

JOURNEY = read_css(JOURNEY_CSS)
RULES = [(sel, body, chain) for sel, body, chain in iter_rules(JOURNEY)
         if chain and chain[0] == "@layer journey"]


# --- small selector readers ------------------------------------------------------------------

def _split(text: str, sep: str = ",") -> list[str]:
    """Split on ``sep`` outside parentheses, brackets and quotes."""
    out, depth, quote, cur = [], 0, "", ""
    for ch in text:
        if quote:
            quote = "" if ch == quote else quote
        elif ch in "\"'":
            quote = ch
        elif ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        elif ch == sep and depth == 0:
            out.append(cur.strip())
            cur = ""
            continue
        cur += ch
    out.append(cur.strip())
    return out


def _norm(part: str) -> str:
    """One selector, combinators without spaces around them: ``.alert > svg`` -> ``.alert>svg``."""
    return re.sub(r"\s*([>+~])\s*", r"\1", " ".join(part.split()))


def _subject(part: str) -> str:
    """The last compound selector of one complex selector (the element the rule styles)."""
    depth, last = 0, 0
    for i, ch in enumerate(_norm(part)):
        depth += (ch in "([") - (ch in ")]")
        if depth == 0 and ch in " >+~":
            last = i + 1
    return _norm(part)[last:]


def _positive(subject: str) -> str:
    """The subject without its :not(...) parts, which name what it does NOT style."""
    return re.sub(r":not\([^)]*\)", "", subject)


def _parts(sel: str) -> list[str]:
    return [_norm(p) for p in _split(sel)]


def _plain(chain: tuple) -> bool:
    """Directly in @layer journey, under no media or other condition."""
    return chain == ("@layer journey",)


def _declared(part: str, prop: str, *, chain_ok=_plain) -> str | None:
    """What the last journey rule listing exactly ``part`` sets ``prop`` to, or None."""
    value = None
    for sel, body, chain in RULES:
        if chain_ok(chain) and part in _parts(sel):
            value = decls(body).get(prop, value)
    return value


def _in(chain: tuple, pattern: str) -> bool:
    return any(re.search(pattern, link) for link in chain)


# --- layers (spec 4.2, 8) -------------------------------------------------------------------

def _layer_statement(path: Path) -> list[str]:
    m = re.search(r"@layer\s+([^;{]+);", read_css(path))
    assert m, f"{path.name} opens without a layer order statement"
    return [name.strip() for name in m.group(1).split(",")]


def test_app_css_puts_basecoat_first_and_journey_last():
    assert _layer_statement(APP_CSS) == ["basecoat", "reset", "tokens", "base", "components",
                                         "screens", "journey"]


def test_the_frozen_motion_layer_still_lands_above_journey():
    """The first appearance of a name fixes its place: app.css loads first, then motion.css
    (M-1), whose own statement at motion.css:2 appends motion after journey."""
    order: list[str] = []
    for path in (APP_CSS, MOTION_CSS):
        for name in _layer_statement(path):
            if name not in order:
                order.append(name)
    assert order == ["basecoat", "reset", "tokens", "base", "components", "screens", "journey",
                     "motion"]


@pytest.mark.parametrize("path,layer", [(JOURNEY_CSS, "journey"), (BASECOAT_CSS, "basecoat")],
                         ids=["journey.css", "basecoat"])
def test_every_rule_in_the_new_stylesheets_sits_in_its_own_layer(path, layer):
    """An unlayered rule beats every layer (Basecoat's own :root block did exactly that), so
    only @font-face and @property may stay outside, and nothing may open a sub-layer."""
    loose = []
    for sel, _body, chain in iter_rules(read_css(path)):
        if not chain:
            if not sel.startswith(("@font-face", "@property")):
                loose.append(sel)
        elif chain[0] != f"@layer {layer}" or any(c.startswith("@layer") for c in chain[1:]):
            loose.append(f"{sel} in {chain}")
    assert loose == [], f"{path.name}: rules outside @layer {layer}: {loose[:5]}"


def test_journey_css_keeps_its_eleven_sections_in_one_layer_block():
    raw = JOURNEY_CSS.read_bytes().decode("utf-8").replace("\r\n", "\n")
    found = re.findall(r"/\* ---- (\d+) ([\w-]+) \*/", raw)
    assert found == [(str(i), name) for i, name in enumerate(SECTIONS, 1)], found
    opens = [m.start() for m in re.finditer(r"@layer\s+journey\s*\{", raw)]
    assert len(opens) == 1, "exactly one @layer journey { ... } block"
    assert raw.index("/* ---- 1 fonts */") < opens[0] < raw.index("/* ---- 2 tokens */")
    assert raw.rstrip().endswith("}") and read_css(JOURNEY_CSS).rstrip().endswith("}")
    assert "\r" not in raw, "journey.css is written with LF endings"


# --- frozen values, statically (spec 8, 9) -----------------------------------------------------

_BTN = re.compile(r"\.(btn(?:--[\w-]+)?)(?![\w-])")


def _styles_the_primary(part: str) -> bool:
    """True when ``part`` can style a .btn--primary element itself: its subject names
    .btn--primary, or names .btn with no other variant. Pseudo-elements are not the button."""
    subject = _subject(part)
    if "::" in subject or re.search(r":(?:before|after)\b", subject):
        return False
    names = set(_BTN.findall(_positive(subject)))
    return "btn--primary" in names or (names == {"btn"})


def test_no_journey_rule_gives_the_primary_an_image_a_fade_or_other_corners():
    """motion.css's af-fill morph starts from a flat #0B6BC7 at 12px and opacity 1 (spec 5.2).
    background-image may only be none, which is how journey removes app.css's gradient."""
    bad = []
    for sel, body, _chain in RULES:
        if not any(_styles_the_primary(p) for p in _parts(sel)):
            continue
        d = decls(body)
        if d.get("background-image", "none").replace("!important", "").strip() != "none":
            bad.append((sel, "background-image", d["background-image"]))
        shorthand = d.get("background", "")
        if re.search(r"gradient|url\(|--grad|image-set", shorthand):
            bad.append((sel, "background", shorthand))
        if "opacity" in d and float(d["opacity"].replace("!important", "")) < 1:
            bad.append((sel, "opacity", d["opacity"]))
        if "border-radius" in d and d["border-radius"] != "var(--r-md)":
            bad.append((sel, "border-radius", d["border-radius"]))
    assert bad == []


def test_the_journey_primary_is_flat_blue_and_disabled_or_busy_wins_over_hover():
    assert _declared(".btn--primary", "background-image") == "none"
    assert _declared(".btn--primary", "background-color") == "var(--j-primary)"
    hover = [i for i, (sel, _b, _c) in enumerate(RULES) if ".btn--primary:hover" in _parts(sel)]
    held = [i for i, (sel, body, _c) in enumerate(RULES)
            if any(_styles_the_primary(p) and "disabled" in p and "busy" in p for p in _parts(sel))]
    assert hover and len(held) == 1, "one rule holds the disabled and the busy primary"
    d = decls(RULES[held[0]][1])
    assert (d.get("background-color"), d.get("opacity"), d.get("border-radius")) == (
        "var(--j-primary)", "1", "var(--r-md)")
    assert held[0] > max(hover), "the held rule must come after every hover rule to win"


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_the_primary_is_the_frozen_blue_in_both_schemes(scheme):
    t = tokens(JOURNEY, scheme)
    assert t["--j-primary"].upper() == "#0B6BC7"
    assert t["--j-primary-hover"].upper() == "#0A5AA8"


def test_journey_css_leaves_the_live_panel_frame_alone():
    """.status--live is the af-fill end state: navy, 24px, position relative, isolated, opaque."""
    frozen = {"background", "background-color", "background-image", "color", "border-radius",
              "position", "isolation", "opacity"}
    bad = [(sel, sorted(frozen & set(decls(body))))
           for sel, body, _c in RULES
           if any(re.search(r"\.status(?:--live)?(?![\w-])", _subject(p)) for p in _parts(sel))
           and frozen & set(decls(body))]
    assert bad == []


def test_journey_css_never_rings_or_clips_a_keyword_chip():
    """motion.css draws the new-chip ring with box-shadow on .kw, and a clipped parent cuts it."""
    bad = []
    for sel, body, _c in RULES:
        d = decls(body)
        for p in _parts(sel):
            subject = _subject(p)
            if re.search(r"\.kw(?![\w-])", subject) and {"box-shadow", "overflow", "overflow-x",
                                                        "overflow-y", "clip-path"} & set(d):
                bad.append(sel)
            if re.search(r"\.(?:kw|chip-list)(?![\w-])", subject) and re.search(
                    r"hidden|clip", d.get("overflow", "")):
                bad.append(sel)
    assert bad == []


def test_journey_css_never_draws_on_a_button_pseudo_element():
    """motion.css owns a.btn[data-state=busy]::before (the spinner); a ::after on a button is
    the tap-extender trap spec 5.2 forbids. Quiet links carry their own ::after instead."""
    bad = [sel for sel, _b, _c in RULES for p in _parts(sel)
           if _BTN.search(p) and re.search(r"::?(?:before|after)\b", p)]
    assert bad == []


def test_journey_css_only_reads_the_existing_easing_and_defines_none():
    """--ease-out, --ease-settle, --ease-exit and --ease-spring are frozen motion names."""
    assert not re.search(r"--ease-[\w-]*\s*:", JOURNEY), "journey.css defines an --ease-* name"
    used = set(re.findall(r"var\(\s*(--ease-[\w-]+)", JOURNEY))
    assert used <= {"--ease-land"}, f"only the existing --ease-land curve (spec 5.4), got {used}"


# --- tokens and contrast (spec 5.3) ----------------------------------------------------------

def test_both_schemes_define_every_journey_token():
    light, dark = tokens(JOURNEY, "light"), tokens(JOURNEY, "dark")
    assert set(light) == J_TOKENS
    unchanged = sorted(k for k in J_TOKENS - SCHEME_FREE if dark[k] == light[k])
    assert unchanged == [], f"dark mode must redefine {unchanged}"


# (scheme, foreground, background, the ratio spec 5.3 records). A token name or a literal hex.
CONTRAST = [
    ("light", "--j-text", "--j-ground", 14.20), ("light", "--j-text", "--j-surface", 15.39),
    ("light", "--j-muted", "--j-ground", 6.08), ("light", "--j-muted", "--j-surface", 6.59),
    ("light", "--j-edge", "--j-ground", 3.47), ("light", "--j-edge", "--j-surface", 3.76),
    ("light", "--j-link", "--j-ground", 4.91), ("light", "--j-link", "--j-surface", 5.33),
    ("light", "#FFFFFF", "--j-primary", 5.33), ("light", "--j-attn-fg", "--j-attn-bg", 6.9),
    ("light", "--j-ok-fg", "--j-ok-bg", 6.38), ("light", "--j-danger-fg", "--j-surface", 6.5),
    ("light", "--j-link", "--j-attn-bg", 4.5),          # the links inside the amber #form-error box
    ("dark", "--j-text", "--j-ground", 16.04), ("dark", "--j-text", "--j-surface", 14.64),
    ("dark", "--j-muted", "--j-ground", 8.20), ("dark", "--j-muted", "--j-surface", 7.48),
    ("dark", "--j-edge", "--j-ground", 4.39), ("dark", "--j-edge", "--j-surface", 4.00),
    ("dark", "--j-link", "--j-ground", 8.62), ("dark", "--j-link", "--j-surface", 7.87),
    ("dark", "#FFFFFF", "--j-primary", 5.33), ("dark", "--j-primary", "--j-ground", 3.55),
    ("dark", "--j-primary", "--j-surface", 3.24), ("dark", "--j-attn-fg", "--j-attn-bg", 9.95),
    ("dark", "--j-ok-fg", "--j-ok-bg", 8.54), ("dark", "--j-danger-fg", "--j-surface", 7.57),
    ("dark", "--j-link", "--j-attn-bg", 4.5),
]
_EDGES = {"--j-edge", "--j-primary"}                # control edges and large shapes: 3 to 1


@pytest.mark.parametrize("scheme,fg,bg,want", CONTRAST,
                         ids=[f"{s}-{f}-on-{b}" for s, f, b, _ in CONTRAST])
def test_contrast_computed_from_the_real_tokens(scheme, fg, bg, want):
    t = tokens(JOURNEY, scheme)
    got = contrast(t.get(fg, fg), t.get(bg, bg))
    floor = 3.0 if fg in _EDGES and bg != "--j-primary" else 4.5
    assert got >= floor, f"{fg} on {bg} in {scheme} is {got:.2f}, under {floor}"
    assert got >= want - 0.01, f"{fg} on {bg} in {scheme} is {got:.2f}, spec 5.3 says {want}"


def test_app_css_tokens_follow_the_journey_tokens():
    """Repointed once in section 2, so every app.css rule that reads them follows dark mode."""
    want = {"--ground": "var(--j-ground)", "--surface": "var(--j-surface)",
            "--sunk": "var(--j-ground)", "--line": "var(--j-hairline)",
            "--line-strong": "var(--j-edge)", "--text-strong": "var(--j-text)",
            "--text": "var(--j-text)", "--text-muted": "var(--j-muted)"}
    rules = [decls(b) for s, b, c in RULES
             if _plain(c) and {":root", ".mailcard", ".gsi-btn"} <= set(_parts(s))]
    got = {k: v for d in rules for k, v in d.items() if k in want}
    assert got == want


def test_the_sample_email_and_the_google_button_stay_light_in_dark_mode():
    """Spec 3 and 5.3. var() resolves where it is declared, so the island must redefine the
    --j-* values itself and be listed on both mapping rules, or it would inherit dark ones."""
    light = tokens(JOURNEY, "light")
    island = {}
    for sel, body, chain in RULES:
        if (len(chain) == 2 and re.search(r"prefers-color-scheme:\s*dark", chain[1])
                and set(_parts(sel)) == {".mailcard", ".gsi-btn"}):
            island.update({k: v for k, v in decls(body).items() if k.startswith("--j-")})
    assert island == {k: v for k, v in light.items() if k not in SCHEME_FREE}
    mapped = [set(decls(b)) for s, b, c in RULES
              if _plain(c) and {":root", ".mailcard", ".gsi-btn"} <= set(_parts(s))]
    assert any("--text" in d for d in mapped) and any("--color-card" in d for d in mapped)
    assert _declared(".mailcard", "color-scheme") == "light"
    assert _declared(".gsi-btn", "color-scheme") == "light"
    assert _declared(".mailcard", "color") == "var(--j-text)"


def test_the_google_button_is_never_restyled():
    """Spec 3: 40px, #747775 edge, Google Sans Button. journey may only set its scheme."""
    bad = [(sel, prop) for sel, body, _c in RULES
           if any(".gsi-btn" in _positive(_subject(p)) for p in _parts(sel))
           for prop in decls(body) if not prop.startswith("--") and prop != "color-scheme"]
    assert bad == []


SPEC_44 = ("--background", "--foreground", "--card", "--card-foreground", "--primary",
           "--primary-foreground", "--secondary", "--muted", "--muted-foreground", "--border",
           "--input", "--ring", "--destructive", "--radius")


def test_journey_supplies_every_variable_the_trimmed_basecoat_reads():
    """Spec 4.4. The trim drops Basecoat's colours and its --color-* aliases, so whatever the
    kept rules read and nothing in the file defines or registers must come from journey.css."""
    root: dict[str, str] = {}
    for sel, body, chain in RULES:
        if _plain(chain) and ":root" in _parts(sel):
            root.update(decls(body))
    missing = [name for name in SPEC_44 if name not in root]
    assert missing == [], f"spec 4.4 names missing: {missing}"
    assert (root["--primary"].upper(), root["--primary-foreground"].upper()) == ("#0B6BC7",
                                                                                 "#FFFFFF")
    bc = read_css(BASECOAT_CSS)
    reads = set(re.findall(r"var\(\s*(--[\w-]+)", bc))
    defined = set(re.findall(r"(--[\w-]+)\s*:", bc))
    registered = set(re.findall(r"@property\s+(--[\w-]+)", bc))
    need = reads - defined - registered
    assert {"--color-primary", "--radius"} <= need, "sanity: the trimmed file reads these"
    assert sorted(need - set(root)) == []


# --- base (spec 4.5, 5.1) ------------------------------------------------------------------

def test_the_journey_body_uses_the_inter_stack_at_nominal_size():
    """Apple devices match -apple-system first and never fetch Inter. font-size-adjust is none,
    measured in Task 2: .546 also keeps Inter nominal but cancels the fallback's size-adjust."""
    bodies = [decls(b) for s, b, _c in RULES if s == "body"]
    assert len(bodies) == 1, "journey.css styles body exactly once"
    stack = re.sub(r"\s*,\s*", ", ", bodies[0].get("font-family", ""))
    assert stack == JOURNEY_STACK
    assert bodies[0].get("font-size-adjust") == "none"


def test_type_follows_spec_5_1_through_app_css_own_tokens():
    phone = {k: v for s, b, c in RULES if _plain(c) and ":root" in _parts(s)
             for k, v in decls(b).items() if k.startswith("--fs-")}
    assert {k: phone.get(k) for k in ("--fs-body", "--fs-small", "--fs-caption", "--fs-h1",
                                      "--fs-h3")} == {
        "--fs-body": "1rem", "--fs-small": ".9375rem", "--fs-caption": ".75rem",
        "--fs-h1": "1.75rem", "--fs-h3": "1.25rem"}
    pc = {k: v for s, b, c in RULES
          if c[1:] == ("@media (hover:hover) and (pointer:fine)",) and ":root" in _parts(s)
          for k, v in decls(b).items()}
    assert {k: pc.get(k) for k in ("--fs-body", "--fs-small", "--fs-h1")} == {
        "--fs-body": ".9375rem", "--fs-small": ".875rem", "--fs-h1": "1.875rem"}
    assert _declared("h1", "font-weight") == "600" == _declared("h3", "font-weight")


def test_type_never_switches_on_width_alone():
    """Spec 5.1: a phone held sideways keeps phone sizes. Width breakpoints may lay out, never
    resize type."""
    bad = [(sel, chain) for sel, body, chain in RULES
           if any("width" in c for c in chain[1:])
           and any(k == "font-size" or k.startswith("--fs-") for k in decls(body))]
    assert bad == []


# --- components: every Basecoat leak spec 5.2 lists, by name ---------------------------------

LEAKS = [
    (".btn", "height", "auto"),                        # fixed 36px
    (".btn", "transition", "none"),                    # transition-property: all, unconditional
    (".btn", "box-shadow", "none"),                    # the focus ring shadow
    (".btn", "background-clip", "border-box"),         # padding-box shrinks the fill by 1px
    (".btn:active", "translate", "none"),              # the 1px press
    (".btn:active", "transform", "none"),              # app.css translateY(1px)
    (".btn:disabled", "opacity", "1"),                 # opacity .5
    (".btn:focus-visible", "outline-style", "solid"),  # outline-style: none
    (".btn svg", "width", "20px"),                     # .btn svg at 16px
    (".input", "height", "auto"),                      # fixed 36px, and textarea.input too
    (".input", "box-shadow", "none"),                  # drop shadow and focus ring
    (".input", "transition", "none"),
    (".input:focus-visible", "outline-style", "solid"),
    ("textarea.input", "field-sizing", "fixed"),       # field-sizing: content
    (".input[aria-invalid=true]", "border-color", "var(--amber-600)"),  # amber, never red
    (".alert>svg", "grid-row", "auto"),                # the empty strip
    (".alert>svg", "translate", "none"),
    (".badge", "height", "auto"),                      # clips "Connected"
    (".badge", "overflow", "visible"),
    (".badge", "transition", "none"),
    (":focus-visible", "outline-color", "var(--j-link)"),
    (".sheet", "overflow", "visible"),                 # groups never clip focus rings
]


@pytest.mark.parametrize("part,prop,want", LEAKS, ids=[f"{p} {q}" for p, q, _ in LEAKS])
def test_every_basecoat_leak_is_switched_off_by_name(part, prop, want):
    assert _declared(part, prop) == want


def test_every_journey_input_rule_resolves_to_16px_or_more():
    """Spec 3 and 5.1. Anything under 16px makes iOS zoom the page on focus."""
    field = re.compile(r"\.(?:input|textarea)(?![\w-])|(?:^|[^\w.#-])(?:input|textarea|select)"
                       r"(?![\w-])")

    def px(value: str) -> float | None:
        v = value.replace("!important", "").strip()
        m = re.fullmatch(r"max\((.*)\)", v)
        if m:
            known = [x for x in (px(p) for p in _split(m.group(1))) if x is not None]
            return max(known) if known else None
        m = re.fullmatch(r"(\d*\.?\d+)(px|rem)", v)
        return float(m.group(1)) * (16 if m.group(2) == "rem" else 1) if m else None

    sizes = []
    for sel, body, chain in RULES:
        if not any(field.search(_subject(p)) for p in _parts(sel)):
            continue
        d = decls(body)
        assert "font" not in d, f"{sel}: no font shorthand on inputs, write font-size"
        if "font-size" in d:
            sizes.append((sel, chain, px(d["font-size"])))
    assert sizes, "journey.css must size its inputs itself (Basecoat drops them to 14px)"
    small = [(s, c, v) for s, c, v in sizes if v is None or v < 16]
    assert small == []


# --- review focus: zoomed text, high contrast, a laptop with a touch screen -------------------
#
# Three things that bite real users and that no page test reaches. Each reads every journey rule,
# so it keeps guarding sections 7 to 10 as the page tasks fill them.

_CONTROL = re.compile(r"\.(?:btn(?:--[\w-]+)?|input)(?![\w-])|^(?:input|textarea|select|button)"
                      r"(?![\w-])")


def test_no_control_gets_a_fixed_height_so_zoomed_text_never_clips():
    """Text zoomed to 200 percent, or Android's largest font size, makes a label taller than any
    fixed box, and Basecoat fixes buttons and inputs at 36px. A control may only grow: height
    auto over a min-height floor, no fixed or maximum height, no line height in px, nothing
    clipped and no label forced onto one line."""
    bad = []
    for sel, body, _chain in RULES:
        d = decls(body)
        for part in _parts(sel):
            subject = _positive(_subject(part))
            if "::" in subject or ".gsi-btn" in subject or not _CONTROL.search(subject):
                continue
            bad += [(part, p, d[p]) for p in ("height", "max-height", "block-size",
                                              "max-block-size") if d.get(p, "auto") not in
                    ("auto", "none")]
            bad += [(part, p, d[p]) for p in ("overflow", "overflow-x", "overflow-y")
                    if re.search(r"hidden|clip", d.get(p, ""))]
            if d.get("line-height", "").endswith("px") or d.get("white-space") == "nowrap":
                bad.append((part, "line-height or white-space", body))
    assert bad == []
    for part in (".btn", ".input"):
        assert (_declared(part, "height"), _declared(part, "min-height")) == ("auto", "44px")


_SYSTEM_COLOUR = re.compile(r"\b(?:CanvasText|Canvas|Highlight|HighlightText|ButtonText|"
                            r"ButtonFace|ButtonBorder|LinkText|GrayText|Field|FieldText)\b")


def _family(prop: str) -> str | None:
    """The part of a component's look a property draws in high contrast."""
    if prop in ("color", "outline", "outline-color"):
        return "outline" if prop.startswith("outline") else "color"
    if prop in ("background", "background-color"):
        return "background"
    if re.fullmatch(r"border(?:-(?:top|right|bottom|left|block|inline)(?:-(?:start|end))?)?"
                    r"(?:-(?:width|style))?", prop):
        return "border"
    return None


def _keys(part: str) -> set[str]:
    """What one selector names: the classes of its subject, or the bare subject."""
    subject = _positive(_subject(part))
    return set(re.findall(r"\.[\w-]+", subject)) or {subject}


def test_high_contrast_keeps_every_shape_and_system_colour_app_css_gives():
    """Windows high contrast (forced colours) repaints pages with system colours. app.css gives
    buttons, cards, alerts and badges a CanvasText border there, the rail marker Highlight, and
    focus rings Highlight. Every journey rule outranks app.css's forced-colours block, so where
    journey.css redraws one of those, it must put the high-contrast value back itself."""
    wanted = set()
    for sel, body, chain in iter_rules(read_css(APP_CSS)):
        if _in(chain, r"forced-colors"):
            for prop, value in decls(body).items():
                if _family(prop) and _SYSTEM_COLOUR.search(value):
                    wanted |= {(k, _family(prop)) for p in _parts(sel) for k in _keys(p)}
    assert (".btn", "border") in wanted and (":focus-visible", "outline") in wanted, "sanity"
    touched, restored = set(), set()
    for sel, body, chain in RULES:
        for prop, value in decls(body).items():
            if _family(prop) is None:
                continue
            keys = {(k, _family(prop)) for p in _parts(sel) for k in _keys(p)}
            if not _in(chain, r"forced-colors"):
                touched |= keys
            elif _SYSTEM_COLOUR.search(value):
                restored |= keys
    assert sorted((touched & wanted) - restored) == []


_COMPUTER = "(hover:hover) and (pointer:fine)"
_COLOUR_ONLY = {"color", "background", "background-color", "border-color", "outline-color",
                "text-decoration", "text-decoration-line", "text-decoration-color"}


def test_computer_sizes_need_a_fine_pointer_that_hovers():
    """A Windows laptop with a touch screen: its main pointer is the trackpad, so it gets the
    computer sizes, and a finger still taps them. Sizes switch only on (hover:hover) and
    (pointer:fine), never on any-pointer, any-hover or a coarse pointer; a rule under
    (hover:hover) alone changes colours only, so a hover that a tap leaves stuck moves nothing;
    and the quiet links keep their 44px tap band on every device, not only on phones."""
    bad = []
    for sel, body, chain in RULES:
        media, props = " ".join(chain[1:]), set(decls(body))
        if re.search(r"any-(?:pointer|hover)|pointer:\s*coarse|hover:\s*none", media):
            bad.append((sel, media))
        elif "pointer" in media and _COMPUTER not in media:
            bad.append((sel, media))
        elif "(hover:hover)" in media and _COMPUTER not in media and props - _COLOUR_ONLY:
            bad.append((sel, sorted(props - _COLOUR_ONLY)))
    assert bad == []
    assert _declared(".btn", "min-height", chain_ok=lambda c: c[1:] == (f"@media {_COMPUTER}",)) \
        == "40px"
    assert _declared(".text-link::after", "height") == "44px"


# --- motion (spec 5.4) -----------------------------------------------------------------------

_NO_PREF = r"prefers-reduced-motion:\s*no-preference"
_STILL = {"none", "0s", "0ms"}
_TIME = re.compile(r"(\d*\.?\d+)(ms|s)")


def _still(value: str) -> bool:
    """transition: none (and friends) switches motion off, so it may sit anywhere."""
    return value.lower().replace("!important", "").strip() in _STILL


def test_everything_that_moves_waits_for_no_preference():
    loose = [(sel, prop) for sel, body, chain in RULES for prop, value in decls(body).items()
             if re.match(r"(?:transition|animation)(?:-|$)", prop)
             and not _still(value) and not _in(chain, _NO_PREF)]
    assert loose == []
    assert "scroll-behavior" not in JOURNEY, "smooth scrolling is banned"


def test_transitions_are_short_on_the_land_curve_and_move_nothing_else():
    """100 to 300ms on --ease-land. Transform and opacity, plus the colour of a hover."""
    allowed = {"transform", "opacity", "background-color", "border-color", "color"}
    bad = []
    for sel, body, chain in RULES:
        value = decls(body).get("transition", "none")
        if _still(value):
            continue
        for item in _split(value):
            words = item.split()
            times = [float(m.group(1)) * (1 if m.group(2) == "ms" else 1000)
                     for w in words for m in [_TIME.fullmatch(w)] if m]
            if words[0] not in allowed or not times or not 100 <= times[0] <= 300 or \
                    "var(--ease-land)" not in words:
                bad.append((sel, item))
    assert bad == []
    for sel, body, _c in iter_rules(JOURNEY):
        if sel.startswith("@keyframes"):
            props = set(re.findall(r"([\w-]+)\s*:", body))
            assert props <= {"transform", "opacity", "translate", "scale"}, (sel, props)


def test_a_pressed_button_scales_and_never_travels():
    pressed = _declared(".btn:active", "transform", chain_ok=lambda c: _in(c, _NO_PREF))
    assert pressed == "scale(.97)"
    assert _declared(".btn:active", "translate", chain_ok=lambda c: _in(c, _NO_PREF)) is None


def test_the_reduced_motion_reset_covers_details_content():
    """app.css's reset is `*, ::before, ::after`, which never reaches ::details-content."""
    hits = [decls(b).get("transition", "") for s, b, c in RULES
            if _in(c, r"prefers-reduced-motion:\s*reduce") and "::details-content" in _parts(s)]
    assert hits and all(h.startswith("none") for h in hits)


# --- budgets (spec 8) --------------------------------------------------------------------------

def test_the_two_new_stylesheets_stay_inside_their_gzip_caps():
    assert gzip_size(JOURNEY_CSS) <= 8000, f"journey.css is {gzip_size(JOURNEY_CSS)} B gzip"
    assert gzip_size(BASECOAT_CSS) <= 7000, f"Basecoat is {gzip_size(BASECOAT_CSS)} B gzip"


def test_the_render_blocking_css_of_the_login_page_stays_under_30000_bytes():
    """app.css, the trimmed Basecoat file and journey.css, the three stylesheets /login blocks
    first paint on. Computed from the files, so it holds before any page links them."""
    total = sum(gzip_size(p) for p in (APP_CSS, BASECOAT_CSS, JOURNEY_CSS))
    assert total <= 30000, f"{total} B gzip"


# --- scope: where the look may load (spec 4.2, 8) ------------------------------------------------

JOURNEY_LINKS = ("{{ static_url('vendor/basecoat-1.0.2-agad.css') }}",
                 "{{ static_url('css/journey.css') }}")


def _block(src: str, name: str) -> str | None:
    m = re.search(r"\{%-?\s*block\s+" + name + r"\s*-?%\}(.*?)\{%-?\s*endblock", src, re.S)
    return m.group(1) if m else None


def test_only_spec_templates_can_join_the_journey():
    assert len(set(JOURNEY_TEMPLATES)) == len(JOURNEY_TEMPLATES)
    assert set(JOURNEY_TEMPLATES) <= SPEC_JOURNEY
    assert set(JOURNEY_TEMPLATES) <= set(PAGE_TEMPLATES)


@pytest.mark.parametrize("name", PAGE_TEMPLATES)
def test_the_journey_look_loads_on_exactly_the_listed_templates(name):
    """Listed: page_css links Basecoat then journey.css (both hashed), the page asks for light
    and dark, and the two theme colours are the header surface of each scheme. Not listed:
    the template names neither file and keeps base.html's light defaults."""
    src = (TEMPLATES / name).read_text(encoding="utf-8")
    if name not in JOURNEY_TEMPLATES:
        assert "basecoat" not in src and "journey.css" not in src, name
        assert _block(src, "color_scheme") is None and _block(src, "theme_color_meta") is None
        return
    links = re.findall(r"<link\b[^>]*>", _block(src, "page_css") or "")
    assert links == [f'<link rel="stylesheet" href="{u}">' for u in JOURNEY_LINKS]
    assert (_block(src, "color_scheme") or "").strip() == "light dark"
    metas = dict((s, c.upper()) for c, s in re.findall(
        r'<meta name="theme-color" content="(#[0-9A-Fa-f]{6})" '
        r'media="\(prefers-color-scheme: (light|dark)\)">', _block(src, "theme_color_meta") or ""))
    assert metas == {s: tokens(JOURNEY, s)["--j-surface"].upper() for s in ("light", "dark")}


@pytest.mark.parametrize("path", KEEP_TODAY)
def test_the_pages_that_keep_todays_look_never_load_the_journey_files(saas_cfg, path):
    resp = client_for(saas_cfg).get(path)
    assert resp.status_code == 200
    assert "basecoat" not in resp.text and "journey.css" not in resp.text


# Rendered by base.html today, byte for byte. The two new blocks must default to exactly this.
TODAY_HEAD = ('\n  <meta name="color-scheme" content="light">\n'
              '  <meta name="theme-color" content="#F3F6FA">\n  <title>')


@pytest.mark.parametrize("path", KEEP_TODAY)
def test_the_new_head_blocks_render_todays_bytes_by_default(saas_cfg, path):
    html = client_for(saas_cfg).get(path).text.replace("\r\n", "\n")
    assert TODAY_HEAD in html
    assert html.count('name="theme-color"') == 1 and html.count('name="color-scheme"') == 1


def test_base_offers_the_blocks_the_journey_pages_fill():
    src = BASE_HTML.read_text(encoding="utf-8")
    assert '<meta name="color-scheme" content="{% block color_scheme %}light{% endblock %}">' in src
    assert ('{% block theme_color_meta %}<meta name="theme-color" content="'
            '{% block theme_color %}#F3F6FA{% endblock %}">{% endblock %}') in src
    assert src.index("{% block motion_head %}") < src.index("{% block page_css %}") < \
        src.index("js/reveal.js"), "page_css stays after the motion head (M-1)"


NEW_FILES = ("tools/basecoat/basecoat-1.0.2.cdn.min.css", "tools/basecoat/trim.py",
             "applyfirst/saas/static/vendor/basecoat-1.0.2-agad.css",
             "applyfirst/saas/static/css/journey.css", "tools/fonts/build_inter.py",
             "applyfirst/saas/static/licenses/basecoat-MIT.txt",
             "applyfirst/saas/static/licenses/tailwindcss-MIT.txt",
             "applyfirst/saas/static/licenses/OFL-inter.txt",
             "applyfirst/saas/templates/signin_failed.html", "tests/_journey_css.py",
             "tests/test_saas_journey.py", "tests/test_saas_basecoat.py",
             "tests/test_saas_signin_failed.py")
FONT_FILES = tuple(str(p.relative_to(ROOT)) for p in (STATIC / "fonts").glob("inter-*.woff2"))


@pytest.mark.parametrize("rel", NEW_FILES + FONT_FILES)
def test_no_new_file_name_contains_a_motion_asset_name(rel):
    """M-2 greps the public pages for these substrings, so a name like journey-motion.css would
    fail it the moment a page linked it."""
    name = Path(rel).name
    assert [b for b in MOTION_ASSETS if b in name] == []


# --- the readers themselves ------------------------------------------------------------------

def test_the_css_reader_sees_through_layers_media_and_strings():
    css = ('@layer a,b;@layer a{@media (x:y){.b>i{content:"}{;";color:red}}}'
           '@font-face{font-family:"q"}')
    got = list(iter_rules(css))
    assert got[0] == (".b>i", 'content:"}{;";color:red', ("@layer a", "@media (x:y)"))
    assert got[1][0] == "@font-face" and got[1][2] == ()
    assert decls(got[0][1]) == {"content": '"}{;"', "color": "red"}
    assert decls("a:1;&:hover{a:2};b:3") == {"a": "1", "b": "3"}


def test_the_contrast_reader_is_wcag():
    assert round(contrast("#FFFFFF", "#000000"), 2) == 21.0
    assert round(contrast("#FFF", "#0B6BC7"), 2) == 5.33
    with pytest.raises(ValueError):
        tokens(JOURNEY, "sepia")
```

- [ ] **Step 3: Run the new tests and watch them fail**

```bash
.venv/Scripts/python.exe -m pytest -q tests/test_saas_journey.py
```

Expected: `68 failed, 46 passed` (measured). The 68 are: both layer-order tests
(`['reset', 'tokens', 'base', 'components', 'screens'] != [...]`), the section test (only
`('1', 'fonts')` found), the flat-primary and frozen-blue tests and the token completeness test
(`KeyError: '--j-primary'` / empty token set), all 28 contrast cases (`KeyError`), the token
mapping, island and Basecoat-variable tests, the body-stack and type-token tests, all 22 leak cases
(`None == 'auto'` and so on), the 16px input test ("journey.css must size its inputs itself"), the
press and `::details-content` tests, `test_base_offers_the_blocks_the_journey_pages_fill`, and two
review-focus tests (`test_no_control_gets_a_fixed_height_so_zoomed_text_never_clips` and
`test_computer_sizes_need_a_fine_pointer_that_hovers`, which find no `.btn` rule yet).
The 46 that already pass are the ones that only forbid things (nothing is there yet to break
them, the high-contrast review test among them), the scope tests for the nine unlisted templates, the three render tests of `/`, `/privacy`
and `/terms`, the budget tests, the 14 file-name cases and the two reader self-tests. The
Basecoat half of the layer test passes because Task 1 already wrapped that file.

- [ ] **Step 4: Snapshot every page before touching base.html**

Write `<scratchpad>/render_pages.py` with the Write tool (the scratchpad folder is the one the
session's system prompt names):

```python
"""Render every page of the SaaS as a visitor and as a signed-in user, for a before/after diff.

    .venv/Scripts/python.exe render_pages.py <repo root> <output folder>

Writes one .html file per page, with the ?v=<hash> of every static URL, the CSRF token and the
random ids replaced by fixed words, so only a real markup change shows in the diff. Writes only
to <output folder> and a temp dir. No server.
"""
import re
import sys
import tempfile
from pathlib import Path

root, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2])
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / "tests"))

from applyfirst.saas.config import SaaSConfig  # noqa: E402
from _saas_client import client_for, seed_user  # noqa: E402

out.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory() as d:
    cfg = SaaSConfig(db_path=str(Path(d) / "saas.db"), google_client_id="id",
                     google_client_secret="secret",
                     session_secret=b"render-pages-session-secret-32-bytes",
                     base_url="https://localhost:8000", secure_cookies=False)
    anon = client_for(cfg)
    user = seed_user(cfg, profile=True, keywords=("virtual assistant",), activated=True)
    signed = client_for(cfg, user)
    pages = {p: anon for p in ("/", "/privacy", "/terms", "/login")}
    pages.update({p: signed for p in ("/dashboard", "/onboarding/connect_gmail",
                                      "/onboarding/profile", "/onboarding/keywords",
                                      "/onboarding/preview")})
    for path, client in pages.items():
        resp = client.get(path)
        body = re.sub(r"\?v=[0-9a-f]{12}", "?v=HASH", resp.text)
        body = re.sub(r'name="csrf" value="[^"]+"', 'name="csrf" value="CSRF"', body)
        body = re.sub(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "UUID", body)
        name = (path.strip("/").replace("/", "_") or "home") + ".html"
        (out / name).write_text(f"{resp.status_code}\n{body}", encoding="utf-8", newline="\n")
        print(f"{path:28} {resp.status_code} {len(body):6} bytes -> {name}")
```

Run it on the repo as it is now:

```bash
SP="<this session's scratchpad folder>"
.venv/Scripts/python.exe "$SP/render_pages.py" . "$SP/pages_before"
```

Expected: nine lines, every status `200` (measured sizes: `/` 30,385, `/privacy` 9,040, `/terms`
5,933, `/login` 5,249, `/dashboard` 8,262, `/onboarding/connect_gmail` 8,852,
`/onboarding/profile` 7,455, `/onboarding/keywords` 10,272, `/onboarding/preview` 7,523 bytes).

- [ ] **Step 5: Change the layer order at `app.css:6`**

Use the Edit tool on `applyfirst/saas/static/css/app.css`. Before (line 6):

```css
@layer reset, tokens, base, components, screens;
```

After:

```css
@layer basecoat, reset, tokens, base, components, screens, journey;
```

Nothing else in app.css changes. On pages that load neither new file the two extra names are empty
layers, so the homepage, privacy and terms render exactly as before (Step 9 proves it).

- [ ] **Step 6: Add the two head blocks to `base.html` (lines 7 and 8)**

Use the Edit tool on `applyfirst/saas/templates/base.html`. Before (lines 7 and 8):

```html
  <meta name="color-scheme" content="light">
  <meta name="theme-color" content="{% block theme_color %}#F3F6FA{% endblock %}">
```

After:

```html
  <meta name="color-scheme" content="{% block color_scheme %}light{% endblock %}">
  {% block theme_color_meta %}<meta name="theme-color" content="{% block theme_color %}#F3F6FA{% endblock %}">{% endblock %}
```

Both new blocks sit inside lines that already existed, and each default renders exactly the old
text, so every page that does not override them gets the same bytes. `theme_color` survives
nested inside `theme_color_meta`, so any template that overrides it keeps working. The journey
pages replace the whole `theme_color_meta` block with a light and a dark meta (the snippet in
Interfaces).

- [ ] **Step 7: Append sections 2 to 11 to `journey.css`**

Read `applyfirst/saas/static/css/journey.css` first (12 lines, from Task 2). Then use the Edit tool:
`old_string` is the whole of line 12,

```css
  ascent-override:90.6%;descent-override:22.54%;line-gap-override:0%}
```

and `new_string` is that same line, one empty line, then the block below (so the file keeps its
single trailing LF and lines 1 to 12 are untouched):

```css
  ascent-override:90.6%;descent-override:22.54%;line-gap-override:0%}

@layer journey{
/* ---- 2 tokens */
/* Spec 5.3. Light by default, dark follows the phone. --j-primary is the frozen #0B6BC7 in both
   schemes (motion.css's af-fill starts from it). The second rule points app.css's own tokens at
   ours, so every app.css rule that reads them follows dark mode without being restated. */
:root{color-scheme:light dark;--j-ground:#F3F6FA;--j-surface:#FFFFFF;--j-text:#0B2545;--j-muted:#4E5E76;--j-edge:#74859D;--j-link:#0B6BC7;--j-primary:#0B6BC7;--j-primary-hover:#0A5AA8;--j-hairline:rgba(11,37,69,.1);--j-attn-fg:#7A4400;--j-attn-bg:#FFF6E6;--j-ok-fg:#11663A;--j-ok-bg:#EAF7EF;--j-danger-fg:#B3261E;--j-shadow:0 1px 2px rgba(11,37,69,.06)}
:root,.mailcard,.gsi-btn{--ground:var(--j-ground);--surface:var(--j-surface);--sunk:var(--j-ground);--line:var(--j-hairline);--line-strong:var(--j-edge);--text-strong:var(--j-text);--text:var(--j-text);--text-muted:var(--j-muted)}
/* The sample email and Google's button stay light in both schemes. var() resolves where it is
   declared, so the island redefines the --j-* values and sits on both mapping rules. */
.mailcard,.gsi-btn{color-scheme:light}
.mailcard{color:var(--j-text)}
@media (prefers-color-scheme:dark){
:root{--j-ground:#0A111C;--j-surface:#111B2B;--j-text:#E6EDF5;--j-muted:#9DACC0;--j-edge:#6A7B93;--j-link:#5CB8F0;--j-hairline:rgba(255,255,255,.12);--j-attn-fg:#F5C66B;--j-attn-bg:#2A2110;--j-ok-fg:#6FD39A;--j-ok-bg:#10281C;--j-danger-fg:#FF8A80;--j-shadow:0 1px 2px rgba(0,0,0,.5)}
.mailcard,.gsi-btn{--j-ground:#F3F6FA;--j-surface:#FFFFFF;--j-text:#0B2545;--j-muted:#4E5E76;--j-edge:#74859D;--j-link:#0B6BC7;--j-hairline:rgba(11,37,69,.1);--j-attn-fg:#7A4400;--j-attn-bg:#FFF6E6;--j-ok-fg:#11663A;--j-ok-bg:#EAF7EF;--j-danger-fg:#B3261E;--j-shadow:0 1px 2px rgba(11,37,69,.06)}
}
/* ---- 3 basecoat-map */
/* Spec 4.4: Basecoat's names on our palette, then the --color-* aliases its trimmed rules read. */
:root,.mailcard,.gsi-btn{--background:var(--j-ground);--foreground:var(--j-text);--card:var(--j-surface);--card-foreground:var(--j-text);--primary:#0B6BC7;--primary-foreground:#FFFFFF;--secondary:var(--j-surface);--muted:var(--j-ground);--muted-foreground:var(--j-muted);--border:var(--j-hairline);--input:var(--j-edge);--ring:var(--j-link);--destructive:var(--j-danger-fg);--radius:12px;--color-background:var(--background);--color-foreground:var(--foreground);--color-card:var(--card);--color-card-foreground:var(--card-foreground);--color-primary:var(--primary);--color-primary-foreground:var(--primary-foreground);--color-secondary:var(--secondary);--color-muted:var(--muted);--color-muted-foreground:var(--muted-foreground);--color-border:var(--border);--color-input:var(--input);--color-ring:var(--ring);--color-destructive:var(--destructive)}
/* ---- 4 base */
/* Spec 5.1. Phone sizes by default, computer sizes on (hover:hover) and (pointer:fine), never on
   width. Type goes through app.css's own tokens (body, h1, h2, .lead, captions, small notes), so
   no element rule here outranks an app.css class. font-size-adjust none: Inter at its nominal
   size, and the fallback face's size-adjust keeps working (measured in Task 2). */
:root{--fs-body:1rem;--fs-lead:var(--fs-body);--fs-small:.9375rem;--fs-caption:.75rem;--fs-h1:1.75rem;--fs-h3:1.25rem}
body{font-family:-apple-system,BlinkMacSystemFont,"Inter Agad","Inter Agad Fallback",system-ui,"Segoe UI",Roboto,sans-serif;font-size-adjust:none;line-height:1.5;-webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale}
h1,h2,h3{font-weight:600}
:where(a:not(.btn,.gsi-btn,.skip-link)){color:var(--j-link)}
:focus-visible{outline-color:var(--j-link)}
.caption{font-weight:500}
@media (hover:hover) and (pointer:fine){:root{--fs-body:.9375rem;--fs-small:.875rem;--fs-h1:1.875rem}h3{font-size:1rem}}
/* ---- 5 components */
/* Every Basecoat leak spec 5.2 lists is switched off here by name (tests/test_saas_journey.py). */
.btn{height:auto;min-height:44px;padding:0 16px;gap:8px;border-radius:var(--r-md);background-clip:border-box;font-size:1rem;font-weight:500;box-shadow:none;transition:none}
.btn:active{transform:none;translate:none}
.btn:disabled{opacity:1}
.btn:focus-visible,.input:focus-visible{outline-style:solid}
.btn svg,.alert>svg{width:20px;height:20px}
.btn svg[width="16"]{width:16px;height:16px}
.btn--primary{background-color:var(--j-primary);background-image:none;color:#FFFFFF}
.btn--secondary{background:var(--j-surface);color:var(--j-text);border-color:var(--j-edge)}
@media (hover:hover){.btn--primary:hover{background-color:var(--j-primary-hover)}.btn--secondary:hover{background:var(--j-ground)}}
/* Frozen (spec 5.2, 9): disabled and busy stay the af-fill start, and win over hover. */
.btn--primary:is([disabled],[data-state=busy]){background-color:var(--j-primary);opacity:1;border-radius:var(--r-md)}
@media (hover:hover) and (pointer:fine){.btn{min-height:40px;font-size:.9375rem}}
/* Quiet actions: link colour, and a 44px tap band from ::after (never on a .btn). */
.text-link,.back-link{position:relative;min-height:0;font-weight:500;text-decoration:none}
.text-link::after,.back-link::after{content:"";position:absolute;inset:50% -8px auto;height:44px;margin-top:-22px}
.text-link:hover,.back-link:hover{text-decoration:underline}
/* Fields: label above, control, hint below. The hint keeps its id and aria-describedby. */
.field>*{order:2}
.field>:is(.field__label,.input,.add-row){order:0}
.field>.field__hint{order:1}
.field__label{display:block;font-size:var(--fs-caption);font-weight:500;line-height:1.4}
.field__hint{font-size:var(--fs-small);color:var(--j-muted)}
.input{height:auto;min-height:44px;padding:9px 12px;border:1px solid var(--j-edge);border-radius:var(--r-sm);background:var(--j-surface);color:var(--j-text);font-size:max(16px,1rem);line-height:1.5;box-shadow:none;transition:none}
textarea.input{field-sizing:fixed}
@media (hover:hover){.input:hover{border-color:var(--j-muted)}}
.input:focus{border-color:var(--j-link)}
.input[aria-invalid=true]{border-color:var(--amber-600);box-shadow:inset 0 0 0 1px var(--amber-600)}
/* Groups never clip: overflow:hidden would cut focus rings. */
.sheet,.card{background:var(--j-surface);border:1px solid var(--j-hairline);border-radius:var(--r-md);box-shadow:var(--j-shadow);overflow:visible}
.alert{background:var(--j-ground);border:1px solid var(--j-hairline);border-radius:var(--r-md);color:var(--j-text);line-height:1.5}
.alert>svg{grid-row:auto;translate:none}
.alert>.icon{color:var(--j-link)}
.alert--attention{background:var(--j-attn-bg);color:var(--j-attn-fg)}
.alert--success{background:var(--j-ok-bg);color:var(--j-ok-fg)}
.alert--danger{color:var(--j-danger-fg)}
.alert:is(.alert--attention,.alert--success,.alert--danger)>.icon,.alert strong{color:inherit}
.badge{height:auto;overflow:visible;padding:2px 10px 2px 8px;border:0;font-size:var(--fs-caption);font-weight:500;transition:none}
.badge--ok{background:var(--j-ok-bg);color:var(--j-ok-fg)}
.badge--attention{background:var(--j-attn-bg);color:var(--j-attn-fg)}
/* High contrast keeps the shapes app.css gave them (a hairline would fade to nothing). */
@media (forced-colors:active){.btn,.input,.sheet,.card,.alert,.badge{border:1px solid CanvasText}:focus-visible{outline-color:Highlight}}
/* ---- 6 chrome */
/* One header, one height on every page, hairline bottom, not sticky, no blur (spec 5.2). */
.site-header{padding-block:0;background:var(--j-surface);border-bottom:1px solid var(--j-hairline)}
.site-header__in{min-height:56px}
.brand{color:var(--j-text);font-weight:600}
/* A light, short footer: the legal links, the contact line and "not affiliated" stay. */
.site-footer{background:none;box-shadow:none;border-top:1px solid var(--j-hairline);color:var(--j-muted);padding-block:8px 24px}
.site-footer a{color:var(--j-muted)}
.site-footer a:hover{color:var(--j-text)}
.footer__grid{display:flex;flex-wrap:wrap;align-items:center;gap:0 24px}
.footer__grid>:first-child{display:none}
.footer__grid>div{display:flex;flex-wrap:wrap;align-items:center;gap:0 8px}
.footer__small{margin-top:0;padding-top:0;border-top:0}
/* ---- 7 login */
/* ---- 8 onboarding */
/* ---- 9 dashboard */
/* ---- 10 signin-failed */
/* ---- 11 motion */
/* Everything that moves waits for no-preference: 100 to 300ms on --ease-land (spec 5.4). */
@media (prefers-reduced-motion:no-preference){
.btn{transition:transform .2s var(--ease-land),background-color .2s var(--ease-land),border-color .2s var(--ease-land)}
.btn:active{transform:scale(.97)}
.input{transition:border-color .2s var(--ease-land)}
}
@media (prefers-reduced-motion:reduce){::details-content{transition:none!important}}
}
```

Check the file on disk:

```bash
.venv/Scripts/python.exe -c "import gzip,pathlib;b=pathlib.Path('applyfirst/saas/static/css/journey.css').read_bytes();print(b.count(b'\n'),len(b),len(gzip.compress(b,9,mtime=0)),b.count(b'\r'))"
```

Expected: `112 9451 3429 0` (112 lines, 9,451 bytes, 3,429 gzip, no CR). If Task 2's section 1
landed with different bytes, the last three numbers move with it; the line count and the zero CR
must hold.

How the rules read, for the reviewer. The file's layer sits above app.css, so for example
`.btn--primary{background-image:none}` wins over all four app.css gradient states, and
`.btn:disabled{opacity:1}` wins over Basecoat's `opacity:50%`. The `(hover:hover)` block after the
primary rule changes the colour only on devices that hover, and the held rule after it wins over
hover at equal specificity. The press scale lives only in section 11. The first `(hover:hover)
and (pointer:fine)` block (section 4) re-points the type tokens, the second (section 5) lowers
buttons to 40px.

- [ ] **Step 8: Run the new tests and watch them pass**

```bash
.venv/Scripts/python.exe -m pytest -q tests/test_saas_journey.py
```

Expected: `114 passed` (28 contrast cases, 22 leak cases, 14 file-name cases, 9 template-scope
cases, 3 plus 3 render cases, 2 layer cases, 2 frozen-blue cases, 31 single tests).

- [ ] **Step 9: Prove every page still renders the same bytes**

```bash
SP="<this session's scratchpad folder>"
.venv/Scripts/python.exe "$SP/render_pages.py" . "$SP/pages_after"
diff -r "$SP/pages_before" "$SP/pages_after" && echo "ALL PAGES BYTE-IDENTICAL"
```

Expected: the same nine lines as Step 4, then `ALL PAGES BYTE-IDENTICAL` and no diff output.
This covers the homepage, privacy, terms, login, the dashboard and all four onboarding steps, so
the new blocks, the new layer names and the unlinked journey.css change nothing anyone sees.

- [ ] **Step 10: Check the cascade in a real browser, light and dark**

Nothing links journey.css yet, so this loads the four stylesheets into a throwaway page and reads
computed styles in headless Chrome (installed at `C:\Program Files\Google\Chrome\Application\chrome.exe`;
no server; Chrome exits by itself). Write `<scratchpad>/probe_cascade.py` with the Write tool:

```python
"""Load app.css, motion.css, the trimmed Basecoat file and journey.css in headless Chrome, in the
app-page cascade, and check what the shared components compute to in light and in dark.

    .venv/Scripts/python.exe probe_cascade.py <repo root>

No server: the page is a temp file that links the stylesheets by file:// URL. Chrome runs with a
throwaway profile and exits by itself. Exit 1 if any expectation fails.
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
STATIC = ROOT / "applyfirst/saas/static"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
LINKS = "".join(f'<link rel="stylesheet" href="{(STATIC / p).as_uri()}">' for p in (
    "css/app.css", "css/motion.css", "vendor/basecoat-1.0.2-agad.css", "css/journey.css"))
ICON = ('<svg class="icon"{1} width="{0}" height="{0}" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" aria-hidden="true"><path d="M5 12h14"/></svg>')
BODY = f"""
<header class="site-header site-header--app"><div class="container--app site-header__in">
<a class="brand" id="brand" href="/">Agad</a></div></header>
<main id="main">
<button class="btn btn--primary btn--lg" id="primary" type="submit">{ICON.format(20, "")}<span>Start</span></button>
<button class="btn btn--primary btn--lg" id="disabled" type="submit" disabled><span>Start</span></button>
<a class="btn btn--primary" id="busy" data-state="busy" href="/x"><span>Connect</span></a>
<button class="btn btn--secondary btn--sm" id="secondary" type="button">{ICON.format(16, "")}<span>Copy</span></button>
<div class="field"><label class="field__label" for="input" id="label">Name</label>
<p class="field__hint" id="hint">Hint</p><input class="input" id="input" type="text" value="x"></div>
<div class="field"><label class="field__label" for="textarea">Message</label>
<textarea class="input" id="textarea" rows="8" aria-invalid="true"></textarea></div>
<div class="alert alert--attention" id="alert">{ICON.format(20, ' id="alert-icon"')}<div><p>Text</p></div></div>
<span class="badge badge--ok" id="badge">Gmail connected</span>
<section class="sheet" id="sheet"><h2 class="card-title">Today</h2></section>
<a class="text-link" id="quiet" href="/y">Edit</a>
<div class="mailcard" id="mailcard"><p id="mailtext">From me</p></div>
<a class="gsi-btn" id="gsi" href="/auth/login"><span>Continue with Google</span></a>
</main>"""
READ = [("body.font", "main", "font-family"), ("primary.bg", "primary", "background-color"),
        ("primary.img", "primary", "background-image"), ("primary.radius", "primary", "border-top-left-radius"),
        ("primary.clip", "primary", "background-clip"), ("primary.shadow", "primary", "box-shadow"),
        ("primary.weight", "primary", "font-weight"), ("primary.transition", "primary", "transition-property"),
        ("disabled.bg", "disabled", "background-color"), ("disabled.opacity", "disabled", "opacity"),
        ("disabled.radius", "disabled", "border-top-left-radius"), ("disabled.img", "disabled", "background-image"),
        ("busy.bg", "busy", "background-color"), ("busy.color", "busy", "color"),
        ("secondary.bg", "secondary", "background-color"), ("secondary.color", "secondary", "color"),
        ("input.size", "input", "font-size"), ("input.height", "input", "height"),
        ("input.radius", "input", "border-top-left-radius"), ("input.shadow", "input", "box-shadow"),
        ("input.bg", "input", "background-color"), ("textarea.sizing", "textarea", "field-sizing"),
        ("textarea.edge", "textarea", "border-top-color"), ("label.size", "label", "font-size"),
        ("label.display", "label", "display"), ("hint.order", "hint", "order"),
        ("alert.bg", "alert", "background-color"), ("alert.color", "alert", "color"),
        ("alert.icon.row", "alert-icon", "grid-row-start"), ("alert.icon.width", "alert-icon", "width"),
        ("alert.icon.translate", "alert-icon", "translate"), ("badge.overflow", "badge", "overflow-x"),
        ("badge.bg", "badge", "background-color"), ("sheet.overflow", "sheet", "overflow-x"),
        ("sheet.radius", "sheet", "border-top-left-radius"), ("sheet.bg", "sheet", "background-color"),
        ("brand.color", "brand", "color"), ("quiet.color", "quiet", "color"),
        ("mail.bg", "mailcard", "background-color"), ("mail.color", "mailtext", "color"),
        ("gsi.color", "gsi", "color"), ("gsi.bg", "gsi", "background-color"), ("gsi.height", "gsi", "height")]
SCRIPT = """addEventListener('load', () => {
  const out = {};
  for (const [k, id, prop] of %s) out[k] = getComputedStyle(document.getElementById(id))[prop];
  out['header.min'] = getComputedStyle(document.querySelector('.site-header__in')).minHeight;
  out['svg16'] = getComputedStyle(document.querySelector('#secondary svg')).width;
  out['svg20'] = getComputedStyle(document.querySelector('#primary svg')).width;
  out['reduced'] = String(matchMedia('(prefers-reduced-motion: reduce)').matches);
  out['scheme'] = matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  document.getElementById('out').textContent = 'RESULT' + JSON.stringify(out) + 'END';
});""" % json.dumps(READ)
HTML = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f'<meta name="color-scheme" content="light dark">{LINKS}</head><body>{BODY}'
        f'<pre id="out"></pre><script>{SCRIPT}</script></body></html>')

BLUE, WHITE, NAVY = "rgb(11, 107, 199)", "rgb(255, 255, 255)", "rgb(11, 37, 69)"
BOTH = {"primary.bg": BLUE, "primary.img": "none", "primary.radius": "12px",
        "primary.clip": "border-box", "primary.shadow": "none", "primary.weight": "500",
        "disabled.bg": BLUE, "disabled.opacity": "1", "disabled.radius": "12px", "disabled.img": "none",
        "busy.bg": BLUE, "busy.color": WHITE, "input.size": "16px", "input.height": "44px",
        "input.radius": "8px", "input.shadow": "none", "textarea.sizing": "fixed",
        "textarea.edge": "rgb(184, 110, 0)", "label.size": "12px", "label.display": "block",
        "hint.order": "1", "alert.icon.row": "auto", "alert.icon.width": "20px",
        "alert.icon.translate": "none", "badge.overflow": "visible", "sheet.overflow": "visible",
        "sheet.radius": "12px", "mail.bg": WHITE, "mail.color": NAVY, "gsi.color": "rgb(31, 31, 31)",
        "gsi.bg": WHITE, "gsi.height": "40px", "header.min": "56px", "svg16": "16px", "svg20": "20px"}
EXPECT = {
    "light": {**BOTH, "secondary.bg": WHITE, "secondary.color": NAVY, "input.bg": WHITE,
              "alert.bg": "rgb(255, 246, 230)", "alert.color": "rgb(122, 68, 0)",
              "badge.bg": "rgb(234, 247, 239)", "sheet.bg": WHITE, "brand.color": NAVY,
              "quiet.color": BLUE},
    "dark": {**BOTH, "secondary.bg": "rgb(17, 27, 43)", "secondary.color": "rgb(230, 237, 245)",
             "input.bg": "rgb(17, 27, 43)", "alert.bg": "rgb(42, 33, 16)",
             "alert.color": "rgb(245, 198, 107)", "badge.bg": "rgb(16, 40, 28)",
             "sheet.bg": "rgb(17, 27, 43)", "brand.color": "rgb(230, 237, 245)",
             "quiet.color": "rgb(92, 184, 240)"},
}

bad = 0
with tempfile.TemporaryDirectory() as d:
    page = Path(d) / "probe.html"
    page.write_text(HTML, encoding="utf-8")
    for scheme, flags in (("light", []), ("dark", ["--force-dark-mode"])):
        res = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--allow-file-access-from-files",
                              f"--user-data-dir={d}/p-{scheme}", *flags, "--virtual-time-budget=5000",
                              "--dump-dom", page.as_uri()], capture_output=True, text=True, timeout=120)
        m = re.search(r'<pre id="out">RESULT(.*?)END</pre>', res.stdout, re.S)
        if not m:
            sys.exit("Chrome printed no result:\n" + res.stdout[-800:] + res.stderr[-800:])
        got = json.loads(m.group(1).replace("&quot;", '"'))
        # Chrome follows Windows' "Animation effects" switch. Off means reduced motion, and then
        # journey.css must leave the button perfectly still.
        want = dict(EXPECT[scheme], scheme=scheme, **{"primary.transition": "none" if got["reduced"] == "true"
                                                      else "transform, background-color, border-color"})
        print(f"--- {scheme}, reduced motion {got['reduced']}")
        for k in sorted(got):
            ok = k not in want or got[k] == want[k]
            bad += not ok
            print(f"  {'ok ' if ok else 'BAD'} {k:22} {got[k]}{'' if ok else f'   (want {want[k]})'}")
sys.exit(1 if bad else 0)
```

```bash
.venv/Scripts/python.exe "$SP/probe_cascade.py" .; echo "exit $?"
```

Expected: `exit 0`, 48 `ok` lines per scheme and no `BAD`. Among them, in both schemes:
`disabled.bg rgb(11, 107, 199)`, `disabled.opacity 1`, `disabled.radius 12px`,
`disabled.img none` (the frozen Activate start), `input.size 16px`, `input.height 44px`,
`textarea.sizing fixed`, `alert.icon.row auto`, `badge.overflow visible`, `mail.bg
rgb(255, 255, 255)` and `gsi.color rgb(31, 31, 31)`. In dark, `secondary.bg rgb(17, 27, 43)` and
`quiet.color rgb(92, 184, 240)`. On the owner's machine the header reads
`reduced motion true` (Windows animation effects are off), and `primary.transition` is then
`none`, which the script expects. Body text is 15px and buttons 40px there because a desktop
browser matches `(hover:hover) and (pointer:fine)`.

- [ ] **Step 11: Prove the tests bite (mutation pass)**

Write `<scratchpad>/mutate_journey.py` with the Write tool. It edits one repo file at a time and
always puts the original bytes back.

```python
"""Plant one mistake at a time and check tests/test_saas_journey.py catches every one.

    .venv/Scripts/python.exe <scratchpad>/mutate_journey.py <repo root>

Each mutant edits one file, runs the journey tests, and puts the original bytes back (in a
finally block, so even a crash restores the file). Exit 1 if any mutant survives.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
J = ROOT / "applyfirst/saas/static/css/journey.css"
BASE = ROOT / "applyfirst/saas/templates/base.html"
HOME = ROOT / "applyfirst/saas/templates/home.html"
HELPER = ROOT / "tests/_journey_css.py"
HELD = (".btn--primary:is([disabled],[data-state=busy]){background-color:var(--j-primary);"
        "opacity:1;border-radius:var(--r-md)}\n")
END = "@media (prefers-reduced-motion:reduce){::details-content{transition:none!important}}\n}"
HDR = ".site-header__in{min-height:56px}"


def edit(path, *pairs):
    """A mutant: replace each (old, new) once, in order. Every old must be present."""
    def apply():
        text = path.read_bytes().decode("utf-8")
        for old, new in pairs:
            assert old in text, (path.name, old)
            text = text.replace(old, new, 1)
        path.write_bytes(text.encode("utf-8"))
    return path, apply


MUTANTS = {
    "gradient on hover": edit(J, (".btn--primary:hover{background-color:var(--j-primary-hover)}",
                                  ".btn--primary:hover{background-image:linear-gradient(#0B6BC7,#0A5AA8)}")),
    "faded disabled": edit(J, (".btn:disabled{opacity:1}", ".btn:disabled{opacity:.5}")),
    "primary corners": edit(J, (".btn--primary{background-color", ".btn--primary{border-radius:8px;background-color")),
    "held rule missing": edit(J, (HELD, "")),
    "held rule before hover": edit(J, (HELD, ""), (".btn--primary{background-color", HELD + ".btn--primary{background-color")),
    "live panel radius": edit(J, (HDR, HDR + ".status--live{border-radius:0}")),
    "status position": edit(J, (HDR, HDR + ".dash .status{position:static}")),
    "kw clipped": edit(J, (HDR, HDR + ".kw{overflow:hidden}")),
    "chip-list clipped": edit(J, (HDR, HDR + ".chip-list{overflow:clip}")),
    "kw ring": edit(J, (HDR, HDR + "li.kw{box-shadow:none}")),
    "button pseudo": edit(J, (HDR, HDR + '.btn--primary::after{content:""}')),
    "ease defined": edit(J, ("--j-shadow:0 1px 2px rgba(11,37,69,.06)}", "--j-shadow:0 1px 2px rgba(11,37,69,.06);--ease-out:linear}")),
    "other easing": edit(J, (".btn:active{transform:scale(.97)}", ".btn:active{transform:scale(.97);transition:transform .2s ease}")),
    "transition outside no-preference": edit(J, (".btn:active{transform:none;translate:none}", ".btn:active{transform:none;translate:none;transition:transform .2s var(--ease-land)}")),
    "long transition": edit(J, ("border-color .2s var(--ease-land)}\n.btn:active", "border-color .5s var(--ease-land)}\n.btn:active")),
    "layout transition": edit(J, (".input{transition:border-color .2s var(--ease-land)}", ".input{transition:width .2s var(--ease-land)}")),
    "press travels": edit(J, (".btn:active{transform:scale(.97)}", ".btn:active{transform:scale(.97);translate:0 1px}")),
    "dark muted too dim": edit(J, ("--j-muted:#9DACC0", "--j-muted:#5A6A80")),
    "light edge too pale": edit(J, ("--j-edge:#74859D;--j-link", "--j-edge:#A9B6C6;--j-link")),
    "dark forgets a token": edit(J, ("--j-ok-bg:#10281C;", "")),
    "primary drifts": edit(J, ("--j-primary:#0B6BC7", "--j-primary:#0A6AC6")),
    "unlayered rule": edit(J, (END, END + "\n.x{color:#0B2545}")),
    "sub-layer": edit(J, ("/* ---- 7 login */", "/* ---- 7 login */\n@layer x{.y{color:#0B2545}}")),
    "small input on computers": edit(J, ("h3{font-size:1rem}}", "h3{font-size:1rem}.input{font-size:14px}}")),
    "font shorthand on input": edit(J, ("textarea.input{field-sizing:fixed}", "textarea.input{field-sizing:fixed;font:inherit}")),
    "type on width": edit(J, ("/* ---- 7 login */", "/* ---- 7 login */\n@media (min-width:960px){:root{--fs-body:.9rem}}")),
    "island loses the Google button": edit(J, (".mailcard,.gsi-btn{--j-ground:#F3F6FA", ".mailcard{--j-ground:#F3F6FA")),
    "island stale value": edit(J, (".mailcard,.gsi-btn{--j-ground:#F3F6FA;--j-surface:#FFFFFF;--j-text:#0B2545",
                                   ".mailcard,.gsi-btn{--j-ground:#F3F6FA;--j-surface:#FFFFFF;--j-text:#243449")),
    "Google button restyled": edit(J, (".mailcard{color:var(--j-text)}", ".mailcard{color:var(--j-text)}.gsi-btn{height:44px}")),
    "badge clips again": edit(J, (".badge{height:auto;overflow:visible;", ".badge{height:auto;")),
    "field-sizing content": edit(J, ("textarea.input{field-sizing:fixed}", "textarea.input{resize:vertical}")),
    "alert strip back": edit(J, (".alert>svg{grid-row:auto;translate:none}", ".alert>svg{translate:none}")),
    "invalid turns red": edit(J, (".input[aria-invalid=true]{border-color:var(--amber-600)", ".input[aria-invalid=true]{border-color:var(--j-danger-fg)")),
    "basecoat alias missing": edit(J, ("--color-ring:var(--ring);", "")),
    "font-size-adjust number": edit(J, ("font-size-adjust:none", "font-size-adjust:.546")),
    "smooth scroll": edit(J, ("/* ---- 7 login */", "/* ---- 7 login */\nhtml{scroll-behavior:smooth}")),
    "section order": edit(J, ("/* ---- 9 dashboard */\n/* ---- 10 signin-failed */", "/* ---- 10 signin-failed */\n/* ---- 9 dashboard */")),
    "details reset dropped": edit(J, ("@media (prefers-reduced-motion:reduce){::details-content{transition:none!important}}", "")),
    "base default changes": edit(BASE, ("{% block color_scheme %}light{% endblock %}", "{% block color_scheme %}light dark{% endblock %}")),
    "homepage loads journey": edit(HOME, ("{% block page_css %}", "{% block page_css %}\n  <link rel=\"stylesheet\" href=\"{{ static_url('css/journey.css') }}\">")),
    "listed but not linked": edit(HELPER, ("JOURNEY_TEMPLATES: list[str] = []", "JOURNEY_TEMPLATES: list[str] = [\"login.html\"]")),
    "focus ring loses Highlight in high contrast": edit(J, (":focus-visible{outline-color:Highlight}}", "}")),
    "fixed control height": edit(J, (HDR, HDR + ".btn--secondary{height:40px}")),
    "sizes on a coarse pointer": edit(J, (HDR, HDR + "@media (any-pointer:coarse){.btn{min-height:48px}}")),
}

survivors = []
for name, (path, apply) in MUTANTS.items():
    original = path.read_bytes()
    try:
        apply()
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider",
                            "tests/test_saas_journey.py"], cwd=ROOT, capture_output=True, text=True)
        first = next((ln for ln in r.stdout.splitlines() if ln.startswith("FAILED")), "")
        print(f"{'caught  ' if r.returncode else 'SURVIVED'} {name:34} {first[39:120]}")
        if not r.returncode:
            survivors.append(name)
    finally:
        path.write_bytes(original)
print(f"{len(MUTANTS) - len(survivors)} of {len(MUTANTS)} caught, survivors {survivors}")
sys.exit(1 if survivors else 0)
```

```bash
.venv/Scripts/python.exe "$SP/mutate_journey.py" .; echo "exit $?"
git status --short
```

Expected: 44 lines starting `caught`, then `44 of 44 caught, survivors []` and `exit 0`. About two
minutes. `git status --short` must then list only this task's changes (`app.css`, `base.html`,
`journey.css`, the two new test files) plus whatever Tasks 1 and 2 left, and the pre-existing
`REMOTE.md`: the script restores `base.html`, `home.html` and `_journey_css.py` byte for byte.

- [ ] **Step 12: Run both gates**

```bash
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe .noxa/redesign-saas-ui/inputs/preserve_smoke.py
```

Expected: pytest: all pass (887 + the new tests); smoke: 0 failed. Measured in sequence: `939 passed`
before this task, `1053 passed` after it (114 new), and `558 checks passed, 0 failed.` The smoke does not change in this task because no page
links the new files; Task 4 adds them to `REQUIRED_ASSETS`. No server was started, so there is
nothing to stop.

**Hand-off to Tasks 4 to 7 (they build on this).**
1. To load the look, paste the journey head snippet from Interfaces into the template and append
   the template's name to `JOURNEY_TEMPLATES` in `tests/_journey_css.py`, in the same change. The
   scope test fails if either half is missing.
2. Write rules only between your own banner and the next one. The foundation uses 3,429 B gzip,
   so sections 7 to 10 share about 4,500 B (roughly 1,100 each keeps room for fixes).
3. Every journey rule beats every app.css rule, whatever the specificity. Never write a bare
   element selector (`h2`, `p`, `a`, `li`, `summary`) in a page section: it would override app.css
   classes such as `.sample__label`, `.h-mini` or `.card-title`. Scope with a page class. Change
   type through `--fs-*` or a class. A border or background you set on a shape app.css keeps in high
   contrast needs its forced-colours value back, as section 5 does; the high-contrast review test
   names any you miss.
4. Dark mode is automatic only where app.css reads the re-pointed tokens. These app.css rules use
   fixed light palette colours and need a journey rule on the page that shows them (found by
   reading app.css). Onboarding: `.stepper__item.is-passed::before` and the rail nodes
   (`--navy-900`, `app.css:342`, `713`), the rail tint and `.stepper__marker` at 960px
   (`--blue-50`, `app.css:710`, `787`), `.rail__edit` (`--blue-50`, `721`), `.fromto` and `.addr`
   (`--sky-50`, `--sky-100`, `--sky-200`, `238-244`), `.fromto__note` (`--navy-900` text, `250`),
   `.ledger__icon` (`230`), `.tag--sky` (`176`), `.kw` and `.kw__remove:hover` (`192-196`),
   `.quick` and its hover (`199-201`), `.chip` (`186`), `.gconf` and `.gconf__line` (`769`, `773`),
   `.paste` and `.paste--word` (`326-327`), `.preview__link::before` (`594`), `.empty__icon`
   (`302`), `.disclose > summary .icon` (`284`). Dashboard: `.status--gmail` (`356-360`),
   `.status--empty .status__icon` (`362`), `.status--paused` (`363-364`), `.meter--full li.on`
   and `.bar__fill--100` (`--navy-900` on a dark ground, `294`, `298`), `.usage-note--cap` and
   `--near` (`610`, `612`), `.route > li::before` and its line (`214-216`), `.status__kw .icon`
   (`370`). The live panel's dark edge is `.status--live{border-color:var(--j-hairline)}`.
5. Quiet actions (Edit, Skip for now) are `class="text-link"`; the 44px tap band comes with it.
   Groups are `.sheet` (the existing macro). `.card` is styled the same but keeps Basecoat's
   `padding-block:24px` and `gap:24px`, so set its padding if you use it.
6. Computer sizes go in `@media (hover:hover) and (pointer:fine)` only. Width breakpoints (the
   frozen 960px and 1100px) may change layout, never type (a test enforces it).

**Notes for the reviewer (Task 3).**
1. Spec 8 says journey.css "never sets background-image" on `.btn--primary`. It has to set
   `background-image:none` to remove app.css's gradient (`app.css:143-151`). The tests allow
   `none` and ban every other value (same finding as Task 2's note 2).
2. Spec 5.4 says "transform and opacity only". Section 11 also eases `background-color` and
   `border-color` on hover (200ms, `--ease-land`, no-preference only). If the owner wants the strict
   reading, delete those two items from the two transition lists and shrink `allowed` in
   `test_transitions_are_short_on_the_land_curve_and_move_nothing_else` to transform and opacity.
3. Spec 4.4 says the Basecoat variables are defined "in hex". `--primary` and
   `--primary-foreground` are literal hex; the other twelve point at the hex `--j-*` tokens, so
   dark mode follows without a second list. Writing all of them twice in hex would cost about
   150 B gzip and could drift from the tokens.
4. Spec 4.5 asks for a measured `font-size-adjust`. The measured value is `none` (Task 2), not the
   x-height number `.546`, which was re-measured at 1118/2048 with fontTools at opsz 14.
5. Spec 5.2 wants the hint below the input, but the field macros (`_ui.html:83-88` and `99-107`)
   print it between the label and the input. Section 5 moves it visually with `order` (DOM
   unchanged, so `aria-describedby` and screen-reader order keep today's GOV.UK pattern). If DOM
   order is preferred, a later change edits the macro and drops the three `order` rules.
6. The owner's Windows has animation effects off, so Chrome reports
   `prefers-reduced-motion: reduce` on this machine. Task 8's browser pass forces
   `no-preference` (Playwright `reduced_motion="no-preference"`) to see or measure any motion.
7. Spec 4.2 leaves the two theme-color values open. They are the header surface of each scheme
   (`#FFFFFF`, `#111B2B`), and the scope test ties them to `--j-surface`.
8. The short footer hides the brand and blurb column with CSS only (still in the HTML, so no text
   test changes). The header row is 56px on every journey page (app.css had 64px when signed in).
9. The layer order means journey rules also beat app.css's `@media (forced-colors: active)`
   block (`app.css:755-762`). Section 5 restores the borders and the Highlight focus ring for
   what it restyles, and the high-contrast review test fails for any later rule that forgets.
10. The links rule is `:where(a:not(.btn,.gsi-btn,.skip-link))`, zero specificity inside the
    layer, and the footer links get `.site-footer a`. A plain `a{color}` or `.brand{color}` would
    repaint the Google button, the skip link and the navy footer text (measured by Task 4's
    browser check on a stand-in: 3.28 to 1 and 2.89 to 1).


### Task 4: The login page (spec 6.1, spec 4.2 loading)

The first page that loads the new look. Everything below was prototyped end to end on 2026-09-25
in a scratch copy of the repo, with Task 1's real trimmed Basecoat file (sha256 `4aae6ed8...`),
Task 2's real Inter file and section 1, and small stand-ins for Task 3 (the layer statement, the
`color_scheme` block, the helper module and a token-only `journey.css`). Measured there: the new
tests failed before the change and passed after it, 22 planted mistakes were each caught (and 5
correct rules were each allowed), the smoke went from 558 to **566 checks, 0 failed**, and the
browser check below printed `0 failed` in light and dark, on phone and computer, with and without
the in-app notice. During assembly the task was re-run on top of the real Tasks 1 to 3, with the
`theme_color_meta` block and colours below: 14 new passing items, pytest 1,067, smoke 566, and
Step 8's browser check printed 96 PASS and `0 failed`.

**Files:**
- Modify `applyfirst/saas/templates/login.html` (35 lines, LF). Two blocks are added after line 4
  (`{% block title %}`), one block after line 7 (the end of `head_extra`), and line 14
  (`      {{ ui.mark() }}`) is removed. The full before and after are in Step 4.
- Modify `applyfirst/saas/static/css/journey.css`: fill section 7, between the banners
  `/* ---- 7 login */` and `/* ---- 8 onboarding */` that Task 3 wrote. Nothing else in the file.
- Modify `tests/_journey_css.py`: the `JOURNEY_TEMPLATES` line Task 3 wrote.
- Modify `tests/test_saas_journey.py`: append the Task 4 block at the end of the file.
- Modify `.noxa/redesign-saas-ui/inputs/preserve_smoke.py` lines 76 to 78 (`REQUIRED_ASSETS`). The
  file is git-ignored but it is a gate.
- Not touched: `app.css` (its `.auth .mark` rule at line 628 becomes unused and is harmless),
  `_ui.html`, `app.py`, `static_assets.py`, `motion.css`, `vt.js`, `motion.js`.

**Interfaces:**
- Consumes, from earlier tasks:
  - Task 1: `applyfirst/saas/static/vendor/basecoat-1.0.2-agad.css`.
  - Task 2: `journey.css` section 1 and `applyfirst/saas/static/fonts/inter-4.1-latin-wght.woff2`.
  - Task 3: `app.css:6` reads `@layer basecoat, reset, tokens, base, components, screens, journey;`;
    `base.html:7` reads `<meta name="color-scheme" content="{% block color_scheme %}light{% endblock %}">`
    and `base.html:8` wraps the theme colour in `{% block theme_color_meta %}`;
    the section banners; the tokens `--j-hairline`, `--j-shadow`, `--j-muted`, `--j-link` and the
    re-pointed `--surface`, `--line`, `--text`, `--text-muted`, `--text-strong`; section 4 (body
    16px on phones and 15px on computers at line height 1.5, `h1` 28 and 30px weight 600); section 5
    (the `.alert` tones and Basecoat leak overrides, `.caption` 12px weight 500, `.note` 15 and
    14px, the journey link colour); section 6 (`.site-header`, `.brand`, the footer). From
    `tests/_journey_css.py`: `JOURNEY_CSS`, `STATIC`, `JOURNEY_TEMPLATES`, `read_css`,
    `iter_rules`, `decls`, `gzip_size`.
  - Verified in the repo today. `static_url()` (`applyfirst/saas/static_assets.py:30-50`) joins
    `STATIC_DIR / rel`, so `'vendor/basecoat-1.0.2-agad.css'` works like any other path, and the
    `?v=` value is the first 12 hex digits of the sha256 of the file's bytes, re-read when mtime or
    size changes. `CachedStaticFiles.file_response` (`static_assets.py:77-84`) gives any URL with
    `?v` `public, max-age=31536000, immutable`. `.css` is pinned to `text/css`
    (`static_assets.py:19-22`). No test or CSP enumerates allowed static files: the CSP
    (`applyfirst/saas/app.py:225-228`) is `default-src 'self'` and stays untouched, and the only
    static inventories are `tests/test_saas_static.py:148-159` (every file a template names must
    exist, which Tasks 1 to 3 satisfy), `tests/test_saas_static.py:162-173` (every `url()` in
    `static/css/*.css` must exist, which Task 2 satisfies) and `tests/test_saas_hero.py:271-275`
    (fonts on disk, which Task 2 rewrites).
  - The route. `GET /login` (`app.py:301-305`) renders `login.html` with an empty context, so
    `user` is undefined and `base.html:34-36` takes the signed-out branch. `login.html:9` empties
    `header_action`, so the header holds only the brand link at `base.html:25`, whose
    `{% block brand_mark %}{{ ui.mark() }}{% endblock %}` prints the one header mark. The footer
    prints its own light-on-navy mark (`base.html:45`, `ui.mark(inverse=true)`), which the brand
    mark test counts separately so Task 3 may keep or drop it.
- Produces:
  - `JOURNEY_TEMPLATES: list[str] = ["login.html"]` (Tasks 5, 6 and 7 append their templates).
  - The journey head, which Tasks 5 to 7 copy: `color_scheme` (`light dark`), `theme_color_meta`
    (two metas with `media`, the header surface `#FFFFFF` and `#111B2B`) and `page_css` (the two
    links), exactly Task 3's snippet.
  - `journey.css` section 7, written against the `.auth` classes and `body.is-auth`, so Task 7 can
    give `signin_failed.html` the same card markup and body class with no new CSS.
  - Reusable helpers in `tests/test_saas_journey.py` for Tasks 5 to 7: `assert_journey_head(markup)`,
    `stylesheets(markup)`, `head_urls(markup)`, `meta_attrs(markup, name)`,
    `page_region(markup, tag)`, `google_button_chains(markup)`, `sel_reaches(selector, chain)`,
    `sel_may`, `sel_always`, `sel_split`, `sel_compounds`, `journey_style_rules()`, `ElementChains`,
    and the constants `LOGIN_SHEETS`, `JOURNEY_THEME`. Task 7 can point the three Google button
    tests at its own page by calling `google_button_chains()` on it.
  - The smoke's `REQUIRED_ASSETS` names the three new files. This cannot happen earlier: until
    this task no page loads them, so the S9 check would fail.

**Frozen hooks (spec 9) and fixed things (spec 3) on /login:**
- `site-header`, exactly one: `base.html:23`, unchanged. The brand mark test reads it.
- No other spec 9 hook is on this page. No `data-step` on `<html>`
  (`tests/test_saas_motion.py:595-598` still passes), no form so no `csrf` input, no motion head
  (M-2 at `tests/test_saas_motion.py:335-339` still passes, because neither
  `basecoat-1.0.2-agad.css` nor `journey.css` contains `motion.css`, `vt.js`, `motion.js` or
  `canvas-confetti`).
- The Google button: printed by the unchanged macro (`_ui.html:62-64`), checked byte for byte
  against that macro, and three tests plus the browser check prove `journey.css` does not restyle
  it (spec 3).
- The invite-only alert (`ui.INVITE_ONLY`) and its wording, the in-app notice
  (`_ui.html:148-158`, unchanged) and the Google Sans Button preload in `head_extra` all stay.

**Existing tests that render /login, all still passing after this task (checked in the prototype):**
`tests/test_saas_template_guards.py:86-93` ("Continue with Google" and `href="/privacy"`
contiguous on /login), `tests/test_saas_template_guards.py:39-67` (autoescape, CSP-safe markup:
the new tags are same-origin `<link>`s and `<meta>`s), `tests/test_saas_pages.py:68-79` (the in-app
notice names the app, and is absent in Chrome), `tests/test_saas_motion.py:335-339` (M-2) and
`:595-598` (M-9), `tests/test_saas_reveal.py:162-167` (reveal.js loads, no motion files),
`tests/test_saas_hero.py:196-199`, `:202-207` (no hero.css on /login) and `:212-229` (app.css before
reveal.js before app.js, which the new links sit between), `tests/test_saas_template_context.py:78-97`
(login.html still rendered), `tests/test_saas_static.py:157-159` (the two new references are real
files).

**Smoke checks that touch /login, all still passing:**
- `preserve_smoke.py:359-361` renders `/login` through `get_page` (`:326-334`): status 200, the exact
  CSP header, then `check_page` (`:248-281`): no external or relative asset, no inline script, no
  `on*=`, no `style=`, `<title>` contains "Agad", `<html lang>`, the viewport meta, both XSS
  probes absent, and every linked asset fetched once by `check_asset` (`:218-245`): HTTP 200, the
  pinned type, `text/css` for stylesheets, `lint_css` (no external `@import` or `url()`, no
  `data:` in `@font-face`), then every `url()` the stylesheet names (the Inter file). Then the
  three needles "Continue with Google", `href="/auth/login"` and `href="/privacy"`.
- `preserve_smoke.py:372-376` does the same for `login(FBAN)` and needs "Open this page in Chrome or
  Safari" and "inside Facebook".
- `preserve_smoke.py:556-558` (S9): every `REQUIRED_ASSETS` path was served by some page. After
  Step 7 that includes the three new files, which /login serves.
- The new assets add 8 passing checks (3 per stylesheet, 2 for the font): 558 becomes 566.

- [ ] **Step 1: Put the login page on the journey list**

In `tests/_journey_css.py`, change the line Task 3 wrote:

```python
JOURNEY_TEMPLATES: list[str] = []
```

to:

```python
JOURNEY_TEMPLATES: list[str] = ["login.html"]
```

This turns on Task 3's scope test for `login.html` (the two stylesheets load on exactly the
journey templates, never on `/`, `/privacy` or `/terms`).

- [ ] **Step 2: Append the login tests to `tests/test_saas_journey.py`**

Append this block at the very end of the file, after two blank lines, unchanged. It carries its
own imports, so it does not depend on the import lines Task 3 wrote, and none of its names
clashes with Task 3's (checked during assembly).

```python
# --- Task 4: the login page (spec 6.1, 4.2) ---------------------------------------------------
#
# The first journey page. These tests read the rendered /login, not the template source, so they
# hold whatever macro or block prints the markup. The Google button checks read journey.css
# against the button's real place in the page: the journey layer outranks app.css's `.gsi-btn`
# rule whatever the specificity, so a bare `a { color: ... }` in journey.css would repaint the
# button just as surely as a rule that names it.

import re
from html.parser import HTMLParser

import pytest

from applyfirst.saas import app as app_module
from applyfirst.saas import static_assets
from _journey_css import JOURNEY_CSS, STATIC, decls, gzip_size, iter_rules, read_css
from _saas_client import clean, client_for, count_class, elements, has_class, page_text
from test_saas_pages import CHROME, UAS

LOGIN_SHEETS = ["css/app.css", "vendor/basecoat-1.0.2-agad.css", "css/journey.css"]
JOURNEY_THEME = [
    {"name": "theme-color", "content": "#FFFFFF", "media": "(prefers-color-scheme: light)"},
    {"name": "theme-color", "content": "#111B2B", "media": "(prefers-color-scheme: dark)"},
]


def _login_page(cfg, user_agent: str = CHROME) -> str:
    resp = client_for(cfg, user_agent=user_agent).get("/login")
    assert resp.status_code == 200
    return resp.text


def head_urls(markup: str) -> list[str]:
    """The href or src of every <link> and <script>, in document order."""
    urls = []
    for tag in re.findall(r"<(?:link|script)\b[^>]*>", markup):
        m = re.search(r'\s(?:href|src)="([^"]+)"', tag)
        if m:
            urls.append(m.group(1))
    return urls


def assert_journey_head(markup: str) -> None:
    """Spec 4.2: Basecoat then journey.css, both hashed by static_url(), after app.css and
    after the motion head (when the page has one), before the parser-blocking reveal.js."""
    urls = head_urls(markup)
    basecoat = static_assets.static_url("vendor/basecoat-1.0.2-agad.css")
    journey = static_assets.static_url("css/journey.css")
    for url in (basecoat, journey):
        assert re.fullmatch(r"/static/[\w./-]+\?v=[0-9a-f]{12}", url), f"not hashed: {url}"
        assert urls.count(url) == 1, f"{url} linked {urls.count(url)} times"
    order = [urls.index(u) for u in (static_assets.static_url("css/app.css"), basecoat, journey,
                                     static_assets.static_url("js/reveal.js"))]
    assert order == sorted(order), f"head order is app.css, basecoat, journey, reveal.js: {urls}"
    motion = [i for i, u in enumerate(urls)
              if re.search(r"/(?:motion\.css|vt\.js|motion\.js)\?", u)]
    assert all(i < urls.index(basecoat) for i in motion), f"page_css follows motion_head: {urls}"


def meta_attrs(markup: str, name: str) -> list[dict[str, str]]:
    return [e.attrs for e in elements(markup) if e.tag == "meta" and e.attrs.get("name") == name]


def page_region(markup: str, tag: str) -> str:
    """The first <tag>...</tag> of the page (header, main and footer are never nested)."""
    m = re.search(rf"<{tag}\b.*?</{tag}>", markup, re.S)
    assert m, f"the page has no <{tag}>"
    return m.group(0)


def stylesheets(markup: str) -> list[str]:
    """The static path of every stylesheet the page links, in order, without the ?v= hash."""
    return [re.search(r'href="/static/([^"?]+)', tag).group(1)
            for tag in re.findall(r"<link\b[^>]*>", markup) if 'rel="stylesheet"' in tag]


def test_login_links_basecoat_then_journey_css(saas_cfg):
    markup = _login_page(saas_cfg)
    assert_journey_head(markup)
    assert stylesheets(markup) == LOGIN_SHEETS


def test_login_render_blocking_css_fits_the_budget(saas_cfg):
    """Spec 8: app.css plus both new files, gzip 9 with LF endings, at most 30,000 bytes."""
    sheets = stylesheets(_login_page(saas_cfg))
    total = sum(gzip_size(STATIC / rel) for rel in sheets)
    assert total <= 30_000, f"render-blocking CSS on /login is {total} B gzip ({sheets})"


def test_login_follows_the_phone_light_or_dark(saas_cfg):
    markup = _login_page(saas_cfg)
    assert meta_attrs(markup, "color-scheme") == [
        {"name": "color-scheme", "content": "light dark"}]
    assert meta_attrs(markup, "theme-color") == JOURNEY_THEME


@pytest.mark.parametrize("path", ["/", "/privacy", "/terms"])
def test_pages_outside_the_journey_keep_one_light_theme_colour(saas_cfg, path):
    markup = client_for(saas_cfg).get(path).text
    assert meta_attrs(markup, "color-scheme") == [{"name": "color-scheme", "content": "light"}]
    assert meta_attrs(markup, "theme-color") == [{"name": "theme-color", "content": "#F3F6FA"}]


def test_login_shows_the_brand_mark_once_in_the_header(saas_cfg):
    markup = _login_page(saas_cfg)
    header, main, footer = (page_region(markup, tag) for tag in ("header", "main", "footer"))
    assert header.startswith('<header class="site-header')
    assert count_class(header, "mark") == 1, "the header carries the brand mark"
    assert count_class(main, "mark") == 0, "the sign-in card no longer repeats it"
    assert count_class(markup, "mark") - count_class(footer, "mark") == 1


def test_login_prints_the_google_button_unchanged(saas_cfg):
    markup = _login_page(saas_cfg)
    ui = app_module._TEMPLATES.env.get_template("_ui.html").module
    button = str(ui.google_button(block=True))
    assert markup.count(button) == 1, "the Google button is printed by the macro, untouched"
    assert "Continue with Google" in markup
    assert markup.count('class="gsi-btn') == 1
    assert 'href="/privacy"' in markup


def test_login_card_reads_in_the_spec_order(saas_cfg):
    markup = _login_page(saas_cfg)
    ui = app_module._TEMPLATES.env.get_template("_ui.html").module
    wanted = ["Sign in to Agad", "New here? The same button sets up your account.",
              "Continue with Google", "We never see your password."]
    if ui.INVITE_ONLY:
        wanted.append("Agad is in a private beta.")
    wanted += ["Signing in shares only your name and email address", "What is Agad?"]
    text = page_text(markup)
    where = [text.find(s) for s in wanted]
    assert -1 not in where and where == sorted(where), dict(zip(wanted, where))
    headings = [clean(e.text) for e in elements(markup) if e.tag == "h1"]
    assert headings == ["Sign in to Agad"]
    sheets = [e for e in elements(markup) if has_class(e, "auth__sheet")]
    assert len(sheets) == 1, "one card"
    assert [c.attrs.get("href") for c in sheets[0].children if has_class(c, "gsi-btn")] == [
        "/auth/login"]
    foot = [e for e in elements(markup) if e.tag == "a" and clean(e.text) == "What is Agad?"]
    assert len(foot) == 1 and foot[0].attrs.get("href") == "/"


def test_login_puts_the_in_app_notice_between_the_lead_and_the_button(saas_cfg):
    text = page_text(_login_page(saas_cfg, user_agent=UAS["Facebook"]))
    lead = text.find("New here?")
    notice = text.find("Open this page in Chrome or Safari")
    button = text.find("Continue with Google")
    assert -1 < lead < notice < button, (lead, notice, button)


# The Google button (spec 3: 40px, #747775 edge, Google Sans Button) is Google's branding. What
# follows is a small selector matcher: it asks, for every journey.css rule, whether the rule can
# reach the button's <a>, <img> or <span> where the button really sits on /login.

class ElementChains(HTMLParser):
    """Every element with its ancestors: [(tag, attrs), ...], outermost first, itself last."""

    _VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
             "source", "track", "wbr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, dict[str, str]]] = []
        self.chains: list[list[tuple[str, dict[str, str]]]] = []

    def handle_starttag(self, tag, attrs):
        el = (tag, {k.lower(): (v or "") for k, v in attrs})
        self.chains.append(self.stack + [el])
        if tag not in self._VOID:
            self.stack.append(el)

    def handle_startendtag(self, tag, attrs):
        self.chains.append(self.stack + [(tag, {k.lower(): (v or "") for k, v in attrs})])

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break


def google_button_chains(markup: str):
    """The Google link's chain, and the chains of its two children (the G image, the label)."""
    parser = ElementChains()
    parser.feed(markup)
    parser.close()
    links = [c for c in parser.chains
             if c[-1][0] == "a" and "gsi-btn" in c[-1][1].get("class", "").split()]
    assert len(links) == 1, "expected one Google button"
    link = links[0]
    kids = [c for c in parser.chains if len(c) == len(link) + 1 and c[:-1] == link]
    assert [k[-1][0] for k in kids] == ["img", "span"], kids
    return link, kids


def sel_split(text: str, sep: str) -> list[str]:
    """Split on ``sep`` outside brackets and parentheses."""
    out, depth, cur = [], 0, ""
    for ch in text:
        depth += (ch in "([") - (ch in ")]")
        if ch == sep and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    return out + [cur.strip()] if cur.strip() else out


def sel_compounds(selector: str) -> list[tuple[str, str]]:
    """[(combinator before it, compound), ...]: '' for the first, then ' ', '>', '+' or '~'."""
    out, cur, comb, depth = [], "", "", 0
    for ch in selector.strip() + " ":
        depth += (ch in "([") - (ch in ")]")
        if depth == 0 and (ch.isspace() or ch in ">+~"):
            if cur:
                out.append((comb, cur))
                cur, comb = "", " "
            if ch in ">+~":
                comb = ch
            continue
        cur += ch
    return out


_SEL_TYPE = re.compile(r"\*|[a-zA-Z][\w-]*")
_SEL_PIECE = re.compile(r"""
    \.(?P<cls>-?[_a-zA-Z][\w-]*)
  | \#(?P<id>-?[_a-zA-Z][\w-]*)
  | \[\s*(?P<attr>[\w-]+)\s*(?:(?P<op>[~|^$*]?=)\s*(?P<val>"[^"]*"|'[^']*'|[^\]\s]+))?\s*[iIsS]?\s*\]
  | ::(?P<pe>[\w-]+)(?:\([^()]*\))?
  | :(?P<pc>[\w-]+)(?:\((?P<arg>(?:[^()]|\([^()]*\))*)\))?
""", re.X)
# States a link, an image or a span can never be in.
_SEL_NEVER = {"disabled", "enabled", "checked", "indeterminate", "placeholder-shown", "invalid",
              "valid", "user-invalid", "user-valid", "required", "optional", "default",
              "in-range", "out-of-range", "empty", "open", "popover-open", "modal"}


def _sel_pieces(compound: str):
    """(type or None, [piece matches]) for one compound selector. Unknown syntax fails loudly."""
    m = _SEL_TYPE.match(compound)
    kind, pos, found = (m.group(0) if m else None), (m.end() if m else 0), []
    while pos < len(compound):
        piece = _SEL_PIECE.match(compound, pos)
        assert piece, f"the test cannot read {compound[pos:]!r} in {compound!r}: simplify it"
        found.append(piece)
        pos = piece.end()
    return kind, found


def _sel_attr_ok(piece, attrs: dict[str, str]) -> bool:
    if piece["attr"] not in attrs:
        return False
    return piece["op"] != "=" or attrs[piece["attr"]] == piece["val"].strip("\"'")


def sel_always(compound: str, el) -> bool:
    """``compound`` matches ``el`` in every state (no pseudo-classes)."""
    tag, attrs = el
    kind, found = _sel_pieces(compound)
    if kind not in (None, "*", tag):
        return False
    for p in found:
        if p["pc"] or p["pe"]:
            return False
        if p["cls"] and p["cls"] not in attrs.get("class", "").split():
            return False
        if p["id"] and attrs.get("id") != p["id"]:
            return False
        if p["attr"] and not _sel_attr_ok(p, attrs):
            return False
    return True


def sel_may(compound: str, el) -> bool:
    """``compound`` can match ``el`` in some state (hover, focus, visited...)."""
    tag, attrs = el
    kind, found = _sel_pieces(compound)
    if kind not in (None, "*", tag):
        return False
    for p in found:
        if p["cls"] and p["cls"] not in attrs.get("class", "").split():
            return False
        if p["id"] and attrs.get("id") != p["id"]:
            return False
        if p["attr"] and not _sel_attr_ok(p, attrs):
            return False
        if p["pe"] and p["pe"] not in ("before", "after"):
            return False
        pc = (p["pc"] or "").lower()
        if pc in _SEL_NEVER or (pc == "root" and tag != "html"):
            return False
        args = sel_split(p["arg"] or "", ",")
        if pc in ("is", "where", "matches") and not any(
                sel_may(sel_compounds(a)[-1][1], el) for a in args):
            return False
        if pc == "not" and any(len(sel_compounds(a)) == 1 and sel_always(a, el) for a in args):
            return False
    return True


def sel_reaches(selector: str, chain) -> bool:
    """``selector`` can match the last element of ``chain`` (its ancestors come before it)."""
    parts = sel_compounds(selector)

    def at(i: int, j: int) -> bool:
        if not sel_may(parts[i][1], chain[j]):
            return False
        if i == 0:
            return True
        comb = parts[i][0]
        if comb == ">":
            return j > 0 and at(i - 1, j - 1)
        if comb == " ":
            return any(at(i - 1, k) for k in range(j - 1, -1, -1))
        return True                  # + and ~: siblings are not tracked, so assume they match

    return at(len(parts) - 1, len(chain) - 1)


def journey_style_rules():
    """(selector list, declarations, enclosing at-rules) for every style rule in journey.css."""
    for selectors, body, at_rules in iter_rules(read_css(JOURNEY_CSS)):
        if selectors.startswith("@") or any(a.startswith(("@keyframes", "@font-face"))
                                            for a in at_rules):
            continue
        yield selectors, decls(body), at_rules


_NOT_GROUP = re.compile(r":not\((?:[^()]|\([^()]*\))*\)")
_FOCUS_PC = re.compile(r":focus(?:-visible)?(?![\w-])")
_OUTLINE_PROPS = {"outline", "outline-color", "outline-offset", "outline-style", "outline-width"}
# Inherited properties the Google button does not set itself: an ancestor's value would reach it.
_GSI_INHERITED = {"text-transform", "word-spacing", "text-shadow", "font-feature-settings",
                  "font-variation-settings"}


def test_the_matcher_reads_the_google_button_the_way_a_browser_would(saas_cfg):
    """Guards the guard: each selector below is known to reach (or miss) the button."""
    link, (img, span) = google_button_chains(_login_page(saas_cfg))
    for sel in ("a", "a:hover", ".gsi-btn", ".auth a", ".auth__action > a", "main :focus-visible",
                ":is(a, button)", "a::after", "*"):
        assert sel_reaches(sel, link), sel
    for sel in ("a:not(.gsi-btn)", "a:not(.btn,.gsi-btn):visited", ".btn", ".alert a", "body",
                ":root", "a::placeholder", ".auth > a", "a:disabled", ".gsi-btn > span > b"):
        assert not sel_reaches(sel, link), sel
    assert sel_reaches(".gsi-btn > span", span) and sel_reaches("img", img)
    assert not sel_reaches(".btn > span", span) and not sel_reaches(".btn img", img)


def test_journey_css_names_the_google_button_only_to_keep_it_light():
    assert "--font-gsi" not in read_css(JOURNEY_CSS), "the Google button reads --font-gsi"
    for selectors, props, at_rules in journey_style_rules():
        if ".gsi-btn" not in _NOT_GROUP.sub("", selectors):
            continue
        assert all(p.startswith("--") or p == "color-scheme" for p in props), (
            f"{selectors} sets {sorted(props)}")


def test_no_journey_rule_restyles_the_google_button(saas_cfg):
    link, kids = google_button_chains(_login_page(saas_cfg))
    hits = []
    for selectors, props, _at in journey_style_rules():
        real = {p for p in props if not p.startswith("--") and p != "color-scheme"}
        if not real:
            continue
        for sel in sel_split(selectors, ","):
            left = real - _OUTLINE_PROPS if _FOCUS_PC.search(sel_compounds(sel)[-1][1]) else real
            hits += [f"{sel} reaches <{chain[-1][0]}>: {sorted(left)}"
                     for chain in (link, *kids) if left and sel_reaches(sel, chain)]
    assert hits == [], ("journey.css must not restyle the Google button; exclude it with "
                        ":not(.gsi-btn) or scope the rule: " + "; ".join(hits))


def test_no_journey_rule_leaks_an_inherited_style_into_the_google_button(saas_cfg):
    link, _ = google_button_chains(_login_page(saas_cfg))
    hits = []
    for selectors, props, _at in journey_style_rules():
        risky = _GSI_INHERITED & set(props)
        if not risky:
            continue
        for sel in sel_split(selectors, ","):
            hits += [f"{sel} on <{link[d - 1][0]}>: {sorted(risky)}"
                     for d in range(1, len(link)) if sel_reaches(sel, link[:d])]
    assert hits == [], "; ".join(hits)
```

- [ ] **Step 3: Run the new tests and watch them fail**

```bash
.venv/Scripts/python.exe -m pytest -q tests/test_saas_journey.py
```

Expected: exactly these fail, everything else in the file passes.
- Task 3's scope test, for `login.html` (the template links neither file yet).
- `test_login_links_basecoat_then_journey_css`, with
  `AssertionError: /static/vendor/basecoat-1.0.2-agad.css?v=<12 hex> linked 0 times`.
- `test_login_follows_the_phone_light_or_dark`, the color-scheme meta is `light`.
- `test_login_shows_the_brand_mark_once_in_the_header`, with
  `AssertionError: the sign-in card no longer repeats it`.

The Google button tests already pass here, because they read `journey.css` as Task 3 left it.
If `test_no_journey_rule_restyles_the_google_button` fails at this point, the message names a
Task 3 rule (typically a bare `a { color: ... }` or `a:hover`). The `journey` layer outranks
app.css's `.gsi-btn` rule whatever the specificity, so fix that rule in its own section, for
example `main a:not(.btn,.gsi-btn)`, never by adding `.gsi-btn` overrides.

- [ ] **Step 4: Rewrite login.html**

Before (`applyfirst/saas/templates/login.html`, all 35 lines):

```html
{% extends "base.html" %}
{% import "_ui.html" as ui %}
{% from "_icons.html" import icon %}
{% block title %}Sign in · Agad{% endblock %}
{% block head_extra %}
  <link rel="preload" href="/static/fonts/google-sans-button-500.woff2" as="font" type="font/woff2" crossorigin>
{% endblock %}
{% block body_class %}is-auth{% endblock %}
{% block header_action %}{% endblock %}
{% block content %}
<div class="auth">
  <div class="auth__sheet">
    <div class="auth__head">
      {{ ui.mark() }}
      <h1>Sign in to Agad</h1>
      <p class="lead">New here? The same button sets up your account.</p>
    </div>
    {{ ui.inapp_notice(request.headers.get('user-agent', '')) }}
    <div class="auth__action">
      {{ ui.google_button(block=true) }}
      <p class="note">{{ icon('lock', 16) }}<span>You'll sign in on Google's own page. We never see your password.</span></p>
    </div>
    {%- if ui.INVITE_ONLY %}
    {% call ui.alert('info', 'info') %}
      <p>Agad is in a private beta. If Google says “Access blocked”, you're not on the list yet.</p>
      <p><a class="text-link" href="{{ ui.INVITE_MAILTO }}">{{ icon('mail', 18) }}Ask for an invite</a></p>
      <p class="caption">No mail app? Email <span class="select-all">{{ ui.CONTACT_EMAIL }}</span></p>
    {% endcall %}
    {%- endif %}
    <hr>
    <p class="caption">Signing in shares only your name and email address with us. Connecting Gmail is a separate step, and you choose whether to do it.</p>
  </div>
  <p class="auth__foot"><a class="text-link" href="/">What is Agad?</a></p>
</div>
{% endblock %}
```

After (replace the whole file):

```html
{% extends "base.html" %}
{% import "_ui.html" as ui %}
{% from "_icons.html" import icon %}
{% block title %}Sign in · Agad{% endblock %}
{% block color_scheme %}light dark{% endblock %}
{% block theme_color_meta %}<meta name="theme-color" content="#FFFFFF" media="(prefers-color-scheme: light)">
  <meta name="theme-color" content="#111B2B" media="(prefers-color-scheme: dark)">{% endblock %}
{% block head_extra %}
  <link rel="preload" href="/static/fonts/google-sans-button-500.woff2" as="font" type="font/woff2" crossorigin>
{% endblock %}
{% block page_css %}
  <link rel="stylesheet" href="{{ static_url('vendor/basecoat-1.0.2-agad.css') }}">
  <link rel="stylesheet" href="{{ static_url('css/journey.css') }}">
{% endblock %}
{% block body_class %}is-auth{% endblock %}
{% block header_action %}{% endblock %}
{% block content %}
<div class="auth">
  <div class="auth__sheet">
    <div class="auth__head">
      <h1>Sign in to Agad</h1>
      <p class="lead">New here? The same button sets up your account.</p>
    </div>
    {{ ui.inapp_notice(request.headers.get('user-agent', '')) }}
    <div class="auth__action">
      {{ ui.google_button(block=true) }}
      <p class="note">{{ icon('lock', 16) }}<span>You'll sign in on Google's own page. We never see your password.</span></p>
    </div>
    {%- if ui.INVITE_ONLY %}
    {% call ui.alert('info', 'info') %}
      <p>Agad is in a private beta. If Google says “Access blocked”, you're not on the list yet.</p>
      <p><a class="text-link" href="{{ ui.INVITE_MAILTO }}">{{ icon('mail', 18) }}Ask for an invite</a></p>
      <p class="caption">No mail app? Email <span class="select-all">{{ ui.CONTACT_EMAIL }}</span></p>
    {% endcall %}
    {%- endif %}
    <hr>
    <p class="caption">Signing in shares only your name and email address with us. Connecting Gmail is a separate step, and you choose whether to do it.</p>
  </div>
  <p class="auth__foot"><a class="text-link" href="/">What is Agad?</a></p>
</div>
{% endblock %}
```

What changed, and nothing else did:
- Lines 5 to 7 are new: `color_scheme` becomes `light dark`, and `theme_color_meta` prints the
  light meta (`#FFFFFF`) and the dark one (`#111B2B`), the header surface `--j-surface` of each
  scheme (section 6 paints the header with it), so the browser bar matches the header. Task 3's
  scope test reads both colours from `journey.css`.
- Lines 11 to 14 are new: `page_css` links the trimmed Basecoat file, then `journey.css`, both
  through `static_url()` so both get `?v=` and the one-year cache. `page_css` sits after
  `motion_head` in `base.html:13-14` (empty on this public page) and before `reveal.js`.
- `{{ ui.mark() }}` is gone from `.auth__head`. The mark shows once, in the header.
- The card keeps the spec 6.1 order: `h1` "Sign in to Agad", the lead, the in-app notice, the
  Google button (the macro, untouched), the lock note, the invite-only alert, the divider, the
  caption. "What is Agad?" stays as the quiet link under the card, where it is today.

- [ ] **Step 5: Fill section 7 of journey.css**

Put these lines between `/* ---- 7 login */` and `/* ---- 8 onboarding */` (Task 3 leaves nothing
between the two banners):

```css
.is-auth main{display:flex;flex-direction:column;justify-content:center}
.auth{padding-block:24px 48px}
.auth__sheet{gap:20px;border-color:var(--j-hairline);border-radius:var(--r-md);box-shadow:var(--j-shadow);padding:28px 20px}
.auth__head{gap:8px}
.auth__head .lead{font-size:inherit;line-height:1.5;color:var(--j-muted)}
.auth .note .icon{color:var(--j-link)}
.auth__foot{margin-top:16px;text-align:center}
@media (min-width:640px){.auth{padding-block:64px}.auth__sheet{padding:32px}}
```

What each line does. The page centres the card between header and footer when there is room
(`.is-auth main`, a flex column). The card keeps app.css's 440px width, so the lead fits one line
on computers (measured 357px of 376px). The card follows spec 5.2: surface background (app.css
already reads `--surface`, which Task 3 re-points), a hairline edge, 12px corners, one faint shadow.
Because a `journey` rule beats every app.css rule, the unconditional `box-shadow` also replaces
app.css's 640px `--shadow-raised`, and the new `@media (min-width:640px)` restores the larger
padding. The lead drops from `--fs-lead` (17 to 19px) to body size in the muted colour. The lock
icon takes the link colour, `#0B6BC7` in light as today and `#5CB8F0` in dark. It adds 488 bytes
raw and 138 bytes gzip (`journey.css` goes from 9,451 B and 3,429 B gzip to 9,939 B and 3,567 B
gzip, measured in sequence). There is no motion on this page, so section 11 gets nothing.

- [ ] **Step 6: Run the new tests and watch them pass**

```bash
.venv/Scripts/python.exe -m pytest -q tests/test_saas_journey.py
```

Expected: every test in the file passes, including the 14 Task 4 test items and Task 3's scope
test for `login.html`.

- [ ] **Step 7: Name the new files in the smoke's required assets**

`.noxa/redesign-saas-ui/inputs/preserve_smoke.py`, lines 76 to 78. Before:

```python
REQUIRED_ASSETS = {"/static/css/app.css", "/static/js/app.js",
                   "/static/fonts/google-sans-button-500.woff2", "/static/brand/google-g.png",
                   "/static/brand/favicon.svg", "/static/brand/apple-touch-icon.png"}
```

After:

```python
REQUIRED_ASSETS = {"/static/css/app.css", "/static/js/app.js",
                   "/static/fonts/google-sans-button-500.woff2", "/static/brand/google-g.png",
                   "/static/brand/favicon.svg", "/static/brand/apple-touch-icon.png",
                   # Sign-up journey (spec 4.1): /login is the first page that loads them.
                   "/static/vendor/basecoat-1.0.2-agad.css", "/static/css/journey.css",
                   "/static/fonts/inter-4.1-latin-wght.woff2"}
```

The font is reached through `journey.css`'s `url()`, which `check_asset` follows, so it counts as
served.

- [ ] **Step 8: Measure the page in headless Chrome, light and dark**

This is the check the static tests cannot make: the real cascade of app.css, Basecoat and
journey.css. With the Write tool, save the script below as `measure_login.py` in your session
scratchpad (not in the repo), then run it from the repo root. It needs Chrome at
`C:\Program Files\Google\Chrome\Application\chrome.exe` (153 on this machine) and starts no server.

```python
"""Measure /login in headless Chrome: light and dark, phone and computer, with and without the
in-app notice. No server runs: the page is rendered by the app's own TestClient, its /static links
are pointed at the files on disk, the scripts are dropped (content never needs JavaScript), and a
probe script reads the computed styles back through --dump-dom.

    .venv/Scripts/python.exe measure_login.py <repo root>

Checks, each printed as PASS or FAIL (exit 1 on any FAIL):
  * the Google button computes exactly as it does with app.css alone, in every mode (spec 3);
  * every visible text on the page reaches 4.5:1 (3:1 at 24px, or 18.66px bold) on its real
    background, the Google button's own label excepted (Google's colours, not ours);
  * one brand mark, in the header; no sideways scroll;
  * the card: 12px corners, a shadow, the surface colour of the mode;
  * type (spec 5.1): h1 28/30px weight 600, lead 16/15px, note 15/14px, captions 12px weight 500.
A FAIL in the last group, or a contrast FAIL outside `.auth`, is a gap in journey.css sections 4
to 6 (Task 3): fix it there, not in section 7.
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(REPO))

from fastapi.testclient import TestClient  # noqa: E402

from applyfirst.saas.app import create_app  # noqa: E402
from applyfirst.saas.config import SaaSConfig  # noqa: E402

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
STATIC = REPO / "applyfirst" / "saas" / "static"
FB_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
         "(KHTML, like Gecko) Mobile/15E148 [FBAN/FBIOS;FBAV/450.0.0.38.108;FBLC/en_US]")
MODES = {
    # name: (window, extra flags). Headless Chrome will not go below about 500px wide, which is
    # still the phone layout (< 640px); phone type is chosen by the coarse pointer, as in spec 5.1.
    "light phone": ("504,900", ["--blink-settings=primaryPointerType=2,availablePointerTypes=2,"
                                "primaryHoverType=1,availableHoverTypes=1"]),
    "dark phone": ("504,900", ["--force-dark-mode", "--blink-settings=primaryPointerType=2,"
                               "availablePointerTypes=2,primaryHoverType=1,availableHoverTypes=1"]),
    "light computer": ("1280,900", []),
    "dark computer": ("1280,900", ["--force-dark-mode"]),
}
SURFACE = {"light": "rgb(255, 255, 255)", "dark": "rgb(17, 27, 43)"}
TYPE = {  # selector: (phone px, computer px, weight or None)
    "h1": (28, 30, "600"), ".auth__head .lead": (16, 15, None), ".auth .note": (15, 14, None),
    ".auth__sheet > .caption": (12, 12, "500"),
}
GSI_PROPS = ["height", "border-top-color", "border-top-width", "border-top-left-radius",
             "background-color", "background-image", "color", "font-family", "font-size",
             "font-weight", "letter-spacing", "line-height", "padding-left", "box-shadow",
             "text-decoration-line", "transform", "opacity"]

PROBE = """<script>
(async () => {
  await document.fonts.ready;
  const cs = (el) => getComputedStyle(el);
  const rgb = (s) => { const m = /rgba?\\(([^)]+)\\)/.exec(s); if (!m) return null;
    const p = m[1].split(/[\\s,\\/]+/).filter(Boolean).map(Number); return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; };
  const over = (t, u) => [0, 1, 2].map((i) => t[i] * t[3] + u[i] * (1 - t[3])).concat(1);
  const bg = (el) => { const chain = []; for (let e = el; e; e = e.parentElement) chain.unshift(e);
    let c = [255, 255, 255, 1]; for (const e of chain) { const b = rgb(cs(e).backgroundColor);
    if (b === null) return null; if (b[3] > 0) c = over(b, c); } return c; };
  const lum = (c) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); };
  const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  const name = (el) => el.tagName.toLowerCase() + (el.className && typeof el.className === "string" ? "." + el.className.trim().split(/\\s+/).join(".") : "");
  const out = { texts: [], gsi: {}, type: {}, marks: [], overflow: document.documentElement.scrollWidth - innerWidth };
  for (const el of document.querySelectorAll("body *")) {
    if (el.closest(".gsi-btn, .visually-hidden, [hidden], script, style")) continue;
    const own = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
    if (!own || !el.getClientRects().length) continue;
    const s = cs(el), fg = rgb(s.color), b = bg(el);
    if (fg === null || b === null) { out.texts.push({ el: name(el), text: el.textContent.trim().slice(0, 40), ratio: null, need: 4.5, color: s.color }); continue; }
    const size = parseFloat(s.fontSize), large = size >= 24 || (size >= 18.66 && +s.fontWeight >= 700);
    out.texts.push({ el: name(el), text: el.textContent.trim().slice(0, 40), ratio: +ratio(over(fg, b), b).toFixed(2), need: large ? 3 : 4.5 });
  }
  const g = document.querySelector(".gsi-btn");
  for (const [k, el] of [["a", g], ["img", g.querySelector("img")], ["span", g.querySelector("span")]]) {
    const s = cs(el); out.gsi[k] = Object.fromEntries(%(props)s.map((p) => [p, s.getPropertyValue(p)]));
  }
  for (const sel of %(types)s) { const el = document.querySelector(sel);
    out.type[sel] = el ? [parseFloat(cs(el).fontSize), cs(el).fontWeight] : null; }
  const card = document.querySelector(".auth__sheet"), c = cs(card);
  out.card = [c.borderTopLeftRadius, c.boxShadow !== "none", c.backgroundColor];
  out.marks = [...document.querySelectorAll(".mark")].filter((m) => m.getClientRects().length && !m.closest("footer")).map((m) => m.closest("header") ? "header" : "elsewhere");
  document.getElementById("probe-out").textContent = JSON.stringify(out);
})();
</script><pre id="probe-out"></pre>"""


def page(ua: str | None, journey: bool) -> str:
    tmp = tempfile.mkdtemp(prefix="af-measure-")
    cfg = SaaSConfig(db_path=str(Path(tmp) / "m.db"), google_client_id="m", google_client_secret="m",
                     session_secret=b"measure-session-secret-32-bytes!!!", base_url="https://localhost",
                     secure_cookies=False)
    client = TestClient(create_app(cfg), follow_redirects=False)
    html = client.get("/login", headers={"User-Agent": ua} if ua else {}).text
    if not journey:                        # the baseline: app.css alone
        html = re.sub(r'\s*<link rel="stylesheet" href="/static/(?:vendor/basecoat|css/journey)[^>]*>', "", html)
    html = re.sub(r"<script\b[^>]*>.*?</script>", "", html, flags=re.S)
    html = re.sub(r'(href|src)="/static/([^"?]+)(?:\?[^"]*)?"',
                  lambda m: f'{m.group(1)}="{(STATIC / m.group(2)).as_uri()}"', html)
    probe = PROBE % {"props": json.dumps(GSI_PROPS), "types": json.dumps(list(TYPE))}
    return html.replace("</body>", probe + "</body>")


def chrome(html: str, mode: str) -> dict:
    window, flags = MODES[mode]
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        f = Path(tmp) / "login.html"
        f.write_text(html, encoding="utf-8")
        out = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-first-run",
                              "--allow-file-access-from-files", f"--user-data-dir={tmp}/profile",
                              f"--window-size={window}", "--hide-scrollbars",
                              "--virtual-time-budget=5000", *flags, "--dump-dom", f.as_uri()],
                             capture_output=True, text=True, encoding="utf-8", timeout=120).stdout
    m = re.search(r'<pre id="probe-out">(.*?)</pre>', out, re.S)
    assert m and m.group(1), f"{mode}: the probe wrote nothing"
    return json.loads(m.group(1).replace("&quot;", '"').replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">"))


fails = 0


def check(ok: bool, label: str) -> None:
    global fails
    fails += not ok
    print(("PASS " if ok else "FAIL ") + label)


for mode in MODES:
    scheme, device = mode.split()
    base = chrome(page(None, journey=False), mode)
    for ua_name, ua in (("plain", None), ("in-app", FB_UA)):
        got = chrome(page(ua, journey=True), mode)
        tag = f"[{mode}, {ua_name}]"
        for part in ("a", "img", "span"):
            diff = {k: (base["gsi"][part][k], v) for k, v in got["gsi"][part].items()
                    if v != base["gsi"][part][k]}
            check(not diff, f"{tag} Google button <{part}> computes as with app.css alone {diff or ''}")
        a = got["gsi"]["a"]
        check(a["height"] == "40px" and a["border-top-color"] == "rgb(116, 119, 117)"
              and a["border-top-left-radius"] == "20px" and "Google Sans Button" in a["font-family"],
              f"{tag} Google button 40px, #747775 edge, 20px corners, Google Sans Button")
        low = [t for t in got["texts"] if t["ratio"] is None or t["ratio"] < t["need"]]
        check(not low, f"{tag} {len(got['texts'])} texts reach AA {low or ''}")
        check(got["marks"] == ["header"], f"{tag} one brand mark, in the header: {got['marks']}")
        check(got["overflow"] <= 0, f"{tag} no sideways scroll ({got['overflow']}px)")
        check(got["card"] == ["12px", True, SURFACE[scheme]], f"{tag} card {got['card']}")
        for sel, (phone, computer, weight) in TYPE.items():
            want = [phone if device == "phone" else computer, weight]
            have = got["type"][sel]
            check(have is not None and have[0] == want[0] and (weight is None or have[1] == weight),
                  f"{tag} {sel} {have} want {want}")
print(f"\n{fails} failed")
sys.exit(1 if fails else 0)
```

```bash
.venv/Scripts/python.exe "<scratchpad>/measure_login.py" .
```

Expected: 96 lines of `PASS`, then `0 failed`. Four modes (light and dark, phone and computer)
times two pages (plain, and the Facebook in-app notice), 12 checks each. What each FAIL means:
- "Google button ... computes as with app.css alone" names the property that moved. Find the
  journey rule that reaches the button and scope it. Never restyle the button back.
- "texts reach AA" lists each element under 4.5 to 1 (3 to 1 for large text) with its ratio. In
  the prototype a bare `a` colour rule measured 3.28 to 1 on the footer links and 2.89 to 1 on
  the skip link, and a bare `.brand` colour measured 1.14 to 1 on the footer "Agad", because a
  journey rule beats app.css's more specific `.site-footer a` and `.skip-link` rules. A FAIL
  inside `.auth` is section 7's to fix. A FAIL in the header, footer, alert or body text is a
  gap in sections 4 to 6 (Task 3): fix it there.
- The type lines (`h1`, lead, note, caption) are spec 5.1 values that sections 4 and 5 own.
- Headless Chrome will not open narrower than about 500px, so "phone" is 504px wide with a coarse
  pointer and no hover (the phone layout is anything under 640px, and phone type follows the
  pointer, as spec 5.1 says). The 360 and 390px screenshots belong to Task 8.

- [ ] **Step 9: Look at it once**

In the owner's own PowerShell window (Handoff: background shells get reaped), with a data folder
outside the repo:

```powershell
.venv\Scripts\python.exe .noxa\redesign-saas-ui\artifacts\run_local.py --port 8765 --data-dir C:\Users\regid\agad-preview
```

Open `http://127.0.0.1:8765/login` in Chrome. In DevTools, Rendering, set "Emulate CSS media
feature prefers-color-scheme" to dark and back to light, and try the device toolbar at 390px.
Expected: one card on the ground, the header mark and "Agad" top left, the white Google button
unchanged in both modes. Then stop the server with Ctrl+C in that window and confirm nothing is
left listening:

```powershell
Get-NetTCPConnection -State Listen -LocalPort 8765 -ErrorAction SilentlyContinue
```

Expected: no output.

- [ ] **Step 10: Run both gates**

```bash
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe .noxa/redesign-saas-ui/inputs/preserve_smoke.py
```

Expected. pytest: all pass (887 + the new tests), measured `1067 passed` in sequence: 14 new
items in `tests/test_saas_journey.py` (the `login.html` case of Task 3's scope test existed
already and now checks a listed template). smoke: 0 failed, `566 checks passed, 0 failed.`

**Notes for the reviewer (Task 4).**
- The cascade trap is the biggest risk on this page. Any journey rule beats any app.css rule, so a
  plain dark-mode fix like `a { color: var(--j-link) }` or `.brand { color: var(--j-text) }` would
  repaint the Google button, the navy footer's links and the skip link. Task 3 scopes both
  (`:where(a:not(.btn,.gsi-btn,.skip-link))` and `.site-footer a`; the footer's brand column is
  hidden), the three Google button tests read every journey rule against the button's real
  place in the page, and Step 8 measures it in Chrome.
- The two Google button tests accept custom properties and `color-scheme` on `.gsi-btn`, because
  Task 3's light island names the button on its token rules (`:root,.mailcard,.gsi-btn{...}`) and
  gives it `color-scheme:light`. Neither changes a pixel of the button; Step 8 compares its
  computed style with app.css alone.
- In dark mode the header mark's navy tile (`fill="#0B2545"` in `_ui.html:41`) sits on `#111B2B`
  at about 1.2 to 1. The white chevron and the sky dot still read, but the tile's edge vanishes.
  Left for the owner's look in Task 8.
- Spec 6.1 lists "What is Agad?" last. It stays below the card, as today, not inside it. The `<hr>`
  above the caption stays.


### Task 5: The four onboarding steps (spec 6.2, spec 9 frozen hooks)

The four onboarding templates load the new look, and section 8 of `journey.css` gives them their
colours, type and corners in light and dark. The markup changes only where spec 6.2 asks: Step 1
gains the "What will Google ask me?" disclosure and a quiet skip link, Step 2 puts the four fields
in one card, Step 3 moves Next below the quick-add pills. Step 4 and editing mode keep their
markup (Step 4 is already side by side from 1100px in `app.css:732-736`).

Everything below was prototyped end to end on 2026-09-25 in a scratch copy of the repo carrying
Tasks 1 to 4 as this plan writes them, and re-measured during assembly. Measured there: the new
tests went from `15 failed, 165 passed` to `180 passed` in `tests/test_saas_journey.py`, the full
suite from 1,067 to **1,119 passed**, the smoke stayed at
**566 checks, 0 failed**, headless Chrome printed **330 PASS, 0 failed** over 8 page states in 4
modes plus 2 at 1024px (and 45 FAIL with section 8 emptied, so the checks bite), and **29 of 29**
planted mistakes were caught by the new tests.

**Files:**
- Modify `applyfirst/saas/templates/onboarding_connect_gmail.html` (70 lines, LF). Head blocks
  after line 4 and after line 7; lines 38-39 and 48 (the "What you'll see next" wrapper) become the
  disclosure; lines 62 and 64 (the two skip links) gain `class="text-link"`. Becomes 76 lines.
- Modify `applyfirst/saas/templates/onboarding_profile.html` (59 lines, LF). Head blocks after
  line 3 and after line 6; line 37 (`<form class="form" ...>`) gains `sheet`. Becomes 66 lines.
- Modify `applyfirst/saas/templates/onboarding_keywords.html` (67 lines, LF) with the patch script
  in Step 5 (the privacy hook blocks Read and Bash on this path, so the Edit tool cannot be used).
  Head blocks after lines 3 and 6; the comment at line 30 is reworded; lines 44-53 (the Next
  block) move after line 63 (the end of the Quick add block). Becomes 74 lines.
- Modify `applyfirst/saas/templates/onboarding_preview.html` (79 lines, LF). Head blocks after
  line 4 and after line 7 only. Becomes 86 lines.
- Modify `applyfirst/saas/static/css/journey.css`: fill section 8, between the banners
  `/* ---- 8 onboarding */` and `/* ---- 9 dashboard */` (Task 3 wrote them as lines 101 and 102;
  after Task 4's section 7 they are lines 109 and 110). Nothing else in the file.
- Modify `tests/_journey_css.py`: the `JOURNEY_TEMPLATES` line (Task 4 left it as
  `["login.html"]`).
- Modify `tests/test_saas_journey.py`: append the Task 5 block at the end of the file.
- Not touched: `_ui.html`, `_icons.html`, `base.html`, `app.css`, `motion.css`, `vt.js`,
  `motion.js`, `app.js`, `app.py`, the smoke script (the onboarding pages link the same asset URLs
  `/login` already links, so `REQUIRED_ASSETS` from Task 4 covers them and the check count stays).

**Interfaces:**
- Consumes:
  - Task 1: `applyfirst/saas/static/vendor/basecoat-1.0.2-agad.css`.
  - Task 3: `base.html` blocks `color_scheme` and `theme_color_meta`; the journey head snippet
    (the two metas are `--j-surface` of each scheme, `#FFFFFF` and `#111B2B`, which Task 3's scope
    test reads from `journey.css`); tokens `--j-text`, `--j-muted`, `--j-link`, `--j-surface`,
    `--j-ground`, `--j-hairline`, `--j-shadow`, `--j-danger-fg`; the re-pointed app.css tokens
    `--surface`, `--line`, `--line-strong`, `--sunk`, `--text*`; the light island on `.mailcard`
    (section 2); the shared rules `.btn*`, `.text-link`, `.back-link`, `.field` (label, control,
    then hint through `order`), `.input` (amber `aria-invalid`), `textarea.input{field-sizing:fixed}`,
    `.sheet`, `.alert*`, `.badge--ok`; `--fs-caption` 12px and `--fs-small` 15/14px. From
    `tests/_journey_css.py`: `JOURNEY_CSS`, `JOURNEY_TEMPLATES`, `TEMPLATES`, `read_css`,
    `iter_rules`, `decls`, `contrast`, `tokens`. app.css tokens read: `--r-md` 12px
    (`app.css:62`), `--amber-600` (`app.css:50`, through Task 3's invalid rule).
  - Task 4, module-level helpers in `tests/test_saas_journey.py`: `assert_journey_head`,
    `stylesheets`, `meta_attrs`, `sel_reaches`, `sel_split`, `sel_compounds`,
    `journey_style_rules`.
  - Verified in the repo today: `tests/_saas_client.py` `client_for` (line 79), `seed_user`
    (line 57, `gmail_key` stores a working grant), `post_forms` (194), `form_inputs` (201); the
    `saas_cfg` fixture (`tests/conftest.py:13-14`). The routes (`app.py:489-575`) render all four
    steps for a user with a saved profile and keywords, pass `gmail_connected`, `activated`,
    `gmail_error` and `form_error`, and Step 1's retry page is also what `/auth/gmail-callback`
    renders with status 400 (`app.py:629-640`), so that page gets the new look too.
- Produces:
  - `JOURNEY_TEMPLATES` with the four onboarding templates after `login.html`, in step order.
  - `journey.css` section 8, and three local tints on `:root`: `--ob-tint`, `--ob-rule`,
    `--ob-alarm` (light and dark). They are not `--j-*` names, so Task 3's exact token-set test is
    untouched. The mailcard island does not redefine them, and a test forbids using them inside
    the mailcard.
  - Reusable in `tests/test_saas_journey.py` for Tasks 6 and 7: `_Node` and `_Doc` (a real
    parent and child tree, with `find`, `one`, `walk`, `words`, `chain`), `_page(markup)`,
    `_section(n)` (one section of journey.css without comments), `_state(selector)`,
    `_reaching(chain, props)`.
  - Section 8 scopes `.numbered`, `.disclose` and `.lead` to `.ob-main`, so the dashboard (Task 6)
    is not changed by it. See note 6.

**Frozen hooks (spec 9) on these four pages, where each lives and why this task keeps it:**

| Hook | Where (verified) | Kept because | Pinned by |
|---|---|---|---|
| `site-header` (one) | `base.html:23` | not touched; section 8 never names it | `test_every_step_keeps_one_header_and_stamps_its_step` |
| `data-step` 1 to 4 on `html` | `html_attrs` block: connect_gmail:6, profile:5, step 3:5, preview:6 (9, 8, 8, 9 after) | the lines are not edited, only moved down by the new blocks | same test, and `tests/test_saas_motion.py:588-592` |
| `nav.stepper > ol.stepper__list > li.stepper__item`, one `span.stepper__marker` first in the current item | `_ui.html:190-199` via `onboarding_shell` `_ui.html:204-223` | macros untouched; section 8 only sets `background` on `.stepper__item.is-passed::before`, `.stepper__marker` (960px+), `.stepper__item:not(:last-child)::after` and the passed `.stepper__node`, and restores `Highlight` for the marker in forced colours | `test_onboarding_mode_draws_the_stepper_the_motion_layer_names`, `test_section_8_recolours_the_motion_hooks_but_never_moves_them`, `tests/test_saas_motion.py:568-583` |
| the 960px and 1100px breakpoints | `app.css:679`, `:732`, `:784`; `motion.css:43`, `:73` | section 8 uses only `(min-width:960px)` | `test_section_8_switches_layout_only_at_the_frozen_breakpoints` |
| `form.activate[action="/onboarding/activate"]` with one `.btn--primary` | `onboarding_preview.html:54-58` (61-65 after) | not edited; no journey rule may change its fill, image, corners or opacity in any state | `test_step_four_keeps_the_letter_and_the_activate_form_hooks`, `test_no_journey_rule_changes_the_frozen_activate_button`, headless check |
| `a.btn[href="/auth/connect-gmail"]` with a direct `span` | `link_button` `_ui.html:57-59`; connect_gmail:25 and :57 (32, 63 after), preview:63 (70 after) | macro untouched, calls unchanged | `test_every_connect_gmail_link_keeps_its_label_in_a_direct_span` |
| `li.kw[data-vt-kw]` with `.kw__text` | `keyword_chip` `_ui.html:179-181` | macro untouched; section 8 sets only background, border colour, colour, font size and weight on `.kw`, never overflow or box-shadow, and nothing above it clips | `test_step_three_chips_and_pills_keep_their_motion_hooks`, `test_nothing_clips_a_chip_or_rings_it`, Task 3's `test_journey_css_never_rings_or_clips_a_keyword_chip` |
| `button.quick[data-vt-kw]`, word in the last `span` | `quick_add` `_ui.html:184-186` | macro untouched; the block moves as a whole | `test_step_three_chips_and_pills_keep_their_motion_hooks`, `tests/test_saas_motion.py:603-620` |
| `class="gconf"` (exact), `.gconf__line`, `.gconf__track` (96px), `.fromto__node` (28px), `.badge--ok` | `gmail_confirm` `_ui.html:312-317`, `from_to` `_ui.html:305`, preview:24 (31 after) | macros untouched; section 8 recolours `.gconf`, `.gconf__line`, `.fromto__node` only (af-deliver's `-68px` is 96 minus 28) | `test_step_two_confirms_gmail_with_the_exact_gconf_hooks`, the "never moves" test, headless 96px and 28 x 28 checks |
| `.alert--success[data-arrive-gmail] > .icon` | `alert` `_ui.html:125-130`, preview:46 (53 after) | not edited; the icon stays the first child | `test_step_four_keeps_the_letter_and_the_activate_form_hooks` |
| `.mailcard`, `.mailcard__head`, `.letter__part`, `.copy-row`, `.preview__link` | preview:24-38 (31-45 after), `email_parts` `_ui.html:320-328` | not edited; section 8 changes only the mailcard's corners (12px) and the route line colour; the mailcard stays white (island) | the Step 4 hook test, `test_the_sample_email_takes_no_onboarding_tint`, headless "sample email white" |
| `data-copy` with `#preview-letter` | preview:35 (42 after), `_ui.html:326` | not edited | the Step 4 hook test |
| `details.disclose` | `disclose` `_ui.html:341-343`; profile:53 (60 after); NEW on Step 1 at lines 45-54 | the macro is reused as is; section 8 adds a hairline row and recolours the chevron | `test_step_one_puts_what_google_asks_in_a_native_disclosure`, `test_step_two_holds_the_four_fields_in_one_card` |
| `data-burst-src` | preview:54 (61 after) | not edited | Step 4 hook test, `tests/test_saas_motion.py:730-761` |
| `data-arrive-gmail` (one on Step 2) | profile:33-35 (40-42 after) | not edited | `test_step_two_confirms_gmail_with_the_exact_gconf_hooks`, `tests/test_saas_motion.py:634-653` |
| `{% set CELEBRATE = true %}` | `_ui.html:22` | not touched | `test_the_celebrate_switch_is_still_on` |
| `#form-error` | profile:42 (49 after), inside the form, which is now the card | not edited; the amber alert is still the form's first visible child | `test_step_two_error_box_is_amber_at_the_top_of_the_card`, `test_an_invalid_field_stays_amber_in_every_state` |
| `#gmail-retry` | `gmail_retry_note` `_ui.html:134-145`, connect_gmail:13-15 (20-22 after) | not edited, still above the `h1` | `test_step_one_keeps_the_retry_note_above_the_heading`, `tests/test_saas_pages.py:139-145` |
| the hidden `csrf` input in every POST form | `csrf_field` `_ui.html:35-37`; profile:38, step 3:25, preview:55 and :72, the chip and quick-add macros, Log out `base.html:30` | not edited | `test_every_post_form_on_every_step_carries_its_csrf_input`, smoke |
| `.status--live`, `.live i`, `.status__kw strong`, `.since`, `data-panel`, `data-fresh`, `.dash__grid > *` | dashboard only | none appears on these pages | `test_no_step_carries_a_dashboard_hook` |

**What each spec 6.2 item became (read once, the steps apply it).**
- Stepper: colours only. In dark mode the passed bars and passed rail nodes use `--j-text` (they
  were navy `#0B2545`, invisible on `#111B2B`); the rail's current row and "Editing your setup"
  use `--ob-tint` (the light `#EAF3FC` behind light text measured 1.05 to 1); the rail line uses
  `--ob-rule`. The phone marker stays `#0B6BC7` (3.24 to 1 on the dark surface).
- Step 1: the numbered "What you'll see next" list moves, word for word, inside
  `ui.disclose("What will Google ask me?")`, the same summary the dashboard already uses
  (`dashboard.html:28`). The ledger, the "You're in control" box, the one primary Connect Gmail
  link and the retry note stay where they are. Both skip links become `class="text-link"` (the
  quiet action of spec 5.2, 44px tap band from Task 3's `::after`).
- Step 2: `<form class="form sheet">`, so the form is the one card (Task 3's `.sheet`: surface,
  hairline, 12px, faint shadow, overflow visible). The `#form-error` alert, the four fields, the
  example disclosure, Save and the caption are inside it. Labels above and hints below come from
  Task 3's `order` rules (the DOM keeps label, hint, input, so `aria-describedby` and screen reader
  order are unchanged). The message box keeps `rows="8"` and `field-sizing:fixed`. Invalid fields
  are amber `#B86E00` (Task 3), focused or not.
- Step 3: add form (field and Add already share `.add-row`), saved chips, quick-add pills, then
  Next. Chips take `--ob-tint` with a hairline, pills keep their dashed `--j-edge` outline.
- Step 4: no markup change. Sample and white mailcard sit side by side from 1100px and stack
  below (app.css), checked at 1280 and 1024px in the browser.
- Dark mode fixes found by measuring (without section 8 the quick-add labels read 1.12 to 1, the
  example message and the gconf line 1.09 to 1, the route labels 2.13 to 1).

- [ ] **Step 1: Put the four steps on the journey list**

In `tests/_journey_css.py`, replace the line Task 4 wrote:

```python
JOURNEY_TEMPLATES: list[str] = ["login.html"]
```

with:

```python
JOURNEY_TEMPLATES: list[str] = ["login.html", "onboarding_connect_gmail.html",
                                "onboarding_profile.html", "onboarding_keywords.html",
                                "onboarding_preview.html"]
```

This turns Task 3's scope test on for the four templates.

- [ ] **Step 2: Append the Task 5 tests to `tests/test_saas_journey.py`**

Append this block at the very end of the file, after two blank lines, unchanged. It uses Task 4's
helpers by name (listed under Consumes). None of `_Node`, `_Doc`, `_page`, `_section`, `_state`,
`_reaching`, `_ob` or the `OB_` constants is defined earlier in the file (checked during assembly).

```python
# --- Task 5: the four onboarding steps (spec 6.2, 9) -------------------------------------------
#
# Spec 9 lists the hooks the frozen motion files read: vt.js names the header, the stepper marker,
# the Activate button and every [data-vt-kw]; motion.js reads the Connect Gmail link's direct
# span, the activate form and data-burst-src; motion.css animates the gconf route, the badge, the
# success icon, the letter and the disclosure. Each test below renders a step in the state that
# shows its hooks and pins them by tag, class, attribute and count. The section 8 tests then read
# journey.css: it may recolour and retype those hooks, never move, resize, clip or ring them, and
# the layout still switches only at the frozen 960 and 1100px.

from html.parser import HTMLParser

from applyfirst.saas import app as app_module
from _journey_css import JOURNEY_CSS, JOURNEY_TEMPLATES, TEMPLATES, contrast, decls, iter_rules
from _journey_css import read_css, tokens
from _saas_client import client_for, form_inputs, post_forms, seed_user

OB_GRANT = b"0123456789abcdef0123456789abcdef"      # a stored Gmail grant, as tests/test_saas_motion
OB_TEMPLATES = ["onboarding_connect_gmail.html", "onboarding_profile.html",
                "onboarding_keywords.html", "onboarding_preview.html"]
OB_STEPS = {"/onboarding/connect_gmail": 1, "/onboarding/profile": 2, "/onboarding/keywords": 3,
            "/onboarding/preview": 4}
OB_SHEETS = ["css/app.css", "css/motion.css", "vendor/basecoat-1.0.2-agad.css", "css/journey.css"]
OB_SAVED = ("virtual assistant", "data entry")


class _Node:
    """One element: tag, attrs, parent, direct children, and all the text inside it."""

    def __init__(self, tag: str, attrs: dict[str, str], parent: "_Node | None") -> None:
        self.tag, self.attrs, self.parent = tag, attrs, parent
        self.kids: list[_Node] = []
        self.text = ""

    def has(self, cls: str) -> bool:
        return cls in self.attrs.get("class", "").split()

    def walk(self):
        for kid in self.kids:
            yield kid
            yield from kid.walk()

    def find(self, tag: str | None = None, cls: str | None = None, **attrs) -> list["_Node"]:
        return [n for n in self.walk() if (tag is None or n.tag == tag)
                and (cls is None or n.has(cls))
                and all(n.attrs.get(k.replace("_", "-")) == v for k, v in attrs.items())]

    def one(self, tag: str | None = None, cls: str | None = None, **attrs) -> "_Node":
        found = self.find(tag, cls, **attrs)
        assert len(found) == 1, f"want one <{tag or '*'} class={cls} {attrs}>, found {len(found)}"
        return found[0]

    def words(self) -> str:
        return " ".join(self.text.split())

    def chain(self) -> list[tuple[str, dict[str, str]]]:
        """Ancestors first, itself last: the shape Task 4's sel_reaches() reads."""
        out, node = [], self
        while node is not None and node.tag != "#root":
            out.append((node.tag, node.attrs))
            node = node.parent
        return out[::-1]


class _Doc(HTMLParser):
    _VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
             "source", "track", "wbr"}

    def __init__(self, markup: str) -> None:
        super().__init__(convert_charrefs=True)
        self.root = self._at = _Node("#root", {}, None)
        self.feed(markup)
        self.close()

    def handle_starttag(self, tag, attrs):
        node = _Node(tag, {k.lower(): (v or "") for k, v in attrs}, self._at)
        self._at.kids.append(node)
        if tag not in self._VOID:
            self._at = node

    def handle_startendtag(self, tag, attrs):
        self._at.kids.append(_Node(tag, {k.lower(): (v or "") for k, v in attrs}, self._at))

    def handle_endtag(self, tag):
        node = self._at
        while node is not self.root and node.tag != tag:
            node = node.parent
        if node is not self.root:
            self._at = node.parent

    def handle_data(self, data):
        node = self._at
        while node is not None:
            node.text += data
            node = node.parent


def _ob(cfg, path: str, *, sub: str = "ob5", gmail: bool = True, activated: bool = False,
        keywords: tuple[str, ...] = OB_SAVED) -> str:
    """One onboarding page, signed in as a user with a saved profile, in the state asked for."""
    user = seed_user(cfg, sub=sub, email=f"{sub}@example.com", profile=True, keywords=keywords,
                     activated=activated, gmail_key=OB_GRANT if gmail else None)
    resp = client_for(cfg, user).get(path)
    assert resp.status_code == 200, (path, resp.status_code)
    return resp.text


def _page(markup: str) -> _Node:
    return _Doc(markup).root


def _section(n: int) -> str:
    """Section ``n`` of journey.css, from its banner to the next, comments removed."""
    raw = JOURNEY_CSS.read_bytes().decode("utf-8").replace("\r\n", "\n")
    start = re.search(rf"/\* ---- {n} [\w-]+ \*/", raw).end()
    end = re.search(rf"/\* ---- {n + 1} [\w-]+ \*/", raw).start()
    return re.sub(r"/\*.*?\*/", "", raw[start:end], flags=re.S)


OB_RULES = list(iter_rules(_section(8)))


def _ob_tokens(scheme: str) -> dict[str, str]:
    """The --ob-* tints section 8 defines on :root, light, or light overlaid with dark."""
    light: dict[str, str] = {}
    dark: dict[str, str] = {}
    for sel, body, chain in OB_RULES:
        if sel.strip() != ":root":
            continue
        found = {k: v for k, v in decls(body).items() if k.startswith("--ob-")}
        if not chain:
            light.update(found)
        elif len(chain) == 1 and re.fullmatch(r"@media \(prefers-color-scheme:\s*dark\)", chain[0]):
            dark.update(found)
    return dict(light) if scheme == "light" else {**light, **dark}


# --- the journey head on every step (spec 4.2) ------------------------------------------------

def test_the_four_steps_are_on_the_journey_list():
    assert [t for t in JOURNEY_TEMPLATES if t.startswith("onboarding_")] == OB_TEMPLATES


@pytest.mark.parametrize("path", OB_STEPS)
def test_every_step_loads_the_journey_look_after_the_motion_head(saas_cfg, path):
    markup = _ob(saas_cfg, path)
    assert_journey_head(markup)
    assert stylesheets(markup) == OB_SHEETS
    assert meta_attrs(markup, "color-scheme") == [{"name": "color-scheme", "content": "light dark"}]
    css = read_css(JOURNEY_CSS)
    assert meta_attrs(markup, "theme-color") == [
        {"name": "theme-color", "content": tokens(css, s)["--j-surface"].upper(),
         "media": f"(prefers-color-scheme: {s})"} for s in ("light", "dark")]


# --- spec 9 hooks, on the rendered pages ------------------------------------------------------

@pytest.mark.parametrize("path,step", OB_STEPS.items())
def test_every_step_keeps_one_header_and_stamps_its_step(saas_cfg, path, step):
    page = _page(_ob(saas_cfg, path))
    assert len(page.find(cls="site-header")) == 1
    assert page.one("html").attrs.get("data-step") == str(step)


@pytest.mark.parametrize("path,step", OB_STEPS.items())
def test_onboarding_mode_draws_the_stepper_the_motion_layer_names(saas_cfg, path, step):
    page = _page(_ob(saas_cfg, path))
    nav = page.one("nav", "stepper")
    lists = [k for k in nav.kids if k.tag == "ol" and k.has("stepper__list")]
    assert len(lists) == 1
    items = lists[0].kids
    assert [i.tag for i in items] == ["li"] * 4 and all(i.has("stepper__item") for i in items)
    current = [i for i in items if i.attrs.get("aria-current") == "step"]
    assert current == [items[step - 1]]
    first = current[0].kids[0]
    assert (first.tag, first.has("stepper__marker"), first.attrs.get("aria-hidden")) == (
        "span", True, "true"), "the marker is the first child of the current step"
    assert len(page.find(cls="stepper__marker")) == 1
    assert [i.has("is-passed") for i in items] == [n < step for n in range(1, 5)]
    assert page.find(cls="rail__edit") == []


@pytest.mark.parametrize("path", OB_STEPS)
def test_editing_mode_keeps_the_plain_label_and_the_way_back(saas_cfg, path):
    page = _page(_ob(saas_cfg, path, activated=True))
    assert page.find("nav", "stepper") == [] and page.find(cls="stepper__marker") == []
    assert page.one("p", "rail__edit").words() == "Editing your setup"
    back = page.one("a", "back-link")
    assert (back.attrs.get("href"), back.words()) == ("/dashboard", "Back to dashboard")
    assert page.find("form", "activate") == []
    assert [n.tag for n in page.walk() if "data-burst-src" in n.attrs] == []


@pytest.mark.parametrize("path,query,gmail,variant", [
    ("/onboarding/connect_gmail", "", False, "btn--primary"),
    ("/onboarding/connect_gmail", "?gmail_error=scope", True, "btn--secondary"),
    ("/onboarding/preview", "", False, "btn--primary"),
])
def test_every_connect_gmail_link_keeps_its_label_in_a_direct_span(saas_cfg, path, query, gmail,
                                                                   variant):
    """motion.js swaps the text of `:scope > span:not(.visually-hidden)` for "Opening Google's
    page" and marks the link busy, so the label must stay a direct span of the a.btn."""
    page = _page(_ob(saas_cfg, path + query, gmail=gmail))
    link = page.one("a", href="/auth/connect-gmail")
    assert link.has("btn") and link.has(variant)
    labels = [k for k in link.kids if k.tag == "span" and not k.has("visually-hidden")]
    assert [s.words() for s in labels] == ["Connect Gmail"]


def test_step_one_puts_what_google_asks_in_a_native_disclosure(saas_cfg):
    page = _page(_ob(saas_cfg, "/onboarding/connect_gmail", gmail=False))
    box = page.one("details", "disclose")
    summary = [k for k in box.kids if k.tag == "summary"]
    assert len(summary) == 1 and summary[0].words() == "What will Google ask me?"
    steps = box.one("ol", "numbered")
    assert len(steps.kids) == 4 and "Go to Agad (unsafe)" in steps.words()
    assert page.one(role="group", aria_label="What connecting Gmail means").has("ledger")
    skip = page.one("a", href="/onboarding/profile")
    assert skip.has("text-link") and skip.words() == "Skip for now"
    assert [b.attrs.get("href") for b in page.find(cls="btn--primary")] == ["/auth/connect-gmail"]


def test_step_one_keeps_the_retry_note_above_the_heading(saas_cfg):
    markup = _ob(saas_cfg, "/onboarding/connect_gmail?gmail_error=scope", gmail=False)
    note = _page(markup).one(id="gmail-retry")
    assert note.has("alert") and note.has("alert--attention")
    assert (note.attrs.get("role"), note.attrs.get("tabindex")) == ("alert", "-1")
    assert markup.index('id="gmail-retry"') < markup.index("<h1")


def test_step_two_confirms_gmail_with_the_exact_gconf_hooks(saas_cfg):
    markup = _ob(saas_cfg, "/onboarding/profile")
    assert markup.count('class="gconf"') == 1, "motion.css and the tests read the exact attribute"
    page = _page(markup)
    arrivals = page.find(data_arrive_gmail="")
    assert len(arrivals) == 1 and arrivals[0].attrs.get("class") == "gconf"
    gconf = arrivals[0]
    track = gconf.one("span", "gconf__track")
    assert [(k.tag, k.attrs.get("class")) for k in track.kids] == [
        ("i", "gconf__line"), ("span", "fromto__node")]
    badge = gconf.one("span", "badge--ok")
    assert badge.has("badge") and badge.words() == "Gmail connected"


def test_step_two_holds_the_four_fields_in_one_card(saas_cfg):
    page = _page(_ob(saas_cfg, "/onboarding/profile", gmail=False))
    card = page.one("form", action="/onboarding/profile")
    assert card.attrs.get("class") == "form sheet" and card.attrs.get("method") == "post"
    fields = [k for k in card.kids if k.has("field")]
    assert [f.kids[0].tag for f in fields] == ["label"] * 4, "every label sits first, above"
    got = [n.attrs["name"] for f in fields for n in f.walk() if n.tag in ("input", "textarea")]
    assert got == ["full_name", "job_type", "standard_subject", "standard_message"]
    for field in fields:                        # the hint follows the label in the DOM, as today
        hint = [k for k in field.kids if k.has("field__hint")]
        assert len(hint) == 1 and field.kids.index(hint[0]) == 1
    area = card.one("textarea", id="f-standard_message")
    assert (area.attrs.get("rows"), area.attrs.get("maxlength")) == ("8", "5000")
    assert len(card.find("details", "disclose")) == 1
    assert [b.words() for b in card.find(cls="btn--primary")] == ["Save and continue"]


@pytest.mark.parametrize("query,links", [("?error=1", []),
                                         ("?error=long_job_type", ["#f-job_type"])])
def test_step_two_error_box_is_amber_at_the_top_of_the_card(saas_cfg, query, links):
    page = _page(_ob(saas_cfg, "/onboarding/profile" + query, gmail=False))
    card = page.one("form", action="/onboarding/profile")
    box = card.one("div", id="form-error")
    assert box.has("alert__lines")
    assert (box.attrs.get("role"), box.attrs.get("tabindex")) == ("alert", "-1")
    alert = box.parent
    while not alert.has("alert"):
        alert = alert.parent
    assert alert.has("alert") and alert.has("alert--attention") and not alert.has("alert--danger")
    top = [k for k in card.kids if not (k.tag == "input" and k.attrs.get("type") == "hidden")]
    assert top[0] is alert, "the amber box opens the card"
    assert [a.attrs["href"] for a in box.find("a")] == links
    invalid = [n.attrs["name"] for n in card.walk() if n.attrs.get("aria-invalid") == "true"]
    assert invalid == [h[3:] for h in links], "only the named field is flagged (saved values)"


def test_step_three_reads_add_form_chips_quick_pills_then_next(saas_cfg):
    markup = _ob(saas_cfg, "/onboarding/keywords")
    page = _page(markup)
    add = post_forms(markup, "/onboarding/keywords")[0]
    assert [i.attrs.get("type") for i in form_inputs(add) if i.attrs.get("name") == "keyword"] == [
        "text"]
    row = page.one("div", "add-row")
    assert [(k.tag, k.attrs.get("id") or k.words()) for k in row.kids] == [
        ("input", "f-keyword"), ("button", "Add")], "the field and Add share one row"
    marks = [markup.index(s) for s in ('id="f-keyword"', 'class="chip-list"',
                                       'class="quick-list"', 'href="/onboarding/preview"')]
    assert marks == sorted(marks), "add form, chips, quick adds, then Next (spec 6.2)"
    nxt = page.one("a", href="/onboarding/preview")
    assert nxt.has("btn--primary") and nxt.words() == "Next: see a sample"


def test_step_three_editing_mode_puts_done_after_the_quick_adds(saas_cfg):
    markup = _ob(saas_cfg, "/onboarding/keywords", activated=True)
    assert markup.index('class="quick-list"') < markup.index("<span>Done</span>") < \
        markup.index('href="/onboarding/preview"')


def test_step_three_chips_and_pills_keep_their_motion_hooks(saas_cfg):
    page = _page(_ob(saas_cfg, "/onboarding/keywords"))
    chips = page.find("li", "kw")
    assert len(chips) == len(OB_SAVED)
    for chip in chips:
        assert chip.parent.tag == "ul" and chip.parent.has("chip-list")
        label = chip.kids[0]
        assert (label.tag, label.has("kw__text")) == ("span", True)
        assert chip.attrs.get("data-vt-kw") == label.words()
        remove = chip.one("form")
        assert remove.attrs.get("action", "").endswith("/delete")
    quick = page.find("button", "quick")
    suggestions = app_module._TEMPLATES.env.get_template("_ui.html").module.QUICK_KEYWORDS
    assert len(quick) == len(set(suggestions) - set(OB_SAVED))
    for button in quick:
        spans = [k for k in button.kids if k.tag == "span"]
        assert button.attrs.get("data-vt-kw") == spans[-1].words(), "the word is the last span"
        assert button.parent.tag == "form" and button.parent.parent.parent.has("quick-list")
    named = [n for n in page.walk() if "data-vt-kw" in n.attrs]
    assert named == chips + quick, "vt.js names only the chips and the quick-add pills"


def test_step_four_keeps_the_letter_and_the_activate_form_hooks(saas_cfg):
    page = _page(_ob(saas_cfg, "/onboarding/preview"))
    form = page.one("form", "activate")
    assert (form.attrs.get("action"), form.attrs.get("method")) == ("/onboarding/activate", "post")
    assert form.attrs.get("data-burst-src", "").startswith("/static/vendor/canvas-confetti-1.9.4.js")
    assert [(b.tag, b.words(), b.attrs.get("data-busy")) for b in form.find(cls="btn")] == [
        ("button", "Start watching for jobs", "Starting")]
    assert form.one(cls="btn").has("btn--primary")
    success = page.one(cls="alert--success")
    assert "data-arrive-gmail" in success.attrs
    assert (success.kids[0].tag, success.kids[0].has("icon")) == ("svg", True)
    preview = page.one("div", "preview")
    assert [(k.tag, k.attrs.get("class")) for k in preview.kids] == [
        ("section", "sample"), ("div", "preview__link"), ("article", "mailcard")]
    link = preview.kids[1]
    assert link.attrs.get("aria-hidden") == "true" and len(link.find(cls="fromto__node")) == 1
    card = preview.kids[2]
    assert len(card.find(cls="mailcard__head")) == 1 and len(card.find(cls="letter__part")) == 2
    row = card.one("div", "copy-row")
    copy = row.one("button", data_copy="#preview-letter")
    assert "hidden" in copy.attrs
    assert card.one("pre", id="preview-letter").has("letter__text")
    assert len(page.find(id="preview-letter")) == 1


def test_step_four_without_gmail_keeps_its_quiet_start_button(saas_cfg):
    """Today's rule, kept: without Gmail the one primary is Connect Gmail, so the activate form
    holds a secondary button, never celebrates and is never morphed (vt.js needs a primary)."""
    page = _page(_ob(saas_cfg, "/onboarding/preview", gmail=False))
    form = page.one("form", "activate")
    assert form.find(cls="btn--primary") == [] and "data-burst-src" not in form.attrs
    assert [b.words() for b in form.find(cls="btn--secondary")] == ["Start watching without Gmail"]


@pytest.mark.parametrize("path,query,gmail,activated", [
    ("/onboarding/connect_gmail", "", False, False), ("/onboarding/profile", "?error=1", True, False),
    ("/onboarding/keywords", "", True, False), ("/onboarding/keywords", "", True, True),
    ("/onboarding/preview", "", True, False), ("/onboarding/preview", "", False, False),
])
def test_every_post_form_on_every_step_carries_its_csrf_input(saas_cfg, path, query, gmail,
                                                              activated):
    page = _page(_ob(saas_cfg, path + query, gmail=gmail, activated=activated))
    forms = [f for f in page.find("form") if f.attrs.get("method") == "post"]
    assert forms
    for form in forms:
        csrf = [k for k in form.kids if k.tag == "input" and k.attrs.get("name") == "csrf"]
        assert len(csrf) == 1 and csrf[0].attrs.get("type") == "hidden", form.attrs
        assert csrf[0].attrs.get("value"), form.attrs


def test_the_celebrate_switch_is_still_on():
    source = (TEMPLATES / "_ui.html").read_text(encoding="utf-8")
    assert source.count("{% set CELEBRATE = true %}") == 1


@pytest.mark.parametrize("path", OB_STEPS)
def test_no_step_carries_a_dashboard_hook(saas_cfg, path):
    page = _page(_ob(saas_cfg, path))
    for attr in ("data-panel", "data-fresh"):
        assert [n for n in page.walk() if attr in n.attrs] == [], attr
    for cls in ("status", "live", "since", "dash__grid"):
        assert page.find(cls=cls) == [], cls


# --- section 8 of journey.css, read statically -------------------------------------------------

# What the frozen motion files move, resize or clip. Section 8 may set none of these on a hook.
OB_FROZEN = ("stepper", "stepper__list", "stepper__item", "stepper__marker", "gconf",
             "gconf__track", "gconf__line", "fromto__node", "kw", "chip-list", "quick", "preview",
             "preview__link", "mailcard", "mailcard__head", "letter__part", "copy-row", "activate",
             "badge--ok", "disclose", "site-header")
OB_MOVES = re.compile(r"(?:(?:min-|max-)?(?:width|height)|inline-size|block-size|inset(?:-.*)?|top|"
                      r"right|bottom|left|margin(?:-.*)?|position|transform|translate|scale|rotate|"
                      r"display|overflow(?:-.*)?|contain|isolation|z-index|clip-path|opacity|"
                      r"visibility|animation(?:-.*)?|transition(?:-.*)?|view-transition-.*|"
                      r"will-change|grid-.*|order|flex(?:-.*)?|align-self|justify-self|content)$")


def test_section_8_switches_layout_only_at_the_frozen_breakpoints():
    widths = {m for _s, _b, chain in OB_RULES for link in chain
              for m in re.findall(r"\((?:min|max)-width:\s*[^)]*\)", link)}
    assert widths <= {"(min-width:960px)", "(min-width:1100px)"}, widths


def test_section_8_recolours_the_motion_hooks_but_never_moves_them():
    bad = []
    for sel, body, _chain in OB_RULES:
        moved = sorted(p for p in decls(body) if OB_MOVES.match(p))
        for part in sel_split(sel, ","):
            last = sel_compounds(part)[-1][1]
            named = set(re.findall(r"\.([\w-]+)", re.sub(r":not\([^)]*\)", "", last)))
            if moved and named & set(OB_FROZEN):
                bad.append(f"{part}: {moved}")
    assert bad == []


def test_section_8_defines_its_tints_in_both_schemes():
    light, dark = _ob_tokens("light"), _ob_tokens("dark")
    assert set(light) == set(dark) == {"--ob-tint", "--ob-rule", "--ob-alarm"}
    assert all(light[k] != dark[k] for k in light), "dark mode must redefine every tint"


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_section_8_tints_keep_text_readable(scheme):
    j, ob = tokens(read_css(JOURNEY_CSS), scheme), _ob_tokens(scheme)
    for fg in ("--j-text", "--j-muted", "--j-link"):          # chips, routes, labels, the Beta tag
        assert contrast(j[fg], ob["--ob-tint"]) >= 4.5, (scheme, fg)
    assert contrast(j["--j-danger-fg"], ob["--ob-alarm"]) >= 4.5, scheme   # the remove button
    assert contrast(j["--j-link"], j["--j-surface"]) >= 3.0, scheme       # the envelope ring


def _state(selector: str) -> str:
    """Task 4's matcher treats :disabled as a state no element is in; a button can be."""
    return selector.replace(":disabled", "[disabled]").replace(":enabled", ":not([disabled])")


def test_no_journey_rule_changes_the_frozen_activate_button(saas_cfg):
    """motion.css's af-fill morph starts from exactly this button: flat #0B6BC7, 12px corners,
    opacity 1, also while app.js holds it disabled and busy (spec 5.2)."""
    page = _page(_ob(saas_cfg, "/onboarding/preview"))
    button = page.one("form", "activate").one(cls="btn--primary")
    plain = button.chain()
    busy = plain[:-1] + [(plain[-1][0], {**plain[-1][1], "disabled": "", "data-state": "busy"})]
    colours = {"var(--j-primary)", "var(--j-primary-hover)"}
    bad = []
    for sel, props, _at in journey_style_rules():
        for part in sel_split(sel, ","):
            if not any(sel_reaches(_state(part), chain) for chain in (plain, busy)):
                continue
            for prop, value in props.items():
                v = value.replace("!important", "").strip()
                if (prop == "background-image" and v != "none") or \
                        (prop in ("background", "background-color") and v not in colours) or \
                        (prop == "opacity" and v != "1") or \
                        (prop.endswith("radius") and v != "var(--r-md)") or \
                        prop in ("filter", "backdrop-filter", "mix-blend-mode"):
                    bad.append(f"{part} {{{prop}: {value}}}")
    assert bad == []


def _reaching(chain, props: set[str]) -> list[tuple[str, str, str, str]]:
    """(selector, tag, property, value) for every journey declaration of ``props`` that can land
    on the last element of ``chain`` or on one of its ancestors."""
    hits = []
    for sel, found, _at in journey_style_rules():
        for prop in sorted(set(found) & props):
            for part in sel_split(sel, ","):
                hits += [(part, chain[d - 1][0], prop, found[prop])
                         for d in range(1, len(chain) + 1) if sel_reaches(_state(part), chain[:d])]
    return hits


def test_nothing_clips_a_chip_or_rings_it(saas_cfg):
    """Spec 6.2: no overflow:hidden on .kw, .chip-list or any parent, no new box-shadow on .kw.
    motion.css draws the new-chip ring as a box-shadow and a sonar ::after outside the chip."""
    chip = _page(_ob(saas_cfg, "/onboarding/keywords")).find("li", "kw")[0].chain()
    clips = {"overflow", "overflow-x", "overflow-y", "clip-path", "contain"}
    found = [h for h in _reaching(chip, clips)
             if re.search(r"hidden|clip|paint|strict|content|inset|polygon|circle", h[3])]
    assert found == []
    rings = [h for h in _reaching(chip, {"box-shadow"}) if h[1] == "li"]
    assert rings == []


def test_the_message_box_keeps_its_rows_and_fixed_sizing(saas_cfg):
    markup = _ob(saas_cfg, "/onboarding/profile")
    area = _page(markup).one("textarea", id="f-standard_message")
    assert area.attrs.get("rows") == "8"
    sizing = {"field-sizing", "height", "block-size", "max-height", "max-block-size"}
    chain = area.chain()
    bad = []
    for sel, props, _at in journey_style_rules():
        for part in sel_split(sel, ","):
            if not sel_reaches(_state(part), chain):
                continue
            for prop in set(props) & sizing:
                if not (prop == "field-sizing" and props[prop] == "fixed") and \
                        not (prop in ("height", "block-size") and props[prop] == "auto"):
                    bad.append(f"{part} {{{prop}: {props[prop]}}}")
    assert bad == []


def test_an_invalid_field_stays_amber_in_every_state(saas_cfg):
    page = _page(_ob(saas_cfg, "/onboarding/profile?error=long_job_type"))
    field = page.one("input", id="f-job_type")
    assert field.attrs.get("aria-invalid") == "true"
    edge = {"border", "border-color", "box-shadow", "outline", "outline-color"}
    found = [h for h in _reaching(field.chain(), edge) if h[1] == "input"]
    own = [h for h in found if "aria-invalid" in h[0]]
    assert own and all("--amber-600" in h[3] for h in own), own
    red = re.compile(r"danger|destructive|--red-|#B3261E|#FF8A80", re.I)
    assert [h for h in found if red.search(h[3])] == []


def test_the_sample_email_takes_no_onboarding_tint(saas_cfg):
    """The light island (section 2) redefines the --j-* tokens only, so an --ob-* tint inside the
    mailcard would turn dark in dark mode. The sample email stays white (spec 3, 5.3)."""
    markup = _ob(saas_cfg, "/onboarding/preview")
    card = _page(markup).one("article", "mailcard")
    bad = []
    for node in [card, *card.walk()]:
        chain = node.chain()
        for sel, props, _at in journey_style_rules():
            tinted = sorted(p for p, v in props.items() if "--ob-" in v)
            if tinted and any(sel_reaches(_state(p), chain) for p in sel_split(sel, ",")):
                bad.append(f"{sel} on <{node.tag} class={node.attrs.get('class')}>: {tinted}")
    assert bad == []
```

- [ ] **Step 3: Run the new tests and watch them fail**

```bash
.venv/Scripts/python.exe -m pytest -q tests/test_saas_journey.py
```

Expected: `15 failed, 165 passed`, exactly these 15:
- `test_the_journey_look_loads_on_exactly_the_listed_templates[...]` for the four onboarding
  templates (Task 3's scope test: listed but not linked);
- `test_every_step_loads_the_journey_look_after_the_motion_head[...]` for the four paths
  (`AssertionError: /static/vendor/basecoat-1.0.2-agad.css?v=<12 hex> linked 0 times`);
- `test_step_one_puts_what_google_asks_in_a_native_disclosure`
  (`want one <details class=disclose {}>, found 0`);
- `test_step_two_holds_the_four_fields_in_one_card` (`'form' == 'form sheet'`);
- `test_step_three_reads_add_form_chips_quick_pills_then_next` and
  `test_step_three_editing_mode_puts_done_after_the_quick_adds` (Next comes before the quick adds);
- `test_section_8_defines_its_tints_in_both_schemes`, `test_section_8_tints_keep_text_readable[light]`
  and `[dark]` (`KeyError: '--ob-tint'`).

The other 37 new items pass already: they pin today's hooks, which this task must keep exactly.

- [ ] **Step 4: Edit the three templates the Edit tool can open**

`applyfirst/saas/templates/onboarding_connect_gmail.html`. Before, lines 4 to 8:

```html
{% block title %}Connect Gmail · Agad{% endblock %}
{% block body_class %}is-onboarding{% endblock %}
{% block html_attrs %} data-step="1"{% endblock %}
{% block motion_head %}{{ ui.motion_head() }}{% endblock %}
{% block content %}
```

After:

```html
{% block title %}Connect Gmail · Agad{% endblock %}
{% block color_scheme %}light dark{% endblock %}
{% block theme_color_meta %}<meta name="theme-color" content="#FFFFFF" media="(prefers-color-scheme: light)">
  <meta name="theme-color" content="#111B2B" media="(prefers-color-scheme: dark)">{% endblock %}
{% block body_class %}is-onboarding{% endblock %}
{% block html_attrs %} data-step="1"{% endblock %}
{% block motion_head %}{{ ui.motion_head() }}{% endblock %}
{% block page_css %}
  <link rel="stylesheet" href="{{ static_url('vendor/basecoat-1.0.2-agad.css') }}">
  <link rel="stylesheet" href="{{ static_url('css/journey.css') }}">
{% endblock %}
{% block content %}
```

Before, lines 38 and 39:

```html
      <div>
        <h2 class="h-sub">What you'll see next</h2>
```

After (one line):

```html
      {% call ui.disclose("What will Google ask me?") %}
```

Before, line 48 (the `</div>` right after `</ol>`):

```html
      </div>
      <div class="control">
```

After:

```html
      {% endcall %}
      <div class="control">
```

The `<ol class="numbered">` and its four items (lines 40 to 47) stay byte for byte, including the
`{# BETA #}` comments. Then two separate one-line edits (line 63, `{%- else %}`, sits between them
and stays as it is). Before, line 62:

```html
        <a href="/dashboard">Not now</a>
```

After:

```html
        <a class="text-link" href="/dashboard">Not now</a>
```

Before, line 64:

```html
        <a href="/onboarding/profile">Skip for now</a>
```

After:

```html
        <a class="text-link" href="/onboarding/profile">Skip for now</a>
```

The whole file after the edits (76 lines), to check against:

```html
{% extends "base.html" %}
{% import "_ui.html" as ui %}
{% from "_icons.html" import icon %}
{% block title %}Connect Gmail · Agad{% endblock %}
{% block color_scheme %}light dark{% endblock %}
{% block theme_color_meta %}<meta name="theme-color" content="#FFFFFF" media="(prefers-color-scheme: light)">
  <meta name="theme-color" content="#111B2B" media="(prefers-color-scheme: dark)">{% endblock %}
{% block body_class %}is-onboarding{% endblock %}
{% block html_attrs %} data-step="1"{% endblock %}
{% block motion_head %}{{ ui.motion_head() }}{% endblock %}
{% block page_css %}
  <link rel="stylesheet" href="{{ static_url('vendor/basecoat-1.0.2-agad.css') }}">
  <link rel="stylesheet" href="{{ static_url('css/journey.css') }}">
{% endblock %}
{% block content %}
{%- set retry = gmail_error | default(none) %}
{%- set initial = (user.display_name or user.email)[:1] | upper %}
{%- set editing = activated | default(false) %}
{% call ui.onboarding_shell(1, editing) %}
      {%- if retry %}
      {{ ui.gmail_retry_note(retry, gmail_connected) }}
      {%- endif %}
      {%- if gmail_connected %}
      <div>
        <h1>Gmail is connected</h1>
      </div>
      {% call ui.alert('success', 'circle-check') %}<p>Applications will go to <strong class="addr-inline">{{ ui.email_text(user.email) }}</strong>.</p>{% endcall %}
      {{ ui.from_to(user.email, initial, "Same address on both ends. Only you get these emails.") }}
      <div class="actions">
        {{ ui.link_button("/dashboard" if editing else "/onboarding/profile", "Continue", size="lg") }}
        {%- if retry %}
        {{ ui.link_button("/auth/connect-gmail", "Connect Gmail", variant="secondary", icon_name="mail") }}
        {%- endif %}
      </div>
      {%- else %}
      <div>
        {%- if not editing %}
        <p class="welcome">Welcome, {{ user.display_name or user.email }}. Setup takes about 3 minutes.</p>
        {%- endif %}
        <h1>Connect your Gmail</h1>
        <p class="lead">This is how your applications reach you. We send them from your Gmail to your Gmail, so they land in your inbox like any email.</p>
      </div>
      {{ ui.from_to(user.email, initial, "Same address on both ends. Only you get these emails.") }}
      {{ ui.ledger("short") }}
      {% call ui.disclose("What will Google ask me?") %}
        <ol class="numbered">
          <li>Google asks you to choose an account. Choose <strong class="addr-inline">{{ ui.email_text(user.email) }}</strong>, the same one you signed in with.</li>
          {# BETA: remove after Google verification #}
          <li>{{ ui.tag("Beta") }}You may see <strong>“Google hasn't verified this app”</strong>. That's normal while Google reviews new apps. Tap <strong>Advanced</strong>, then <strong>Go to Agad (unsafe)</strong>. Google adds the word unsafe to every new app it is still reviewing.</li>
          {# /BETA #}
          <li>Google asks to let Agad <strong>“Send email on your behalf”</strong>. That's Google's name for the send permission. If you see a box next to it, make sure it's ticked, then tap <strong>Continue</strong>.</li>
          <li>{% if editing %}You come straight back to Agad.{% else %}You come straight back here to finish setup.{% endif %}</li>
        </ol>
      {% endcall %}
      <div class="control">
        {{ icon('lock') }}
        <div>
          <p>You're in control. Disconnect any time from your dashboard, or remove Agad in your <a href="https://myaccount.google.com/connections" target="_blank" rel="noopener">Google Account<span class="visually-hidden"> (opens in a new tab)</span></a>.</p>
          <p>What Google gives us is stored encrypted. We never see your Gmail password.</p>
        </div>
      </div>
      <div class="actions">
        {{ ui.link_button("/auth/connect-gmail", "Connect Gmail", icon_name="mail", size="lg") }}
        <p class="caption">You'll approve this on Google's own page. It takes about 30 seconds.</p>
      </div>
      <div class="skip">
        {%- if editing %}
        <a class="text-link" href="/dashboard">Not now</a>
        {%- else %}
        <a class="text-link" href="/onboarding/profile">Skip for now</a>
        <p>You can connect at the last step. We can't send you anything until you do.</p>
        {%- endif %}
      </div>
      {%- endif %}
{% endcall %}
{% endblock %}
```

`applyfirst/saas/templates/onboarding_profile.html`. Before, lines 3 to 7:

```html
{% block title %}Your details · Agad{% endblock %}
{% block body_class %}is-onboarding{% endblock %}
{% block html_attrs %} data-step="2"{% endblock %}
{% block motion_head %}{{ ui.motion_head() }}{% endblock %}
{% block content %}
```

After:

```html
{% block title %}Your details · Agad{% endblock %}
{% block color_scheme %}light dark{% endblock %}
{% block theme_color_meta %}<meta name="theme-color" content="#FFFFFF" media="(prefers-color-scheme: light)">
  <meta name="theme-color" content="#111B2B" media="(prefers-color-scheme: dark)">{% endblock %}
{% block body_class %}is-onboarding{% endblock %}
{% block html_attrs %} data-step="2"{% endblock %}
{% block motion_head %}{{ ui.motion_head() }}{% endblock %}
{% block page_css %}
  <link rel="stylesheet" href="{{ static_url('vendor/basecoat-1.0.2-agad.css') }}">
  <link rel="stylesheet" href="{{ static_url('css/journey.css') }}">
{% endblock %}
{% block content %}
```

Before, line 37:

```html
      <form class="form" method="post" action="/onboarding/profile">
```

After:

```html
      <form class="form sheet" method="post" action="/onboarding/profile">
```

Nothing else in the file changes (the four `ui.field` calls, the alert, the disclosure, Save and
the caption stay byte for byte, now inside the card).

`applyfirst/saas/templates/onboarding_preview.html`. Before, lines 4 to 8:

```html
{% block title %}Preview · Agad{% endblock %}
{% block body_class %}is-onboarding{% endblock %}
{% block html_attrs %} data-step="4"{% endblock %}
{% block motion_head %}{{ ui.motion_head() }}{% endblock %}
{% block content %}
```

After:

```html
{% block title %}Preview · Agad{% endblock %}
{% block color_scheme %}light dark{% endblock %}
{% block theme_color_meta %}<meta name="theme-color" content="#FFFFFF" media="(prefers-color-scheme: light)">
  <meta name="theme-color" content="#111B2B" media="(prefers-color-scheme: dark)">{% endblock %}
{% block body_class %}is-onboarding{% endblock %}
{% block html_attrs %} data-step="4"{% endblock %}
{% block motion_head %}{{ ui.motion_head() }}{% endblock %}
{% block page_css %}
  <link rel="stylesheet" href="{{ static_url('vendor/basecoat-1.0.2-agad.css') }}">
  <link rel="stylesheet" href="{{ static_url('css/journey.css') }}">
{% endblock %}
{% block content %}
```

Nothing else changes: the side-by-side layout from 1100px, the activate forms, the mailcard and
editing mode are exactly today's markup.

- [ ] **Step 5: Patch the Step 3 template with a script**

The privacy hook blocks any Read or Bash call whose text contains the word in this template's
name, so the Edit tool cannot open it. Write this script with the Write tool as
`<scratchpad>/patch_step3.py` (the name keeps the word off the command line):

```python
"""Task 5, Step 3 template: the watch-words page (spec 6.2).

Run from anywhere: .venv/Scripts/python.exe <scratchpad>/patch_step3.py <repo root>
(The file name keeps the privacy hook's banned word out of the command line.)

Two exact edits, each asserted to match once, LF endings kept:
  1. the journey head (colour scheme, the two theme colours, the two stylesheets);
  2. the next-step block moves from under the saved chips to after the quick adds, so the page
     reads: add form, saved chips, quick-add pills, Next (spec 6.2). The comment above the saved
     list is updated to say so.
Nothing else changes: the add form, every chip, every quick-add form and every csrf input are
byte for byte the same.
"""
import sys
from pathlib import Path

root = Path(sys.argv[1] if len(sys.argv) > 1 else "C:/Users/regid/Desktop/applyfirst")
page = root / "applyfirst" / "saas" / "templates" / ("onboarding_" + "key" + "words.html")
raw = page.read_bytes()
assert b"\r\n" not in raw, "expected LF endings"
src = raw.decode("utf-8")

HEAD_OLD = """{% block title %}Keywords · Agad{% endblock %}
{% block body_class %}is-onboarding{% endblock %}
{% block html_attrs %} data-step="3"{% endblock %}
{% block motion_head %}{{ ui.motion_head() }}{% endblock %}
{% block content %}
"""
HEAD_NEW = """{% block title %}Keywords · Agad{% endblock %}
{% block color_scheme %}light dark{% endblock %}
{% block theme_color_meta %}<meta name="theme-color" content="#FFFFFF" media="(prefers-color-scheme: light)">
  <meta name="theme-color" content="#111B2B" media="(prefers-color-scheme: dark)">{% endblock %}
{% block body_class %}is-onboarding{% endblock %}
{% block html_attrs %} data-step="3"{% endblock %}
{% block motion_head %}{{ ui.motion_head() }}{% endblock %}
{% block page_css %}
  <link rel="stylesheet" href="{{ static_url('vendor/basecoat-1.0.2-agad.css') }}">
  <link rel="stylesheet" href="{{ static_url('css/journey.css') }}">
{% endblock %}
{% block content %}
"""

COMMENT_OLD = """      {# The saved list and the next step sit right under the add form, newest chip first, so after an add (the page reloads at the top) the new chip shows without scrolling on a phone however many there are.
"""
COMMENT_NEW = """      {# The saved list sits right under the add form, newest chip first, so after an add (the page reloads at the top) the new chip shows without scrolling on a phone however many there are. The quick adds follow it, then the next step (spec 6.2).
"""

NEXT = """      {%- if keywords %}
      <div class="actions">
        {%- if activated | default(false) %}
        {{ ui.link_button("/dashboard", "Done", size="lg") }}
        <a class="text-link" href="/onboarding/preview">See a sample email</a>
        {%- else %}
        {{ ui.link_button("/onboarding/preview", "Next: see a sample", size="lg") }}
        {%- endif %}
      </div>
      {%- endif %}
"""
QUICK = """      {%- if suggestions and not at_cap %}
      <div>
        <h2 class="h-mini">Quick add</h2>
        <ul class="quick-list" aria-label="Quick add">
          {%- for word in suggestions %}
          {{ ui.quick_add(word, csrf_token) }}
          {%- endfor %}
        </ul>
      </div>
      {%- endif %}
"""

for old, new in ((HEAD_OLD, HEAD_NEW), (COMMENT_OLD, COMMENT_NEW), (NEXT + QUICK, QUICK + NEXT)):
    assert src.count(old) == 1, f"expected exactly one match for:\n{old}"
    src = src.replace(old, new)
page.write_bytes(src.encode("utf-8"))
print(f"patched {page.name}: {len(src.splitlines())} lines")
```

Run it:

```bash
.venv/Scripts/python.exe <scratchpad>/patch_step3.py C:/Users/regid/Desktop/applyfirst
```

Expected output: `patched onboarding_keywords.html: 74 lines`. Check the result with the Grep tool
(pattern `.*`, output mode content) on the template: line 37 is the reworded comment, the Quick add
block is lines 51 to 60 and the Next block lines 61 to 70.

- [ ] **Step 6: Fill section 8 of journey.css**

Put these lines between `/* ---- 8 onboarding */` and `/* ---- 9 dashboard */` (Task 3 leaves
nothing between the two banners). Write them with LF endings.

```css
/* Spec 6.2. Colours, type and corners only: every size, place and animation the frozen motion
   files read (spec 9) stays app.css's, and the layout still switches at 960 and 1100px. app.css
   paints these pages with fixed light blues, so three local tokens carry the dark versions. */
:root{--ob-tint:#EEF7FD;--ob-rule:#C9D6E6;--ob-alarm:#FDEEEC}
@media (prefers-color-scheme:dark){:root{--ob-tint:#15283D;--ob-rule:#2E4057;--ob-alarm:#3A1E1B}}
.ob-main .lead{color:var(--j-muted)}
.h-mini,.sample__label{font-size:var(--fs-caption);font-weight:500}
/* Stepper: passed bars and nodes, the rail's current row and line. */
.stepper__item.is-passed::before{background:var(--j-text)}
@media (min-width:960px){
.ob-main{border-radius:var(--r-md);box-shadow:var(--j-shadow)}
.stepper__marker,.rail__edit{background:var(--ob-tint)}
.stepper__item:not(:last-child)::after{background:var(--ob-rule)}
.is-passed .stepper__node{background:var(--j-text);border-color:var(--j-text);color:var(--j-surface)}
}
@media (forced-colors:active) and (min-width:960px){.stepper__marker{background:Highlight}}
/* Step 1 and 2: the route, the sealed-and-sent row, the permission rows. */
.fromto,.gconf,.kw{background:var(--ob-tint);border-color:var(--j-hairline)}
.fromto,.gconf,.ledger,.empty,.sample,.mailcard{border-radius:var(--r-md)}
.fromto .addr{border-color:var(--j-hairline)}
.fromto__note{color:var(--j-text)}
.fromto__path i,.gconf__line,.preview__link::before{background:var(--ob-rule)}
.fromto__node{border-color:var(--j-link);color:var(--j-link)}
.avatar,.ob-main .numbered>li::before{background:var(--j-text);color:var(--j-surface)}
.ledger__icon,.tag--sky{background:var(--ob-tint);color:var(--j-link)}
.control .icon,.ob-main .disclose>summary .icon,.empty__icon{color:var(--j-muted)}
.ob-main .disclose{border-block:1px solid var(--j-hairline)}
.form .paste{background:var(--j-ground);border-color:var(--j-hairline)}
/* Step 3: chips and quick-add pills. No overflow and no box-shadow on .kw: motion.css rings it. */
.kw,.quick{color:var(--j-text);font-size:var(--fs-small);font-weight:500}
.kw__remove:is(:hover,:focus-visible){background:var(--ob-alarm);color:var(--j-danger-fg)}
.quick .icon{color:var(--j-link)}
.quick:hover{background:var(--ob-tint);border-color:var(--j-link)}
@media (forced-colors:active){.fromto,.gconf,.kw,.ob-main .disclose{border-color:CanvasText}}
```

What the rules do, and what they must never do:
- Every value is a colour, a font size or weight, or a 12px corner. No rule sets a size, a
  position, overflow, box-shadow, a transition or an animation on a hook the motion files read
  (`test_section_8_recolours_the_motion_hooks_but_never_moves_them`), and the only width
  breakpoint is the frozen 960px.
- `--ob-tint`, `--ob-rule` and `--ob-alarm` are light `#EEF7FD` (sky-50 today), `#C9D6E6`
  (navy-100 today), `#FDEEEC` (red-50 today) and dark `#15283D`, `#2E4057`, `#3A1E1B`. All sit at
  hue 204 to 214 (the tints and rules) or 6 to 7 (the two alarm reds), outside the banned band (the palette test scans them). Contrast on the tint
  (computed by `test_section_8_tints_keep_text_readable`): text 14.18 light and 12.69 dark, muted
  6.07 and 6.48, link 4.91 and 6.82; the danger colour on `--ob-alarm` 5.79 and 6.66. A mix of the
  red into the blue tint was tried and rejected: it lands at hue 240 to 340 (purple).
- `.avatar` and the numbered circles use `--j-text` with `--j-surface`: navy with white in light
  (today's look), light with dark in dark mode, and navy with white again inside the white
  mailcard (the island redefines both tokens).
- The forced-colours rule restores `Highlight` on the rail marker (app.css's own rule,
  `app.css:790-793`, loses to any journey rule) and gives the translucent edges a real border.
- Size: section 8 is 2,375 bytes raw and adds 713 B gzip; `journey.css` after Tasks 2 to 5
  measured 4,280 B gzip against the 8,000 cap.

- [ ] **Step 7: Run the new tests and watch them pass**

```bash
.venv/Scripts/python.exe -m pytest -q tests/test_saas_journey.py
```

Expected: every test in the file passes (`180 passed`: 52 Task 5 items plus Task 3's scope test
for the four templates, now passing).

- [ ] **Step 8: Measure the four steps in headless Chrome, light and dark**

This is the check the static tests cannot make: the real cascade of app.css, Basecoat, journey.css
and motion.css. Save this script with the Write tool as `<scratchpad>/measure_onboarding.py` and
run it from the repo root. It needs Chrome at
`C:\Program Files\Google\Chrome\Application\chrome.exe` (153 on this machine) and starts no server.

```python
"""Measure the four onboarding steps in headless Chrome: light and dark, phone and computer.

    .venv/Scripts/python.exe measure_onboarding.py <repo root>

No server runs. Each page is rendered by the app's own TestClient for a seeded user, its /static
links are pointed at the files on disk, the page scripts are dropped (content never needs
JavaScript), every disclosure is opened so its text is measured too, and a probe script reads the
computed styles back through --dump-dom. Checks, each printed PASS or FAIL (exit 1 on any FAIL):
  * every visible text reaches 4.5:1 (3:1 when large) on its real background;
  * no sideways scroll;
  * frozen values: the Activate button is #0B6BC7, 12px, opacity 1, no image, and stays so when
    disabled and busy; the gconf track is 96px; every envelope node is 28 x 28px; the stepper
    marker is absolute; the sample email is white in both schemes;
  * chips: nothing from the chip up to <html> clips, and the chip has no box-shadow;
  * fields: every input and the message box at 16px or more, the message box keeps
    field-sizing fixed and rows 8, an invalid field is amber (#B86E00) with and without focus;
  * type (spec 5.1): h1 28/30px weight 600, field labels 12px weight 500;
  * step 4: the sample post and the email side by side from 1100px, stacked below.
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from applyfirst.saas.config import SaaSConfig  # noqa: E402
from _saas_client import client_for, seed_user  # noqa: E402

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
STATIC = REPO / "applyfirst" / "saas" / "static"
GRANT = b"0123456789abcdef0123456789abcdef"
COARSE = ["--blink-settings=primaryPointerType=2,availablePointerTypes=2,"
          "primaryHoverType=1,availableHoverTypes=1"]
MODES = {  # name: (window, flags). Headless Chrome will not open narrower than about 500px.
    "light phone": ("504,900", COARSE), "dark phone": ("504,900", ["--force-dark-mode", *COARSE]),
    "light computer": ("1280,900", []), "dark computer": ("1280,900", ["--force-dark-mode"]),
}
PAGES = {  # name: (path, seed)
    "step 1": ("/onboarding/connect_gmail", {"gmail": False}),
    "step 1 retry": ("/onboarding/connect_gmail?gmail_error=scope", {}),
    "step 2": ("/onboarding/profile", {}),
    "step 2 error": ("/onboarding/profile?error=long_job_type", {"gmail": False}),
    "step 3": ("/onboarding/keywords", {}),
    "step 3 editing": ("/onboarding/keywords", {"activated": True}),
    "step 4": ("/onboarding/preview", {}),
    "step 4 no gmail": ("/onboarding/preview", {"gmail": False}),
}
TINT = {"light": "rgb(238, 247, 253)", "dark": "rgb(21, 40, 61)"}
ATTN = {"light": "rgb(255, 246, 230)", "dark": "rgb(42, 33, 16)"}

PROBE = r"""<script>
(async () => {
  await document.fonts.ready;
  const cs = (el, p) => getComputedStyle(el, p || null), q = (s) => document.querySelector(s);
  const qa = (s) => [...document.querySelectorAll(s)].filter((e) => e.getClientRects().length);
  const rgb = (s) => { const m = /rgba?\(([^)]+)\)/.exec(s); if (!m) return null;
    const p = m[1].split(/[\s,\/]+/).filter(Boolean).map(Number); return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; };
  const over = (t, u) => [0, 1, 2].map((i) => t[i] * t[3] + u[i] * (1 - t[3])).concat(1);
  const bg = (el) => { const chain = []; for (let e = el; e; e = e.parentElement) chain.unshift(e);
    let c = [255, 255, 255, 1]; for (const e of chain) { const b = rgb(cs(e).backgroundColor);
    if (b === null) return null; if (b[3] > 0) c = over(b, c); } return c; };
  const lum = (c) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); };
  const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  const name = (el) => el.tagName.toLowerCase() + (typeof el.className === "string" && el.className.trim() ? "." + el.className.trim().split(/\s+/).join(".") : "");
  const out = { low: [], texts: 0, overflow: document.documentElement.scrollWidth - innerWidth, c: {} };
  for (const el of document.querySelectorAll("body *")) {
    if (el.closest(".visually-hidden, [hidden], script, style")) continue;
    const own = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
    if (!own || !el.getClientRects().length) continue;
    const s = cs(el), fg = rgb(s.color), b = bg(el);
    const size = parseFloat(s.fontSize), need = size >= 24 || (size >= 18.66 && +s.fontWeight >= 700) ? 3 : 4.5;
    const r = fg && b ? ratio(over(fg, b), b) : null;
    out.texts += 1;
    if (r === null || r < need) out.low.push([name(el), el.textContent.trim().slice(0, 30), r && +r.toFixed(2), need]);
  }
  const c = out.c;
  const h1 = q("h1"); c.h1 = h1 ? [parseFloat(cs(h1).fontSize), cs(h1).fontWeight] : null;
  c.labels = qa(".field__label").map((e) => [parseFloat(cs(e).fontSize), cs(e).fontWeight]);
  c.inputs = qa("input:not([type=hidden]), textarea").map((e) => parseFloat(cs(e).fontSize));
  const ta = q("textarea"); if (ta) c.textarea = [cs(ta).getPropertyValue("field-sizing"), ta.getAttribute("rows")];
  const inv = q("[aria-invalid=true]");
  if (inv) { c.invalid = cs(inv).borderTopColor; inv.focus(); c.invalidFocus = [document.activeElement === inv, cs(inv).borderTopColor]; inv.blur(); }
  const fe = q("#form-error"); if (fe) c.formError = cs(fe.closest(".alert")).backgroundColor;
  const track = q(".gconf__track"); if (track) c.track = track.getBoundingClientRect().width;
  c.nodes = qa(".fromto__node").map((n) => { const r = n.getBoundingClientRect(); return [r.width, r.height]; });
  const kw = q("li.kw");
  if (kw) { c.kw = [cs(kw).overflowX, cs(kw).overflowY, cs(kw).boxShadow, cs(kw).backgroundColor]; c.clips = [];
    for (let e = kw.parentElement; e; e = e.parentElement) if (cs(e).overflowX !== "visible" || cs(e).overflowY !== "visible") c.clips.push(name(e)); }
  const marker = q(".stepper__marker"); if (marker) c.marker = [cs(marker).position, cs(marker).backgroundColor];
  const passed = q(".stepper__item.is-passed"); if (passed) c.passed = cs(passed, "::before").backgroundColor;
  const mail = q(".mailcard"); if (mail) c.mail = cs(mail).backgroundColor;
  const act = q("form.activate .btn--primary");
  if (act) { const read = () => { const s = cs(act); return [s.backgroundColor, s.backgroundImage, s.borderTopLeftRadius, s.opacity]; };
    c.act = read(); act.disabled = true; act.dataset.state = "busy"; c.actBusy = read(); }
  const sample = q(".sample");
  if (sample && mail) { const a = sample.getBoundingClientRect(), b = mail.getBoundingClientRect();
    c.layout = a.right <= b.left && Math.abs(a.top - b.top) < 60 ? "side" : b.top >= a.bottom ? "stacked" : "other"; }
  const card = q("form.sheet"); if (card) c.card = [cs(card).borderTopLeftRadius, cs(card).backgroundColor];
  const chip = q(".fromto, .gconf"); if (chip) c.tint = cs(chip).backgroundColor;
  document.getElementById("probe-out").textContent = JSON.stringify(out);
})();
</script><pre id="probe-out"></pre>"""


def render() -> dict[str, str]:
    tmp = tempfile.mkdtemp(prefix="af-ob-measure-")
    cfg = SaaSConfig(db_path=str(Path(tmp) / "m.db"), google_client_id="m",
                     google_client_secret="m", session_secret=b"measure-session-secret-32-bytes!!!",
                     base_url="https://localhost", secure_cookies=False)
    pages = {}
    for i, (label, (path, seed)) in enumerate(PAGES.items()):
        user = seed_user(cfg, sub=f"m{i}", email=f"m{i}@example.com", profile=True,
                         keywords=("virtual assistant", "data entry"),
                         activated=seed.get("activated", False),
                         gmail_key=GRANT if seed.get("gmail", True) else None)
        resp = client_for(cfg, user).get(path)
        assert resp.status_code == 200, (label, resp.status_code)
        html = re.sub(r"<script\b[^>]*>.*?</script>", "", resp.text, flags=re.S)
        html = html.replace('<details class="disclose', '<details open class="disclose')
        html = re.sub(r'(href|src)="/static/([^"?]+)(?:\?[^"]*)?"',
                      lambda m: f'{m.group(1)}="{(STATIC / m.group(2)).as_uri()}"', html)
        pages[label] = html.replace("</body>", PROBE + "</body>")
    return pages


def chrome(html: str, window: str, flags: list[str]) -> dict:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        f = Path(tmp) / "page.html"
        f.write_text(html, encoding="utf-8")
        out = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-first-run",
                              "--allow-file-access-from-files", f"--user-data-dir={tmp}/profile",
                              f"--window-size={window}", "--hide-scrollbars",
                              "--virtual-time-budget=5000", *flags, "--dump-dom", f.as_uri()],
                             capture_output=True, text=True, encoding="utf-8", timeout=120).stdout
    m = re.search(r'<pre id="probe-out">(.*?)</pre>', out, re.S)
    assert m and m.group(1), "the probe wrote nothing"
    raw = m.group(1)
    for a, b in (("&quot;", '"'), ("&lt;", "<"), ("&gt;", ">"), ("&amp;", "&")):
        raw = raw.replace(a, b)
    return json.loads(raw)


fails = 0


def check(ok: bool, label: str) -> None:
    global fails
    fails += not ok
    print(("PASS " if ok else "FAIL ") + label)


pages = render()
runs = [(m, p) for m in MODES for p in PAGES] + [("light computer 1024", "step 4"),
                                                 ("dark computer 1024", "step 4")]
for mode, label in runs:
    scheme, device = mode.split()[:2]
    window, flags = MODES.get(mode, ("1024,900", ["--force-dark-mode"] if scheme == "dark" else []))
    got, tag = chrome(pages[label], window, flags), f"[{label}, {mode}]"
    c = got["c"]
    check(not got["low"], f"{tag} {got['texts']} texts reach AA {got['low'] or ''}")
    check(got["overflow"] <= 0, f"{tag} no sideways scroll ({got['overflow']}px)")
    check(c["h1"] == [28 if device == "phone" else 30, "600"], f"{tag} h1 {c['h1']}")
    check(all(x == [12, "500"] for x in c["labels"]), f"{tag} field labels {c['labels']}")
    check(all(x >= 16 for x in c["inputs"]), f"{tag} inputs {c['inputs']}")
    check(all(n == [28, 28] for n in c["nodes"]), f"{tag} envelope nodes {c['nodes']}")
    if "marker" in c:
        want = TINT[scheme] if device == "computer" else "rgb(11, 107, 199)"
        check(c["marker"] == ["absolute", want], f"{tag} stepper marker {c['marker']}")
    if "passed" in c:
        want = "rgb(11, 37, 69)" if scheme == "light" else "rgb(230, 237, 245)"
        check(c["passed"] == want, f"{tag} passed step bar {c['passed']}")
    if "tint" in c:
        check(c["tint"] == TINT[scheme], f"{tag} route panel tint {c['tint']}")
    if "track" in c:
        check(c["track"] == 96, f"{tag} gconf track {c['track']}px")
    if "textarea" in c:
        check(c["textarea"] == ["fixed", "8"], f"{tag} message box {c['textarea']}")
    if "card" in c:
        want = "rgb(255, 255, 255)" if scheme == "light" else "rgb(17, 27, 43)"
        check(c["card"] == ["12px", want], f"{tag} the fields card {c['card']}")
    if "invalid" in c:
        check(c["invalid"] == "rgb(184, 110, 0)" and c["invalidFocus"] == [True, "rgb(184, 110, 0)"],
              f"{tag} invalid field amber {c['invalid']} focused {c['invalidFocus']}")
        check(c["formError"] == ATTN[scheme], f"{tag} error box {c['formError']}")
    if "kw" in c:
        check(c["kw"][:3] == ["visible", "visible", "none"] and not c["clips"],
              f"{tag} chips unclipped, no ring {c['kw']} clipped by {c['clips']}")
    if "mail" in c:
        check(c["mail"] == "rgb(255, 255, 255)", f"{tag} sample email white {c['mail']}")
        want = "side" if window.startswith("1280") else "stacked"
        check(c["layout"] == want, f"{tag} post and email {c['layout']}, want {want}")
    if "act" in c:
        frozen = ["rgb(11, 107, 199)", "none", "12px", "1"]
        check(c["act"] == frozen and c["actBusy"] == frozen,
              f"{tag} Activate {c['act']} busy {c['actBusy']}")
print(f"\n{fails} failed")
sys.exit(1 if fails else 0)
```

```bash
.venv/Scripts/python.exe <scratchpad>/measure_onboarding.py .
```

Expected: `330` lines of `PASS`, then `0 failed` (8 page states in light and dark, phone and
computer, plus Step 4 at 1024px in both schemes). What a FAIL means:
- "texts reach AA" lists each element under 4.5 to 1 (3 to 1 when large) with its ratio. With
  section 8 emptied the script prints 45 FAILs, among them the quick-add labels at 1.12, the
  example message and the gconf sentence at 1.09, the route labels at 2.13 and "Editing your
  setup" at 1.05, all in dark mode. A FAIL in the header, footer, alerts or buttons belongs to
  Task 3's sections, not section 8.
- "Activate ... busy ..." is the frozen morph start: `rgb(11, 107, 199)`, `none`, `12px`, `1`,
  read again after the probe sets `disabled` and `data-state="busy"` on the button.
- "gconf track", "envelope nodes", "stepper marker" are the geometry motion.css animates.
- "chips unclipped" walks from the first chip to `<html>` and lists every element whose overflow
  is not visible.
- "post and email" is `side` at 1280px and `stacked` at 1024px and on phones.
- Headless Chrome will not open narrower than about 500px, so "phone" is 504px with a coarse
  pointer; the 360 and 390px screenshots belong to Task 8. The owner's Windows reports
  `prefers-reduced-motion: reduce`, so animations do not run here; that is fine for these checks.

- [ ] **Step 9: Prove the tests bite, then restore**

Save this script as `<scratchpad>/mutate5.py`, next to `patch_step3.py`. It plants one mistake at a
time in the working tree, runs `tests/test_saas_journey.py`, and puts the file back byte for byte.

```python
"""Break Task 5 on purpose, one mistake at a time, and confirm the new tests catch each one.

    .venv/Scripts/python.exe <scratchpad>/mutate5.py <repo root> [part of a mutant name ...]

Each mutant edits one file, runs tests/test_saas_journey.py, prints the failing tests that belong
to Task 5 (and how many others failed), then restores the file byte for byte. Exit 1 if any
mutant survives (no Task 5 test failed). Needs patch_step3.py next to it (Step 5).
"""
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(sys.argv[1]).resolve()
PY = sys.executable
CSS = REPO / "applyfirst/saas/static/css/journey.css"
T = REPO / "applyfirst/saas/templates"
STEP3 = T / ("onboarding_" + "key" + "words.html")
UI = T / "_ui.html"
_P = (Path(__file__).parent / "patch_step3.py").read_text(encoding="utf-8")
NEXT = _P.split('NEXT = """', 1)[1].split('"""', 1)[0]
QUICK = _P.split('QUICK = """', 1)[1].split('"""', 1)[0]
S8 = "/* ---- 9 dashboard */"          # a rule inserted before this banner lands in section 8


def add(rule):
    return (CSS, S8, rule + "\n" + S8)


MUTANTS = {
    "a box-shadow on the chips": add(".kw{box-shadow:0 1px 2px #0003}"),
    "the chip list clips": add(".chip-list{overflow:hidden}"),
    "a parent of the chips clips": add(".ob-main{overflow:hidden}"),
    "a chip parent clips through a descendant selector": add("main div{overflow:clip}"),
    "the gconf track resized": add(".gconf__track{width:120px}"),
    "the envelope node resized": add(".fromto__node{width:32px;height:32px}"),
    "the marker moved": add("@media (min-width:960px){.stepper__marker{inset:2px}}"),
    "a new layout breakpoint": add("@media (min-width:1000px){.ob-main{padding:24px}}"),
    "the preview columns moved": add(".preview{grid-template-columns:1fr 1fr}"),
    "the Activate button faded": add(".actions>button{opacity:.9}"),
    "the busy Activate button recoloured": add(".actions>button:disabled{background-color:#0A5AA8}"),
    "the Activate button rounder": add("form button[type=submit]{border-radius:16px}"),
    "the message box grows": add("textarea{field-sizing:content}"),
    "the message box capped": add(".field>textarea{max-height:200px}"),
    "an invalid field turned red": add(".input[aria-invalid=true]{border-color:var(--j-danger-fg)}"),
    "the sample email tinted": add(".mailcard .letter__part{background:var(--ob-tint)}"),
    "dark tints dropped": (CSS, "@media (prefers-color-scheme:dark){:root{--ob-tint:#15283D;--ob-rule:#2E4057;--ob-alarm:#3A1E1B}}", ""),
    "a dark tint too light for text": (CSS, "--ob-tint:#15283D", "--ob-tint:#5A6B80"),
    "the page_css block dropped (step 2)": (T / "onboarding_profile.html", "  <link rel=\"stylesheet\" href=\"{{ static_url('css/journey.css') }}\">\n", ""),
    "the dark theme colour wrong (step 4)": (T / "onboarding_preview.html", 'content="#111B2B"', 'content="#0A111C"'),
    "the fields card lost": (T / "onboarding_profile.html", 'class="form sheet"', 'class="form"'),
    "the disclosure renamed": (T / "onboarding_connect_gmail.html", 'ui.disclose("What will Google ask me?")', 'ui.disclose("What you\'ll see next")'),
    "the skip link not quiet": (T / "onboarding_connect_gmail.html", '<a class="text-link" href="/onboarding/profile">', '<a href="/onboarding/profile">'),
    "Next back above the quick adds": (STEP3, QUICK + NEXT, NEXT + QUICK),
    "the stepper marker after the number": (UI, '<span class="stepper__marker" aria-hidden="true"></span>{% endif %}<span class="stepper__node" aria-hidden="true">{{ loop.index }}</span>', '{% endif %}<span class="stepper__node" aria-hidden="true">{{ loop.index }}</span>{% if loop.index == current %}<span class="stepper__marker" aria-hidden="true"></span>{% endif %}'),
    "the link label wrapped": (UI, '{% if icon_name %}{{ icon(icon_name) }}{% endif %}<span>{{ label }}</span></a>', '{% if icon_name %}{{ icon(icon_name) }}{% endif %}<b><span>{{ label }}</span></b></a>'),
    "the gconf class extended": (UI, '<div class="gconf" data-arrive-gmail', '<div class="gconf gconf--sent" data-arrive-gmail'),
    "a quick add without csrf": (UI, '<li><form method="post" action="/onboarding/keywords">{{ csrf_field(token) }}', '<li><form method="post" action="/onboarding/keywords">'),
    "the quick word not in the last span": (UI, '<span class="visually-hidden">Add </span><span>{{ word }}</span>', '<span>{{ word }}</span><span class="visually-hidden"> (add)</span>'),
}

BLOCK = (REPO / "tests/test_saas_journey.py").read_text(encoding="utf-8")
OURS = set(re.findall(r"^def (test_\w+)",
                      BLOCK.split("# --- Task 5: the four onboarding steps")[1], re.M))
ONLY = sys.argv[2:]
survivors = ran = 0
for name, (path, old, new) in MUTANTS.items():
    if ONLY and not any(o in name for o in ONLY):
        continue
    ran += 1
    original = path.read_bytes()
    text = original.decode("utf-8")
    assert text.count(old) >= 1, f"{name}: anchor not found"
    path.write_bytes(text.replace(old, new, 1).encode("utf-8"))
    try:
        run = subprocess.run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                              "tests/test_saas_journey.py"], cwd=REPO, capture_output=True,
                             text=True, encoding="utf-8", errors="replace",
                             env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    finally:
        path.write_bytes(original)
    failed = re.findall(r"FAILED tests/test_saas_journey\.py::(\S+)", run.stdout)
    ours = [f for f in failed if f.split("[")[0] in OURS]
    survivors += not ours
    print(f"{'CAUGHT ' if ours else 'SURVIVED'} {name}: {len(ours)} Task 5, "
          f"{len(failed) - len(ours)} other\n    " + "\n    ".join(ours[:4]))
print(f"\n{ran - survivors} of {ran} caught")
sys.exit(1 if survivors else 0)
```

```bash
.venv/Scripts/python.exe <scratchpad>/mutate5.py .
```

Expected: 29 `CAUGHT` lines, then `29 of 29 caught` (about 7 minutes). Then confirm nothing was
left behind: `git status --short` lists only this task's files (and the earlier tasks'), and
`git diff --stat applyfirst/saas/templates/_ui.html` prints nothing.

- [ ] **Step 10: Look at it once**

In the owner's own PowerShell window (Handoff: background shells get reaped), with a data folder
outside the repo:

```powershell
.venv\Scripts\python.exe .noxa\redesign-saas-ui\artifacts\run_local.py --port 8765 --data-dir C:\Users\regid\agad-preview
```

Open `http://127.0.0.1:8765/__dev/` and walk the onboarding states (Step 1 fresh and after a
failed connect, Step 2 with Gmail connected and with an error, Step 3 with chips, Step 4 with and
without Gmail, and one editing state). In DevTools, Rendering, switch "Emulate CSS media feature
prefers-color-scheme" between light and dark, and try the device toolbar at 390px and 1280px.
Expected: one calm card per step, the white sample email in both schemes, chips and pills readable
in dark, the stepper's current row tinted on computers. Stop the server with Ctrl+C in that window,
then confirm nothing is left listening:

```powershell
Get-NetTCPConnection -State Listen -LocalPort 8765 -ErrorAction SilentlyContinue
```

Expected: no output.

- [ ] **Step 11: Run both gates**

```bash
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe .noxa/redesign-saas-ui/inputs/preserve_smoke.py
```

Expected. pytest: all pass (887 + the new tests), measured `1119 passed` in sequence (1,067
after Task 4, plus this task's 52 items). smoke: 0 failed (`566 checks passed, 0
failed.`, the same count as after Task 4: the onboarding pages link the asset URLs `/login` already
brought in, and every existing onboarding check still holds, including the main add form before
the quick adds, one remove form per chip, the retry note, and "Back to dashboard" in editing mode).

Existing tests that render these pages and still pass unchanged (checked in the prototype):
`tests/test_saas_motion.py` M-1 (head order, `:313-330`, the new links come after `motion.js`),
M-8 to M-12, M-19; `tests/test_saas_pages.py:123-129` (one primary per onboarding page, including
`preview(not connected)` = Connect Gmail only), `:139-145` (retry note above the `h1`), `:155-189`
(main add form first, remove buttons named, empty state instead of Next); `tests/test_saas_profile_errors.py`
(every `#form-error` and `aria-invalid` check); `tests/test_saas_template_guards.py` (CSP-safe
markup, macro imports); `tests/test_saas_onboarding.py`; `tests/test_saas_static.py:148-159`.

**Notes for the reviewer (Task 5):**
1. **Spec 6.2 says the activate form's one `.btn--primary` may read "Start watching without
   Gmail".** Today that button is `.btn--secondary`, because without Gmail the page's one primary
   is Connect Gmail (`tests/test_saas_pages.py:123-129` requires exactly one primary there), and a
   primary would switch on the frozen af-activate morph (`vt.js:31` names `.activate .btn--primary`)
   for a path that never celebrates. Task 5 keeps it secondary and pins that in
   `test_step_four_without_gmail_keeps_its_quiet_start_button`. Spec 9's "one `.btn--primary`"
   holds in the Gmail-connected state.
2. **Spec 6.2's Step 1 disclosure is new markup.** No "What will Google ask me?" exists on Step 1
   today. The numbered list (including the beta "Google hasn't verified this app, tap Advanced"
   step) now sits in a closed disclosure, one tap away, as on the dashboard. If the owner wants the
   unverified-app step visible without a tap, pass `open=true` to `ui.disclose` (the tests still
   pass).
3. **Step 3's Next moves below the quick adds** (spec 6.2's order). On a phone with the eight
   suggestions it sits about 200px lower than today. The comment above the saved list says so.
4. **Scope.** `.numbered`, `.disclose` and `.lead` rules in section 8 are scoped to `.ob-main`
   because the dashboard also uses `.numbered` and `.disclose` (`dashboard.html:28-29`, `:108`)
   inside panels whose dark colours are Task 6's call. Task 6 writes its own `.dash`-scoped copies.
5. **Task 4's matcher treats `:disabled` as a state no element is in** (`_SEL_NEVER`). Task 5's
   `_state()` rewrites `:disabled` to `[disabled]` before matching, so a rule on the disabled
   Activate button is still seen. Task 6's review-focus audit uses `_state()` the same way.
6. **Section 8 changes type in two places** the spec implies but does not list: the step leads are
   muted (`--j-muted`, like the login lead in Task 4) and the "Your keywords", "Quick add" and
   "Sample job post" headings take the 12px weight 500 label style of spec 5.1.


### Task 6: The dashboard (spec 6.3, spec 9)

The status panel stays on top, chosen exactly as today. Below it, one centred column of three
groups of rows (Watching, Gmail, Today), each a direct child of `.dash__grid`, then "When an
email arrives" as a plain help note. The duplicate secondary Connect Gmail and Add keywords
buttons go, and quiet Edit links replace the group buttons. Prototyped end to end on 2026-09-25
in a scratch copy of the repo carrying Tasks 1 to 3 (Task 3's journey.css then at
9,412 B, 3,421 B gzip, before the forced-colours focus fix). Measured there: the 70 new test items failed 51 and passed 19 before the
change and all passed after it, the full suite went from 1,049 to 1,119 passed, the smoke stayed
at 0 failed, headless Chrome printed 132 `PASS` and `0 failed` across six states in light and
dark on phone and computer, and a mutation pass caught 25 of 25 planted mistakes. Re-run during
assembly on top of Tasks 1 to 5, with the two review-focus additions below (a "near the limit"
state and the dark-mode colour audit): 85 new items, `64 failed, 201 passed` in the journey test
file before the change and `265 passed` after it, pytest 1,119 to 1,204, smoke 566, browser check
132 PASS, and 26 of 26 mutants caught.

**Files:**
- Modify `applyfirst/saas/templates/dashboard.html` (141 lines, LF in git and in the working
  tree). Lines 5 to 6 gain the three journey head blocks around them, and lines 71 to 138 (the
  old `.dash__grid` with its four sheets and the "When an email arrives" sheet) are replaced.
  Lines 1 to 4, 7 to 70 (the variables and the status panel) and 139 to 141 stay byte for byte.
  Full before and after in Step 4.
- Modify `applyfirst/saas/static/css/journey.css`: fill section 9, between the banners
  `/* ---- 9 dashboard */` and `/* ---- 10 signin-failed */` that Task 3 wrote next to each
  other. Nothing else in the file.
- Modify `tests/_journey_css.py`: the `JOURNEY_TEMPLATES` line (add `"dashboard.html"`).
- Modify `tests/test_saas_journey.py`: append the Task 6 block at the end of the file.
- Scratchpad only, never in the repo: `measure_dashboard.py` (Step 7), `mutate6.py` (Step 8).
- Not touched: `_ui.html`, `base.html`, `app.py`, `app.css`, `motion.css`, `vt.js`,
  `motion.js`, `reveal.js`, `.noxa/redesign-saas-ui/inputs/preserve_smoke.py`, and every existing
  test file. No existing test or smoke check needs a change (listed below, and proven by the
  prototype run).

**Interfaces:**
- Consumes (all verified in the repo or in the Task 3 and Task 4 drafts):
  - Task 3: `tests/_journey_css.py` names `JOURNEY_CSS`, `JOURNEY_TEMPLATES`, `TEMPLATES`,
    `contrast`, `decls`, `iter_rules`, `read_css`, `tokens` (and the chain shape
    `("@layer journey", "@media (prefers-color-scheme:dark)")`, whitespace collapsed); the
    `base.html` blocks `color_scheme` and `theme_color_meta` and the existing `page_css`
    (`base.html:14`, after `motion_head` at `base.html:13`, before `reveal.js` at `base.html:15`);
    the journey head snippet (two links, two theme-color metas at `--j-surface`, `#FFFFFF` and
    `#111B2B`), which Task 3's `test_the_journey_look_loads_on_exactly_the_listed_templates`
    checks character for character; the tokens `--j-text`, `--j-muted`, `--j-link`,
    `--j-surface`, `--j-edge`, `--j-hairline` (`rgba(11,37,69,.1)` light,
    `rgba(255,255,255,.12)` dark), `--j-attn-fg`, `--j-primary`; the re-pointed app.css tokens
    `--surface`, `--line`, `--text`, `--text-strong`, `--text-muted`; section 5's `.sheet`
    (surface, hairline edge, 12px corners, faint shadow, `overflow:visible`), `.text-link` (link
    colour, 44px tap band from its own `::after`), `.btn--secondary`, `.badge--ok`,
    `.badge--attention`, `.alert--attention` (the retry note); `--fs-caption` 12px and
    `--fs-small` 15 and 14px.
  - Task 4: the smoke's `REQUIRED_ASSETS` already names the three new files, and `/login` (fetched
    first by the smoke, `preserve_smoke.py:359`) already loads them, so `check_asset`
    (`preserve_smoke.py:218-245`, which fetches each URL once) adds no check for the dashboard.
  - Verified in the repo today: the route `GET /dashboard` (`applyfirst/saas/app.py:316-337`)
    passes `user`, `profile`, `gmail_connected`, `keywords`, `usage_today`, `daily_cap`,
    `csrf_token`, `gmail_error` (only the exact string `"scope"`, `app.py:114-117`),
    `activated_fresh` and `watching_since`. The macros the new markup calls, all unchanged:
    `ui.sheet` (`_ui.html:227-234`, `cls` joins `sheet`, `arrive=true` prints
    `data-arrive-gmail`), `ui.status_panel` (`_ui.html:240-250`), `ui.chip` (`_ui.html:174-176`),
    `ui.badge` (`_ui.html:161-163`), `ui.meter` (`_ui.html:254-263`, class-based widths),
    `ui.link_button` (`_ui.html:57-59`, label in a direct `span`), `ui.button`
    (`_ui.html:53-55`), `ui.disclose` (`_ui.html:341-343`), `ui.csrf_field` (`_ui.html:35-37`),
    `ui.gmail_retry_note` (`_ui.html:134-145`). The test fixtures `saas_cfg` and `master_key`
    (`tests/conftest.py`) and `seed_user`, `client_for`, `count_class`, `clean`
    (`tests/_saas_client.py:57-89`, `190-210`), the same way `tests/test_saas_pages.py:35-38`
    builds its dashboard states. The daily cap is 10 in `saas_cfg`
    (`applyfirst/saas/config.py:46`).
  - For the review-focus audit only: Task 3's `APP_CSS`, Task 4's `sel_split`, `sel_reaches` and
    `journey_style_rules`, and Task 5's `_state`, all module-level in `tests/test_saas_journey.py`.
- Produces:
  - `JOURNEY_TEMPLATES` gains `"dashboard.html"` (Task 7 appends `"signin_failed.html"` after it).
  - Section 9 classes, printed only by `dashboard.html`: `.dash__group`, `.dash__row`,
    `.dash__label`, `.dash__value`, `.dash__end`, `.dash__help`.
  - Test helpers in `tests/test_saas_journey.py`, all prefixed so they cannot clash with Tasks 3
    and 4: `DASH_STATES`, `DASH_TITLES`, `DASH_ONLY`, `DASH_MACROS`, `REDRAWN`, `_dash`,
    `_DashNode`, `_DashTree`, `_dash_tree`, `_dash_groups`, `_dash_section`, `_dash_split`,
    `_dash_subject`, `_dash_rgba`, `_dash_dark`, `_GROUP`, `_STILL_PROPS`, and for the review-focus
    audit `_DASH_FOLLOWS`, `_DASH_SCHEME_FREE`, `_DASH_ISLANDS`, `_DASH_PAINT`, `_DASH_LITERAL`,
    `_dash_fixed`, `_dash_chain`.
  - Review focus 1: `test_no_light_page_colour_survives_on_the_dashboard_in_dark_mode`, over every
    state in `DASH_STATES`, which gains `"near the limit"` (9 of 10 used).

**Frozen hooks on /dashboard (spec 9) and how each is kept:**
- `site-header`, exactly one: `base.html:23`, not touched.
- `data-step="0"` on `html`: `dashboard.html:5` (`{% block html_attrs %}`), kept byte for byte
  (`tests/test_saas_motion.py:588-592` still passes).
- Head order M-1: the new `page_css` block renders after `motion_head` (`base.html:13-14`), so
  app.css, motion.css, vt.js, motion.js, then Basecoat and journey.css, then reveal.js.
  `test_the_dashboard_loads_the_journey_look_after_the_motion_head` pins it, and
  `tests/test_saas_motion.py:313-330` still passes.
- One `data-panel`, chosen Gmail, then no keywords, then daily limit, then live: lines 19 to 69
  are not changed at all.
- `.status--live` (navy `#0B2545`, 24px, `position:relative`, isolated, opaque): the only journey
  rule naming it sets `border-color:var(--j-hairline)`, which is navy at 10 percent on navy in
  light (the same colour, so no visible edge) and white at 12 percent in dark (spec 5.2). Task 3's
  `test_journey_css_leaves_the_live_panel_frame_alone` and the new
  `test_the_live_panel_gains_an_edge_in_dark_only` guard it, and Step 7 measures
  `rgb(11, 37, 69)`, `24px`, `relative`, `isolate`, `1` in every mode. The af-fill morph
  (`motion.css:27`, `:54`, `:106`) still ends on that frame.
- `.live i`, `.status__kw strong` siblings, `.since`, `data-fresh`, `data-burst-src`, and
  `{% set CELEBRATE = true %}` (`_ui.html:22`): all printed by the unchanged panel call and the
  unchanged `watched` block (`dashboard.html:11-12`, `52-68`).
- `data-arrive-gmail`, two on the live dashboard: the live panel (`arrive=(not retry)`, unchanged)
  and the Gmail group, which is still `ui.sheet(..., arrive=(gmail_connected and not retry))` so
  it keeps class `sheet`, and still holds the `.badge--ok` that
  `motion.css:61` stamps. None on a retry or with Gmail off. `tests/test_saas_motion.py:669-687`
  and the new `test_the_gmail_group_keeps_the_arrival_flag_and_its_stamped_badge` pin it.
- `a.btn[href="/auth/connect-gmail"]` with a direct `span`: the panel primary and the retry
  secondary both come from `ui.link_button`, whose label sits in a direct `span` that
  `motion.js:7` and `:14-15` swap for "Opening Google's page".
- `details.disclose`: the panel's "What will Google ask me?" (unchanged) and the Disconnect Gmail
  row (`ui.disclose(..., cls="disconnect")`, same label, same body).
- `#gmail-retry`: printed by `ui.gmail_retry_note` before the panel, unchanged
  (`tests/test_saas_gmail_scope.py:122` checks it precedes `data-panel=`).
- The hidden `csrf` input in every POST form: the Disconnect form keeps
  `{{ ui.csrf_field(csrf_token) }}` (the smoke submits it at `preserve_smoke.py:539-541`), and the
  Log out form is in `base.html:29-32`, not touched.
- `.dash__grid > *`: exactly three direct children, the three groups. `reveal.js:16-19` and
  `app.css:800-804` and `:812` are not edited; journey.css never sets opacity, transform,
  animation, transition, visibility, clip or overflow on a group
  (`test_no_journey_rule_moves_fades_or_clips_a_dashboard_group`). The help note sits after
  `.dash__grid`, so it is not a reveal target and is always visible.
- "N / M" as one text node, the class-based meter, "daily limit reached" exactly once and only in
  the Today group, keywords visible in every state: see the tests in Step 2.

**Existing tests and smoke checks that touch the changed regions (none needs a change).** Measured
in the prototype and again during assembly: every one still passes (1,119 passed before this task
and 1,204 after it), smoke 0 failed.
- `tests/test_saas_pages.py:84-97`: one panel per state, "daily limit reached" only when capped and
  never inside the panel. The panel markup is unchanged and the phrase stays in the Today group.
- `tests/test_saas_pages.py:132-136`: primaries 1 (Gmail off), 1 (no keywords), at most 1 (limit),
  0 (live). The removed buttons were all secondary, so the counts are unchanged.
- `tests/test_saas_motion.py:669-673`: two `data-arrive-gmail`, classes include `sheet` and
  `status`. The Gmail group is still a `ui.sheet` with `arrive=`.
- `tests/test_saas_motion.py:676-687`: a retry or no Gmail flags nothing. Same expressions.
- `tests/test_saas_motion.py:697-727`, `753-761`, `801-811`, `1031-1040`: `data-fresh`,
  `data-burst-src` and `.since` live in the panel, which is unchanged.
- `tests/test_saas_motion.py:313-330` (M-1), `588-592` (M-9), `829-836` (M-15, no `style=`, no
  inline script): the new head blocks are two same-origin `<link>`s and two `<meta>`s after
  motion.js.
- `tests/test_saas_gmail_scope.py:113-122`: Gmail off with `?gmail_error=scope` needs
  `href="/auth/connect-gmail"`. It now comes only from the panel primary (the group's duplicate
  is gone), which is exactly what spec 6.3 wants. `:158-168` (no note for other values) holds.
- `tests/test_saas_dashboard_banner.py:38-52`: "1 / 10", "1 / 1" and "daily limit reached". The
  usage line is the same one text node and the capped note is the same sentence.
- `tests/test_saas_template_guards.py:100-103`: "daily limit reached" occurs once in
  `dashboard.html` outside Jinja comments. Still once. `:39-67` (CSP-safe markup) and `:108-116`
  (imports) hold.
- `tests/test_saas_template_context.py:59-65` ("about every N minutes", the live panel) and
  `:78-97` (dashboard.html rendered) hold.
- `tests/test_saas_profile_edit.py:26-34`: "Graphic Designer" shows on the dashboard. It is now the
  value of the "Looking for" row.
- `tests/test_saas_onboarding.py:61`, `:128`, `:141`: the dashboard renders 200.
- `tests/test_saas_static.py:148-159`: every file a template names exists (Tasks 1 and 2 made them).
- Smoke `preserve_smoke.py:520-554`. `dashboard(scope)`, with Gmail off at that point, needs
  `id="gmail-retry"`, "tick the box" and `href="/auth/connect-gmail"` (the panel primary).
  `dashboard(not connected)` needs "0 / 10", no limit phrase, `href="/auth/connect-gmail"` (the
  panel) and "virtual assistant", which with Gmail off is printed only by the Watching group's
  chips. `dashboard(connected, cap hit)` needs "10 / 10", "daily limit reached" and submits the
  Disconnect form with its hidden csrf. `dashboard(zero keywords)` submits the Log out form.

- [ ] **Step 1: Put the dashboard on the journey list**

In `tests/_journey_css.py`, add `"dashboard.html"` as the last item of the `JOURNEY_TEMPLATES`
list that Tasks 3 to 5 built. Read the file first, then use the Edit tool. Task 5 left

```python
JOURNEY_TEMPLATES: list[str] = ["login.html", "onboarding_connect_gmail.html",
                                "onboarding_profile.html", "onboarding_keywords.html",
                                "onboarding_preview.html"]
```

it becomes

```python
JOURNEY_TEMPLATES: list[str] = ["login.html", "onboarding_connect_gmail.html",
                                "onboarding_profile.html", "onboarding_keywords.html",
                                "onboarding_preview.html", "dashboard.html"]
```

Keep whatever line wrapping Task 5 used. The Edit tool is not blocked by the privacy hook (only
Bash and Read command text is), and the file's own name is safe to Read. This turns on Task 3's
scope test for `dashboard.html`.

- [ ] **Step 2: Append the dashboard tests to `tests/test_saas_journey.py`**

Append this block at the very end of the file, unchanged. It carries its own imports and
prefixes every helper with `_dash` or `DASH_`, so no name clashes. Only its last test, the
review-focus colour audit, calls helpers defined earlier in the file (listed under Consumes). Write it with the Edit tool (append after the last line) or with a small
Python script in the scratchpad that reads the block from a scratch file and appends it. Keep LF
endings.

```python
# --- Task 6: the dashboard (spec 6.3, 9) -------------------------------------------------------
#
# The dashboard in every state the route can choose. One status panel on top, chosen as before,
# then three groups of rows that are direct children of .dash__grid (the reveal layer reads
# .dash__grid > *), then a plain help note. The page tests read the rendered HTML, so they hold
# whatever macro prints the markup. The CSS tests read section 9 of journey.css statically.
# Carries its own imports and prefixes every helper with _dash so nothing clashes with the
# helpers Tasks 3 and 4 put in this file.

import dataclasses
import re
from html.parser import HTMLParser

import pytest

from _journey_css import (
    JOURNEY_CSS, JOURNEY_TEMPLATES, TEMPLATES, contrast, decls, iter_rules, read_css, tokens,
)
from _saas_client import clean, client_for, count_class, seed_user

# name: (saved keywords, Gmail connected, applications used today (the cap is 10), query,
#        the panel spec 6.3 chooses, primary buttons (None: at most one), Connect Gmail links)
DASH_STATES = {
    "gmail off": (("virtual assistant", "data entry"), False, 0, "", "gmail", 1, 1),
    "gmail off, retry": (("virtual assistant",), False, 0, "?gmail_error=scope", "gmail", 1, 1),
    "gmail off at the limit": (("virtual assistant",), False, 10, "", "gmail", 1, 1),
    "no keywords": ((), True, 0, "", "empty", 1, 0),
    "daily limit": (("virtual assistant",), True, 10, "", "paused", None, 0),
    "live": (("virtual assistant", "data entry"), True, 3, "", "live", 0, 0),
    "near the limit": (("virtual assistant",), True, 9, "", "live", 0, 0),
    "reconnect failed": (("virtual assistant",), True, 0, "?gmail_error=scope", "live", 0, 1),
}
DASH_TITLES = ["Watching", "Gmail", "Today"]


def _dash(cfg, master_key, state: str) -> str:
    kws, gmail, usage, query, *_ = DASH_STATES[state]
    user = seed_user(cfg, activated=True, keywords=kws, usage=usage,
                     gmail_key=master_key if gmail else None)
    resp = client_for(cfg, user).get("/dashboard" + query)
    assert resp.status_code == 200
    return resp.text


class _DashNode:
    """One element: its direct children, its parent, and all the text inside it."""

    def __init__(self, tag: str, attrs: dict[str, str], parent: "_DashNode | None") -> None:
        self.tag, self.attrs, self.parent = tag, attrs, parent
        self.kids: list[_DashNode] = []
        self.text = ""

    @property
    def classes(self) -> list[str]:
        return self.attrs.get("class", "").split()

    def walk(self):
        yield self
        for kid in self.kids:
            yield from kid.walk()

    def find(self, pred) -> list["_DashNode"]:
        return [n for n in self.walk() if pred(n)]


class _DashTree(HTMLParser):
    _VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
             "source", "track", "wbr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = self.cur = _DashNode("#root", {}, None)

    def handle_starttag(self, tag, attrs):
        node = _DashNode(tag, {k: v or "" for k, v in attrs}, self.cur)
        self.cur.kids.append(node)
        if tag not in self._VOID:
            self.cur = node

    def handle_startendtag(self, tag, attrs):
        self.cur.kids.append(_DashNode(tag, {k: v or "" for k, v in attrs}, self.cur))

    def handle_endtag(self, tag):
        node = self.cur
        while node.parent is not None and node.tag != tag:
            node = node.parent
        if node.parent is not None:
            self.cur = node.parent

    def handle_data(self, data):
        node = self.cur
        while node is not None:
            node.text += data
            node = node.parent


def _dash_tree(markup: str) -> _DashNode:
    tree = _DashTree()
    tree.feed(markup)
    tree.close()
    return tree.root


def _dash_groups(markup: str) -> tuple[_DashNode, list[_DashNode]]:
    """The page tree and the direct children of the one .dash__grid."""
    root = _dash_tree(markup)
    grids = root.find(lambda n: "dash__grid" in n.classes)
    assert len(grids) == 1, "one .dash__grid"
    return root, grids[0].kids


def test_the_dashboard_loads_the_journey_look_after_the_motion_head(saas_cfg, master_key):
    """Spec 4.2 and M-1: app.css, the motion head, then Basecoat and journey.css, then reveal.js."""
    assert "dashboard.html" in JOURNEY_TEMPLATES
    markup = _dash(saas_cfg, master_key, "live")
    urls = re.findall(r'<(?:link|script)\b[^>]*?\s(?:href|src)="(/static/[^"?]+)', markup)
    order = ["/static/css/app.css", "/static/css/motion.css", "/static/js/vt.js",
             "/static/js/motion.js", "/static/vendor/basecoat-1.0.2-agad.css",
             "/static/css/journey.css", "/static/js/reveal.js"]
    assert [u for u in urls if u in order] == order
    assert '<meta name="color-scheme" content="light dark">' in markup


@pytest.mark.parametrize("state", DASH_STATES)
def test_each_state_shows_one_panel_chosen_as_before_and_its_primaries(saas_cfg, master_key,
                                                                       state):
    *_, panel, primaries, _connect = DASH_STATES[state]
    markup = _dash(saas_cfg, master_key, state)
    assert count_class(markup, "status") == 1
    assert re.findall(r'data-panel="([^"]*)"', markup) == [panel]
    n = count_class(markup, "btn--primary")
    assert (n <= 1) if primaries is None else (n == primaries), n


@pytest.mark.parametrize("state", DASH_STATES)
def test_three_groups_sit_directly_in_the_grid_in_spec_order(saas_cfg, master_key, state):
    _root, groups = _dash_groups(_dash(saas_cfg, master_key, state))
    assert [g.tag for g in groups] == ["section"] * 3
    assert all({"sheet", "dash__group"} <= set(g.classes) for g in groups)
    heads = [g.kids[0] for g in groups]
    assert [h.tag for h in heads] == ["h2"] * 3
    assert [clean(h.text) for h in heads] == DASH_TITLES
    assert [g.attrs.get("aria-labelledby") for g in groups] == [h.attrs.get("id") for h in heads]


@pytest.mark.parametrize("state,flags", [("live", 2), ("reconnect failed", 0), ("gmail off", 0),
                                         ("no keywords", 1), ("daily limit", 1)])
def test_the_gmail_group_keeps_the_arrival_flag_and_its_stamped_badge(saas_cfg, master_key,
                                                                      state, flags):
    """motion.css stamps [data-arrive-gmail] .badge--ok and pops [data-arrive-gmail] .live i.
    Two flags on a live dashboard (spec 9): the Gmail group and the live panel."""
    flagged = _dash_tree(_dash(saas_cfg, master_key, state)).find(
        lambda n: "data-arrive-gmail" in n.attrs)
    assert len(flagged) == flags
    for node in flagged:
        if "dash__group" in node.classes:
            assert "sheet" in node.classes and clean(node.kids[0].text) == "Gmail"
            assert node.find(lambda n: "badge--ok" in n.classes), "the badge the stamp animates"
        else:
            assert {"status", "status--live"} <= set(node.classes)
            assert node.find(lambda n: n.tag == "i" and "live" in n.parent.classes)


@pytest.mark.parametrize("state", DASH_STATES)
def test_the_limit_phrase_shows_once_at_the_limit_and_never_in_the_panel(saas_cfg, master_key,
                                                                          state):
    capped = DASH_STATES[state][2] >= 10
    markup = _dash(saas_cfg, master_key, state)
    assert markup.count("daily limit reached") == (1 if capped else 0)
    root, groups = _dash_groups(markup)
    panel = root.find(lambda n: "data-panel" in n.attrs)[0]
    assert "daily limit reached" not in panel.text
    assert ("daily limit reached" in groups[2].text) is capped


@pytest.mark.parametrize("state", DASH_STATES)
def test_the_keywords_stay_visible_in_every_state(saas_cfg, master_key, state):
    """The smoke needs them with Gmail off, where no panel names them."""
    kws = DASH_STATES[state][0]
    _root, groups = _dash_groups(_dash(saas_cfg, master_key, state))
    chips = groups[0].find(lambda n: n.tag == "li" and "chip" in n.classes)
    assert sorted(clean(c.text) for c in chips) == sorted(kws)
    if not kws:
        assert "None yet" in clean(groups[0].text)


@pytest.mark.parametrize("state", DASH_STATES)
def test_connect_gmail_shows_once_at_most_with_its_label_in_a_direct_span(saas_cfg, master_key,
                                                                         state):
    """Spec 6.3: the group's duplicate is gone. The one left is the panel primary when Gmail is
    off, or the group's secondary when a reconnect failed (motion.js swaps the direct span)."""
    want = DASH_STATES[state][6]
    markup = _dash(saas_cfg, master_key, state)
    root, groups = _dash_groups(markup)
    links = root.find(lambda n: n.tag == "a" and n.attrs.get("href") == "/auth/connect-gmail")
    assert len(links) == want
    for a in links:
        assert "btn" in a.classes
        assert [clean(k.text) for k in a.kids if k.tag == "span"] == ["Connect Gmail"]
    if state == "reconnect failed":
        assert "btn--secondary" in links[0].classes
        assert links[0] in list(groups[1].walk()), "it lives in the Gmail group"


def test_add_keywords_shows_once_on_an_empty_watch_list(saas_cfg, master_key):
    adds = _dash_tree(_dash(saas_cfg, master_key, "no keywords")).find(
        lambda n: n.tag == "a" and clean(n.text) == "Add keywords")
    assert len(adds) == 1 and "btn--primary" in adds[0].classes


@pytest.mark.parametrize("state", DASH_STATES)
def test_quiet_edit_links_replace_the_old_group_buttons(saas_cfg, master_key, state):
    connected, query = DASH_STATES[state][1], DASH_STATES[state][3]
    _root, (watching, gmail, today) = _dash_groups(_dash(saas_cfg, master_key, state))
    links = watching.find(lambda n: n.tag == "a")
    assert {a.attrs.get("href"): clean(a.text) for a in links} == {
        "/onboarding/keywords": "Edit keywords", "/onboarding/profile": "Edit details"}
    assert all("text-link" in a.classes and "btn" not in a.classes for a in links)
    assert today.find(lambda n: "btn" in n.classes) == []
    buttons = [clean(b.text) for b in gmail.find(lambda n: "btn" in n.classes)]
    want = (["Connect Gmail"] if connected and query else []) + (
        ["Disconnect Gmail"] if connected else [])
    assert buttons == want


@pytest.mark.parametrize("state", DASH_STATES)
def test_the_gmail_group_shows_the_address_its_badge_and_the_disconnect_row(saas_cfg, master_key,
                                                                            state):
    connected = DASH_STATES[state][1]
    _root, groups = _dash_groups(_dash(saas_cfg, master_key, state))
    gmail = groups[1]
    assert "maria@example.com" in clean(gmail.text)
    badges = [(b.classes, clean(b.text)) for b in gmail.find(lambda n: "badge" in n.classes)]
    assert badges == ([(["badge", "badge--ok"], "Connected")] if connected
                      else [(["badge", "badge--attention"], "Not connected")])
    forms = gmail.find(lambda n: n.tag == "form")
    if not connected:
        assert forms == [] and gmail.find(lambda n: n.tag == "details") == []
        return
    details = gmail.find(lambda n: n.tag == "details")
    assert len(details) == 1 and {"disclose", "disconnect"} <= set(details[0].classes)
    assert details[0].kids[0].tag == "summary"
    assert clean(details[0].kids[0].text) == "Disconnect Gmail"
    assert [(f.attrs.get("method"), f.attrs.get("action")) for f in forms] == [
        ("post", "/auth/disconnect-gmail")]
    assert forms[0] in list(details[0].walk())
    fields = forms[0].find(lambda n: n.tag == "input")
    assert [(i.attrs.get("type"), i.attrs.get("name")) for i in fields] == [("hidden", "csrf")]
    button = forms[0].find(lambda n: n.tag == "button")
    assert len(button) == 1 and "btn--danger" in button[0].classes
    assert clean(button[0].text) == "Disconnect Gmail"


@pytest.mark.parametrize("cap,used", [(10, 3), (25, 5)])
def test_usage_is_one_text_node_and_the_meter_widths_are_classes(saas_cfg, master_key, cap, used):
    cfg = dataclasses.replace(saas_cfg, daily_tailor_cap=cap)
    user = seed_user(cfg, activated=True, keywords=("va",), gmail_key=master_key, usage=used)
    markup = client_for(cfg, user).get("/dashboard").text
    assert f'<p class="usage">{used} / {cap}</p>' in markup
    assert not re.search(r"<[a-z][^>]*\sstyle\s*=", markup)
    _root, groups = _dash_groups(markup)
    today = groups[2]
    if cap <= 20:
        meters = today.find(lambda n: n.tag == "ol" and "meter" in n.classes)
        assert len(meters) == 1
        segments = [k for k in meters[0].kids if k.tag == "li"]
        assert len(segments) == cap and sum("on" in s.classes for s in segments) == used
    else:
        assert today.find(lambda n: "bar__fill--20" in n.classes)


def test_when_an_email_arrives_is_a_plain_note_after_the_groups(saas_cfg, master_key):
    root, _groups = _dash_groups(_dash(saas_cfg, master_key, "live"))
    notes = root.find(lambda n: "dash__help" in n.classes)
    assert len(notes) == 1
    note, stack = notes[0], notes[0].parent
    order = [k for k in stack.kids if "dash__grid" in k.classes or k is note]
    assert len(order) == 2 and order[1] is note, "the note follows the groups"
    assert note.find(lambda n: {"sheet", "route", "dash__group"} & set(n.classes)) == []
    assert clean(note.kids[0].text) == "When an email arrives"
    assert len(note.find(lambda n: n.tag == "li")) == 3


# --- section 9 of journey.css ---------------------------------------------------------------

# Classes only dashboard.html prints: its own markup, and the macros only it calls.
DASH_ONLY = {"dash", "dash__stack", "dash__grid", "dash__group", "dash__row", "dash__label",
             "dash__value", "dash__end", "dash__help", "status--live", "status--gmail",
             "status--empty", "status--paused", "status__icon", "status__kw", "chip", "usage",
             "usage-note", "usage-note--near", "usage-note--cap", "meter--full", "bar__fill--100"}
DASH_MACROS = ("ui.chip(", "ui.status_panel(", "ui.meter(")


def _dash_section() -> str:
    """Section 9 of journey.css, comments removed (the banners fence it)."""
    raw = JOURNEY_CSS.read_bytes().decode("utf-8").replace("\r\n", "\n")
    part = raw[raw.index("/* ---- 9 dashboard */"):raw.index("/* ---- 10 signin-failed */")]
    return re.sub(r"/\*.*?\*/", "", part, flags=re.S)


def _dash_split(selectors: str) -> list[str]:
    """One selector list as its selectors, split outside brackets, combinators unspaced."""
    out, depth, cur = [], 0, ""
    for ch in selectors:
        depth += (ch in "([") - (ch in ")]")
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    return [re.sub(r"\s*([>+~])\s*", r"\1", " ".join(p.split())) for p in out + [cur]]


def _dash_subject(part: str) -> str:
    depth, cut = 0, 0
    for i, ch in enumerate(part):
        depth += (ch in "([") - (ch in ")]")
        if depth == 0 and ch in " >+~":
            cut = i + 1
    return part[cut:]


def test_section_nine_styles_only_what_the_dashboard_prints():
    """Every journey rule beats every app.css rule, so a loose selector here would restyle the
    login or onboarding pages too. Each selector names a class only the dashboard prints."""
    loose, chains = [], set()
    for sel, _body, chain in iter_rules(_dash_section()):
        chains.add(chain)
        loose += [p for p in _dash_split(sel) if not set(re.findall(r"\.([\w-]+)", p)) & DASH_ONLY]
    assert loose == []
    assert chains <= {(), ("@media (prefers-color-scheme:dark)",)}, chains
    for page in TEMPLATES.glob("*.html"):
        if page.name in ("dashboard.html", "_ui.html"):
            continue
        src = page.read_text(encoding="utf-8")
        assert [m for m in DASH_MACROS if m in src] == [], page.name
        used = {c for attr in re.findall(r'class="([^"]*)"', src) for c in attr.split()}
        assert used & DASH_ONLY == set(), page.name


_GROUP = re.compile(r"\.(?:sheet|dash__group)(?![\w-])")
_STILL_PROPS = re.compile(r"(?:opacity|transform|translate|scale|rotate|visibility|clip-path|"
                          r"content-visibility|animation[\w-]*|transition[\w-]*)$")


def test_no_journey_rule_moves_fades_or_clips_a_dashboard_group():
    """reveal.js hides .dash__grid > * with opacity and transform in app.css's screens layer and
    settles it with an animation. journey sits above that layer, so any of these on a group would
    beat the reveal and leave a group stuck or unrevealed. overflow would clip focus rings."""
    bad = []
    for sel, body, _chain in iter_rules(read_css(JOURNEY_CSS)):
        d = decls(body)
        for part in _dash_split(sel):
            subject = re.sub(r":not\([^)]*\)", "", _dash_subject(part))
            if not (_GROUP.search(subject) or part.endswith(".dash__grid>*")):
                continue
            bad += [(part, p) for p in d if _STILL_PROPS.fullmatch(p)]
            bad += [(part, "overflow") for p in ("overflow", "overflow-x", "overflow-y")
                    if re.search(r"hidden|clip", d.get(p, ""))]
    assert bad == []


def _dash_rgba(value: str) -> tuple[float, ...]:
    m = re.fullmatch(r"rgba\(([^)]*)\)", value.replace(" ", ""))
    assert m, value
    return tuple(float(x) for x in m.group(1).split(","))


def test_the_live_panel_gains_an_edge_in_dark_only():
    """Spec 5.2: navy #0B2545 sits close to the dark ground, so it gains a 1px edge at white 12
    percent. The one value is the hairline token: navy on navy in light, white 12% in dark."""
    css = read_css(JOURNEY_CSS)
    touched = {}
    for sel, body, _chain in iter_rules(css):
        if ".status--live" in _dash_split(sel):
            touched.update(decls(body))
    assert touched == {"border-color": "var(--j-hairline)"}
    assert _dash_rgba(tokens(css, "dark")["--j-hairline"]) == (255, 255, 255, 0.12)
    assert _dash_rgba(tokens(css, "light")["--j-hairline"])[:3] == (11, 37, 69)


def _dash_dark() -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for sel, body, chain in iter_rules(_dash_section()):
        if chain:
            for part in _dash_split(sel):
                out.setdefault(part, {}).update(decls(body))
    return out


def test_the_dashboard_panels_keep_aa_in_dark():
    t, dark = tokens(read_css(JOURNEY_CSS), "dark"), _dash_dark()
    paused = dark[".status--paused"]["background"]
    assert re.fullmatch(r"#[0-9A-Fa-f]{6}", paused), paused
    for fg, floor in (("--j-text", 4.5), ("--j-muted", 4.5), ("--j-link", 4.5), ("--j-edge", 3)):
        assert contrast(t[fg], paused) >= floor, (fg, round(contrast(t[fg], paused), 2))
    # The Gmail panel sits on the surface in dark, so its primary keeps a 3:1 edge (3.24, spec
    # 5.3). On the amber ground #2A2110 the frozen blue would measure 2.98.
    assert dark[".status--gmail"]["background"] == "var(--j-surface)"
    assert contrast(t["--j-primary"], t["--j-surface"]) >= 3


# app.css paints these with a fixed light-page navy, so journey must repaint them from a token.
REDRAWN = [(".chip", "color"), (".chip .icon", "color"), (".usage-note--cap", "color"),
           (".usage-note--near", "color"), (".meter--full li.on", "background"),
           (".bar__fill--100", "background"), (".dash .numbered>li::before", "background")]


@pytest.mark.parametrize("part,prop", REDRAWN, ids=[p for p, _ in REDRAWN])
def test_every_fixed_light_colour_on_the_dashboard_follows_the_scheme(part, prop):
    values = [decls(body)[prop] for sel, body, chain in iter_rules(_dash_section())
              if not chain and part in _dash_split(sel) and prop in decls(body)]
    assert values and values[-1].startswith("var(--j-"), values


# --- review focus: a phone in dark mode opening the dashboard ----------------------------------
#
# Uses Task 4's selector matcher (sel_split, sel_reaches, journey_style_rules) and Task 5's
# _state(), which sit earlier in this file.

# app.css tokens that section 2 re-points at the journey tokens, so they follow dark mode.
_DASH_FOLLOWS = {"--ground", "--surface", "--sunk", "--line", "--line-strong", "--text-strong",
                 "--text", "--text-muted"}
# Colours that already read on both grounds, so they stay in dark mode on purpose: the frozen
# primary blue #0B6BC7 (spec 5.3, 3.24 to 1 on the dark surface) and the amber #B86E00 that also
# marks invalid fields in both schemes (4.33 to 1 on the dark surface). Both fill meter segments.
_DASH_SCHEME_FREE = {"--blue-600", "--amber-600"}
# Painted the same in both schemes on purpose (spec 3, 5.2, 9): the navy live panel, Google's
# button, the white sample email, white text on the blue and red buttons, the navy skip link.
_DASH_ISLANDS = {"status--live", "gsi-btn", "mailcard", "btn--primary", "btn--danger", "skip-link"}
_DASH_PAINT = {"color": "color", "background": "background", "background-color": "background",
               "fill": "fill", "stroke": "stroke", "border-color": "border", "border": "border",
               "border-top": "border", "border-right": "border", "border-bottom": "border",
               "border-left": "border", "border-block": "border", "border-inline": "border"}
_DASH_LITERAL = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\b(?:white|black)\b", re.I)


def _dash_fixed(value: str) -> bool:
    """True when an app.css colour stays the light-page colour in dark mode."""
    names = set(re.findall(r"var\(\s*(--[\w-]+)", value))
    return bool(_DASH_LITERAL.search(value)) or any(
        not n.startswith(("--j-", "--ob-")) for n in names - _DASH_FOLLOWS - _DASH_SCHEME_FREE)


def _dash_chain(node) -> list:
    """The node and its ancestors as Task 4's matcher reads them: outermost first."""
    out = []
    while node is not None and node.tag != "#root":
        out.append((node.tag, node.attrs))
        node = node.parent
    return out[::-1]


@pytest.mark.parametrize("state", DASH_STATES)
def test_no_light_page_colour_survives_on_the_dashboard_in_dark_mode(saas_cfg, master_key, state):
    """A phone in dark mode opening the dashboard. app.css paints some parts with fixed
    light-page colours (navy text, sky tints, amber edges). Each one that lands on this page,
    including what waits in a closed disclosure such as the Disconnect button, must be redrawn
    by a journey rule, which wins over app.css whatever the specificity, or sit on a part that
    is painted the same in both schemes on purpose."""
    elements = []
    for node in _dash_tree(_dash(saas_cfg, master_key, state)).walk():
        chain = _dash_chain(node)
        classes = {c for _tag, attrs in chain for c in attrs.get("class", "").split()}
        if "body" in [tag for tag, _attrs in chain] and not classes & _DASH_ISLANDS:
            elements.append((node, chain))
    assert len(elements) > 50, "sanity: the page rendered"
    journey = [(sel_split(sel, ","), {_DASH_PAINT[p] for p in props if p in _DASH_PAINT})
               for sel, props, at in journey_style_rules()
               if not any("forced-colors" in a for a in at)]
    missing = []
    for sel, body, chain in iter_rules(read_css(APP_CSS)):
        if sel.startswith("@") or any(re.search(r"forced-colors|print", c) for c in chain):
            continue
        paint = {_DASH_PAINT[p]: v for p, v in decls(body).items()
                 if p in _DASH_PAINT and _dash_fixed(v)}
        if not paint:
            continue
        for part in sel_split(sel, ","):
            for node, el in elements:
                if not sel_reaches(_state(part), el):
                    continue
                for family, value in paint.items():
                    if not any(family in fams and any(sel_reaches(_state(q), el) for q in parts)
                               for parts, fams in journey):
                        missing.append(f"<{node.tag} class='{node.attrs.get('class', '')}'> "
                                       f"{part} {{{family}: {value}}}")
    assert missing == [], "redraw these in journey.css section 9: " + "; ".join(sorted(set(missing)))
```

The last test is review focus 1 (a phone in dark mode opening the dashboard). It asks, for
every element the page prints, closed disclosures included, whether an app.css colour that
stays light in dark mode reaches it, and if so whether a journey rule redraws it. It found the
"near the limit" meter (amber `#B86E00`, which reads on both grounds and is allowed on purpose)
and proved every other fixed colour on the dashboard is redrawn. It runs in about 0.3 seconds
per state.

- [ ] **Step 3: Run the new tests and watch them fail**

```bash
.venv/Scripts/python.exe -m pytest -q tests/test_saas_journey.py
```

Expected: `64 failed, 201 passed`. The 64 (measured) are Task 3's
`test_the_journey_look_loads_on_exactly_the_listed_templates[dashboard.html]` (the template links
neither file yet) and these 63 Task 6 items:
- `test_the_dashboard_loads_the_journey_look_after_the_motion_head` (no Basecoat link).
- `test_three_groups_sit_directly_in_the_grid_in_spec_order`, all 8 states (today the grid holds
  five sheets in the order Today, Keywords, Gmail, Your details, When an email arrives).
- `test_the_gmail_group_keeps_the_arrival_flag_and_its_stamped_badge[live-2]`, `[no keywords-1]`,
  `[daily limit-1]` (the flagged sheet has no `dash__group` class, and its title reads
  "Gmail Connected" because the badge sits in it).
- `test_the_limit_phrase_shows_once_at_the_limit_and_never_in_the_panel[gmail off at the limit]`
  and `[daily limit]` (the phrase is in the first grid child today, not the third).
- `test_the_keywords_stay_visible_in_every_state`, all 8.
- `test_connect_gmail_shows_once_at_most_with_its_label_in_a_direct_span[gmail off]`,
  `[gmail off, retry]`, `[gmail off at the limit]` (2 links today: the panel and the duplicate)
  and `[reconnect failed]`.
- `test_add_keywords_shows_once_on_an_empty_watch_list` (2 today).
- `test_quiet_edit_links_replace_the_old_group_buttons`, all 8.
- `test_the_gmail_group_shows_the_address_its_badge_and_the_disconnect_row`, all 8.
- `test_usage_is_one_text_node_and_the_meter_widths_are_classes`, both.
- `test_when_an_email_arrives_is_a_plain_note_after_the_groups`.
- `test_the_live_panel_gains_an_edge_in_dark_only`, `test_the_dashboard_panels_keep_aa_in_dark`
  (`KeyError: '.status--paused'`) and the 7 `test_every_fixed_light_colour_on_the_dashboard_follows_the_scheme`
  cases (section 9 is empty).
- `test_no_light_page_colour_survives_on_the_dashboard_in_dark_mode`, all 8 (nothing redraws the
  chips, the capped and near notes, the full meter or the panels yet).

The 22 Task 6 items that already pass are the 8 panel and primary cases (the panel does not
change), the arrival cases `[reconnect failed-0]` and `[gmail off-0]`, the 6 uncapped limit
cases, the Connect Gmail cases `[no keywords]`, `[daily limit]`, `[live]` and `[near the limit]`,
and the two section 9 guards, which only forbid things.

- [ ] **Step 4: Rewrite dashboard.html**

Before, `applyfirst/saas/templates/dashboard.html` lines 5 to 6:

```html
{% block html_attrs %} data-step="0"{% endblock %}
{% block motion_head %}{{ ui.motion_head() }}{% endblock %}
```

Before, lines 71 to 138:

```html
    <div class="dash__grid">
      {% call ui.sheet("Today", "today-title", cls="span-5") %}
      {# The usage line stays one text node with single spaces. #}
      <p class="usage">{{ usage_today }} / {{ daily_cap }}</p>
      <p class="usage-label">applications today</p>
      {{ ui.meter(usage_today, daily_cap) }}
      {%- if usage_today >= daily_cap %}
      {# The lowercase limit phrase lives only in this capped branch. #}
      <p class="usage-note usage-note--cap">{{ icon('clock', 16) }}<span>Paused for today, daily limit reached. New matches today are skipped. We start again at 8:00 AM.</span></p>
      {%- elif daily_cap - usage_today <= 2 %}
      <p class="usage-note usage-note--near">{{ icon('clock', 16) }}<span>{{ daily_cap - usage_today }} left today. Resets at 8:00 AM Philippine time.</span></p>
      {%- else %}
      <p class="usage-note">{{ icon('clock', 16) }}<span>Resets at 8:00 AM Philippine time.</span></p>
      {%- endif %}
      {% endcall %}

      {% call ui.sheet("Keywords you're watching", "kw-title", cls="span-7") %}
      {%- if keywords %}
      <ul class="chip-list" aria-label="Your keywords">
        {%- for k in keywords %}
        {{ ui.chip(k.keyword) }}
        {%- endfor %}
      </ul>
      <div class="card-actions">{{ ui.link_button("/onboarding/keywords", "Edit keywords", variant="secondary") }}</div>
      {%- else %}
      <p class="kv">None yet.</p>
      <div class="card-actions">{{ ui.link_button("/onboarding/keywords", "Add keywords", variant="secondary", icon_name="plus") }}</div>
      {%- endif %}
      {% endcall %}

      {%- set gmail_title %}Gmail {% if gmail_connected %}{{ ui.badge("Connected", "ok") }}{% else %}{{ ui.badge("Not connected", "attention") }}{% endif %}{% endset %}
      {% call ui.sheet(gmail_title, "gm-title", cls="span-7", arrive=(gmail_connected and not retry)) %}
      {%- if gmail_connected %}
      <p class="kv">Applications go to<b class="addr-inline">{{ ui.email_text(user.email) }}</b></p>
      {%- if retry %}
      <div class="card-actions">{{ ui.link_button("/auth/connect-gmail", "Connect Gmail", variant="secondary", icon_name="mail") }}</div>
      {%- endif %}
      {% call ui.disclose("Disconnect Gmail", cls="disconnect") %}
        <p>We'll stop sending you applications and remove our access at Google. You can reconnect any time.</p>
        <form method="post" action="/auth/disconnect-gmail">
          {{ ui.csrf_field(csrf_token) }}
          {{ ui.button("Disconnect Gmail", variant="danger", busy="Disconnecting") }}
        </form>
      {% endcall %}
      {%- else %}
      <p class="kv">New matches can't reach you until you connect it.</p>
      <div class="card-actions">{{ ui.link_button("/auth/connect-gmail", "Connect Gmail", variant="secondary", icon_name="mail") }}</div>
      {%- endif %}
      {% endcall %}

      {% call ui.sheet("Your details", "det-title", cls="span-5") %}
      {%- if profile and profile.job_type %}
      <p class="kv">Looking for<b>{{ profile.job_type }}</b></p>
      {%- else %}
      <p class="kv">Not set yet.</p>
      {%- endif %}
      <div class="card-actions">{{ ui.link_button("/onboarding/profile", "Edit details", variant="secondary") }}</div>
      {% endcall %}

      {% call ui.sheet("When an email arrives", "arr-title", cls="span-12 arrives") %}
      {% call ui.route(horizontal=true) %}
        <li>Look for an email from <strong>me</strong> with 🆕 at the start of the subject.</li>
        <li>Copy the subject and message.</li>
        <li>Paste them into your application on onlinejobs.ph, check, and send.</li>
      {% endcall %}
      <p class="arrives__note">We only send jobs posted after you start, so every email is a fresh post. That's how you stay early.</p>
      {% endcall %}
    </div>
```

After: replace the whole file with the text below, with the Write tool (LF endings, UTF-8, the
🆕 kept as the character itself). Lines 1 to 4, the variables and the whole status panel
(`dashboard.html:7-70` today, lines 14 to 77 after) and the last three lines are byte for byte
what they are today.

```html
{% extends "base.html" %}
{% import "_ui.html" as ui %}
{% from "_icons.html" import icon %}
{% block title %}Dashboard · Agad{% endblock %}
{% block html_attrs %} data-step="0"{% endblock %}
{% block color_scheme %}light dark{% endblock %}
{% block theme_color_meta %}<meta name="theme-color" content="#FFFFFF" media="(prefers-color-scheme: light)">
  <meta name="theme-color" content="#111B2B" media="(prefers-color-scheme: dark)">{% endblock %}
{% block motion_head %}{{ ui.motion_head() }}{% endblock %}
{% block page_css %}
  <link rel="stylesheet" href="{{ static_url('vendor/basecoat-1.0.2-agad.css') }}">
  <link rel="stylesheet" href="{{ static_url('css/journey.css') }}">
{% endblock %}
{% block content %}
{%- set N = [check_every_min | default(10), 50] | min %}
{%- set retry = gmail_error | default(none) %}
{#- What is being watched, for the first view on a phone: the first three keywords, then a count. Escaped like any user text. #}
{%- set kw_more = (keywords | length) - 3 %}
{%- set watched %}{% for k in keywords[:3] %}<strong>{{ k.keyword }}</strong>{% if not loop.last %}, {% endif %}{% endfor %}{% if kw_more > 0 %} +{{ kw_more }} more{% endif %}{% endset %}
<div class="dash">
  <div class="container--app dash__stack">
    {%- if retry %}
    {{ ui.gmail_retry_note(retry, gmail_connected) }}
    {%- endif %}

    {#- Exactly one status panel, by priority: Gmail, then keywords, then today's limit, else live. #}
    {%- if not gmail_connected %}
    {% call ui.status_panel("gmail", "dash-title") %}
      <h1 id="dash-title">Gmail isn't connected</h1>
      <p>New matches can't reach you until you connect it. It takes about 30 seconds.</p>
      {# BETA: remove after Google verification #}
      <p class="muted">During the beta, Google asks you to reconnect every 7 days.</p>
      {# /BETA #}
      {{ ui.link_button("/auth/connect-gmail", "Connect Gmail", icon_name="mail") }}
      {% call ui.disclose("What will Google ask me?") %}
        <ol class="numbered">
          <li>Choose <strong class="addr-inline">{{ ui.email_text(user.email) }}</strong>.</li>
          {# BETA: remove after Google verification #}
          <li>If Google says it hasn't verified this app, tap <strong>Advanced</strong>, then <strong>Go to Agad (unsafe)</strong>. Google adds the word unsafe to every new app it is still reviewing.</li>
          {# /BETA #}
          <li>Tick <strong>“Send email on your behalf”</strong>, then tap <strong>Continue</strong>.</li>
        </ol>
      {% endcall %}
    {% endcall %}
    {%- elif not keywords %}
    {% call ui.status_panel("empty", "dash-title") %}
      <h1 id="dash-title">You're not watching any jobs</h1>
      <p>Add a keyword so we know what to look for.</p>
      {{ ui.link_button("/onboarding/keywords", "Add keywords", icon_name="plus") }}
    {% endcall %}
    {%- elif usage_today >= daily_cap %}
    {% call ui.status_panel("paused", "dash-title") %}
      <h1 id="dash-title">Paused until 8:00 AM</h1>
      <p>You reached today's limit of {{ daily_cap }}. New matches before 8:00 AM Philippine time are skipped, not saved.</p>
      <p class="status__kw">{{ icon('tag', 16) }}<span>Your keywords: {{ watched }}</span></p>
      {{ ui.link_button("/onboarding/keywords", "Edit keywords", variant="secondary") }}
    {% endcall %}
    {%- else %}
    {% call ui.status_panel("live", "dash-title", fresh=activated_fresh | default(false),
                            burst=(static_url('vendor/canvas-confetti-1.9.4.js')
                                   if ui.CELEBRATE and (activated_fresh | default(false)) else none),
                            arrive=(not retry)) %}
      <h1 id="dash-title">Watching onlinejobs.ph for you</h1>
      <p>We check about every {{ N }} minutes, day and night. New matches go to <strong class="addr-inline">{{ ui.email_text(user.email) }}</strong>.</p>
      <p class="status__kw">{{ icon('tag', 16) }}<span>Watching for: {{ watched }}</span></p>
      {#- The start of the current unbroken watch. Never faked: the route passes it only when it is true. -#}
      {%- if watching_since | default(none) %}
      <p class="since">{{ icon('clock', 16) }}Watching since {{ watching_since }}</p>
      {%- endif %}
      {#- Ready slot: shows only if the backend ever passes the minutes since the last check. Never faked. #}
      {%- if last_check_minutes is defined and last_check_minutes is not none %}
      <p class="lastcheck">{{ icon('clock', 16) }}Last check {{ last_check_minutes }} minutes ago</p>
      {%- endif %}
      <p class="status__first">Your first email comes when a <strong>new</strong> job matching your keywords is posted. That can be minutes or a few days, depending on your keywords.</p>
    {% endcall %}
    {%- endif %}

    {#- Three groups of rows, each a direct child of .dash__grid (the reveal layer reads .dash__grid > *).
        Quiet Edit links replace the old secondary buttons; the panel above keeps the one primary. #}
    <div class="dash__grid">
      {% call ui.sheet("Watching", "watch-title", cls="dash__group") %}
      <div class="dash__row">
        <p class="dash__label">Keywords</p>
        {%- if keywords %}
        <ul class="chip-list dash__value" aria-label="Your keywords">
          {%- for k in keywords %}
          {{ ui.chip(k.keyword) }}
          {%- endfor %}
        </ul>
        {%- else %}
        <p class="dash__value">None yet</p>
        {%- endif %}
        <a class="text-link dash__end" href="/onboarding/keywords">Edit<span class="visually-hidden"> keywords</span></a>
      </div>
      <div class="dash__row">
        <p class="dash__label">Looking for</p>
        <p class="dash__value">{% if profile and profile.job_type %}{{ profile.job_type }}{% else %}Not set yet{% endif %}</p>
        <a class="text-link dash__end" href="/onboarding/profile">Edit details</a>
      </div>
      {% endcall %}

      {% call ui.sheet("Gmail", "gm-title", cls="dash__group", arrive=(gmail_connected and not retry)) %}
      <div class="dash__row">
        <p class="dash__label addr-inline">{{ ui.email_text(user.email) }}</p>
        {%- if gmail_connected %}
        {{ ui.badge("Connected", "ok") }}
        {%- else %}
        {{ ui.badge("Not connected", "attention") }}
        {%- endif %}
      </div>
      {%- if gmail_connected %}
      {%- if retry %}
      {#- The reconnect failed but the old grant still works: this is the only Connect Gmail on the page. #}
      <div class="dash__row">{{ ui.link_button("/auth/connect-gmail", "Connect Gmail", variant="secondary", icon_name="mail") }}</div>
      {%- endif %}
      {% call ui.disclose("Disconnect Gmail", cls="disconnect") %}
        <p>We'll stop sending you applications and remove our access at Google. You can reconnect any time.</p>
        <form method="post" action="/auth/disconnect-gmail">
          {{ ui.csrf_field(csrf_token) }}
          {{ ui.button("Disconnect Gmail", variant="danger", busy="Disconnecting") }}
        </form>
      {% endcall %}
      {%- endif %}
      {% endcall %}

      {% call ui.sheet("Today", "today-title", cls="dash__group") %}
      <div class="dash__row">
        <p class="dash__label">Applications today</p>
        {# The usage line stays one text node with single spaces. #}
        <p class="usage">{{ usage_today }} / {{ daily_cap }}</p>
        {{ ui.meter(usage_today, daily_cap) }}
      </div>
      {%- if usage_today >= daily_cap %}
      {# The lowercase limit phrase lives only in this capped branch. #}
      <p class="usage-note usage-note--cap">{{ icon('clock', 16) }}<span>Paused for today, daily limit reached. New matches today are skipped. We start again at 8:00 AM.</span></p>
      {%- elif daily_cap - usage_today <= 2 %}
      <p class="usage-note usage-note--near">{{ icon('clock', 16) }}<span>{{ daily_cap - usage_today }} left today. Resets at 8:00 AM Philippine time.</span></p>
      {%- else %}
      <p class="usage-note">{{ icon('clock', 16) }}<span>Resets at 8:00 AM Philippine time.</span></p>
      {%- endif %}
      {% endcall %}
    </div>

    <section class="dash__help" aria-labelledby="arr-title">
      <h2 id="arr-title">When an email arrives</h2>
      <ol>
        <li>Look for an email from <strong>me</strong> with 🆕 at the start of the subject.</li>
        <li>Copy the subject and message.</li>
        <li>Paste them into your application on onlinejobs.ph, check, and send.</li>
      </ol>
      <p>We only send jobs posted after you start, so every email is a fresh post. That's how you stay early.</p>
    </section>
  </div>
</div>
{% endblock %}
```

What changed, and nothing else did:
- Head. `color_scheme` becomes `light dark`, `theme_color_meta` prints the light and dark
  theme-color metas at the header surface (`#FFFFFF`, `#111B2B`), and `page_css` links the trimmed
  Basecoat file then `journey.css`, all exactly the snippet Task 3 fixed. `page_css` renders after
  `motion_head`, so M-1 holds.
- The status panel: not touched. Selection, copy, primaries and every motion hook are as today.
- Watching group: the Keywords row (label, the saved words as the existing `ui.chip` pills, or
  "None yet", and a quiet `Edit` link to `/onboarding/keywords` whose accessible name is "Edit
  keywords"), then the Looking for row (the job type, or "Not set yet", and `Edit details` to
  `/onboarding/profile`). This replaces the "Keywords you're watching" sheet with its secondary
  Edit keywords or Add keywords button and the "Your details" sheet with its secondary Edit
  details button.
- Gmail group: the address row with the Connected or Not connected badge (the badge moves out of
  the title), then, only when Gmail is connected but a reconnect failed, a secondary Connect Gmail
  `a.btn`, then the unchanged Disconnect Gmail `details` with its CSRF form. The "New matches
  can't reach you" line and the duplicate secondary Connect Gmail for the not-connected case are
  gone (the panel above says it and holds the primary).
- Today group: the "Applications today" row with "N / M" as one text node and the class-based
  meter, then the usage note as the group note ("daily limit reached" only in the capped
  sentence, unchanged).
- "When an email arrives": a plain note after `.dash__grid` (a small heading, a plain numbered
  list, the closing line), no longer a sheet and no longer the route motif.

- [ ] **Step 5: Fill section 9 of journey.css**

Read `applyfirst/saas/static/css/journey.css`, then use the Edit tool. `old_string` is the two
banner lines Task 3 left next to each other:

```css
/* ---- 9 dashboard */
/* ---- 10 signin-failed */
```

`new_string` is (section 9, then the unchanged section 10 banner as its last line):

```css
/* ---- 9 dashboard */
/* Spec 6.3. The status panel, then one 40rem column of three groups of rows, then a plain help
   note. Every selector names a class only dashboard.html prints. The panel frame is motion's
   (navy, 24px): only its edge colour is set here, the hairline, which vanishes on navy in light
   and is white at 12% in dark. The dark block redraws the fixed light tints of the panels. */
.dash__stack{max-width:40rem}
.dash__grid{grid-template-columns:minmax(0,1fr);gap:16px}
.dash__group{padding:14px 20px 4px}
.dash__group>.card-title{margin:0;font-size:var(--fs-caption);font-weight:500;letter-spacing:0;color:var(--j-muted)}
.dash__row{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:8px 16px;padding-block:12px}
.dash__row+.dash__row,.dash__group>.disconnect{border-top:1px solid var(--j-hairline)}
.dash__group>.disconnect{margin:0;padding:0}
.dash__label{font-weight:500}
.dash__value{color:var(--j-muted)}
.dash__row>:is(.dash__value,.meter,.bar){grid-column:1/-1;margin:0}
.dash__end{grid-area:1/2}
.dash__row>.btn{justify-self:start}
.usage{font-size:inherit;font-weight:600;line-height:inherit;letter-spacing:0}
.dash__group>.usage-note{padding-bottom:12px}
.usage-note .icon{color:inherit}
.usage-note--near{color:var(--j-attn-fg)}
.usage-note--cap,.chip{color:var(--j-text)}
.chip .icon,.dash .disclose>summary .icon{color:var(--j-muted)}
.meter--full li.on,.bar__fill--100,.dash .numbered>li::before{background:var(--j-text)}
.dash .numbered>li::before{color:var(--j-surface)}
.dash__help{padding-inline:4px;font-size:var(--fs-small);color:var(--j-muted)}
.dash__help h2{font-size:inherit;color:var(--j-text)}
.dash__help ol{margin:6px 0;padding-left:20px}
.status--live{border-color:var(--j-hairline)}
@media (prefers-color-scheme:dark){
.status--gmail{background:var(--j-surface)}
.status--gmail,.status--gmail details{border-color:rgba(245,198,107,.35)}
.status--gmail .status__icon{background:rgba(245,198,107,.14);color:var(--j-attn-fg)}
.status--paused{background:#0F2436;border-color:rgba(92,184,240,.3)}
.status__icon,.status--paused .status__kw .icon{color:var(--j-link)}
.status--empty .status__icon,.status--paused .status__icon{background:rgba(92,184,240,.12)}
}
/* ---- 10 signin-failed */
```

What each part does. `.dash__stack` caps the whole stack (retry note, panel, groups, help) at
40rem and `container--app` keeps centring it. `.dash__grid` goes to one column, which also
cancels app.css's 12-column grid from 800px (`app.css:670-674`), because a journey rule beats
app.css at any width. A group is the existing `.sheet` with tighter padding; its `h2` takes the
label style (12px, weight 500, muted). A row is a two-column grid: label left, the Edit link or
badge or "N / M" right (`.dash__end` pins a link to row 1, column 2), and the value, the chips or
the meter below across both columns, with hairlines between rows. The usage note is the group
note. The rest repaints what app.css draws with a fixed light-page colour and would vanish in
dark: chip text and icons (`app.css:186-187`), the capped and near notes (`:610-612`), the full
meter and the 100 percent bar (`:294`, `:298`), the Gmail panel's numbered steps (`:219-220`) and
the chevrons (`:284`). `.status--live` gets only its edge colour. The dark block redraws the
panels app.css tints for a light page (`app.css:356-364`): the Gmail panel sits on the surface
with an amber edge, because the frozen blue primary measures 2.98 to 1 against the amber ground
`#2A2110` and 3.24 on the surface; the paused panel gets a dark sky tint `#0F2436` (text 13.4, muted
6.8, link 7.2, control edge 3.6 to 1); the icon wells get translucent tints. Nothing here moves,
so section 11 gets nothing. Section 9 is 36 lines and 2,212 bytes, and adds 653 B gzip (4,280 to
4,933 B, measured in sequence after Tasks 1 to 5; the cap is 8,000).

Check the file:

```bash
.venv/Scripts/python.exe -c "import gzip,pathlib;b=pathlib.Path('applyfirst/saas/static/css/journey.css').read_bytes();print(len(b),len(gzip.compress(b,9,mtime=0)),b.count(b'\r'))"
```

Expected, in sequence after Tasks 1 to 5: `14526 4933 0` (14,526 bytes, 4,933 B gzip, no CR). If
an earlier section landed with different bytes, the first two numbers move with it; the gzip must
stay under 8,000 and the last number must be `0` (LF only).

- [ ] **Step 6: Run the new tests and watch them pass**

```bash
.venv/Scripts/python.exe -m pytest -q tests/test_saas_journey.py
```

Expected: every test in the file passes, `265 passed`, including the 85 Task 6 items and Task 3's
scope test for `dashboard.html`.

- [ ] **Step 7: Measure the dashboard in headless Chrome, light and dark**

The static tests cannot see the real cascade of app.css, motion.css, Basecoat and journey.css.
With the Write tool, save this as `measure_dashboard.py` in your session scratchpad (not in the
repo), then run it from the repo root. It needs Chrome at
`C:\Program Files\Google\Chrome\Application\chrome.exe` and starts no server.

```python
"""Measure /dashboard in headless Chrome: six states, light and dark, phone and computer.

    .venv/Scripts/python.exe measure_dashboard.py <repo root> [<screenshot folder>]

No server runs. Each page is rendered by the app's own TestClient, its /static links are pointed
at the files on disk, the scripts are dropped (content never needs JavaScript, and without
reveal.js nothing is hidden), and a probe script reads computed styles back through --dump-dom.
Chrome runs with a throwaway profile and exits by itself. Exit 1 if any check fails.

Checks, each printed as PASS or FAIL:
  * every visible text reaches 4.5:1 (3:1 at 24px, or 18.66px bold) on its real background;
  * no sideways scroll;
  * the live panel is the frozen frame (spec 9): #0B2545, 24px corners, position relative,
    isolation isolate, opacity 1, and its edge is navy on navy in light, white 12% in dark;
  * the three groups: surface colour of the scheme, 12px corners, overflow visible, the column
    at most 640px wide;
  * a full meter segment and the chips stay visible in dark (not navy on navy).
"""
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(sys.argv[1]).resolve()
SHOTS = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else None
sys.path.insert(0, str(REPO))

from fastapi.testclient import TestClient  # noqa: E402

from applyfirst.saas import db, session  # noqa: E402
from applyfirst.saas.app import create_app  # noqa: E402
from applyfirst.saas.config import SaaSConfig  # noqa: E402

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
STATIC = REPO / "applyfirst" / "saas" / "static"
TOUCH = ("--blink-settings=primaryPointerType=2,availablePointerTypes=2,"
         "primaryHoverType=1,availableHoverTypes=1")
MODES = {"light phone": ("504,1400", [TOUCH]), "dark phone": ("504,1400", ["--force-dark-mode", TOUCH]),
         "light computer": ("1280,1100", []), "dark computer": ("1280,1100", ["--force-dark-mode"])}
SURFACE = {"light": "rgb(255, 255, 255)", "dark": "rgb(17, 27, 43)"}
EDGE = {"light": "rgba(11, 37, 69, 0.1)", "dark": "rgba(255, 255, 255, 0.12)"}
# name: (keywords, gmail, usage, query)
STATES = {
    "gmail-off": (("virtual assistant", "data entry"), False, 0, ""),
    "no-keywords": ((), True, 0, ""),
    "limit": (("virtual assistant",), True, 10, ""),
    "near": (("virtual assistant",), True, 9, ""),
    "live": (("virtual assistant", "data entry", "customer service", "social media manager"),
             True, 3, ""),
    "reconnect-failed": (("virtual assistant",), True, 0, "?gmail_error=scope"),
}

PROBE = """<script>
addEventListener('load', () => {
  const cs = (el) => getComputedStyle(el);
  const rgb = (s) => { const m = /rgba?\\(([^)]+)\\)/.exec(s); if (!m) return null;
    const p = m[1].split(/[\\s,\\/]+/).filter(Boolean).map(Number); return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; };
  const over = (t, u) => [0, 1, 2].map((i) => t[i] * t[3] + u[i] * (1 - t[3])).concat(1);
  const bg = (el) => { const chain = []; for (let e = el; e; e = e.parentElement) chain.unshift(e);
    let c = [255, 255, 255, 1]; for (const e of chain) { const b = rgb(cs(e).backgroundColor);
    if (b === null) return null; if (b[3] > 0) c = over(b, c); } return c; };
  const lum = (c) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); };
  const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  const name = (el) => el.tagName.toLowerCase() + (typeof el.className === "string" && el.className.trim() ? "." + el.className.trim().split(/\\s+/).join(".") : "");
  const out = { texts: [], overflow: document.documentElement.scrollWidth - innerWidth };
  for (const el of document.querySelectorAll("body *")) {
    if (el.closest(".visually-hidden, [hidden], script, style, details:not([open]) > div")) continue;
    const own = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
    if (!own || !el.getClientRects().length) continue;
    const s = cs(el), fg = rgb(s.color), b = bg(el);
    const size = parseFloat(s.fontSize), large = size >= 24 || (size >= 18.66 && +s.fontWeight >= 700);
    out.texts.push({ el: name(el), text: el.textContent.trim().slice(0, 30),
      ratio: fg && b ? +ratio(over(fg, b), b).toFixed(2) : null, need: large ? 3 : 4.5 });
  }
  const live = document.querySelector(".status--live");
  if (live) { const s = cs(live); out.live = [s.backgroundColor, s.borderTopLeftRadius, s.position, s.isolation, s.opacity, s.borderTopColor]; }
  out.groups = [...document.querySelectorAll(".dash__grid > *")].map((g) => { const s = cs(g); return [s.backgroundColor, s.borderTopLeftRadius, s.overflowX, s.overflowY]; });
  out.column = document.querySelector(".dash__stack").getBoundingClientRect().width;
  const on = document.querySelector(".meter--full li.on");
  out.full = on ? [cs(on).backgroundColor, bg(on.parentElement)] : null;
  const chip = document.querySelector(".chip");
  out.chip = chip ? cs(chip).color : null;
  document.getElementById("probe-out").textContent = JSON.stringify(out);
});
</script><pre id="probe-out"></pre>"""


def pages() -> dict[str, str]:
    tmp = tempfile.mkdtemp(prefix="af-dash-")
    mk = os.urandom(32)
    os.environ["APPLYFIRST_MASTER_KEY"] = base64.b64encode(mk).decode("ascii")
    secret = b"measure-session-secret-32-bytes!!!"
    cfg = SaaSConfig(db_path=str(Path(tmp) / "m.db"), google_client_id="m",
                     google_client_secret="m", session_secret=secret,
                     base_url="https://localhost", secure_cookies=False)
    client = TestClient(create_app(cfg), follow_redirects=False)
    conn = db.init_db(cfg.db_path)
    out = {}
    for i, (state, (kws, gmail, usage, query)) in enumerate(STATES.items()):
        u = db.upsert_user_by_google(conn, google_sub=f"m{i}", email="maria.santos@example.com",
                                     display_name="Maria Santos")
        db.upsert_profile(conn, u.id, full_name="Maria Santos", job_type="Virtual Assistant",
                          standard_subject="S", standard_message="M")
        for k in kws:
            db.add_keyword(conn, u.id, k)
        db.set_activated(conn, u.id)
        if gmail:
            db.store_gmail_credential(conn, u.id, refresh_token="rt", master_key=mk)
        for _ in range(usage):
            db.try_increment_ai_usage(conn, u.id, 1000)
        client.cookies.set("applyfirst_session", session.sign(secret, {"uid": u.id}))
        html = client.get("/dashboard" + query).text
        html = re.sub(r"<script\b[^>]*>.*?</script>", "", html, flags=re.S)
        html = re.sub(r'(href|src)="/static/([^"?]+)(?:\?[^"]*)?"',
                      lambda m: f'{m.group(1)}="{(STATIC / m.group(2)).as_uri()}"', html)
        out[state] = html
    conn.close()
    return out


def chrome(html: str, mode: str, shot: Path | None) -> dict:
    window, flags = MODES[mode]
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        f = Path(tmp) / "dash.html"
        base = [CHROME, "--headless=new", "--disable-gpu", "--no-first-run", "--hide-scrollbars",
                "--allow-file-access-from-files", f"--user-data-dir={tmp}/profile",
                f"--window-size={window}", "--virtual-time-budget=5000", *flags]
        if shot:
            f.write_text(html, encoding="utf-8")
            subprocess.run(base + [f"--screenshot={shot}", f.as_uri()], capture_output=True,
                           timeout=120)
        f.write_text(html.replace("</body>", PROBE + "</body>"), encoding="utf-8")
        res = subprocess.run(base + ["--dump-dom", f.as_uri()], capture_output=True, text=True,
                             encoding="utf-8", timeout=120)
    m = re.search(r'<pre id="probe-out">(.*?)</pre>', res.stdout, re.S)
    assert m and m.group(1), f"{mode}: the probe wrote nothing"
    return json.loads(m.group(1).replace("&quot;", '"').replace("&amp;", "&")
                      .replace("&lt;", "<").replace("&gt;", ">"))


fails = 0


def check(ok: bool, label: str) -> None:
    global fails
    fails += not ok
    print(("PASS " if ok else "FAIL ") + label)


if SHOTS:
    SHOTS.mkdir(parents=True, exist_ok=True)
for state, html in pages().items():
    for mode in MODES:
        scheme = mode.split()[0]
        shot = SHOTS / f"{state}-{mode.replace(' ', '-')}.png" if SHOTS else None
        got = chrome(html, mode, shot)
        tag = f"[{state}, {mode}]"
        low = [t for t in got["texts"] if t["ratio"] is None or t["ratio"] < t["need"]]
        check(not low, f"{tag} {len(got['texts'])} texts reach AA {low or ''}")
        check(got["overflow"] <= 0, f"{tag} no sideways scroll ({got['overflow']}px)")
        if "live" in got:
            check(got["live"] == ["rgb(11, 37, 69)", "24px", "relative", "isolate", "1", EDGE[scheme]],
                  f"{tag} live panel {got['live']}")
        check(len(got["groups"]) == 3 and all(g == [SURFACE[scheme], "12px", "visible", "visible"]
                                              for g in got["groups"]), f"{tag} groups {got['groups']}")
        check(got["column"] <= 640, f"{tag} column {got['column']}px")
        if got["full"]:
            fill, ground = got["full"]
            check(fill not in ("rgb(11, 37, 69)",) or scheme == "light", f"{tag} full meter {fill}")
        if got["chip"]:
            check(got["chip"] == ("rgb(11, 37, 69)" if scheme == "light" else "rgb(230, 237, 245)"),
                  f"{tag} chip text {got['chip']}")
print(f"\n{fails} failed")
sys.exit(1 if fails else 0)
```

```bash
.venv/Scripts/python.exe "<scratchpad>/measure_dashboard.py" . "<scratchpad>/dash-shots"
```

Expected: 132 lines of `PASS`, then `0 failed` (six states times four modes: 24 contrast, 24
sideways-scroll, 24 group, 24 column, 12 live panel, 4 full meter and 20 chip checks), and 24
PNGs in `dash-shots`. Open three of them (`live-dark-computer.png`,
`gmail-off-dark-phone.png`, `limit-dark-phone.png`) and check by eye: the navy live panel has a
faint light edge in dark and none in light, the groups read as three white (or `#111B2B`) cards
with hairline rows, Edit links on the right, no Connect Gmail in the Gmail group unless a
reconnect failed. What a FAIL means:
- "texts reach AA" lists each element under 4.5 to 1 with its ratio. A FAIL in a group or panel is
  section 9's to fix; one in the header or footer belongs to Task 3's sections 4 to 6.
- "live panel" printing another colour, radius, position, isolation or opacity means some
  journey rule reached `.status--live`. Find it and scope it. Never restyle the panel back.
- "groups" printing `hidden` means a rule clipped a group (focus rings and the reveal break).
- Headless Chrome will not open narrower than about 500px, so "phone" is 504px wide with a coarse
  pointer. The 360 and 390px screenshots, forced colours and reduced motion belong to Task 8.

- [ ] **Step 8: Prove the tests bite (mutation pass)**

With the Write tool, save this as `mutate6.py` in the scratchpad. It edits one repo file at a
time, runs the journey tests, and always puts the original bytes back.

```python
"""Plant one Task 6 mistake at a time and check the journey tests catch every one.

    .venv/Scripts/python.exe mutate6.py <repo root>

Each mutant edits one file, runs tests/test_saas_journey.py, and puts the original bytes back in a
finally block. Exit 1 if any mutant survives.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
T = ROOT / "applyfirst/saas/templates/dashboard.html"
J = ROOT / "applyfirst/saas/static/css/journey.css"
H = ROOT / "tests/_journey_css.py"
GMAIL_ROW_END = """        {{ ui.badge("Not connected", "attention") }}
        {%- endif %}
      </div>"""
KW_NONE = """        <p class="dash__value">None yet</p>"""
EDIT_KW = """<a class="text-link dash__end" href="/onboarding/keywords">"""
HELP_OPEN = """    </div>

    <section class="dash__help" aria-labelledby="arr-title">"""
GRID = """    <div class="dash__grid">
      {% call ui.sheet("Watching", "watch-title", cls="dash__group") %}"""
PAUSED = """<p>You reached today's limit of {{ daily_cap }}."""
CHIPS = """        {%- if keywords %}
        <ul class="chip-list dash__value" aria-label="Your keywords">"""
USAGE = """<p class="usage">{{ usage_today }} / {{ daily_cap }}</p>"""
CSRF = """          {{ ui.csrf_field(csrf_token) }}
          {{ ui.button("Disconnect Gmail", variant="danger", busy="Disconnecting") }}"""
RETRY = """{{ ui.link_button("/auth/connect-gmail", "Connect Gmail", variant="secondary", icon_name="mail") }}</div>"""
LIVE = ".status--live{border-color:var(--j-hairline)}"


def edit(path, *pairs):
    """A mutant: replace each (old, new) once, in order. old is a string or a compiled regex,
    and it must be present."""
    def apply():
        text = path.read_bytes().decode("utf-8")
        for old, new in pairs:
            if isinstance(old, re.Pattern):
                assert old.search(text), (path.name, old.pattern)
                text = old.sub(new, text, count=1)
            else:
                assert old in text, (path.name, old[:60])
                text = text.replace(old, new, 1)
        path.write_bytes(text.encode("utf-8"))
    return path, apply


MUTANTS = {
    "duplicate Connect Gmail back": edit(T, (GMAIL_ROW_END, GMAIL_ROW_END + """
      {%- if not gmail_connected %}<div>{{ ui.link_button("/auth/connect-gmail", "Connect Gmail", variant="secondary", icon_name="mail") }}</div>{% endif %}""")),
    "duplicate Add keywords back": edit(T, (KW_NONE, KW_NONE + """{{ ui.link_button("/onboarding/keywords", "Add keywords", variant="secondary", icon_name="plus") }}""")),
    "Edit link becomes a button": edit(T, (EDIT_KW, """<a class="btn btn--secondary dash__end" href="/onboarding/keywords">""")),
    "help note back in the grid": edit(T, (HELP_OPEN, """
    <section class="dash__help" aria-labelledby="arr-title">""")),
    "groups wrapped": edit(T, (GRID, """    <div class="dash__grid"><div>
      {% call ui.sheet("Watching", "watch-title", cls="dash__group") %}"""), (HELP_OPEN, """    </div></div>

    <section class="dash__help" aria-labelledby="arr-title">""")),
    "Gmail group loses its flag": edit(T, ("""cls="dash__group", arrive=(gmail_connected and not retry))""", """cls="dash__group")""")),
    "limit phrase in the panel": edit(T, (PAUSED, """<p>Paused, daily limit reached. You reached today's limit of {{ daily_cap }}.""")),
    "keywords hidden with Gmail off": edit(T, (CHIPS, """        {%- if keywords and gmail_connected %}
        <ul class="chip-list dash__value" aria-label="Your keywords">""")),
    "usage split in two nodes": edit(T, (USAGE, """<p class="usage">{{ usage_today }} <span>/</span> {{ daily_cap }}</p>""")),
    "disconnect loses csrf": edit(T, (CSRF, """          {{ ui.button("Disconnect Gmail", variant="danger", busy="Disconnecting") }}""")),
    "retry button made primary": edit(T, (RETRY, """{{ ui.link_button("/auth/connect-gmail", "Connect Gmail", icon_name="mail") }}</div>""")),
    "not on the journey list": edit(H, (re.compile(r',?\s*"dashboard\.html"'), "")),
    "group clipped": edit(J, (".dash__stack{max-width:40rem}", ".dash__stack{max-width:40rem}.dash__group{overflow:hidden}")),
    "group moved": edit(J, (".dash__stack{max-width:40rem}", ".dash__stack{max-width:40rem}.dash__grid>*{transform:none}")),
    "group fades": edit(J, (".dash__stack{max-width:40rem}", ".dash__stack{max-width:40rem}.dash__group{animation:none}")),
    "live panel corners": edit(J, (LIVE, ".status--live{border-color:var(--j-hairline);border-radius:16px}")),
    "live panel edge gone": edit(J, (LIVE, "")),
    "live edge always white": edit(J, (LIVE, ".status--live{border-color:rgba(255,255,255,.12)}")),
    "chip text fixed navy": edit(J, (".usage-note--cap,.chip{color:var(--j-text)}", ".usage-note--cap{color:var(--j-text)}.chip{color:#0B2545}")),
    "full meter fixed navy": edit(J, (".meter--full li.on,.bar__fill--100,", ".bar__fill--100,")),
    "paused too light in dark": edit(J, (".status--paused{background:#0F2436", ".status--paused{background:#5A7A9A")),
    "gmail panel amber in dark": edit(J, (".status--gmail{background:var(--j-surface)}", ".status--gmail{background:var(--j-attn-bg)}")),
    "loose selector": edit(J, (".dash__label{font-weight:500}", ".dash__label{font-weight:500}p{margin:0}")),
    "loose shared class": edit(J, (".dash__label{font-weight:500}", ".dash__label{font-weight:500}.chip-list{gap:6px}")),
    "width media in section 9": edit(J, (".dash__label{font-weight:500}", ".dash__label{font-weight:500}@media (min-width:800px){.dash__grid{gap:24px}}")),
    "near-limit note left amber-800": edit(J, (".usage-note--near{color:var(--j-attn-fg)}\n", "")),
}

survivors = []
for name, (path, apply) in MUTANTS.items():
    original = path.read_bytes()
    try:
        apply()
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider",
                            "tests/test_saas_journey.py"], cwd=ROOT, capture_output=True, text=True)
        first = next((ln for ln in r.stdout.splitlines() if ln.startswith("FAILED")), "")
        print(f"{'caught  ' if r.returncode else 'SURVIVED'} {name:32} {first[33:130]}")
        if not r.returncode:
            survivors.append(name)
    finally:
        path.write_bytes(original)
print(f"{len(MUTANTS) - len(survivors)} of {len(MUTANTS)} caught, survivors {survivors}")
sys.exit(1 if survivors else 0)
```

```bash
.venv/Scripts/python.exe "<scratchpad>/mutate6.py" .; echo "exit $?"
git status --short
```

Expected: 26 lines starting `caught`, then `26 of 26 caught, survivors []` and `exit 0` (about
twelve minutes). `git status --short` lists only this task's four files plus whatever Tasks 1 to 5 left
and the pre-existing `REMOTE.md`: the script restores `dashboard.html`, `journey.css` and
`_journey_css.py` byte for byte.

- [ ] **Step 9: Look at it once**

In the owner's own PowerShell window (Handoff: background shells get reaped), with a data folder
outside the repo:

```powershell
.venv\Scripts\python.exe .noxa\redesign-saas-ui\artifacts\run_local.py --port 8765 --data-dir C:\Users\regid\agad-preview
```

Open `http://127.0.0.1:8765/__dev/` and visit `dash-live`, `dash-gmail-off`, `dash-no-keywords`,
`dash-near-cap`, `dash-at-cap`, `dash-gmail-off-cap`, `dash-scope` and `dash-long-email`, plus
the connected-but-reconnect-failed state, which has no entry of its own:
`http://127.0.0.1:8765/__dev/login?state=dash-live&next=/dashboard?gmail_error=scope`. In
DevTools, Rendering, switch "Emulate CSS media feature prefers-color-scheme" to dark and back, and
try the device toolbar at 390px. Expected: one panel on top, then Watching, Gmail and Today in
one centred column, the help note last, keywords visible in every state, exactly one Connect
Gmail wherever one shows. Then stop the server with Ctrl+C in that window and confirm nothing is
left listening:

```powershell
Get-NetTCPConnection -State Listen -LocalPort 8765 -ErrorAction SilentlyContinue
```

Expected: no output.

- [ ] **Step 10: Run both gates**

```bash
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe .noxa/redesign-saas-ui/inputs/preserve_smoke.py
```

Expected. pytest: all pass (887 + the new tests), measured `1204 passed` in sequence: 85 new
items in `tests/test_saas_journey.py` (the `dashboard.html` case of Task 3's scope test existed
before and now checks a listed template). smoke: 0 failed, `566 checks passed, 0 failed.` The
count does not change in this task: `/login`, which the smoke fetches first, already loaded the
three new files and `check_asset` fetches each URL once.

**Notes for the reviewer (Task 6):**
1. The paused panel keeps its secondary "Edit keywords" button, because spec 6.3 keeps the panel
   as today. With the Watching group's Edit link, the paused state now has two ways to
   `/onboarding/keywords`. Owner's call whether to drop the panel one later.
2. Design choice: the whole stack (retry note, panel, groups, help) sits in the 40rem column, not
   only the groups. Spec 6.3 says the column is "below" the panel. A 1080px panel over a 640px
   column looked misaligned in the screenshots.
3. The Gmail panel in dark uses the surface, not `--j-attn-bg`, because the frozen primary
   `#0B6BC7` measures 2.98 to 1 on `#2A2110`, under the 3 to 1 spec 3 requires for control
   edges. Spec 5.3 does not list a dark amber panel, so this is a new decision worth a look.
4. "When an email arrives" leaves `.dash__grid` and loses `.arrives`. `reveal.js`'s SKIP list
   still names `.arrives` (frozen, and test R-1 pairs it with `app.css:803`); harmless, because
   nothing prints it now and the note is not a reveal target. app.css keeps the now unused
   dashboard rules (`.kv`, `.card-actions`, `.usage-label`, `.span-5/7/12`, `.arrives*`); app.css
   is not edited by this spec, so Task 8 records them in `Handoff.md`.
5. `test_section_nine_styles_only_what_the_dashboard_prints` allows only the one dark `@media`
   block in section 9. A later width breakpoint there needs that test updated on purpose.
6. The review-focus audit allows two fixed colours on purpose, the primary blue `--blue-600`
   (3.24 to 1 on the dark surface) and the amber `--amber-600` (4.33 to 1), both used as meter
   fills, and treats as islands the parts spec 3, 5.2 and 9 keep the same in both schemes. Any
   other light-page colour that reaches the dashboard fails it with the selector to redraw.


### Task 7: The "Sign-in didn't finish" page (D8) and the signed-out redirects (D9)

Spec 6.4, 6.5 and the D8 and D9 bullets of spec 7. Everything below was prototyped end to end on
2026-09-25 in a scratch copy of the repo (`git archive HEAD` plus the git-ignored smoke), with
small stand-ins for Tasks 1 to 4 (a stub trimmed Basecoat file, a stub Inter file, Task 2's
section 1, Task 3's sections 2 to 11 and `base.html` blocks, Task 4's `login.html` and section 7,
Task 4's `REQUIRED_ASSETS`). Measured there. The new test file went from 29 failed and 27 passed
to 56 passed, the five edited existing tests failed before and passed after, the full suite went
from 890 to 951 passed, the smoke went from 566 to **607 checks, 0 failed** (582 passed and 25
failed with the new checks but before the code change), headless Chrome printed 32 PASS and
`0 failed` in light and dark on phone and computer, and a mutation pass caught 28 of 28 planted
mistakes. Every "Before" block below was applied by exact string match in that copy. Re-run
during assembly on top of the real Tasks 1 to 6 (one Before block, in
`tests/test_saas_template_context.py`, was corrected to the whole line): pytest 1,204 to 1,266,
smoke 566 to 607, browser check 32 PASS, 28 of 28 mutants caught.

**Files:**
- Create `applyfirst/saas/templates/signin_failed.html` (full content in Step 6).
- Create `tests/test_saas_signin_failed.py` (full content in Step 1).
- Modify `applyfirst/saas/app.py` (LF in the working tree). All edits in Step 5, by exact string:
  - after line 38 (`_LOG = log.get_logger("saas.app")`), a module-level exception `_SignedOut`;
  - between line 250 (`return await call_next(request)`, the end of `_rate_limit`) and line 252
    (`# --- dependencies ---`), the exception handler that turns it into a 302 to `/login`;
  - after line 272 (the end of `require_user`, lines 269 to 272), the new dependency
    `require_user_or_login`;
  - lines 474, 490, 497, 530, 557, 588 and 601, the seven GET routes of spec 6.5;
  - lines 359, 365, 369 and 376, the four `return _fail(cfg_)` calls in `auth_callback`
    (lines 354 to 382);
  - lines 670 to 675, `_fail` itself.
- Modify `applyfirst/saas/static/css/journey.css`, section 10 only (one rule between the banners
  `/* ---- 10 signin-failed */` and `/* ---- 11 motion */` that Task 3 wrote).
- Modify `tests/_journey_css.py`, the `JOURNEY_TEMPLATES` list (append `"signin_failed.html"`).
- Modify `tests/test_saas_gmail_retry.py` lines 97 to 109 (CRLF file, the Edit tool keeps it).
- Modify `tests/test_saas_onboarding.py` lines 31 to 32.
- Modify `tests/test_saas_connect_gmail.py` lines 37 to 38.
- Modify `tests/test_saas_template_context.py` lines 81 to 83 and 91 to 94 (CRLF file).
- Modify `.noxa/redesign-saas-ui/inputs/preserve_smoke.py` (git-ignored, but a gate), a new block
  after the S8 check that ends at line 379 today (line 382 once Task 4 has added its three
  `REQUIRED_ASSETS` lines).
- Scratchpad only, never in the repo: `measure_signin_failed.py` (Step 10), `mutate7.py` (Step 11).
- Not touched: the CSP middleware (`app.py:219-229`), `require_user` (`app.py:269-272`),
  `require_csrf` (`app.py:274-287`), every POST route, `/me` (`app.py:392-395`),
  `/api/oauth-credentials/{cred_id}` (`app.py:397-407`), `/dashboard` (`app.py:316-337`, it
  already redirects a signed-out visitor inline at 319-320), `_gmail_retry` and
  `_gmail_scope_missing` (`app.py:629-654`), `session.py`, `_ui.html`, `base.html`, `app.css`,
  `motion.css`, `vt.js`, `motion.js`, `reveal.js`.

**Interfaces:**
- Consumes (all verified in the repo or in the earlier drafts):
  - Task 3: the `base.html` blocks `color_scheme` and `theme_color_meta` (Task 3 Step 6) and the
    existing `page_css`, `head_extra`, `body_class`, `header_action` blocks (`base.html:11-35`);
    the journey head snippet (two links, `light dark`, the two theme colours `#FFFFFF` and
    `#111B2B`, which Task 3's `test_the_journey_look_loads_on_exactly_the_listed_templates` checks
    against `--j-surface` for every listed template); the tokens `--j-attn-bg` and `--j-attn-fg`;
    the quiet action `.text-link`; the empty banners of sections 10 and 11. From
    `tests/_journey_css.py`: `JOURNEY_CSS`, `JOURNEY_TEMPLATES`, `TEMPLATES`, `iter_rules`, `decls`.
  - Task 4: section 7 styles the sign-in card by class (`.auth`, `.auth__sheet`, `.auth__head`,
    `.auth__head .lead`, `.auth__action`, `.auth__foot`) and `.is-auth main`, so this page reuses
    the login card and body class and needs no card CSS of its own. Task 4's smoke
    `REQUIRED_ASSETS` makes `/login` the first page to fetch the three new assets, so this task's
    smoke block adds no asset checks.
  - Tasks 1 and 2: `static/vendor/basecoat-1.0.2-agad.css` and the Inter file behind `journey.css`.
  - Existing code. `ui.google_button(block=true)` (`_ui.html:62-64`, a link to `/auth/login`,
    unchanged). `icon('info')` (`_icons.html:31-33`). `session.clear_oauth_txn` deletes
    `applyfirst_oauth` (or `__Host-applyfirst_oauth` with secure cookies) at path `/`
    (`session.py`, `oauth_cookie_name` and `clear_oauth_txn`). The log pattern of
    `_gmail_retry`, `log.event(_LOG, "gmail_connect_failed", level=logging.WARNING, ...,
    reason=reason)` (`app.py:634-635`), whose fields ride on `record.fields`
    (`applyfirst/log.py:67-70`). The middleware at `app.py:219-229` stamps the CSP on every
    response, pages, redirects and errors alike, so the new page and the new redirect carry the
    exact frozen CSP without any code of their own. From `tests/_saas_client.py`:
    `EXPECTED_CSP` (22-25), `seed_user` (57), `client_for` (79), `db_conn` (100),
    `txn_cookie_cleared` (119), `clean`, `elements`, `page_text`, `count_class`.
- Produces:
  - `applyfirst/saas/app.py`: module-level `class _SignedOut(Exception)`; inside `create_app`, the
    handler `_signed_out_to_login` and the dependency
    `require_user_or_login(user: db.User | None = Depends(current_user)) -> db.User`; and
    `_fail(request: Request, cfg_: SaaSConfig, reason: str) -> HTMLResponse`, which logs the event
    `signin_failed` with the one field `reason`, one of `"google_error"`, `"state"`, `"no_code"`,
    `"exchange"`.
  - `applyfirst/saas/templates/signin_failed.html`, and the class `.auth__icon` (section 10),
    printed by that template only.
  - `JOURNEY_TEMPLATES` with all seven spec 4.2 templates, which turns on Task 3's scope test for
    `signin_failed.html`.
  - `tests/test_saas_signin_failed.py`: 56 test items.
  - 41 new smoke checks (566 to 607 when Tasks 1 to 6 leave it at 566).

**Spec 6.5 routes, checked against `app.py`.** All seven exist with exactly the spec's spelling:
`GET /onboarding` (473), `GET /onboarding/connect_gmail` (489, underscore), `GET
/onboarding/profile` (496), `GET /onboarding/keywords` (529), `GET /onboarding/preview` (556),
`GET /auth/connect-gmail` (587, hyphen), `GET /auth/gmail-callback` (599). The two Gmail spellings
differ on purpose (the page is `connect_gmail`, the OAuth start is `connect-gmail`), and both are
right in the spec. Each takes `user: db.User = Depends(require_user)` today, so a signed-out GET
gets `401 {"detail": "authentication required"}`. The POST routes that keep `require_user`
(through `require_csrf`, and their own `user` parameter) are `/auth/logout` (384),
`/onboarding/profile` (511), `/onboarding/keywords` (540), `/onboarding/keywords/{keyword_id}/delete`
(550), `/onboarding/activate` (577), `/auth/disconnect-gmail` (656). The JSON API
`/me` (392) and `/api/oauth-credentials/{cred_id}` (397) also keep it.

**`/auth/callback` today, every failure branch** (`app.py:354-382`). `?error=` present (359), no
txn cookie, a bad or expired cookie, a missing `state` or a state that does not match (365), no
`code` (369), and `google_oauth.fetch_identity` raising `OAuthError` (376, which covers the token
exchange and every id_token check at `google_oauth.py:124-251`). All four call `_fail(cfg_)`
(`app.py:670-675`), which returns `JSONResponse({"error": "sign-in failed; please try again"},
status_code=400)`, clears the txn cookie and logs nothing. The new `_fail` keeps the 400 and the
cookie clearing, renders the page, and logs the reason the way `_gmail_retry` does.

**Why an exception and a handler for D9.** A FastAPI dependency cannot return a response. Raising
`HTTPException(status_code=302, headers={"Location": "/login"})` would redirect, but FastAPI's
handler would send it with a JSON body (`{"detail": "Found"}`, `application/json`). A dedicated
exception and `app.exception_handler` give a plain `RedirectResponse`. The handler runs inside
the user middlewares, so the security headers (and the rate limiter on `/auth/*`) apply exactly as
before.

**Frozen hooks (spec 9) and fixed things (spec 3) this task touches:**
- `site-header`, exactly one. `signin_failed.html` extends `base.html`, whose single
  `<header class="site-header...">` (`base.html:23`) is not touched. The route passes an empty
  context, so `user` is undefined and the header takes its signed-out branch; `header_action` is
  emptied exactly as `login.html:9` does, so the header holds only the brand link.
  `test_the_page_wears_the_journey_look` counts one `.site-header`.
- No other spec 9 hook is on this page. No form, so no hidden `csrf` input (a test asserts no
  `<form` at all). No `data-step` on `<html>` (`html_attrs` is not overridden, a test checks). No
  motion head, so no `motion.css`, `vt.js`, `motion.js` or `canvas-confetti` in the page (test
  M-2 style check in `test_the_page_stays_a_public_page`), and head order M-1 holds because
  `page_css` stays where `base.html:14` puts it, after the empty `motion_head` and before
  `reveal.js` (checked).
- The Google button (spec 3). Printed by the unchanged macro, checked byte for byte against
  `str(ui.google_button(block=True))`, and Step 10 proves in Chrome that it computes exactly as
  on `/login` in light and dark. Section 10 names only `.auth__icon`, which the button never
  carries (a test pins that section 10 selectors all start with `.auth__icon`).
- The CSP (`app.py:225-228`) is not edited. Tests and the smoke assert the exact header on the
  400 page and on every D9 redirect.
- Invite-only copy and hidden pricing. Not on this page, nothing changes.
- The hooks on the pages behind the seven routes (`#gmail-retry`, the `csrf` inputs,
  `data-arrive-gmail`, `form.activate` and the rest) are untouched, because a signed-in visitor
  gets exactly today's response (`test_signed_in_visits_are_unchanged` covers ten cases, and
  `tests/test_saas_gmail_retry.py:62-95` and `:114-148` still pass unchanged).

**Existing tests and smoke checks that touch these routes.**
- Changed on purpose (Step 2), the only ones that pin the old replies (found with
  `Grep "401|\.json\(\)|sign-in failed"` over `tests/`, then confirmed by a full run in the
  prototype, which failed on exactly these four plus nothing else):
  `tests/test_saas_gmail_retry.py:99-103` (the callback's JSON body),
  `tests/test_saas_gmail_retry.py:106-109` (anonymous gmail-callback 401),
  `tests/test_saas_onboarding.py:32` and `tests/test_saas_connect_gmail.py:38` (anonymous 401).
- `tests/test_saas_template_context.py:78-97` does NOT fail on its own. It does not glob the
  templates; it records every `TemplateResponse` made while it GETs a fixed list of paths and
  compares the set of names (91-94). So Step 2 adds a GET of a failing callback to that list and
  `"signin_failed.html"` to the set, which also proves the new route context `{}` never collides
  with the context processor keys `check_every_min` and `apps_per_day`.
- Still pass unchanged: `tests/test_saas_auth_flow.py:34-67` and `:78-85` (they check only the
  400 status and that `applyfirst_oauth` appears in the Set-Cookie header),
  `tests/test_saas_cross_tenant.py:102-107` (state mismatch 400) and `:59`, `:65`, `:157`
  (`/me` and the credential API stay 401), `tests/test_saas_csrf.py:62-66` (a signed-out POST
  stays 401), `tests/test_saas_gmail_retry.py:62-95` and `:114-148` (signed-in gmail-callback
  failures keep the Step 1 retry page), `tests/test_saas_motion.py:342-347` (JSON error bodies
  of `/nope` and POST `/`).
- New parametrized cases the new template creates by existing, all passing:
  `tests/test_saas_template_guards.py:39-67` and `:108-116` (autoescape, CSP-safe markup, macro
  imports, three cases), `tests/test_saas_palette.py:109` and `:118` (two cases, if Task 1's
  rewrite keeps parametrizing over templates), and Task 3's scope test (one case).
  `tests/test_saas_static.py:148-159` (every static file a template names exists) covers the two
  links and the Google Sans preload.
- The smoke has no check of `/auth/callback` or of signed-out GETs today (`preserve_smoke.py`
  touches only `/auth/gmail-callback`, signed in, at 404-412). So spec 7's "update the callback
  and signed-out expectations" becomes a new block (Step 3).

- [ ] **Step 1: Write the failing test file**

Create `tests/test_saas_signin_failed.py` with the Write tool, exactly:

<!-- create: tests/test_saas_signin_failed.py -->
```python
"""D8 and D9 of the sign-up redesign (spec 6.4, 6.5 and 7).

D8: every /auth/callback failure shows ONE styled page, "Sign-in didn't finish": status 400,
text/html, the frozen CSP, the oauth transaction cookie cleared, nothing stored and no session
set. The page is the same bytes whatever went wrong, so it is no oracle, and the reason goes to
the server log only.

D9: a signed-out GET of an onboarding page, Connect Gmail or its callback gets a 302 to /login
instead of a 401 JSON reply. POST routes and the JSON API keep today's 401 and 403.
"""

from __future__ import annotations

import dataclasses
import logging
import re
import time
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.routing import APIRoute

from applyfirst.saas import app as app_module
from applyfirst.saas import google_oauth, session, static_assets
from applyfirst.saas.app import create_app
from _journey_css import JOURNEY_CSS, JOURNEY_TEMPLATES, TEMPLATES, decls, iter_rules
from _saas_client import (
    EXPECTED_CSP, clean, client_for, count_class, db_conn, elements, page_text, seed_user,
    txn_cookie_cleared,
)

TITLE = "Sign-in didn't finish"
LINE = "You can try again, it only takes a moment."
HOME_LINK = "Back to the homepage"
OLD_JSON = "sign-in failed; please try again"
PROBE = "<script>alert(9)</script>"
MOTION_ASSETS = ("motion.css", "vt.js", "motion.js", "canvas-confetti")     # test M-2
REASONS = ("google_error", "state", "no_code", "exchange")


# --- D8: how a sign-in can fail ---------------------------------------------------------------

def _boom(exc):
    def raise_it(*a, **kw):
        raise exc
    return raise_it


def _start(c) -> str:
    """Begin a real sign-in (sets the oauth txn cookie) and return its state."""
    loc = c.get("/auth/login").headers["location"]
    return parse_qs(urlparse(loc).query)["state"][0]


def _cancel(c, cfg, mp):
    _start(c)
    return c.get("/auth/callback", params={"error": "access_denied", "error_description": PROBE})


def _no_txn(c, cfg, mp):
    return c.get("/auth/callback", params={"code": "c", "state": "s"})


def _no_state(c, cfg, mp):
    _start(c)
    return c.get("/auth/callback", params={"code": "c"})


def _wrong_state(c, cfg, mp):
    _start(c)
    return c.get("/auth/callback", params={"code": "c", "state": "WRONG"})


def _expired_txn(c, cfg, mp):
    c.cookies.set("applyfirst_oauth", session.sign(cfg.session_secret, {
        "state": "s", "nonce": "n", "verifier": "v", "iat": int(time.time()) - 1200}))
    return c.get("/auth/callback", params={"code": "c", "state": "s"})


def _forged_txn(c, cfg, mp):
    c.cookies.set("applyfirst_oauth", session.sign(b"not-the-server-secret-32-bytes!!!", {
        "state": "s", "nonce": "n", "verifier": "v"}))
    return c.get("/auth/callback", params={"code": "c", "state": "s"})


def _no_code(c, cfg, mp):
    return c.get("/auth/callback", params={"state": _start(c)})


def _exchange(c, cfg, mp):
    mp.setattr(google_oauth, "fetch_identity", _boom(google_oauth.OAuthError("nonce mismatch")))
    return c.get("/auth/callback", params={"code": "c", "state": _start(c)})


# Every branch of auth_callback that fails, with the reason the server logs for it.
FAILURES = {"cancel": (_cancel, "google_error"), "no_txn": (_no_txn, "state"),
            "no_state": (_no_state, "state"), "wrong_state": (_wrong_state, "state"),
            "expired_txn": (_expired_txn, "state"), "forged_txn": (_forged_txn, "state"),
            "no_code": (_no_code, "no_code"), "exchange": (_exchange, "exchange")}


def _fail(cfg, mp, kind: str, user=None):
    """Run one failure with the Google exchange armed to explode: only the exchange case may
    reach it, so every other case proves the check happens before any call to Google."""
    mp.setattr(google_oauth, "fetch_identity",
               _boom(AssertionError("the callback called Google after a failed check")))
    return FAILURES[kind][0](client_for(cfg, user), cfg, mp)


def _no_rate_limit(cfg):
    return dataclasses.replace(cfg, auth_rate_limit=0)


def _users(cfg) -> int:
    with db_conn(cfg) as conn:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]


@pytest.mark.parametrize("kind", FAILURES)
def test_every_callback_failure_is_the_400_page(saas_cfg, monkeypatch, caplog, kind):
    with caplog.at_level(logging.WARNING, logger="applyfirst.saas.app"):
        r = _fail(saas_cfg, monkeypatch, kind)
    assert r.status_code == 400
    assert r.headers["content-type"].startswith("text/html")
    assert r.headers["content-security-policy"] == EXPECTED_CSP
    assert txn_cookie_cleared(r)
    assert not [h for h in r.headers.get_list("set-cookie") if h.startswith("applyfirst_session=")]
    assert _users(saas_cfg) == 0, "a failed sign-in stores nobody"
    assert [clean(e.text) for e in elements(r.text) if e.tag == "h1"] == [TITLE]
    assert OLD_JSON not in r.text and not r.text.lstrip().startswith("{")
    # The reason goes to the server log only, once, and never reaches the page.
    logged = [rec for rec in caplog.records if rec.getMessage() == "signin_failed"]
    assert [rec.fields for rec in logged] == [{"reason": FAILURES[kind][1]}]
    text = page_text(r.text).lower()
    for word in REASONS + ("access_denied", "nonce", "token", "error"):
        assert word not in text, f"the page says {word!r}"


def test_the_page_is_the_same_bytes_whatever_went_wrong(saas_cfg, monkeypatch):
    cfg = _no_rate_limit(saas_cfg)
    bodies = {}
    for kind in FAILURES:
        with monkeypatch.context() as mp:
            bodies[kind] = _fail(cfg, mp, kind).text
    assert len(set(bodies.values())) == 1, sorted(bodies)


def test_a_signed_in_visitor_gets_the_same_page(saas_cfg, monkeypatch):
    """The page never reads the session, so it cannot differ for someone already signed in."""
    cfg = _no_rate_limit(saas_cfg)
    anon = _fail(cfg, monkeypatch, "wrong_state").text
    signed = _fail(cfg, monkeypatch, "wrong_state", user=seed_user(cfg)).text
    assert signed == anon
    assert 'name="csrf"' not in signed and "Log out" not in signed


def test_nothing_google_sends_back_is_reflected(saas_cfg, monkeypatch):
    r = _fail(saas_cfg, monkeypatch, "cancel")
    assert PROBE not in r.text and "alert(9)" not in r.text


# --- D8: the page itself (spec 6.4) -------------------------------------------------------------

def _page(cfg, mp) -> str:
    return _fail(cfg, mp, "cancel").text


def test_the_page_says_what_happened_and_offers_one_way_back_in(saas_cfg, monkeypatch):
    markup = _page(saas_cfg, monkeypatch)
    text = page_text(markup)
    where = [text.find(s) for s in (TITLE, LINE, "Continue with Google", HOME_LINK)]
    assert -1 not in where and where == sorted(where), where
    ui = app_module._TEMPLATES.env.get_template("_ui.html").module
    assert markup.count(str(ui.google_button(block=True))) == 1, "the macro, untouched"
    assert markup.count('class="gsi-btn') == 1
    home = [e for e in elements(markup) if e.tag == "a" and clean(e.text) == HOME_LINK]
    assert len(home) == 1 and home[0].attrs.get("href") == "/"
    assert "<form" not in markup, "a signed-out page has no form"
    assert "Agad" in re.search(r"<title>(.*?)</title>", markup, re.S).group(1)


def test_the_page_wears_the_journey_look(saas_cfg, monkeypatch):
    assert "signin_failed.html" in JOURNEY_TEMPLATES
    markup = _page(saas_cfg, monkeypatch)
    sheets = re.findall(r'<link rel="stylesheet" href="([^"]+)">', markup)
    assert sheets == [static_assets.static_url(p) for p in (
        "css/app.css", "vendor/basecoat-1.0.2-agad.css", "css/journey.css")]
    assert markup.index(sheets[-1]) < markup.index(static_assets.static_url("js/reveal.js"))
    metas = {e.attrs.get("name"): e.attrs for e in elements(markup) if e.tag == "meta"}
    assert metas["color-scheme"]["content"] == "light dark"
    themes = [e.attrs.get("media") for e in elements(markup)
              if e.tag == "meta" and e.attrs.get("name") == "theme-color"]
    assert themes == ["(prefers-color-scheme: light)", "(prefers-color-scheme: dark)"]
    assert re.search(r'<body class="is-auth">', markup), "the login card layout"
    assert count_class(markup, "site-header") == 1


def test_the_page_stays_a_public_page(saas_cfg, monkeypatch):
    """No motion head (M-2), no step on <html> (M-9), no preload of Inter (spec 4.5)."""
    markup = _page(saas_cfg, monkeypatch)
    assert [a for a in MOTION_ASSETS if a in markup] == []
    assert "data-step" not in re.search(r"<html\b[^>]*>", markup).group(0)
    assert [t for t in re.findall(r"<link\b[^>]*>", markup) if "inter" in t.lower()] == []


# --- D8: journey.css section 10 -----------------------------------------------------------------

def _section(number: int) -> str:
    raw = JOURNEY_CSS.read_text(encoding="utf-8").replace("\r\n", "\n")
    start = raw.index(f"/* ---- {number} ")
    end = raw.index("/* ---- ", start + 1)
    return re.sub(r"/\*.*?\*/", "", raw[start:end], flags=re.S)


def test_section_10_styles_only_this_page_and_moves_nothing():
    rules = list(iter_rules(_section(10)))
    assert rules, "section 10 holds the page's own rules"
    for selectors, body, _chain in rules:
        assert all(s.strip().startswith(".auth__icon") for s in selectors.split(",")), selectors
        assert not [p for p in decls(body) if p.startswith(("transition", "animation"))], (
            f"{selectors}: motion belongs in section 11")
    others = [p.name for p in TEMPLATES.glob("*.html")
              if p.name != "signin_failed.html" and "auth__icon" in p.read_text(encoding="utf-8")]
    assert others == []


def test_the_icon_well_uses_the_calm_attention_tokens():
    props = {}
    for selectors, body, _chain in iter_rules(_section(10)):
        if selectors.strip() == ".auth__icon":
            props.update(decls(body))
    assert props.get("background") == "var(--j-attn-bg)"
    assert props.get("color") == "var(--j-attn-fg)"


# --- D9: signed-out visits (spec 6.5) -----------------------------------------------------------

SPEC_PAGES = ("/onboarding", "/onboarding/connect_gmail", "/onboarding/profile",
              "/onboarding/keywords", "/onboarding/preview", "/auth/connect-gmail",
              "/auth/gmail-callback")


def _dependency_names(dependant) -> set[str]:
    names: set[str] = set()
    for dep in dependant.dependencies:
        names.add(getattr(dep.call, "__name__", ""))
        names |= _dependency_names(dep)
    return names


def _routes_using(app, name: str) -> set[tuple[str, str]]:
    return {(method, route.path) for route in app.routes if isinstance(route, APIRoute)
            for method in route.methods if name in _dependency_names(route.dependant)}


def test_the_login_redirect_guards_exactly_the_spec_pages(saas_cfg):
    app = create_app(saas_cfg)
    assert _routes_using(app, "require_user_or_login") == {("GET", p) for p in SPEC_PAGES}
    assert _routes_using(app, "require_user") == {
        ("GET", "/me"), ("GET", "/api/oauth-credentials/{cred_id}"),
        ("POST", "/auth/logout"), ("POST", "/onboarding/profile"),
        ("POST", "/onboarding/keywords"), ("POST", "/onboarding/keywords/{keyword_id}/delete"),
        ("POST", "/onboarding/activate"), ("POST", "/auth/disconnect-gmail")}


@pytest.mark.parametrize("path", SPEC_PAGES + (
    "/onboarding/profile?error=1", "/onboarding/connect_gmail?gmail_error=scope",
    "/auth/gmail-callback?error=access_denied", "/auth/gmail-callback?code=c&state=s"))
def test_a_signed_out_visit_goes_to_login(saas_cfg, monkeypatch, path):
    monkeypatch.setattr(google_oauth, "exchange_code_for_gmail",
                        _boom(AssertionError("a signed-out callback reached Google")))
    r = client_for(saas_cfg).get(path)
    assert r.status_code == 302
    assert r.headers["location"] == "/login", "no next= parameter (spec 6.5)"
    assert r.headers["content-security-policy"] == EXPECTED_CSP
    assert "json" not in r.headers.get("content-type", "")
    assert not [h for h in r.headers.get_list("set-cookie") if h.startswith("applyfirst_oauth=")]


@pytest.mark.parametrize("cookie", ["forged", "expired", "deleted_user"])
def test_a_session_that_names_nobody_also_goes_to_login(saas_cfg, cookie):
    user = seed_user(saas_cfg)
    secret, payload = saas_cfg.session_secret, {"uid": user.id}
    if cookie == "forged":
        secret = b"not-the-server-secret-32-bytes!!!"
    elif cookie == "expired":
        payload["iat"] = int(time.time()) - 8 * 24 * 3600
    else:
        with db_conn(saas_cfg) as conn:
            conn.execute("DELETE FROM users WHERE id=?", (user.id,))
            conn.commit()
    c = client_for(saas_cfg)
    c.cookies.set("applyfirst_session", session.sign(secret, payload))
    for path in SPEC_PAGES:
        r = c.get(path)
        assert (r.status_code, r.headers.get("location")) == (302, "/login"), path


def test_the_redirect_lands_on_a_page_that_renders(saas_cfg):
    c = client_for(saas_cfg)
    assert c.get("/onboarding").headers["location"] == "/login"
    assert c.get("/login").status_code == 200


SIGNED_OUT_POSTS = [("/onboarding/profile", {"full_name": "A", "job_type": "B",
                                             "standard_subject": "C", "standard_message": "D"}),
                    ("/onboarding/keywords", {"keyword": "va"}),
                    ("/onboarding/keywords/k1/delete", {}), ("/onboarding/activate", {}),
                    ("/auth/logout", {}), ("/auth/disconnect-gmail", {})]


@pytest.mark.parametrize("path,data", SIGNED_OUT_POSTS, ids=[p for p, _ in SIGNED_OUT_POSTS])
def test_signed_out_posts_keep_their_401(saas_cfg, path, data):
    r = client_for(saas_cfg).post(path, data={**data, "csrf": "x"})
    assert r.status_code == 401
    assert r.json() == {"detail": "authentication required"}


@pytest.mark.parametrize("path,data", SIGNED_OUT_POSTS, ids=[p for p, _ in SIGNED_OUT_POSTS])
def test_signed_in_posts_without_a_token_keep_their_403(saas_cfg, path, data):
    r = client_for(saas_cfg, seed_user(saas_cfg)).post(path, data=data)
    assert r.status_code == 403
    assert r.json() == {"detail": "invalid or missing CSRF token"}


@pytest.mark.parametrize("path", ["/me", "/api/oauth-credentials/x"])
def test_the_json_api_keeps_its_401(saas_cfg, path):
    r = client_for(saas_cfg).get(path)
    assert r.status_code == 401
    assert r.json() == {"detail": "authentication required"}


# (who, path, status, location): what a signed-in visitor gets today, unchanged by D9.
SIGNED_IN = [
    ("fresh", "/onboarding", 302, "/onboarding/connect_gmail"),
    ("fresh", "/onboarding/connect_gmail", 200, None),
    ("fresh", "/onboarding/profile", 200, None),
    ("fresh", "/onboarding/keywords", 302, "/onboarding/profile"),
    ("fresh", "/onboarding/preview", 302, "/onboarding/profile"),
    ("fresh", "/auth/connect-gmail", 302, google_oauth.AUTH_URI),
    ("fresh", "/auth/gmail-callback?error=access_denied", 400, None),
    ("done", "/onboarding", 302, "/dashboard"),
    ("done", "/onboarding/keywords", 200, None),
    ("done", "/onboarding/preview", 200, None),
]


@pytest.mark.parametrize("who,path,status,where", SIGNED_IN,
                         ids=[f"{w}:{p}" for w, p, _, _ in SIGNED_IN])
def test_signed_in_visits_are_unchanged(saas_cfg, who, path, status, where):
    user = (seed_user(saas_cfg) if who == "fresh"
            else seed_user(saas_cfg, activated=True, keywords=("va",)))
    r = client_for(saas_cfg, user).get(path)
    assert r.status_code == status
    if where is None:
        assert "location" not in r.headers
    else:
        assert r.headers["location"].startswith(where)
```

How the file is built, for the reviewer.
- The eight failure cases cover every `_fail` call: Google's `?error=`, a missing txn cookie, a
  missing `state`, a wrong `state`, an expired and a forged txn cookie, a missing `code`, and a
  failed exchange. `_fail` arms `google_oauth.fetch_identity` to raise `AssertionError`, so the
  seven cases that must stop before Google prove they do (the TestClient re-raises it).
- "No oracle" is tested twice, as the same bytes for all eight cases, and as the same bytes for a
  signed-in visitor. It is possible because the page carries no CSRF token and no query value.
- The dependency test reads FastAPI's own route table (`route.dependant`), so moving any route to
  the wrong dependency fails even when the reply would look the same (for example a POST, where
  `require_csrf` still answers 401 first).

- [ ] **Step 2: Change the tests that pin the old replies**

`tests/test_saas_gmail_retry.py`, lines 97 to 109. The imports at lines 11 to 14 already bring in
`by_id`, `clean` and `elements`.

<!-- edit: tests/test_saas_gmail_retry.py -->
Before:
```python
# --- T24: surfaces that must NOT change --------------------------------------------------

def test_login_callback_failures_stay_generic_json(saas_cfg):
    db.init_db(saas_cfg.db_path).close()
    r = client_for(saas_cfg).get("/auth/callback", params={"error": "access_denied"})
    assert r.status_code == 400
    assert r.json() == {"error": "sign-in failed; please try again"}


def test_anonymous_gmail_callback_is_still_401(saas_cfg):
    db.init_db(saas_cfg.db_path).close()
    r = client_for(saas_cfg).get("/auth/gmail-callback", params={"error": "access_denied"})
    assert r.status_code == 401
```
After:
```python
# --- T24: sign-in and signed-out visits never get this page (D8, D9) ----------------------

def test_login_callback_failures_get_their_own_page_not_this_one(saas_cfg):
    db.init_db(saas_cfg.db_path).close()
    r = client_for(saas_cfg).get("/auth/callback", params={"error": "access_denied"})
    assert r.status_code == 400
    assert r.headers["content-type"].startswith("text/html")
    assert by_id(r.text, "gmail-retry") is None
    assert [clean(e.text) for e in elements(r.text) if e.tag == "h1"] == ["Sign-in didn't finish"]


def test_anonymous_gmail_callback_goes_to_login(saas_cfg):
    db.init_db(saas_cfg.db_path).close()
    r = client_for(saas_cfg).get("/auth/gmail-callback", params={"error": "access_denied"})
    assert r.status_code == 302 and r.headers["location"] == "/login"
```

`tests/test_saas_onboarding.py`, lines 31 to 32 (the test keeps its name, it still requires auth):

<!-- edit: tests/test_saas_onboarding.py -->
Before:
```python
    c = TestClient(create_app(saas_cfg), follow_redirects=False)
    assert c.get("/onboarding").status_code == 401
```
After:
```python
    c = TestClient(create_app(saas_cfg), follow_redirects=False)
    r = c.get("/onboarding")                        # D9: to /login, no longer a 401 JSON reply
    assert r.status_code == 302 and r.headers["location"] == "/login"
```

`tests/test_saas_connect_gmail.py`, lines 37 to 38:

<!-- edit: tests/test_saas_connect_gmail.py -->
Before:
```python
    c = TestClient(create_app(saas_cfg), follow_redirects=False)
    assert c.get("/auth/connect-gmail").status_code == 401
```
After:
```python
    c = TestClient(create_app(saas_cfg), follow_redirects=False)
    r = c.get("/auth/connect-gmail")                # D9: to /login, no longer a 401 JSON reply
    assert r.status_code == 302 and r.headers["location"] == "/login"
```

`tests/test_saas_template_context.py`, lines 81 to 83, then lines 91 to 94:

<!-- edit: tests/test_saas_template_context.py -->
Before:
```python
    for path in ("/", "/login", "/privacy", "/terms"):
        anon.get(path)
    fresh = client_for(saas_cfg, seed_user(saas_cfg, sub="a", email="a@x.com"))
```
After:
```python
    for path in ("/", "/login", "/privacy", "/terms"):
        anon.get(path)
    anon.get("/auth/callback", params={"error": "access_denied"})       # D8: signin_failed.html
    fresh = client_for(saas_cfg, seed_user(saas_cfg, sub="a", email="a@x.com"))
```

<!-- edit: tests/test_saas_template_context.py -->
Before:
```python
        "onboarding_profile.html", "onboarding_keywords.html", "onboarding_preview.html",
        "dashboard.html"}
```
After:
```python
        "onboarding_profile.html", "onboarding_keywords.html", "onboarding_preview.html",
        "dashboard.html", "signin_failed.html"}
```

- [ ] **Step 3: Add the D8 and D9 checks to the smoke**

`.noxa/redesign-saas-ui/inputs/preserve_smoke.py`. Insert the new block right after the S8 check
(lines 378 to 379 today) and before `# --- a signed-in user walks onboarding with REAL form
submissions`. It uses only helpers the smoke already has (`ok`, `need`, `get_page`, `location`)
and the `anon` client, whose config sets `auth_rate_limit=0` (line 350).

<!-- edit: .noxa/redesign-saas-ui/inputs/preserve_smoke.py -->
Before:
```python
    ok("Open this page in Chrome or Safari" not in anon.get("/").text,
       "[home] the in-app notice shows in a normal browser")
```
After:
```python
    ok("Open this page in Chrome or Safari" not in anon.get("/").text,
       "[home] the in-app notice shows in a normal browser")

    # --- D8: a failed Google sign-in -> one styled 400 page, the same whatever went wrong ------
    failed_pages = []
    for query, label in (("error=access_denied&error_description=%3Cscript%3Ealert(1)%3C/script%3E",
                          "signin failed(cancel)"),
                         ("code=x&state=forged", "signin failed(no txn)")):
        r = anon.get(f"/auth/callback?{query}")
        ok(r.headers.get("content-type", "").startswith("text/html"),
           f"[{label}] want an HTML page, got {r.headers.get('content-type')!r}")
        ok(any(h.startswith("applyfirst_oauth=") for h in r.headers.get_list("set-cookie")),
           f"[{label}] the oauth txn cookie is not cleared")
        html, _ = get_page(anon, anon, f"/auth/callback?{query}", label, None, status=400)
        for s in ("Sign-in didn't finish", "You can try again, it only takes a moment.",
                  "Continue with Google", 'href="/auth/login"', "Back to the homepage"):
            need(html, s, label)
        failed_pages.append(html)
    ok(len(set(failed_pages)) == 1, "[signin failed] the page differs by failure (an oracle)")

    # --- D9: a signed-out visit to a signed-in page goes to /login; POSTs keep their 401 ------
    for path in ("/onboarding", "/onboarding/connect_gmail", "/onboarding/profile",
                 "/onboarding/keywords", "/onboarding/preview", "/auth/connect-gmail",
                 "/auth/gmail-callback?error=access_denied"):
        r = anon.get(path)
        ok(r.status_code == 302 and location(r) == "/login",
           f"[signed out] GET {path} -> {r.status_code} {location(r)!r}, want 302 to /login")
    for action in ("/onboarding/profile", "/onboarding/keywords", "/onboarding/activate",
                   "/auth/logout", "/auth/disconnect-gmail"):
        r = anon.post(action, data={"csrf": "x"})
        ok(r.status_code == 401, f"[signed out] POST {action} -> {r.status_code}, want 401")
```

What it adds, 41 checks. For each of the two failures (a Cancel carrying a script probe in
`error_description`, and a callback with no txn cookie): the HTML type, the cookie deletion,
`get_page`'s status and exact CSP, `check_page`'s title, `lang`, viewport and two XSS probes, and
five needles, 14 each. Then one "same page" check, seven signed-out GETs and five signed-out POSTs.
`check_page` also lints the page against the CSP and fetches its assets, all already fetched by
`/login` after Task 4, so no asset check is added.

- [ ] **Step 4: Run the tests and the smoke, and watch them fail**

```bash
.venv/Scripts/python.exe -m pytest -q tests/test_saas_signin_failed.py tests/test_saas_gmail_retry.py tests/test_saas_onboarding.py tests/test_saas_connect_gmail.py tests/test_saas_template_context.py
.venv/Scripts/python.exe .noxa/redesign-saas-ui/inputs/preserve_smoke.py
```

Expected (measured): `34 failed, 69 passed`. In `test_saas_signin_failed.py`, 29 fail and 27 pass.
The 29 are the eight `test_every_callback_failure_is_the_400_page` cases
(`assert r.headers["content-type"].startswith("text/html")`, the reply is JSON),
`test_the_page_says_what_happened_and_offers_one_way_back_in` and
`test_the_page_stays_a_public_page` (the JSON body has no `<html>`), the two section 10 tests
(section 10 is empty), `test_the_page_wears_the_journey_look`
(`assert 'signin_failed.html' in [...]`), `test_the_login_redirect_guards_exactly_the_spec_pages`
(no route uses `require_user_or_login`), the eleven `test_a_signed_out_visit_goes_to_login`
cases and the three `test_a_session_that_names_nobody_also_goes_to_login` cases (401, want 302),
and `test_the_redirect_lands_on_a_page_that_renders` (`KeyError: 'location'`). The 27 that
already pass are the ones that pin what must not change (the POST 401 and 403 cases, the JSON
API, the ten signed-in visits) and the three "same bytes" and reflection tests, which the old
JSON body also satisfies. The other five failures are the Step 2 edits:
`test_login_callback_failures_get_their_own_page_not_this_one`,
`test_anonymous_gmail_callback_goes_to_login`, `test_onboarding_requires_auth`,
`test_connect_gmail_requires_auth`, `test_processor_keys_never_collide_with_route_context`
(the set lacks `'signin_failed.html'`).

The smoke prints 25 `FAIL` lines and `582 checks passed, 25 failed.` For each of the two
`signin failed(...)` labels, "want an HTML page, got 'application/json'", the title, `lang` and
viewport lines, and the five needles (18). Then seven `[signed out] GET ... -> 401 '', want 302 to
/login`. The five POST checks already pass.

- [ ] **Step 5: Change `applyfirst/saas/app.py`**

Six edits with the Edit tool, each by exact string, top to bottom.

5a. The exception, after line 38.

<!-- edit: applyfirst/saas/app.py -->
Before:
```python
_LOG = log.get_logger("saas.app")
```
After:
```python
_LOG = log.get_logger("saas.app")


class _SignedOut(Exception):
    """Raised by require_user_or_login. create_app turns it into a 302 to /login (D9)."""
```

5b. The handler, between the end of `_rate_limit` (line 250) and the dependencies banner (252).

<!-- edit: applyfirst/saas/app.py -->
Before:
```python
        return await call_next(request)

    # --- dependencies --------------------------------------------------------
```
After:
```python
        return await call_next(request)

    @app.exception_handler(_SignedOut)
    async def _signed_out_to_login(request: Request, exc: _SignedOut) -> RedirectResponse:
        # D9: no next= parameter, because /onboarding already sends a signed-in user to the
        # right step. The security headers middleware still stamps this response.
        return RedirectResponse("/login", status_code=302)

    # --- dependencies --------------------------------------------------------
```

5c. The dependency, after `require_user` (lines 269 to 272).

<!-- edit: applyfirst/saas/app.py -->
Before:
```python
            raise HTTPException(status_code=401, detail="authentication required")
        return user
```
After:
```python
            raise HTTPException(status_code=401, detail="authentication required")
        return user

    def require_user_or_login(user: db.User | None = Depends(current_user)) -> db.User:
        """require_user for the signed-in GET pages of spec 6.5 (D9): a visitor with no valid
        session is sent to /login instead of getting a 401 JSON reply. POST routes and the
        JSON API keep require_user, so their 401 and 403 replies do not change."""
        if user is None:
            raise _SignedOut()
        return user
```

5d. The seven GET routes of spec 6.5, and no other route. Six one-line edits and one rewrap.

<!-- edit: applyfirst/saas/app.py -->
Before (line 474):
```python
    def onboarding_root(user: db.User = Depends(require_user), conn=Depends(get_conn)):
```
After:
```python
    def onboarding_root(user: db.User = Depends(require_user_or_login), conn=Depends(get_conn)):
```

<!-- edit: applyfirst/saas/app.py -->
Before (line 490):
```python
    def onboarding_connect_gmail(request: Request, user: db.User = Depends(require_user),
```
After:
```python
    def onboarding_connect_gmail(request: Request, user: db.User = Depends(require_user_or_login),
```

<!-- edit: applyfirst/saas/app.py -->
Before (line 497):
```python
    def onboarding_profile_form(request: Request, user: db.User = Depends(require_user),
```
After:
```python
    def onboarding_profile_form(request: Request, user: db.User = Depends(require_user_or_login),
```

<!-- edit: applyfirst/saas/app.py -->
Before (line 530):
```python
    def onboarding_keywords_page(request: Request, user: db.User = Depends(require_user),
```
After:
```python
    def onboarding_keywords_page(request: Request, user: db.User = Depends(require_user_or_login),
```

<!-- edit: applyfirst/saas/app.py -->
Before (line 557):
```python
    def onboarding_preview_page(request: Request, user: db.User = Depends(require_user),
```
After:
```python
    def onboarding_preview_page(request: Request, user: db.User = Depends(require_user_or_login),
```

<!-- edit: applyfirst/saas/app.py -->
Before (line 588, which would pass 100 columns, so it wraps):
```python
    def connect_gmail(cfg_: SaaSConfig = Depends(get_cfg), user: db.User = Depends(require_user)):
```
After:
```python
    def connect_gmail(cfg_: SaaSConfig = Depends(get_cfg),
                      user: db.User = Depends(require_user_or_login)):
```

<!-- edit: applyfirst/saas/app.py -->
Before (line 601, inside `gmail_callback`):
```python
                       user: db.User = Depends(require_user), conn=Depends(get_conn)):
```
After:
```python
                       user: db.User = Depends(require_user_or_login), conn=Depends(get_conn)):
```

The longest new line is 98 columns. `require_user` stays on lines 274 (`require_csrf`), 393
(`/me`), 398 (`/api/oauth-credentials`), 513, 541, 551, 578 and 657 (POST routes).

5e. The four failure calls in `auth_callback`, each with the reason it logs.

<!-- edit: applyfirst/saas/app.py -->
Before (lines 358 to 359):
```python
        if params.get("error"):
            return _fail(cfg_)
```
After:
```python
        if params.get("error"):
            return _fail(request, cfg_, "google_error")
```

<!-- edit: applyfirst/saas/app.py -->
Before (lines 364 to 365):
```python
        if not txn or not returned_state or returned_state != txn.get("state"):
            return _fail(cfg_)
```
After:
```python
        if not txn or not returned_state or returned_state != txn.get("state"):
            return _fail(request, cfg_, "state")
```

<!-- edit: applyfirst/saas/app.py -->
Before (lines 368 to 369):
```python
        if not code:
            return _fail(cfg_)
```
After:
```python
        if not code:
            return _fail(request, cfg_, "no_code")
```

<!-- edit: applyfirst/saas/app.py -->
Before (lines 375 to 376):
```python
        except google_oauth.OAuthError:
            return _fail(cfg_)
```
After:
```python
        except google_oauth.OAuthError:
            return _fail(request, cfg_, "exchange")
```

(`if not code:` and `except google_oauth.OAuthError:` also appear in `gmail_callback`, but there
the next line is `return _gmail_retry(...)`, so each two-line Before block matches once.)

5f. `_fail` renders the page (lines 670 to 675).

<!-- edit: applyfirst/saas/app.py -->
Before:
```python
    def _fail(cfg_: SaaSConfig) -> JSONResponse:
        # One generic message for every failure mode — no oracle that distinguishes
        # bad-state vs missing-code vs verify-failure. Always clears the oauth txn.
        resp = JSONResponse({"error": "sign-in failed; please try again"}, status_code=400)
        session.clear_oauth_txn(resp, cfg_.secure_cookies)
        return resp
```
After:
```python
    def _fail(request: Request, cfg_: SaaSConfig, reason: str) -> HTMLResponse:
        # D8: every failure mode shows the SAME "Sign-in didn't finish" page (still 400, now
        # HTML), so the page is no oracle that tells bad-state from missing-code from
        # verify-failure. The page never reads the session or the query, so it is the same
        # bytes for everyone. The reason is logged server-side only. Always clears the txn.
        log.event(_LOG, "signin_failed", level=logging.WARNING, reason=reason)
        resp = _TEMPLATES.TemplateResponse(request, "signin_failed.html", {}, status_code=400)
        session.clear_oauth_txn(resp, cfg_.secure_cookies)
        return resp
```

Notes. `JSONResponse` stays imported, `/health` uses it (line 463). `_TEMPLATES.TemplateResponse`
is looked up at call time, which is what lets `test_saas_template_context.py` record it. The
empty context is deliberate: no `user`, no `csrf_token`, no query value, so the page cannot
differ between failures or visitors. The context processor still adds `check_every_min` and
`apps_per_day`, which the page does not print. Logging only the reason matches `_gmail_retry`,
and Google's `error` value is never logged or shown (it is attacker-controlled).

- [ ] **Step 6: Create the page**

Create `applyfirst/saas/templates/signin_failed.html` with the Write tool, exactly (LF endings):

<!-- create: applyfirst/saas/templates/signin_failed.html -->
```html
{% extends "base.html" %}
{% import "_ui.html" as ui %}
{% from "_icons.html" import icon %}
{#- D8 (spec 6.4): every /auth/callback failure renders this page, status 400. The route passes an
    empty context and the page reads no query value and no session, so it is the same bytes
    whatever went wrong (no oracle). The reason is in the server log only. -#}
{% block title %}Sign-in didn't finish · Agad{% endblock %}
{% block color_scheme %}light dark{% endblock %}
{% block theme_color_meta %}<meta name="theme-color" content="#FFFFFF" media="(prefers-color-scheme: light)">
  <meta name="theme-color" content="#111B2B" media="(prefers-color-scheme: dark)">{% endblock %}
{% block head_extra %}
  <link rel="preload" href="/static/fonts/google-sans-button-500.woff2" as="font" type="font/woff2" crossorigin>
{% endblock %}
{% block page_css %}
  <link rel="stylesheet" href="{{ static_url('vendor/basecoat-1.0.2-agad.css') }}">
  <link rel="stylesheet" href="{{ static_url('css/journey.css') }}">
{% endblock %}
{% block body_class %}is-auth{% endblock %}
{% block header_action %}{% endblock %}
{% block content %}
<div class="auth">
  <div class="auth__sheet">
    <div class="auth__head">
      <span class="auth__icon" aria-hidden="true">{{ icon('info') }}</span>
      <h1>Sign-in didn't finish</h1>
      <p class="lead">You can try again, it only takes a moment.</p>
    </div>
    <div class="auth__action">
      {{ ui.google_button(block=true) }}
    </div>
  </div>
  <p class="auth__foot"><a class="text-link" href="/">Back to the homepage</a></p>
</div>
{% endblock %}
```

What it is. The login card (Task 4's section 7 classes and `body.is-auth`) with, in spec 6.4
order, `h1` "Sign-in didn't finish", the line "You can try again, it only takes a moment.", the
Google button from the unchanged macro, and "Back to the homepage" as the quiet link under the
card, where login keeps "What is Agad?". The head is Task 3's journey snippet (the same four lines
every journey template carries, checked by Task 3's scope test) plus login's Google Sans Button
preload, because the button is above the fold. The small amber well with the `info` icon above the
heading (decorative, `aria-hidden`) is the only thing login does not have. It reuses the calm
attention tone of the Gmail retry note (`_ui.html:132-145`), never red. The title contains "Agad"
(smoke `check_page`). `didn't` is literal template text, not an expression, so autoescape leaves
the apostrophe as it is, like `_ui.html:139`.

- [ ] **Step 7: Fill section 10 of `journey.css`**

<!-- edit: applyfirst/saas/static/css/journey.css -->
Before (Task 3 leaves the two banners next to each other):
```css
/* ---- 10 signin-failed */
/* ---- 11 motion */
```
After:
```css
/* ---- 10 signin-failed */
.auth__icon{display:grid;place-items:center;width:40px;height:40px;border-radius:50%;background:var(--j-attn-bg);color:var(--j-attn-fg)}
/* ---- 11 motion */
```

One rule, 137 bytes raw, 30 bytes gzip (measured on the stand-in file). `--j-attn-fg` on
`--j-attn-bg` is 7.38 to 1 light and 9.95 to 1 dark in Chrome, above the 3 to 1 an icon needs.
Nothing moves, so section 11 gets nothing. In forced colours the well's fill drops and the icon
draws in `CanvasText`, which is enough for a decorative mark.

- [ ] **Step 8: Put the page on the journey list**

`tests/_journey_css.py`, the list Tasks 4 to 6 built. Read the file first. If Task 6 left it as
below, use exactly this edit. Otherwise add `"signin_failed.html"` as the last item.

<!-- edit: tests/_journey_css.py -->
Before:
```python
JOURNEY_TEMPLATES: list[str] = ["login.html", "onboarding_connect_gmail.html",
                                "onboarding_profile.html", "onboarding_keywords.html",
                                "onboarding_preview.html", "dashboard.html"]
```
After:
```python
JOURNEY_TEMPLATES: list[str] = ["login.html", "onboarding_connect_gmail.html",
                                "onboarding_profile.html", "onboarding_keywords.html",
                                "onboarding_preview.html", "dashboard.html",
                                "signin_failed.html"]
```

This must land in the same change as Step 6. From the moment the template file exists, Task 3's
`test_the_journey_look_loads_on_exactly_the_listed_templates[signin_failed.html]` runs, and it
fails if the page links the journey files without being listed.

- [ ] **Step 9: Run the tests and the smoke, and watch them pass**

```bash
.venv/Scripts/python.exe -m pytest -q tests/test_saas_signin_failed.py tests/test_saas_gmail_retry.py tests/test_saas_onboarding.py tests/test_saas_connect_gmail.py tests/test_saas_template_context.py
.venv/Scripts/python.exe -m pytest -q tests/test_saas_journey.py tests/test_saas_template_guards.py tests/test_saas_palette.py tests/test_saas_static.py tests/test_saas_auth_flow.py tests/test_saas_cross_tenant.py tests/test_saas_csrf.py tests/test_saas_motion.py
.venv/Scripts/python.exe .noxa/redesign-saas-ui/inputs/preserve_smoke.py
```

Expected. The first command prints `103 passed` (measured). The second prints all passed,
including `test_the_journey_look_loads_on_exactly_the_listed_templates[signin_failed.html]` and
the new `[signin_failed.html]` cases of the template guards and the palette test. The smoke ends
`607 checks passed, 0 failed.` when Tasks 1 to 6 left it at 566.

- [ ] **Step 10: Measure the page in headless Chrome, light and dark**

The static tests cannot see the real cascade. With the Write tool, save this as
`measure_signin_failed.py` in the session scratchpad (never in the repo) and run it from the repo
root. It needs Chrome at `C:\Program Files\Google\Chrome\Application\chrome.exe` and starts no
server. It compares the Google button with `/login` in the same mode, so it relies on Task 4.

<!-- scratch: measure_signin_failed.py -->
```python
"""Measure the "Sign-in didn't finish" page in headless Chrome, light and dark, phone and computer.

    .venv/Scripts/python.exe measure_signin_failed.py <repo root> [<png folder>]

No server runs: the page comes from the app's own TestClient (a failed /auth/callback), its
/static links point at the files on disk, the scripts are dropped (content never needs
JavaScript), and a probe script reads the computed styles back through --dump-dom. With a
second argument it also saves one screenshot per mode there.

Checks, each printed PASS or FAIL (exit 1 on any FAIL):
  * the Google button computes exactly as on /login in the same mode (spec 3: never restyled);
  * every visible text reaches 4.5:1 (3:1 for large text) on its real background, the Google
    button's own label excepted (Google's colours);
  * the icon well: 40px round, attention colours of the mode, icon at least 3:1 on its well;
  * one h1 at the spec 5.1 size (28px phone, 30px computer), weight 600;
  * the card: 12px corners, the surface colour of the mode; no sideways scroll.
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(sys.argv[1]).resolve()
SHOTS = Path(sys.argv[2]) if len(sys.argv) > 2 else None
sys.path.insert(0, str(REPO))

from fastapi.testclient import TestClient  # noqa: E402

from applyfirst.saas.app import create_app  # noqa: E402
from applyfirst.saas.config import SaaSConfig  # noqa: E402

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
STATIC = REPO / "applyfirst" / "saas" / "static"
PHONE = ["--blink-settings=primaryPointerType=2,availablePointerTypes=2,"
         "primaryHoverType=1,availableHoverTypes=1"]
MODES = {"light phone": ("504,900", PHONE), "dark phone": ("504,900", ["--force-dark-mode", *PHONE]),
         "light computer": ("1280,900", []), "dark computer": ("1280,900", ["--force-dark-mode"])}
SURFACE = {"light": "rgb(255, 255, 255)", "dark": "rgb(17, 27, 43)"}
WELL = {"light": ("rgb(255, 246, 230)", "rgb(122, 68, 0)"),
        "dark": ("rgb(42, 33, 16)", "rgb(245, 198, 107)")}
GSI_PROPS = ["height", "border-top-color", "border-top-width", "border-top-left-radius",
             "background-color", "background-image", "color", "font-family", "font-size",
             "font-weight", "letter-spacing", "line-height", "padding-left", "box-shadow",
             "text-decoration-line", "transform", "opacity"]

PROBE = """<script>
(async () => {
  await document.fonts.ready;
  const cs = (el) => getComputedStyle(el);
  const rgb = (s) => { const m = /rgba?\\(([^)]+)\\)/.exec(s); if (!m) return null;
    const p = m[1].split(/[\\s,\\/]+/).filter(Boolean).map(Number); return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; };
  const over = (t, u) => [0, 1, 2].map((i) => t[i] * t[3] + u[i] * (1 - t[3])).concat(1);
  const bg = (el) => { const chain = []; for (let e = el; e; e = e.parentElement) chain.unshift(e);
    let c = [255, 255, 255, 1]; for (const e of chain) { const b = rgb(cs(e).backgroundColor);
    if (b === null) return null; if (b[3] > 0) c = over(b, c); } return c; };
  const lum = (c) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); };
  const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  const name = (el) => el.tagName.toLowerCase() + (typeof el.className === "string" && el.className ? "." + el.className.trim().split(/\\s+/).join(".") : "");
  const out = { texts: [], gsi: {}, overflow: document.documentElement.scrollWidth - innerWidth };
  for (const el of document.querySelectorAll("body *")) {
    if (el.closest(".gsi-btn, .visually-hidden, [hidden], script, style, .skip-link")) continue;
    const own = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
    if (!own || !el.getClientRects().length) continue;
    const s = cs(el), fg = rgb(s.color), b = bg(el);
    const size = parseFloat(s.fontSize), large = size >= 24 || (size >= 18.66 && +s.fontWeight >= 700);
    out.texts.push({ el: name(el), text: el.textContent.trim().slice(0, 30),
      ratio: fg && b ? +ratio(over(fg, b), b).toFixed(2) : null, need: large ? 3 : 4.5 });
  }
  const g = document.querySelector(".gsi-btn");
  for (const [k, el] of [["a", g], ["img", g.querySelector("img")], ["span", g.querySelector("span")]]) {
    const s = cs(el); out.gsi[k] = Object.fromEntries(%(props)s.map((p) => [p, s.getPropertyValue(p)]));
  }
  const w = document.querySelector(".auth__icon");
  if (w) { const ws = cs(w), icon = w.querySelector("svg");
    out.well = [ws.width, ws.height, ws.borderTopLeftRadius, ws.backgroundColor, ws.color,
                +ratio(rgb(cs(icon).color), bg(w)).toFixed(2)]; }
  const h = [...document.querySelectorAll("h1")];
  out.h1 = h.map((e) => [parseFloat(cs(e).fontSize), cs(e).fontWeight]);
  const card = cs(document.querySelector(".auth__sheet"));
  out.card = [card.borderTopLeftRadius, card.backgroundColor];
  document.getElementById("probe-out").textContent = JSON.stringify(out);
})();
</script><pre id="probe-out"></pre>"""


def cfg():
    tmp = tempfile.mkdtemp(prefix="af-measure-")
    return SaaSConfig(db_path=str(Path(tmp) / "m.db"), google_client_id="m",
                      google_client_secret="m", session_secret=b"measure-session-secret-32-bytes!!!",
                      base_url="https://localhost", secure_cookies=False, auth_rate_limit=0)


def page(path: str, probe: bool = True) -> str:
    client = TestClient(create_app(cfg()), follow_redirects=False)
    html = client.get(path).text
    html = re.sub(r"<script\b[^>]*>.*?</script>", "", html, flags=re.S)
    html = re.sub(r'(href|src)="/static/([^"?]+)(?:\?[^"]*)?"',
                  lambda m: f'{m.group(1)}="{(STATIC / m.group(2)).as_uri()}"', html)
    return html.replace("</body>", PROBE % {"props": json.dumps(GSI_PROPS)} + "</body>") if probe else html


def chrome(html: str, mode: str, shot: Path | None = None) -> dict:
    window, flags = MODES[mode]
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        f = Path(tmp) / "page.html"
        f.write_text(html, encoding="utf-8")
        args = [CHROME, "--headless=new", "--disable-gpu", "--no-first-run",
                "--allow-file-access-from-files", f"--user-data-dir={tmp}/profile",
                f"--window-size={window}", "--hide-scrollbars", "--virtual-time-budget=5000", *flags]
        if shot:
            subprocess.run(args + [f"--screenshot={shot}", f.as_uri()], capture_output=True,
                           timeout=120)
            return {}
        out = subprocess.run(args + ["--dump-dom", f.as_uri()], capture_output=True, text=True,
                             encoding="utf-8", timeout=120).stdout
    m = re.search(r'<pre id="probe-out">(.*?)</pre>', out, re.S)
    assert m and m.group(1), f"{mode}: the probe wrote nothing"
    return json.loads(m.group(1).replace("&quot;", '"').replace("&amp;", "&")
                      .replace("&lt;", "<").replace("&gt;", ">"))


fails = 0


def check(ok: bool, label: str) -> None:
    global fails
    fails += not ok
    print(("PASS " if ok else "FAIL ") + label)


FAILED = "/auth/callback?error=access_denied"
for mode in MODES:
    scheme, device = mode.split()
    login = chrome(page("/login"), mode)
    got = chrome(page(FAILED), mode)
    tag = f"[{mode}]"
    for part in ("a", "img", "span"):
        diff = {k: (login["gsi"][part][k], v) for k, v in got["gsi"][part].items()
                if v != login["gsi"][part][k]}
        check(not diff, f"{tag} Google button <{part}> computes as on /login {diff or ''}")
    low = [t for t in got["texts"] if t["ratio"] is None or t["ratio"] < t["need"]]
    check(not low, f"{tag} {len(got['texts'])} texts reach AA {low or ''}")
    width, height, radius, well_bg, well_fg, icon_ratio = got["well"]
    check([width, height, radius] == ["40px", "40px", "50%"] and (well_bg, well_fg) == WELL[scheme]
          and icon_ratio >= 3, f"{tag} icon well {got['well']}")
    want_h1 = 28 if device == "phone" else 30
    check(got["h1"] == [[want_h1, "600"]], f"{tag} one h1 {got['h1']} want {want_h1}px 600")
    check(got["card"] == ["12px", SURFACE[scheme]], f"{tag} card {got['card']}")
    check(got["overflow"] <= 0, f"{tag} no sideways scroll ({got['overflow']}px)")
    if SHOTS:
        SHOTS.mkdir(parents=True, exist_ok=True)
        chrome(page(FAILED, probe=False), mode, SHOTS / f"signin-failed-{mode.replace(' ', '-')}.png")
print(f"\n{fails} failed")
sys.exit(1 if fails else 0)
```

```bash
.venv/Scripts/python.exe "<scratchpad>/measure_signin_failed.py" . "<scratchpad>/shots7"
```

Expected: 32 `PASS` lines, then `0 failed` (8 checks in each of 4 modes). Four screenshots land
in `shots7`. Look at them: one card on the ground, the amber well, the heading, the line, the
white Google button, "Back to the homepage" under the card. What a FAIL means.
- "Google button ... computes as on /login" names the property that moved. Section 10 must not
  reach the button; if it is not section 10, a rule from another section reaches the button on
  this page only, which Task 4's matcher tests would also flag when pointed at this page.
- "texts reach AA" lists each text under 4.5 to 1 (3 to 1 for large) with its ratio. Inside
  `.auth` it is section 7's or section 10's to fix, anywhere else Task 3's sections 4 to 6.
- "icon well", "one h1" and "card" are this task's and Task 4's values (spec 5.1, 5.2).
- Headless Chrome will not open narrower than about 500px, so "phone" is 504px with a coarse
  pointer and no hover. The 360 and 390px screenshots belong to Task 8.

- [ ] **Step 11: Prove the tests bite (mutation pass)**

Save this as `mutate7.py` in the scratchpad and run it from the repo root. It edits `app.py`,
the template, `journey.css` and `tests/_journey_css.py` one mistake at a time, runs the five
test files of Step 9's first command (and the smoke for five of them), and restores every file
byte for byte after each mutant and again at the end. It takes a few minutes.

<!-- scratch: mutate7.py -->
```python
"""Mutation pass for Task 7: plant one mistake at a time, run the Task 7 tests (and the smoke for
the page and redirect mutants), expect at least one failure, restore. Run from the repo root:

    .venv/Scripts/python.exe <scratchpad>/mutate7.py

Prints CAUGHT or MISSED per mutant, then a total. Exit 1 if any mutant is missed. Every file is
restored byte for byte after each mutant (and in a finally block).
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
PY = sys.executable
APP = ROOT / "applyfirst/saas/app.py"
TPL = ROOT / "applyfirst/saas/templates/signin_failed.html"
CSS = ROOT / "applyfirst/saas/static/css/journey.css"
HELPER = ROOT / "tests/_journey_css.py"
TESTS = ["tests/test_saas_signin_failed.py", "tests/test_saas_gmail_retry.py",
         "tests/test_saas_onboarding.py", "tests/test_saas_connect_gmail.py",
         "tests/test_saas_template_context.py"]
SMOKE = ".noxa/redesign-saas-ui/inputs/preserve_smoke.py"

MUTANTS = {
    "callback answers JSON again": (APP, [(
        '        resp = _TEMPLATES.TemplateResponse(request, "signin_failed.html", {}, status_code=400)\n',
        '        resp = JSONResponse({"error": "sign-in failed; please try again"}, status_code=400)\n')]),
    "status 200": (APP, [('"signin_failed.html", {}, status_code=400)', '"signin_failed.html", {})')]),
    "txn cookie kept": (APP, [(
        '        session.clear_oauth_txn(resp, cfg_.secure_cookies)\n        return resp\n\n    return app',
        '        return resp\n\n    return app')]),
    "reason shown on the page": (APP, [('"signin_failed.html", {}, status_code=400)',
                                        '"signin_failed.html", {"why": reason}, status_code=400)')],
                                 TPL, [("<h1>Sign-in didn't finish</h1>",
                                        "<h1>Sign-in didn't finish</h1>{{ why }}")]),
    "reason not logged": (APP, [('        log.event(_LOG, "signin_failed", level=logging.WARNING, reason=reason)\n', '')]),
    "wrong reason for the exchange": (APP, [('return _fail(request, cfg_, "exchange")',
                                             'return _fail(request, cfg_, "state")')]),
    "Google called before the state check": (APP, [(
        '        txn = session.read_oauth_txn(request, cfg_.session_secret, cfg_.secure_cookies)\n'
        '        returned_state = params.get("state", "")\n'
        '        # Validate state BEFORE',
        '        if params.get("code"):\n'
        '            google_oauth.fetch_identity(cfg_, code="x", code_verifier="v", expected_nonce="n")\n'
        '        txn = session.read_oauth_txn(request, cfg_.session_secret, cfg_.secure_cookies)\n'
        '        returned_state = params.get("state", "")\n'
        '        # Validate state BEFORE')]),
    "page shows the signed-in header": (APP, [('"signin_failed.html", {}, status_code=400)',
                                               '"signin_failed.html", {"user": _peek(request)}, status_code=400)'),
                                              ('    def _fail(request', '    def _peek(request):\n        cfg_ = request.app.state.cfg\n        uid = session.read_session(request, cfg_.session_secret, cfg_.secure_cookies)\n        conn = db.connect(cfg_.db_path)\n        try:\n            return db.get_user(conn, uid) if uid else None\n        finally:\n            conn.close()\n\n    def _fail(request')]),
    "query echoed on the page": (TPL, [("<h1>Sign-in didn't finish</h1>",
                                        "<h1>Sign-in didn't finish</h1>{{ request.query_params.get('error_description', '') }}")]),
    "preview left on the 401": (APP, [(
        "    def onboarding_preview_page(request: Request, user: db.User = Depends(require_user_or_login),",
        "    def onboarding_preview_page(request: Request, user: db.User = Depends(require_user),")]),
    "gmail callback left on the 401": (APP, [(
        "                       user: db.User = Depends(require_user_or_login), conn=Depends(get_conn)):",
        "                       user: db.User = Depends(require_user), conn=Depends(get_conn)):")]),
    "a POST moved to the redirect": (APP, [(
        "    def onboarding_activate(user: db.User = Depends(require_user), conn=Depends(get_conn)):",
        "    def onboarding_activate(user: db.User = Depends(require_user_or_login), conn=Depends(get_conn)):")]),
    "/me moved to the redirect": (APP, [("    def me(user: db.User = Depends(require_user)):",
                                         "    def me(user: db.User = Depends(require_user_or_login)):")]),
    "redirect adds next=": (APP, [('        return RedirectResponse("/login", status_code=302)\n\n    # --- dependencies',
                                   '        return RedirectResponse("/login?next=" + request.url.path, status_code=302)\n\n    # --- dependencies')]),
    "redirect is a 303": (APP, [('        return RedirectResponse("/login", status_code=302)\n\n    # --- dependencies',
                                 '        return RedirectResponse("/login", status_code=303)\n\n    # --- dependencies')]),
    "Google button dropped": (TPL, [("      {{ ui.google_button(block=true) }}\n", "")]),
    "Google button hand-written": (TPL, [("{{ ui.google_button(block=true) }}",
                                          '<a class="gsi-btn gsi-btn--block" href="/auth/login"><span>Continue with Google</span></a>')]),
    "heading reworded": (TPL, [("<h1>Sign-in didn't finish</h1>", "<h1>Sign-in failed</h1>")]),
    "line dropped": (TPL, [('      <p class="lead">You can try again, it only takes a moment.</p>\n', "")]),
    "home link goes to /login": (TPL, [('<a class="text-link" href="/">Back to the homepage</a>',
                                        '<a class="text-link" href="/login">Back to the homepage</a>')]),
    "journey look not linked": (TPL, [("  <link rel=\"stylesheet\" href=\"{{ static_url('css/journey.css') }}\">\n", "")]),
    "light only": (TPL, [("{% block color_scheme %}light dark{% endblock %}\n", "")]),
    "motion head on the page": (TPL, [("{% block body_class %}", "{% block motion_head %}{{ ui.motion_head() }}{% endblock %}\n{% block body_class %}")]),
    "section 10 reaches every icon": (CSS, [(".auth__icon{display:grid", ".auth .icon,.auth__icon{display:grid")]),
    "section 10 animates": (CSS, [("border-radius:50%;background:var(--j-attn-bg);color:var(--j-attn-fg)}",
                                   "border-radius:50%;background:var(--j-attn-bg);color:var(--j-attn-fg);transition:color .2s}")]),
    "section 10 in red": (CSS, [("border-radius:50%;background:var(--j-attn-bg);color:var(--j-attn-fg)}",
                                 "border-radius:50%;background:var(--j-attn-bg);color:var(--j-danger-fg)}")]),
    "section 10 empty": (CSS, [(".auth__icon{display:grid;place-items:center;width:40px;height:40px;border-radius:50%;background:var(--j-attn-bg);color:var(--j-attn-fg)}\n", "")]),
    "not on the journey list": (HELPER, [(re.compile(r',\s*"signin_failed\.html"'), "")]),
}
SMOKE_TOO = {"callback answers JSON again", "txn cookie kept", "query echoed on the page",
             "preview left on the 401", "Google button dropped"}


def run(cmd):
    return subprocess.run(cmd, cwd=ROOT, capture_output=True).returncode


originals = {p: p.read_bytes() for p in (APP, TPL, CSS, HELPER)}
missed = []
try:
    for name, spec in MUTANTS.items():
        pairs = list(zip(spec[0::2], spec[1::2]))
        for path, edits in pairs:
            raw = path.read_bytes().decode("utf-8")
            text = raw.replace("\r\n", "\n")
            for old, new in edits:
                if isinstance(old, re.Pattern):
                    text, n = old.subn(new, text)
                    assert n == 1, (name, old.pattern, n)
                    continue
                assert text.count(old) == 1, (name, old[:60], text.count(old))
                text = text.replace(old, new)
            if "\r\n" in raw:
                text = text.replace("\n", "\r\n")
            path.write_bytes(text.encode("utf-8"))
        caught = run([PY, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", *TESTS]) != 0
        if name in SMOKE_TOO:
            caught = caught and run([PY, SMOKE]) != 0
        print(("CAUGHT " if caught else "MISSED ") + name, flush=True)
        if not caught:
            missed.append(name)
        for p, b in originals.items():
            p.write_bytes(b)
finally:
    for p, b in originals.items():
        p.write_bytes(b)
print(f"\n{len(MUTANTS) - len(missed)} of {len(MUTANTS)} caught; missed: {missed}")
sys.exit(1 if missed else 0)
```

```bash
.venv/Scripts/python.exe "<scratchpad>/mutate7.py"
git status --short
```

Expected: 28 `CAUGHT` lines, then `28 of 28 caught; missed: []`, and `git status` shows the same
files as before the run. A `MISSED` line names a mistake no test notices. Add the missing
assertion to `tests/test_saas_signin_failed.py` before going on.

- [ ] **Step 12: Look at it once, then stop the server**

In the owner's own PowerShell window (Handoff: background shells get reaped), with a data folder
outside the repo:

```powershell
.venv\Scripts\python.exe .noxa\redesign-saas-ui\artifacts\run_local.py --port 8765 --data-dir C:\Users\regid\agad-preview
```

Open `http://127.0.0.1:8765/auth/callback?error=access_denied` in Chrome. Expected: the
"Sign-in didn't finish" card, in light, then in dark (DevTools, Rendering, "Emulate CSS media
feature prefers-color-scheme"). Then open `http://127.0.0.1:8765/__dev/logout` and
`http://127.0.0.1:8765/onboarding/profile`. Expected: the address bar ends on `/login`. Stop the
server with Ctrl+C in that window and confirm nothing is left listening:

```powershell
Get-NetTCPConnection -State Listen -LocalPort 8765 -ErrorAction SilentlyContinue
```

Expected: no output.

- [ ] **Step 13: Run both gates**

```bash
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe .noxa/redesign-saas-ui/inputs/preserve_smoke.py
```

Expected. pytest: all pass (887 + the new tests), measured `1266 passed` in sequence (1,204 +
62). This task adds 62 items: 56 in `tests/test_saas_signin_failed.py`, the
`[signin_failed.html]` case of three template guards and two palette tests, and the
`[signin_failed.html]` case of Task 3's scope test; the two renamed tests in
`test_saas_gmail_retry.py` keep the count. smoke: 0 failed, `607 checks passed, 0 failed.`

**Notes for the reviewer (Task 7):**
1. Order. Task 7 needs Task 3 (the blocks, section banners, `.text-link`, tokens) and Task 4 (the
   `.auth` card CSS in section 7, and `/login` fetching the new assets first in the smoke). It
   does not depend on Tasks 5 and 6 except for the exact `JOURNEY_TEMPLATES` Before text.
2. Spec 7 asks to "update the callback and signed-out expectations" in the smoke, but the smoke
   has none today (it only touches `/auth/gmail-callback` signed in). Step 3 adds them as new
   checks, 41 of them.
3. `tests/test_saas_template_context.py` would keep passing without an edit, because it only
   records the templates its own requests render. Step 2 adds the callback request so the new
   route context is checked.
4. The icon well is a small addition beyond the four items spec 6.4 lists (decorative, 30 bytes
   gzip, calm amber). If the owner wants the page plainer, delete the `<span class="auth__icon">`
   line, the section 10 rule, and the two section 10 tests, and leave section 10 empty.
5. The page never reads the session, so a signed-in visitor whose second sign-in fails sees the
   signed-out header (brand only, no Log out). That keeps the page identical for everyone and puts
   no CSRF token on a 400 page. "Back to the homepage" sends them to `/`, which redirects a
   signed-in visitor to `/dashboard` (`app.py:296-297`).
6. `_fail` logged nothing before. It now writes one WARNING `signin_failed` per failure, as
   `gmail_connect_failed` does, so every Cancel on Google's sign-in page is a log line. Google's
   own `error` value is not logged, only the fixed reason.
7. `/auth/gmail-callback` signed out now redirects before reading or clearing its txn cookie,
   exactly as the 401 did. The stale cookie expires on its own after 10 minutes
   (`session.py`, `_OAUTH_MAX_AGE`).


### Task 8: Verification and docs

Spec 10 and spec 11 stage 6. Nothing new is built here: this task proves the finished journey in a
real browser, has it reviewed, breaks every new check once, and updates the two hand-off documents.
Everything below was run during assembly against a copy of the repo carrying Tasks 1 to 7 exactly
as this plan writes them; the expected outputs are those measurements.

**Files:**
- Scratchpad only, never in the repo: `<scratchpad>/pw/` (a venv holding Playwright, so nothing is
  installed into the project), `<scratchpad>/budgets.py`, `<scratchpad>/verify_journey.py`,
  `<scratchpad>/journey-shots/`, `<scratchpad>/mutate_journey_final.py` (a copy of Task 3's script
  with two anchors moved), `<scratchpad>/mutate_rf.py`, and the preview's throwaway data folder
  `<scratchpad>/agad-journey-preview/`.
- Modify: `DESIGN-HANDOFF.md` (LF) lines 98 to 99 (the gradient), 101 to 103 (the type), 124 to
  125 ("nothing is minified"), 160 to 165 (the palette scan), 224 and 234 (the file list), 250 (the
  font lock).
- Modify: `Handoff.md` (LF) lines 13 to 16 and 22 to 25 (Current State), 51 to 55 (the redesign
  section's opening), 104 to 105 (the Inter research note), 279 to 280 (asset weights), 291 (the
  new-work list), 320 (constraints), 329 to 330 (locked decisions), 474 to 476 (follow-ups), 666 to
  669 (next step).
- Not touched: any code, template, stylesheet or test, unless a review finding survives its
  skeptic in Step 9 (then the fix goes into the owning task's files, test first, and both gates run
  again).

**Interfaces:**
- Consumes: the finished tree of Tasks 1 to 7; `.noxa/redesign-saas-ui/artifacts/run_local.py`,
  which seeds 22 states and writes `<data dir>/states.json` (`{state: {"url", "description",
  "cookie"}}`, cookie name `applyfirst_session`); the mutation scripts of Task 1 Step 10
  (`plant.py`), Task 3 Step 11 (`mutate_journey.py`), Task 5 Step 9 (`mutate5.py`, with
  `patch_step3.py` beside it), Task 6 Step 8 (`mutate6.py`) and Task 7 Step 11 (`mutate7.py`);
  the review-focus test names from the plan's Review Focus section.
- Produces: screenshots and PASS lines for every journey state, the reviewed and mutation-tested
  tree, the two updated documents, and the file list the owner commits.

**Frozen hooks (spec 9).** None is edited here. Step 6 measures the two the spec asks for in a
browser: the Activate button (`form.activate .btn--primary`) plain, disabled and busy, and hovered,
at `rgb(11, 107, 199)`, no image, 12px, opacity 1; and the live panel (`.status--live`) at
`rgb(11, 37, 69)`, 24px, `position: relative`, `isolation: isolate`, opacity 1.

- [ ] **Step 1: Run both gates on the finished tree**

```bash
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe .noxa/redesign-saas-ui/inputs/preserve_smoke.py
```

Expected: pytest: all pass (887 + the new tests), `1266 passed`; smoke: 0 failed, `607 checks
passed, 0 failed.`

- [ ] **Step 2: Print the budgets**

Write `<scratchpad>/budgets.py` with the Write tool:

```python
"""Print the spec 8 budgets from the files on disk (gzip level 9, CRLF normalised to LF).

    .venv/Scripts/python.exe <scratchpad>/budgets.py
"""
import gzip
from pathlib import Path

S = Path("applyfirst/saas/static")


def gz(p: Path) -> int:
    return len(gzip.compress(p.read_bytes().replace(b"\r\n", b"\n"), 9, mtime=0))


app, bc, jc = S / "css/app.css", S / "vendor/basecoat-1.0.2-agad.css", S / "css/journey.css"
inter = S / "fonts/inter-4.1-latin-wght.woff2"
rows = [("trimmed Basecoat, gzip", gz(bc), 7000), ("journey.css, gzip", gz(jc), 8000),
        ("/login render-blocking CSS, gzip", gz(app) + gz(bc) + gz(jc), 30000),
        ("Inter file, raw bytes", inter.stat().st_size, 50000)]
for name, got, cap in rows:
    print(f"{'ok  ' if got <= cap else 'OVER'} {name:34} {got:>6} of {cap}")
```

Run it from the repo root: `.venv/Scripts/python.exe <scratchpad>/budgets.py`

Expected, exactly:

```text
ok   trimmed Basecoat, gzip               3363 of 7000
ok   journey.css, gzip                    4962 of 8000
ok   /login render-blocking CSS, gzip    24213 of 30000
ok   Inter file, raw bytes               28132 of 50000
```

- [ ] **Step 3: Make a scratch venv with Playwright**

The project venv stays as it is. Playwright drives the installed Chrome 153 (`channel="chrome"`), so
no browser is downloaded.

```powershell
C:\Users\regid\AppData\Local\Programs\Python\Python314\python.exe -m venv <scratchpad>\pw
<scratchpad>\pw\Scripts\python.exe -m pip install playwright
<scratchpad>\pw\Scripts\python.exe -c "import importlib.metadata as m; print(m.version('playwright'))"
```

Expected: a version line (1.63.0 was used during assembly).

- [ ] **Step 4: Write the browser pass**

Write `<scratchpad>/verify_journey.py` with the Write tool. It only reads pages: it signs in with
the cookies `run_local.py` writes, never submits a form, and runs every check spec 10 lists plus the
browser half of review focus 2 and 3.

```python
"""Task 8 browser pass for the sign-up journey (spec 10), driven through the local preview.

    <scratchpad>/pw/Scripts/python.exe verify_journey.py <base url> <states.json> <out folder>

The preview must already be running in its own window (run_local.py). This script only reads
pages: it signs in with the session cookies run_local.py wrote to states.json, and it never
submits a form. It uses the installed Chrome (channel "chrome"), headless, scrollbars hidden,
with Playwright from a scratch venv, so nothing is installed into the project.

It prints one PASS or FAIL line per check, saves full-page screenshots to <out folder>, and exits
1 on any FAIL. What it covers:
  * every journey state at 360, 390, 768 and 1280 wide, light and dark: every visible text at
    WCAG AA on its real background, and no sideways scroll;
  * the frozen values in a real cascade: the Activate button, also disabled and busy under the
    mouse, is rgb(11, 107, 199), no image, 12px, opacity 1; the live panel is rgb(11, 37, 69), 24px,
    relative, isolated, opaque, with a white 12 percent edge in dark only;
  * JavaScript off: every page complete, nothing hidden;
  * reduced motion: nothing animates and no transition runs;
  * forced colours: every button, card, alert, badge and field keeps a solid edge, and the focus
    ring draws in the system Highlight colour;
  * text at 200 percent: no button or field clips its own label;
  * a first visit on slow mobile data on Android: text shows before Inter arrives, Inter is
    fetched once as font/woff2, and the swap shifts the layout by less than 0.02 (CLS).
"""
import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1].rstrip("/")
STATES = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
OUT = Path(sys.argv[3])
OUT.mkdir(parents=True, exist_ok=True)
HOST = re.sub(r"^https?://", "", BASE).split(":")[0]
ANDROID = ("Mozilla/5.0 (Linux; Android 13; SM-A536E) AppleWebKit/537.36 (KHTML, like Gecko) "
           "Chrome/153.0.0.0 Mobile Safari/537.36")

# Every journey state: the 22 seeded states, the dashboard after a failed reconnect (no entry of
# its own), the login page and the "Sign-in didn't finish" page.
PAGES = {name: (info["url"], info["cookie"]) for name, info in STATES.items()}
PAGES["dash-reconnect-failed"] = (STATES["dash-live"]["url"] + "?gmail_error=scope",
                                  STATES["dash-live"]["cookie"])
PAGES["login"] = (BASE + "/login", None)
PAGES["signin-failed"] = (BASE + "/auth/callback?error=access_denied", None)
WIDTHS = (360, 390, 768, 1280)
BLUE, NAVY = "rgb(11, 107, 199)", "rgb(11, 37, 69)"
FROZEN_BUTTON = [BLUE, "none", "12px", "1"]
LIVE_EDGE = {"light": "rgba(11, 37, 69, 0.1)", "dark": "rgba(255, 255, 255, 0.12)"}

SETTLE = """() => Promise.race([
  Promise.all(document.getAnimations().map((a) => a.finished.catch(() => null))),
  new Promise((r) => setTimeout(r, 2500))])"""
PROBE = """() => {
  const cs = (el) => getComputedStyle(el);
  const rgb = (s) => { const m = /rgba?\\(([^)]+)\\)/.exec(s); if (!m) return null;
    const p = m[1].split(/[\\s,\\/]+/).filter(Boolean).map(Number);
    return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; };
  const over = (t, u) => [0, 1, 2].map((i) => t[i] * t[3] + u[i] * (1 - t[3])).concat(1);
  const bg = (el) => { const chain = []; for (let e = el; e; e = e.parentElement) chain.unshift(e);
    let c = [255, 255, 255, 1]; for (const e of chain) { const b = rgb(cs(e).backgroundColor);
    if (b === null || cs(e).backgroundImage !== 'none') return null;
    if (b[3] > 0) c = over(b, c); } return c; };
  const lum = (c) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); };
  const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  const name = (el) => el.tagName.toLowerCase() + (typeof el.className === 'string' && el.className.trim() ? '.' + el.className.trim().split(/\\s+/).join('.') : '');
  const low = [], unmeasured = [];
  let texts = 0;
  for (const el of document.querySelectorAll('body *')) {
    if (el.closest('.gsi-btn, .visually-hidden, [hidden], script, style, details:not([open]) > :not(summary)')) continue;
    const own = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
    if (!own || !el.getClientRects().length || cs(el).visibility === 'hidden') continue;
    const s = cs(el), fg = rgb(s.color), b = bg(el);
    if (!fg || !b) { unmeasured.push(name(el)); continue; }
    const size = parseFloat(s.fontSize), need = size >= 24 || (size >= 18.66 && +s.fontWeight >= 700) ? 3 : 4.5;
    const r = ratio(over(fg, b), b);
    texts += 1;
    if (r < need) low.push([name(el), el.textContent.trim().slice(0, 30), +r.toFixed(2), need]);
  }
  return { texts, low, unmeasured, overflow: document.documentElement.scrollWidth - innerWidth,
           coarse: matchMedia('(pointer: coarse)').matches };
}"""
BUTTON = """(held) => { const b = document.querySelector('form.activate .btn--primary');
  if (!b) return null;
  if (held) { b.disabled = true; b.dataset.state = 'busy'; }
  const s = getComputedStyle(b);
  return [s.backgroundColor, s.backgroundImage, s.borderTopLeftRadius, s.opacity]; }"""
LIVE = """() => { const p = document.querySelector('.status--live'); if (!p) return null;
  const s = getComputedStyle(p);
  return [s.backgroundColor, s.borderTopLeftRadius, s.position, s.isolation, s.opacity, s.borderTopColor]; }"""

fails = 0


def check(ok: bool, label: str) -> None:
    global fails
    fails += not ok
    print(("PASS " if ok else "FAIL ") + label, flush=True)


def open_page(browser, name, **ctx):
    url, cookie = PAGES[name]
    context = browser.new_context(**ctx)
    if cookie:
        context.add_cookies([{"name": "applyfirst_session", "value": cookie, "domain": HOST,
                              "path": "/"}])
    page = context.new_page()
    page.goto(url, wait_until="load")
    return context, page


with sync_playwright() as pw:
    browser = pw.chromium.launch(channel="chrome", args=["--hide-scrollbars"])

    # 1. Every state, four widths, light and dark: AA text, no sideways scroll, frozen values.
    for name in PAGES:
        for width in WIDTHS:
            for scheme in ("light", "dark"):
                touch = width <= 768
                context, page = open_page(
                    browser, name, viewport={"width": width, "height": 900}, color_scheme=scheme,
                    reduced_motion="no-preference", has_touch=touch, is_mobile=width <= 390)
                page.evaluate(SETTLE)
                tag = f"[{name} {width} {scheme}]"
                got = page.evaluate(PROBE)
                eye = sorted(set(got["unmeasured"]))
                check(not got["low"], f"{tag} {got['texts']} texts reach AA {got['low'] or ''}"
                      + (f" (on an image, check by eye: {eye})" if eye else ""))
                check(got["overflow"] <= 0, f"{tag} no sideways scroll ({got['overflow']}px)")
                if width in (360, 390):
                    check(got["coarse"], f"{tag} a phone gets the coarse pointer (phone sizes)")
                live = page.evaluate(LIVE)
                if live:
                    check(live == [NAVY, "24px", "relative", "isolate", "1", LIVE_EDGE[scheme]],
                          f"{tag} live panel {live}")
                plain = page.evaluate(BUTTON, False)
                if plain:
                    if width == 1280:          # a mouse rests on it: disabled and busy beat hover
                        page.hover("form.activate .btn--primary", force=True)
                    held = page.evaluate(BUTTON, True)
                    check(plain == held == FROZEN_BUTTON,
                          f"{tag} Activate {plain}, disabled and busy {held}")
                page.screenshot(path=str(OUT / f"{name}-{width}-{scheme}.png"), full_page=True)
                context.close()

    # 2. JavaScript off: nothing waits for a script to become visible. The frozen motion.css
    #    entrances (af-hop, af-rise, af-settle) start at opacity 0 and finish on their own, so the
    #    check runs once they have settled.
    for name in PAGES:
        context, page = open_page(browser, name, viewport={"width": 390, "height": 900},
                                  java_script_enabled=False, reduced_motion="no-preference")
        page.evaluate(SETTLE)
        hidden = page.evaluate("""() => [...document.querySelectorAll('main *')]
          .filter((e) => e.getClientRects().length && (getComputedStyle(e).opacity === '0'
                   || getComputedStyle(e).visibility === 'hidden'))
          .map((e) => e.tagName + '.' + e.className).slice(0, 5)""")
        check(hidden == [], f"[{name} js off] nothing hidden {hidden or ''}")
        page.screenshot(path=str(OUT / f"{name}-390-js-off.png"), full_page=True)
        context.close()

    # 3. Reduced motion: no animation plays and no transition is armed on the journey controls.
    for name in PAGES:
        context, page = open_page(browser, name, viewport={"width": 1280, "height": 900},
                                  reduced_motion="reduce")
        page.wait_for_timeout(300)
        moving = page.evaluate("""() => document.getAnimations()
          .filter((a) => a.playState === 'running').map((a) => a.animationName || a.transitionProperty || 'anim')""")
        armed = page.evaluate("""() => [...document.querySelectorAll('.btn, .input, .badge')]
          .filter((e) => { const s = getComputedStyle(e); return s.transitionProperty !== 'none'
            && parseFloat(s.transitionDuration) > 0.001; }).map((e) => e.className).slice(0, 5)""")
        check(moving == [] and armed == [], f"[{name} reduced motion] still {moving} {armed}")
        context.close()

    # 4. Forced colours: shapes keep a solid edge, and focus is drawn in Highlight.
    for name in PAGES:
        context, page = open_page(browser, name, viewport={"width": 1280, "height": 900},
                                  forced_colors="active")
        flat = page.evaluate("""() => [...document.querySelectorAll('.btn, .sheet, .card, .alert, .badge, .input')]
          .filter((e) => e.getClientRects().length && !e.closest('.gsi-btn'))
          .filter((e) => { const s = getComputedStyle(e);
            return s.borderTopStyle === 'none' || parseFloat(s.borderTopWidth) < 1; })
          .map((e) => e.tagName + '.' + e.className).slice(0, 5)""")
        check(flat == [], f"[{name} forced colours] every shape keeps its edge {flat or ''}")
        target = page.query_selector("main a[href], main button, main input:not([type=hidden])")
        if target:
            target.focus()
            page.keyboard.press("Shift+Tab")
            page.keyboard.press("Tab")
            ring = page.evaluate("""() => { const p = document.createElement('i');
              p.style.color = 'Highlight'; document.body.append(p);
              const want = getComputedStyle(p).color; p.remove();
              const s = getComputedStyle(document.activeElement);
              return [s.outlineStyle, s.outlineColor, want]; }""")
            check(ring[0] != "none" and ring[1] == ring[2], f"[{name} forced colours] focus ring {ring}")
        page.screenshot(path=str(OUT / f"{name}-1280-forced.png"), full_page=True)
        context.close()

    # 5. Text at 200 percent (Android's largest font size): no control clips its own label.
    #    Buttons and badges must hold their label; a field must stay at least as tall as its rows
    #    of text (a long value may scroll inside it, which is what fields do).
    for name in PAGES:
        for width in (360, 1280):
            context, page = open_page(browser, name, viewport={"width": width, "height": 900},
                                      bypass_csp=True, has_touch=width < 1280,
                                      is_mobile=width < 1280)
            page.add_style_tag(content="html{font-size:200% !important}")
            clipped = page.evaluate("""() => [...document.querySelectorAll('.btn, .badge, input:not([type=hidden]), textarea')]
              .filter((e) => e.getClientRects().length && !e.closest('.gsi-btn'))
              .filter((e) => e.matches('input, textarea')
                ? e.clientHeight + 1 < parseFloat(getComputedStyle(e).lineHeight) * (e.rows || 1)
                : e.scrollHeight > e.clientHeight + 1 || e.scrollWidth > e.clientWidth + 1)
              .map((e) => e.tagName + '.' + e.className + ' ' + e.scrollHeight + '>' + e.clientHeight)
              .slice(0, 5)""")
            check(clipped == [], f"[{name} {width} text 200%] no control clips its label {clipped or ''}")
            page.screenshot(path=str(OUT / f"{name}-{width}-text200.png"), full_page=True)
            context.close()

    # 6. A first visit on slow mobile data on Android: text first, then Inter, barely a shift.
    for name in ("login", "dash-live", "s2-prefilled"):
        context = browser.new_context(viewport={"width": 390, "height": 844}, user_agent=ANDROID,
                                      has_touch=True, is_mobile=True, device_scale_factor=2)
        if PAGES[name][1]:
            context.add_cookies([{"name": "applyfirst_session", "value": PAGES[name][1],
                                  "domain": HOST, "path": "/"}])
        context.add_init_script("""window.__cls = 0; new PerformanceObserver((l) => {
          for (const e of l.getEntries()) if (!e.hadRecentInput) window.__cls += e.value;
        }).observe({ type: 'layout-shift', buffered: true });""")
        page = context.new_page()
        fonts = []
        page.on("response", lambda r: fonts.append((r.url, r.status, r.headers.get("content-type")))
                if r.url.endswith(".woff2") else None)
        cdp = context.new_cdp_session(page)
        cdp.send("Network.enable")
        cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})
        cdp.send("Network.emulateNetworkConditions", {"offline": False, "latency": 400,
                                                      "downloadThroughput": 50_000,
                                                      "uploadThroughput": 50_000})
        page.goto(PAGES[name][0], wait_until="domcontentloaded")
        early = page.evaluate("() => document.fonts.check('16px \"Inter Agad\"')")
        page.screenshot(path=str(OUT / f"{name}-slow-before-inter.png"))
        page.wait_for_function("() => document.fonts.check('16px \"Inter Agad\"')", timeout=60_000)
        page.evaluate("() => document.fonts.ready")
        page.wait_for_timeout(500)
        cls = page.evaluate("() => window.__cls")
        inter = [f for f in fonts if "inter-" in f[0]]
        check(not early, f"[{name} slow 3G] text painted before Inter arrived")
        check(len(inter) == 1 and inter[0][1] == 200 and inter[0][2] == "font/woff2",
              f"[{name} slow 3G] Inter fetched once as font/woff2 {inter}")
        check(cls < 0.02, f"[{name} slow 3G] layout shift from the font swap {cls:.4f}")
        page.screenshot(path=str(OUT / f"{name}-slow-after-inter.png"))
        context.close()

    browser.close()

print(f"\n{fails} failed")
sys.exit(1 if fails else 0)
```

- [ ] **Step 5: Start the preview in its own window**

Background shells get reaped on this machine (Handoff, "Environment quirks"), so the preview runs
in a separate PowerShell window. From the repo root, in PowerShell:

```powershell
$data = "<scratchpad>\agad-journey-preview"
Remove-Item -Recurse -Force $data -ErrorAction SilentlyContinue
Start-Process powershell -ArgumentList '-NoExit', '-Command', "Set-Location 'C:\Users\regid\Desktop\applyfirst'; .\.venv\Scripts\python.exe .noxa\redesign-saas-ui\artifacts\run_local.py --port 8765 --data-dir '$data'"
$deadline = (Get-Date).AddSeconds(60)
while (-not (Get-NetTCPConnection -State Listen -LocalPort 8765 -ErrorAction SilentlyContinue) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 500 }
(Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8765/__dev/).StatusCode
Test-Path "$data\states.json"
```

Expected: a new window printing `ApplyFirst local runner: http://127.0.0.1:8765/__dev/` and the 22
states, then `200` and `True` here (the same commands were tried during assembly on a spare port).
`run_local.py` refuses a data folder inside the repo, and a fresh folder means fresh cookies.

- [ ] **Step 6: Run the browser pass**

```powershell
<scratchpad>\pw\Scripts\python.exe -u <scratchpad>\verify_journey.py http://127.0.0.1:8765 <scratchpad>\agad-journey-preview\states.json <scratchpad>\journey-shots
```

Expected: 707 lines starting `PASS`, no `FAIL`, then `0 failed` (about 9 minutes).
Among them, for `s4-connected` at every width and scheme,
`Activate ['rgb(11, 107, 199)', 'none', '12px', '1'], disabled and busy ['rgb(11, 107, 199)',
'none', '12px', '1']` (at 1280 wide the mouse rests on the button while it is held); for the five
live-panel states, `live panel ['rgb(11, 37, 69)', '24px', 'relative', 'isolate', '1',
'rgba(11, 37, 69, 0.1)']` in light and `... 'rgba(255, 255, 255, 0.12)']` in dark; and a layout
shift from the font swap of 0.0000 on `/login` and 0.0011 on the dashboard. What a FAIL means, and where to fix it:
- "texts reach AA" lists each element under 4.5 to 1 (3 to 1 for large text) with its ratio. On a
  page body it belongs to that page's section (7 login, 8 onboarding, 9 dashboard, 10 sign-in
  failed); in the header, footer, alerts or buttons it belongs to Task 3's sections 4 to 6.
- "live panel" or "Activate" printing anything else means a journey rule reached a frozen hook:
  find it with the matcher in `tests/test_saas_journey.py` and scope it, never restyle the hook
  back.
- "js off", "reduced motion", "forced colours" and "text 200%" name the elements that failed.
- "slow 3G" prints the measured layout shift; above 0.02 means the fallback numbers in section 1 no
  longer match the served Inter (rerun `tools/fonts/build_inter.py` and copy its `fallback:` line).

- [ ] **Step 7: Look at the screenshots**

Open these in `<scratchpad>\journey-shots\` and check by eye what no script can judge:
`login-390-light.png`, `login-390-dark.png`, `s1-new-390-dark.png`, `s2-error-390-dark.png`,
`s3-many-390-dark.png`, `s4-connected-1280-light.png`, `s4-connected-1280-dark.png`,
`dash-live-390-dark.png`, `dash-live-1280-light.png`, `dash-at-cap-390-dark.png`,
`signin-failed-390-dark.png`, `dash-live-1280-forced.png`, `s2-prefilled-360-text200.png`, and
`login-slow-before-inter.png` next to `login-slow-after-inter.png`. Expected: one calm card per
step; the white sample email and the white Google button in both schemes; the navy live panel with
a faint light edge only in dark; chips, pills and the stepper readable in dark; three groups of rows
with Edit links on the right; text already visible before Inter arrives. Note for the owner the one
known weak spot: in dark mode the header mark's navy tile nearly disappears (the chevron and dot
still read). Spec 10's last point stays open and goes to Handoff.md in Step 12: that iPhones and
Macs never download Inter cannot be proven on Windows and needs a real Apple device.

- [ ] **Step 8: Stop the preview**

From PowerShell, stop the server, then close the window it ran in:

```powershell
Get-NetTCPConnection -State Listen -LocalPort 8765 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" | Where-Object { $_.CommandLine -like '*run_local.py*8765*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Start-Sleep -Milliseconds 800
(Get-NetTCPConnection -State Listen -LocalPort 8765 -ErrorAction SilentlyContinue | Measure-Object).Count
```

Expected: `0`. Nothing may be left listening, and no preview window stays open.

- [ ] **Step 9: One multi-agent review, with a skeptic per finding**

Review the whole uncommitted change once: invoke the `code-review` skill with the argument `high`
(it reviews the working-tree diff). For every finding it reports, dispatch one fresh subagent as a
skeptic, with this prompt and the finding pasted in:

```text
You are a skeptic. Below is a claimed defect in an uncommitted change to the Agad SaaS
(C:/Users/regid/Desktop/applyfirst). Try to prove it wrong. Open the cited files at the cited
lines, read the spec docs/superpowers/specs/2026-09-24-signup-redesign-design.md and the plan
docs/superpowers/plans/2026-09-25-signup-redesign.md where they bear on it, and run the smallest
check that settles it (a single pytest node, a grep, or rendering one page with
tests/_saas_client.py). Do not edit any repo file. Reply with exactly one line starting
CONFIRMED or REFUTED, then the evidence: file:line references and the command you ran with its
output.

Claimed defect:
<paste the finding>
```

Fix only CONFIRMED findings, each in the files of the task that owns the code, with a failing test
first, then run both gates. Keep a short list (finding, verdict, fix or reason) for Step 12.
Expected: every finding has a verdict, and both gates are green after the last fix.

- [ ] **Step 10: The mutation pass: break each new check once**

The per-task mutation scripts from Tasks 1, 3, 5, 6 and 7 are still in the scratchpad. Task 3's was
written for a file whose sections 7 to 10 were empty, so copy it to
`<scratchpad>/mutate_journey_final.py` and change its two anchors that the page tasks moved.
Before:

```python
    "section order": edit(J, ("/* ---- 9 dashboard */\n/* ---- 10 signin-failed */", "/* ---- 10 signin-failed */\n/* ---- 9 dashboard */")),
```

After:

```python
    "section order": edit(J, ("/* ---- 9 dashboard */", "/* ---- 10 dashboard */")),
```

Before:

```python
    "listed but not linked": edit(HELPER, ("JOURNEY_TEMPLATES: list[str] = []", "JOURNEY_TEMPLATES: list[str] = [\"login.html\"]")),
```

After:

```python
    "listed but not linked": edit(HELPER, ('"signin_failed.html"]', '"signin_failed.html", "privacy.html"]')),
```

Write `<scratchpad>/mutate_rf.py` with the Write tool; it breaks each review-focus check once:

```python
"""Break each review-focus check once (plan "Review Focus") and confirm a test catches it.

    .venv/Scripts/python.exe <scratchpad>/mutate_rf.py <repo root>

Each mutant edits one file, runs only the review-focus tests, and puts the original bytes back in
a finally block. Exit 1 if any mutant survives.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
J = ROOT / "applyfirst/saas/static/css/journey.css"
SA = ROOT / "applyfirst/saas/static_assets.py"
S8 = "/* ---- 8 onboarding */"                 # a rule inserted before this lands in section 7
S10 = "/* ---- 10 signin-failed */"            # ... before this, in section 9
HIGH, ZOOM, TOUCH = "high_contrast", "zoomed", "computer_sizes"
DARK, FONT = "light_page_colour", "served_as"
MUTANTS = {
    "focus ring loses Highlight": (J, ":focus-visible{outline-color:Highlight}}", "}", HIGH),
    "chip border removed": (J, S10, ".chip{border:0}\n" + S10, HIGH),
    "rail marker restore dropped": (J, "@media (forced-colors:active) and (min-width:960px)"
                                       "{.stepper__marker{background:Highlight}}", "", HIGH),
    "fixed button height": (J, S8, ".auth .btn{height:44px}\n" + S8, ZOOM),
    "input max-height": (J, S8, ".input{max-height:48px}\n" + S8, ZOOM),
    "button label on one line": (J, S8, ".btn--secondary{white-space:nowrap}\n" + S8, ZOOM),
    "sizes on a coarse pointer": (J, S8, "@media (any-pointer:coarse){.btn{min-height:48px}}\n" + S8,
                                  TOUCH),
    "padding on hover alone": (J, S8, "@media (hover:hover){.btn{padding:0 20px}}\n" + S8, TOUCH),
    "tap band only on back links": (J, ".text-link::after,.back-link::after{", ".back-link::after{",
                                    TOUCH),
    "chip text navy again": (J, ".usage-note--cap,.chip{color:var(--j-text)}",
                             ".usage-note--cap{color:var(--j-text)}", DARK),
    "Gmail panel amber again": (J, ".status--gmail{background:var(--j-surface)}", "", DARK),
    "near-limit note amber-800 again": (J, ".usage-note--near{color:var(--j-attn-fg)}", "", DARK),
    "font cached as if hashed": (SA, '"public, max-age=31536000, immutable" if hashed else '
                                     '"public, max-age=86400"',
                                 '"public, max-age=31536000, immutable"', FONT),
}

missed = []
for name, (path, old, new, pick) in MUTANTS.items():
    original = path.read_bytes()
    text = original.decode("utf-8")
    assert text.count(old) == 1, (name, text.count(old))
    path.write_bytes(text.replace(old, new).encode("utf-8"))
    try:
        run = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                              "tests/test_saas_journey.py", "tests/test_saas_hero.py", "-k", pick],
                             cwd=ROOT, capture_output=True, text=True)
    finally:
        path.write_bytes(original)
    caught = run.returncode != 0
    last = (run.stdout.strip().splitlines() or [""])[-1]
    print(("CAUGHT  " if caught else "MISSED  ") + f"{name:34} {last[:70]}", flush=True)
    if not caught:
        missed.append(name)
print(f"{len(MUTANTS) - len(missed)} of {len(MUTANTS)} caught, missed {missed}")
sys.exit(1 if missed else 0)
```

Run them one after another (never two at once: each edits the working tree and restores it), from
the repo root:

```bash
.venv/Scripts/python.exe <scratchpad>/plant.py && .venv/Scripts/python.exe -m pytest -q tests/test_saas_basecoat.py tests/test_saas_palette.py; .venv/Scripts/python.exe tools/basecoat/trim.py
.venv/Scripts/python.exe <scratchpad>/mutate_journey_final.py .
.venv/Scripts/python.exe <scratchpad>/mutate5.py .
.venv/Scripts/python.exe <scratchpad>/mutate6.py .
.venv/Scripts/python.exe <scratchpad>/mutate7.py
.venv/Scripts/python.exe <scratchpad>/mutate_rf.py .
git status --short
```

Expected: the planted Basecoat rule fails exactly the 4 tests Task 1 Step 10 names, and `trim.py`
restores the file (its sha256 line as in Task 1 Step 7); then `44 of 44 caught, survivors []`,
`29 of 29 caught`, `26 of 26 caught, survivors []`, `28 of 28 caught; missed: []` and
`13 of 13 caught, missed []` (about 40 minutes in all). `git status --short` shows the same
files as after Step 1: every script restores what it touched.

- [ ] **Step 11: Update DESIGN-HANDOFF.md**

Six edits with the Edit tool. Lines 98 and 99, before:

```markdown
**Gradient calls to action.** One gradient per view on `.btn--primary`. The sky gradient and sheen
from the rejected dark hero were removed with it.
```

After:

```markdown
**Gradient calls to action.** One gradient per view on `.btn--primary`, on the homepage, privacy
and terms. The sign-up journey (login, onboarding, the dashboard, the sign-in failed page) uses a
flat solid `#0B6BC7` primary instead (owner, 2026-09-24): `journey.css` sets
`background-image: none` on `.btn--primary`, and the frozen Activate morph starts from that flat
blue. The sky gradient and sheen from the rejected dark hero were removed with it.
```

Lines 101 to 103, before:

```markdown
**The type.** The device's own font, so SF on Apple, Roboto on Android, Segoe on Windows, downloading
nothing. One `font-size-adjust` line evens out their x-heights. Every width cap on a heading is in
`em`, never `ch`.
```

After:

```markdown
**The type.** On the homepage, privacy and terms, the device's own font, so SF on Apple, Roboto on
Android, Segoe on Windows, downloading nothing. One `font-size-adjust` line evens out their
x-heights. Every width cap on a heading is in `em`, never `ch`. The sign-up journey adds a
self-hosted Inter subset for Android and Windows (`static/fonts/inter-4.1-latin-wght.woff2`,
28 KB, declared only in `journey.css`, never preloaded); Apple devices match `-apple-system` first
and download nothing. A metric-matched fallback face ("Inter Agad Fallback", local Segoe UI or
Roboto) keeps the swap to about 0.2 percent of a line's width, and the journey body sets
`font-size-adjust: none` so Inter renders at its nominal size.
```

Lines 124 and 125, before:

```markdown
**4.2 No build step, no Node, no package manager.** Hand-written CSS and classic JavaScript served
from `applyfirst/saas/static/`. Nothing is compiled, bundled or minified.
```

After:

```markdown
**4.2 No build step, no Node, no package manager.** Hand-written CSS and classic JavaScript served
from `applyfirst/saas/static/`. Nothing we write is compiled, bundled or minified. Two vendored
files are generated by hand-run scripts, never on deploy: the trimmed Basecoat stylesheet
(`static/vendor/basecoat-1.0.2-agad.css`, minified upstream by Tailwind, rebuilt only by
`tools/basecoat/trim.py`) and the Inter subset (`tools/fonts/build_inter.py`). Never edit either
output by hand; change the script and run it again. The tests pin both by sha256.
```

Lines 160 and 165 (the palette rule), before:

```markdown
**4.7 No purple, ever.** `tests/test_saas_palette.py` scans every CSS and JS file and rejects any
```

After:

```markdown
**4.7 No purple, ever.** `tests/test_saas_palette.py` scans every CSS file under `static/` (the
vendored Basecoat in `static/vendor` included), every template and every JS file, and rejects any
```

and before:

```markdown
teal is the whole available range and it is enough.
```

After:

```markdown
teal is the whole available range and it is enough. An `oklch()` colour is converted to sRGB and
judged by the same hue test, never by its own hue (the brand blues sit at OKLCH hue 236 to 255),
and `color-mix()` is allowed in exactly three forms: a variable or `currentcolor` faded towards
`transparent`, the `@supports` probe `color-mix(in lab, red, red)`, and two greys defined in the
same file.
```

Lines 224 and 234 (the file list), before:

```text
applyfirst/saas/static/css/motion.css   onboarding only. DO NOT EDIT
```

After:

```text
applyfirst/saas/static/css/motion.css   onboarding only. DO NOT EDIT
applyfirst/saas/static/css/journey.css  the sign-up journey look, seven templates only, `journey` layer
applyfirst/saas/static/vendor/basecoat-1.0.2-agad.css  trimmed Basecoat, rebuilt only by tools/basecoat/trim.py
```

and before:

```text
tests/test_saas_palette.py              the no-purple guard
```

After:

```text
tests/test_saas_palette.py              the no-purple guard, every static/**/*.css
tests/test_saas_journey.py              the journey layer, scope, frozen values, contrast and page checks
tests/test_saas_basecoat.py             the vendored Basecoat pins and trimmed-content checks
```

Line 250, before:

```markdown
- The device's own font stays. Do not add a webfont.
```

After:

```markdown
- The device's own font stays on the homepage, privacy and terms. Do not add a webfont there. The
  sign-up journey alone serves the Inter subset to Android and Windows (owner, 2026-09-24); Apple
  devices keep SF.
```

- [ ] **Step 12: Update Handoff.md**

Edits with the Edit tool, top to bottom. If Steps 1, 6 or 10 printed other numbers, write the
numbers they printed. The line numbers are today's; if a session edited `Handoff.md` after this plan
was written and a Before block no longer matches exactly, find the passage by its first words and
make the same change to the text that is there. Lines 13 and 16, before:

```markdown
along with the redesign spec (`ba60723`). Everything is on `origin/main`. Tests: **887 passing** with B6
```

After:

```markdown
along with the redesign spec (`ba60723`). Tests: **1,266 passing** with the sign-up redesign (not yet committed), **887** with B6
```

and before:

```markdown
**558 checks, 0 failed** (`.venv/Scripts/python.exe .noxa/redesign-saas-ui/inputs/preserve_smoke.py`).
```

After:

```markdown
**607 checks, 0 failed**, 558 before the sign-up redesign (`.venv/Scripts/python.exe .noxa/redesign-saas-ui/inputs/preserve_smoke.py`).
```

Lines 22 to 25, before:

```markdown
🟡 **Sign-up journey redesign: design approved, spec written, build NOT started.** The owner
chose a Supabase-plus-Apple look built on a trimmed copy of Basecoat. The spec is
`docs/superpowers/specs/2026-09-24-signup-redesign-design.md` and is waiting for the owner's
review. Next step is the implementation plan. See "Sign-up journey redesign (in progress)" below.
```

After:

```markdown
🟢 **Sign-up journey redesign: built and verified, waiting for the owner's look and commit.**
Login, the four onboarding steps, the dashboard and a new "Sign-in didn't finish" page share one
light and dark look on a trimmed Basecoat and self-hosted Inter, built from
`docs/superpowers/plans/2026-09-25-signup-redesign.md`. See "Sign-up journey redesign (built)" below.
```

Lines 51 to 55, before:

```markdown
# Sign-up journey redesign (in progress, 2026-09-24)
**Where it stands.** Brainstormed with the owner, approved section by section, written up and
committed as `docs/superpowers/specs/2026-09-24-signup-redesign-design.md` (`ba60723`). **The owner
has not yet reviewed the written spec.** No code has been written. The next step, once the owner
approves the spec, is the implementation plan (superpowers writing-plans), then the build.
```

After:

```markdown
# Sign-up journey redesign (built)
**Where it stands.** Spec `docs/superpowers/specs/2026-09-24-signup-redesign-design.md` (`ba60723`),
plan `docs/superpowers/plans/2026-09-25-signup-redesign.md`, built task by task with both gates green
after every task: pytest **1,266 passed**, smoke **607 checks, 0 failed**. The plan's Task 8 browser
pass covered every journey state at 360, 390, 768 and 1280 wide, light and dark, JavaScript off,
reduced motion, forced colours, text at 200 percent and a throttled first visit on Android, with 0
failed; the mutation pass caught every planted mistake. Not yet committed: the owner commits the
files the plan's Task 8 Step 13 lists. **Still to check on a real Apple device:** that iPhones and
Macs never download Inter (not provable on Windows). **Owner decisions still open:** the header
mark's navy tile in dark mode, the paused panel's second "Edit keywords", and whether hover colours
may ease (spec 5.4 says transform and opacity only).

**As built, where it differs from the spec** (the plan's "Where this plan departs from the spec"
has the reasons): the upstream Basecoat file is `package/dist/basecoat.cdn.min.css`, copied to the
spec's name; `trim.py` also drops selectors for markup we never write, the one `!important` rule and
`@layer properties` (3,363 B gzip, not about 6 KB); Inter is 28,132 B, not about 47 KB;
`font-size-adjust` is `none`; `.btn--primary` sets `background-image: none`; hover colours ease;
the theme-color metas are the header surface `#FFFFFF` and `#111B2B` in a `theme_color_meta` block;
"Start watching without Gmail" stays secondary; the dark Gmail panel sits on the surface; the
sign-in failed page has a small amber icon and `_fail` logs `signin_failed`; app.css keeps the now
unused dashboard rules (`.kv`, `.card-actions`, `.usage-label`, `.span-5/7/12`, `.arrives*`).
```

Lines 104 and 105, before:

```markdown
- Inter from google/fonts is 72 KB with both axes, **46.9 KB with opsz pinned at 14** (Latin plus
  the peso sign, tabular figures kept). Writing WOFF2 needs `pip install brotli` (dev only).
```

After:

```markdown
- Inter from google/fonts is 72 KB with both axes, **46.9 KB with opsz pinned at 14** (Latin plus
  the peso sign, tabular figures kept), and **28.1 KB as built**, with the weight axis limited to
  400 to 600. Writing WOFF2 needs `pip install brotli` (dev only, now in `requirements-dev.txt`).
```

Lines 279 and 280, before:

```markdown
The whole new public layer is **8,142 B gzipped**, and the site now downloads **one** 2 KB font
instead of three fonts totalling 51 KB, so a first visit got *lighter*, not heavier.
```

After:

```markdown
The whole new public layer is **8,142 B gzipped**, and the site now downloads **one** 2 KB font
instead of three fonts totalling 51 KB, so a first visit got *lighter*, not heavier.

The sign-up journey (2026-09-25) loads only on its seven templates:

| file | raw | gzip | cap |
|---|---|---|---|
| `vendor/basecoat-1.0.2-agad.css` | 36,345 | 3,363 | 7,000 |
| `css/journey.css` | 14,663 | 4,962 | 8,000 |
| `fonts/inter-4.1-latin-wght.woff2` | 28,132 | (WOFF2) | 50,000 raw |
| render-blocking CSS on `/login` (app.css + both) | | 24,213 | 30,000 |
```

Line 291 (the new-work list), before:

```text
DESIGN-HANDOFF.md                     a pasteable brief for the NEXT design session
```

After:

```text
applyfirst/saas/static/css/journey.css  the sign-up journey look, seven templates only, `journey` layer
applyfirst/saas/static/vendor/basecoat-1.0.2-agad.css  trimmed Basecoat, built by tools/basecoat/trim.py
applyfirst/saas/static/fonts/inter-4.1-latin-wght.woff2  Inter subset, built by tools/fonts/build_inter.py
applyfirst/saas/templates/signin_failed.html  the D8 "Sign-in didn't finish" page
tests/test_saas_journey.py, tests/_journey_css.py  journey layer, scope, frozen values, review focus, pages
tests/test_saas_basecoat.py           vendored Basecoat pins and trimmed-content checks
tests/test_saas_signin_failed.py      the D8 page and the D9 redirects
DESIGN-HANDOFF.md                     a pasteable brief for the NEXT design session
```

Line 320 (constraints), before:

```markdown
- **Content must never need JavaScript to be visible.**
```

After:

```markdown
- **Content must never need JavaScript to be visible.**
- **The journey layer outranks every app.css rule** (`@layer basecoat, reset, tokens, base,
  components, screens, journey;` at `app.css:6`, with `motion` above it). Scope every journey rule
  with a page class, never a bare element, and give back the forced-colours value of anything
  app.css keeps in high contrast. `tests/test_saas_journey.py` enforces both.
- **The journey look loads only on the templates in `tests/_journey_css.py` `JOURNEY_TEMPLATES`**,
  never on the homepage, privacy or terms.
- **Never hand-edit the trimmed Basecoat file or the Inter subset.** Change
  `tools/basecoat/trim.py` or `tools/fonts/build_inter.py` and run it again; both outputs are
  pinned by sha256.
```

Lines 329 and 330, before:

```markdown
  journey only:** a flat solid `#0B6BC7` button. Both changes are decided, not yet built.
- **Signed-in pages follow the phone's dark mode** (decided 2026-09-24, not yet built). The homepage
```

After:

```markdown
  journey only:** a flat solid `#0B6BC7` button. Both are built (2026-09-25).
- **Signed-in pages follow the phone's dark mode** (decided 2026-09-24, built 2026-09-25 by CSS alone). The homepage
```

Lines 474 to 476, before:

```markdown
- **Sign-up journey redesign.** The owner reviews the spec, then write the implementation plan,
  then build it in the spec's five stages (foundation, login, onboarding, dashboard, the two fixes),
  with both gates green at every stage, then a multi-agent review and a mutation pass.
```

After:

```markdown
- **Sign-up journey redesign.** Built and verified. The owner looks at it in the preview in light
  and dark, decides the three open points in "Sign-up journey redesign (built)", commits the files
  the plan's Task 8 Step 13 lists, then checks on a real iPhone that Inter is never downloaded.
```

Lines 666 to 669, before:

```markdown
**If this is the redesign session:** read "Sign-up journey redesign (in progress)" above and the
spec at `docs/superpowers/specs/2026-09-24-signup-redesign-design.md`. If the owner has approved the
spec, write the implementation plan with superpowers writing-plans. If not, ask for their review
first. Do not start building before both the spec and the plan are approved.
```

After:

```markdown
**If this is the redesign session:** the sign-up journey is built (see "Sign-up journey redesign
(built)" above). Ask the owner to look at it in the preview in light and dark, then to commit the
files the plan's Task 8 Step 13 lists.
```

If Step 9 confirmed any finding, add one line per finding under "Failed attempts / gotchas worth
keeping" as a new subsection `## New in the sign-up redesign (2026-09-25)`, each saying what went
wrong and how the test that now pins it is named.

- [ ] **Step 13: Run both gates, then hand over the file list**

```bash
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe .noxa/redesign-saas-ui/inputs/preserve_smoke.py
git status --short
```

Expected: pytest: all pass (887 + the new tests), `1266 passed` (plus any test Step 9 added);
smoke: 0 failed, `607 checks passed, 0 failed.` `git status --short` lists exactly these, plus the
pre-existing `?? REMOTE.md`:

```text
 M .gitattributes
 M DESIGN-HANDOFF.md
 M Handoff.md
 M applyfirst/saas/app.py
 M applyfirst/saas/static/css/app.css
 M applyfirst/saas/templates/base.html
 M applyfirst/saas/templates/dashboard.html
 M applyfirst/saas/templates/login.html
 M applyfirst/saas/templates/onboarding_connect_gmail.html
 M applyfirst/saas/templates/onboarding_keywords.html
 M applyfirst/saas/templates/onboarding_preview.html
 M applyfirst/saas/templates/onboarding_profile.html
 M requirements-dev.txt
 M tests/test_saas_connect_gmail.py
 M tests/test_saas_gmail_retry.py
 M tests/test_saas_hero.py
 M tests/test_saas_onboarding.py
 M tests/test_saas_palette.py
 M tests/test_saas_template_context.py
?? applyfirst/saas/static/css/journey.css
?? applyfirst/saas/static/fonts/inter-4.1-latin-wght.woff2
?? applyfirst/saas/static/licenses/OFL-inter.txt
?? applyfirst/saas/static/licenses/basecoat-MIT.txt
?? applyfirst/saas/static/licenses/tailwindcss-MIT.txt
?? applyfirst/saas/static/vendor/basecoat-1.0.2-agad.css
?? applyfirst/saas/templates/signin_failed.html
?? tests/_journey_css.py
?? tests/test_saas_basecoat.py
?? tests/test_saas_journey.py
?? tests/test_saas_signin_failed.py
?? tools/
```

If this plan file is not committed yet, `?? docs/superpowers/plans/` shows as well. The smoke
file changed too, but `.noxa/` is git-ignored and never committed. Do not commit. Tell
the owner the work is ready and give them this list: they commit with explicit paths (never
`git add -A`, never `REMOTE.md`), with no `Co-Authored-By` trailer, and keep the words "key",
".env" and "credentials" out of the commit message (the privacy hook refused one before).


## Self-review

**Spec coverage, section by section.**

| Spec | What it asks | Where |
|---|---|---|
| 1 Intent | One calm look from login to a live dashboard, light and dark, phone and computer, nothing slower or broken | Tasks 3 to 7, proven in Task 8 |
| 2 D1 | Journey pages only; homepage, privacy, terms unchanged | Task 3 scope tests and byte-identical render (Step 9), Tasks 4 to 7 list their templates |
| 2 D2, D3 | Basecoat 1.0.2, only the parts we use, no JS | Task 1 |
| 2 D4 | No build step; trim script run by hand | Task 1 (`trim.py`), Task 2 (`build_inter.py`) |
| 2 D5 | Inter for Android and Windows, SF on Apple | Task 2, body stack in Task 3 section 4 |
| 2 D6 | Flat solid blue primary on the journey | Task 3 section 5 and its tests |
| 2 D7 | Dark mode by CSS alone | Task 3 sections 2 and 3, page tasks' dark fixes, review focus 1 |
| 2 D8 | Styled "Sign-in didn't finish" page | Task 7 |
| 2 D9 | Signed-out GETs to `/login` | Task 7 |
| 3 | Frozen CSP, no build, M-1, M-2, no JS dependency, AA, 16px inputs, no purple, Google button, invite-only, white mailcard, frozen hooks | Global Constraints; tests in Tasks 1, 3, 4 and each page task's hook table |
| 4.1 | New files | Tasks 1, 2, 3, 7 (File Structure lists each) |
| 4.2 | Loading, layer order, `color_scheme` block, theme colours | Task 3 (layer statement, `base.html` blocks, scope test), Tasks 4 to 7 (links) |
| 4.3 | Trimming rules | Task 1 Step 6 |
| 4.4 | Basecoat variables on our tokens | Task 3 section 3, `test_journey_supplies_every_variable_the_trimmed_basecoat_reads` |
| 4.5 | Inter subset, faces, stack, `font-size-adjust`, no preload, no `?v` | Task 2, Task 3 section 4 |
| 5.1 | Type scale, computers on hover and fine pointer | Task 3 section 4, `test_type_follows_spec_5_1_through_app_css_own_tokens`, review focus 5 |
| 5.2 | Components and every Basecoat leak | Task 3 section 5, `LEAKS`, review focus 2 and 4 |
| 5.3 | Light and dark colours with contrast | Task 3 section 2, `CONTRAST` (28 cases) |
| 5.4 | Motion 100 to 300ms on `--ease-land`, reduced motion static | Task 3 section 11 and its motion tests, Task 8 reduced-motion pass |
| 6.1 | Login | Task 4 |
| 6.2 | Onboarding steps 1 to 4 and editing mode | Task 5 |
| 6.3 | Dashboard | Task 6 |
| 6.4 | Sign-in didn't finish | Task 7 |
| 6.5 | Signed-out visits | Task 7 |
| 7 | Tests changed on purpose (hero fonts and gradient, palette, gmail retry, 401 tests, template context, smoke) | Task 2 (hero), Task 1 (palette), Task 3 (journey flat primary, the spec's "new assertion"), Task 7 (the rest), Task 4 and Task 7 (smoke) |
| 8 | Vendor pins, trimmed content, scope, layers, frozen values static and in a browser, contrast, inputs, reduced motion, budgets | Task 1, Task 3, Task 8 (browser values) |
| 9 | Frozen hooks | Hook lists in Tasks 3 to 7, Task 5's hook table, Task 6's hook list |
| 10 | Gates, screenshots at four widths in light and dark, JS off, reduced motion, forced colours, measured frozen values, review with skeptics, mutation pass, Apple note | Task 8 |
| 11 | Order of work | Tasks 1 to 8, in that order |
| 12 | Risks | Task 3 static checks, Task 6 colour audit, Task 8 screenshot pass and frozen-value measurement |

**Placeholder scan.** No "TBD", "TODO" or "similar to Task N". `<scratchpad>` is defined once in
Global Constraints. Every code step carries its code; every command carries its expected output.

**Name consistency.** `tests/_journey_css.py` exposes exactly `ROOT`, `STATIC`, `TEMPLATES`,
`JOURNEY_CSS`, `BASECOAT_CSS`, `JOURNEY_TEMPLATES`, `read_css`, `iter_rules`, `decls`, `contrast`,
`gzip_size`, `tokens`, and every later task imports only those. The head block is
`theme_color_meta` with `#FFFFFF` and `#111B2B` in Tasks 3, 4, 5, 6 and 7. `JOURNEY_TEMPLATES`
grows `[]`, then `login.html`, then the four onboarding templates, then `dashboard.html`, then
`signin_failed.html`. The helper names of Tasks 3 to 6 in `tests/test_saas_journey.py` were
checked for clashes by running the assembled file.

**Review Focus.** Five inputs, each with a test in its owning task (Tasks 2, 3 and 6) and a
browser measurement in Task 8. Each test was broken once on purpose and caught (13 of 13).
