# Sign-up journey redesign: design

Date: 2026-09-24. Status: approved in conversation, section by section, awaiting review of this
written spec. Owner decisions are marked **(owner)**. Everything else is a design choice that the
owner approved as part of a section.

## 1. Intent

Make the pages a new user touches when signing up feel premium, in the way Apple products and
Supabase's dashboard do: clean, minimal, easy to find your way around, small readable type on
computers, buttons that are easy to read. The pages in scope are the login page, the four
onboarding steps and the dashboard. **(owner)**

Success means a new user moving from login to a live dashboard sees one calm, consistent look in
light and dark mode, on a mid-range Android phone on mobile data and on a computer, with nothing
slower, nothing broken without JavaScript, and every existing behaviour test still true.

Out of scope for this spec: the homepage, the privacy and terms pages (they keep today's look),
any new feature, any new interactive component that needs JavaScript, and three.js or other 3D.

## 2. Decisions

| # | Decision | Source |
|---|---|---|
| D1 | Sign-up journey first (login, onboarding steps 1 to 4, dashboard). Homepage, privacy and terms unchanged | owner |
| D2 | Basecoat (basecoat-css 1.0.2, the shadcn/ui look as plain HTML) is the component kit | owner |
| D3 | Only the Basecoat parts we use are vendored: buttons, cards, fields, inputs, labels, textareas, alerts, badges. No reset, no menus, dialogs or popovers, no Basecoat JavaScript | owner |
| D4 | No build step. A trimming script runs only when Basecoat is upgraded, like the font subsetting | owner |
| D5 | Inter, self-hosted, for Android and Windows. Apple devices keep SF and download nothing. Reverses the "device font" lock (DESIGN-HANDOFF.md 6) for the journey pages only | owner |
| D6 | Flat solid blue primary button on the journey pages. The homepage keeps its gradient | owner |
| D7 | Dark mode follows the phone's setting, by CSS alone | owner |
| D8 | A styled "sign-in didn't finish" page replaces the bare JSON error on `/auth/callback` failures | owner |
| D9 | A signed-out visitor who opens an onboarding page is redirected to `/login` instead of a 401 JSON reply | owner |

## 3. Constraints that stay (each enforced today)

- The frozen CSP in `applyfirst/saas/app.py` is not touched. No inline script, no `style=` attribute,
  no `<style>` block, no CDN, no `blob:`.
- No Node, no package manager, no build step on deploy.
- `motion.css`, `vt.js` and `motion.js` are not edited. No new file name may contain `motion.css`,
  `vt.js`, `motion.js` or `canvas-confetti` (test M-2). Head order M-1 holds.
- Content never depends on JavaScript (rule 4.10). Reduced motion is fully static. WCAG AA for text
  (4.5 to 1), large text and control edges (3 to 1). Inputs never below 16px.
- No purple (hue 230 to 345 at 8 percent saturation or more), checked by `tests/test_saas_palette.py`.
- The Google button (`.gsi-btn`, 40px, `#747775` border, Google Sans Button) is not restyled.
- Invite-only copy and hidden pricing stay. The sample email preview stays bright white.
- Every hook the frozen motion files read keeps its exact name, structure and count. The full list is
  in section 9.

## 4. Architecture

### 4.1 Files

| File | Purpose |
|---|---|
| `tools/basecoat/basecoat-1.0.2.cdn.min.css` | Upstream source, byte for byte, sha256 pinned. Not served. `-text` in `.gitattributes` |
| `tools/basecoat/trim.py` | Rebuilds the trimmed vendor file from the upstream source (section 4.3). Run by hand on upgrade only |
| `applyfirst/saas/static/vendor/basecoat-1.0.2-agad.css` | The trimmed, served file. sha256 pinned, and a test re-runs `trim.py` and requires identical bytes |
| `applyfirst/saas/static/css/journey.css` | The sign-up look: Inter face, Basecoat variable mapping, light and dark tokens, components, page layouts |
| `applyfirst/saas/static/fonts/inter-4.1-latin-wght.woff2` | Inter subset (section 4.5), about 47 KB. The version in the name is the one the build script records from the source; if the source is another version, the name follows it and so do the tests |
| `tools/fonts/build_inter.py` | Reproduces the font subset with fontTools (needs `brotli`, dev only). Records the source URL and sha256 |
| `applyfirst/saas/static/licenses/basecoat-MIT.txt`, `tailwindcss-MIT.txt`, `OFL-inter.txt` | Licences for everything vendored |
| `applyfirst/saas/templates/signin_failed.html` | The new page for D8 |

### 4.2 Loading and cascade

- Only these templates load the new look, from their existing `{% block page_css %}` (after
  `motion_head`, so M-1 holds): `login.html`, `onboarding_connect_gmail.html`,
  `onboarding_profile.html`, `onboarding_keywords.html`, `onboarding_preview.html`,
  `dashboard.html`, and the new `signin_failed.html`. Each links, in this order, the trimmed
  Basecoat file and `journey.css`, both through `static_url()` so both get the `?v=` hash and the
  one-year cache. There is no `@import`, so there is no second wait before first paint.
- The layer order statement at `app.css:6` becomes
  `@layer basecoat, reset, tokens, base, components, screens, journey;`. The first appearance
  sets the order, so Basecoat is the lowest layer everywhere, and `journey` sits below `motion`,
  which `motion.css:2` adds after it. The homepage never loads either file, so declaring the two
  names there changes nothing it renders.
- The trimmed Basecoat file wraps everything it contains in `@layer basecoat { ... }` (the trimmer
  writes the wrapper). `journey.css` wraps everything in `@layer journey { ... }`, except its
  `@font-face` rules, which layers do not affect. A test forbids any other unlayered rule in
  either file.
- Result: any rule we write beats Basecoat, and nothing in `journey.css` can outrank the frozen
  `motion` layer.
- `base.html` gains a `{% block color_scheme %}light{% endblock %}` for the `color-scheme` meta and
  keeps `theme_color`. Journey templates set `light dark` and emit a light and a dark
  `theme-color` meta with `media` queries. The homepage output is unchanged.

### 4.3 Trimming rules (`tools/basecoat/trim.py`)

Input is the upstream minified file. The script parses top-level statements with a brace-matching
tokenizer that respects strings, and writes one output file:

1. Keeps the Tailwind licence comment and adds a header naming the upstream file, its sha256, the
   script and the date.
2. Drops `@layer base` entirely (the Tailwind preflight reset), `@layer utilities`, the unlayered
   `:root` and `.dark` colour blocks (all the `oklch()` values), and the `pulse` and `toast-up`
   keyframes.
3. From `@layer theme`, keeps only the size, radius, spacing, text-size, weight and leading
   variables the kept rules read. Drops `--font-*` and every `--ease-*` (they collide with
   `app.css --font-sans` and the frozen `--ease-out`) and every colour.
4. From `@layer components`, keeps a rule only when every selector in its list names at least one
   allowed class (`btn`, `card`, `card-title`, `card-description`, `card-action`, `field`, `input`,
   `label`, `textarea`, `alert`, `badge`) and no other component class, and is not a bare element
   selector (for example the global `details` rules). Everything else is dropped (dialogs, menus,
   combobox, select, tabs, toast, sidebar, table, avatar, empty, item, progress and the rest).
5. Rewrites every dark variant (`:is(html.dark *)` and `.dark` forms) into the same rule inside
   `@media (prefers-color-scheme: dark)`, so dark mode needs no class and no script.
6. Keeps only the `@property` registrations whose `--tw-*` name a kept rule reads.
7. Wraps the result in `@layer basecoat { ... }` and writes it with LF line endings.

Expected size is about 6 KB gzip. It must stay under the cap in section 8.

### 4.4 Basecoat variables mapped onto our tokens

`journey.css` defines Basecoat's variables in hex, in the `journey` layer, so they beat
Basecoat's own theme: `--background`, `--foreground`, `--card`, `--card-foreground`,
`--primary` (`#0B6BC7`), `--primary-foreground` (`#FFFFFF`), `--secondary`, `--muted`,
`--muted-foreground`, `--border`, `--input`, `--ring`, `--destructive`, and `--radius`. The Tailwind
aliases the kept rules read (`--color-*`) point at them. Colour values are in section 5.3.

### 4.5 Inter

- Source is google/fonts `ofl/inter` (variable, axes opsz and wght). The build script pins opsz at
  14 with the fontTools instancer, limits wght to 400 to 600, keeps Basic Latin, Latin-1, general
  punctuation and U+20B1 (peso), keeps the `tnum` feature, and writes WOFF2. About 47 KB.
- `@font-face` in `journey.css`: family `"Inter Agad"`, `font-display: swap`, a `unicode-range`
  matching the subset. A second face, `"Inter Agad Fallback"`, uses `local()` Roboto and Segoe UI
  with `size-adjust`, `ascent-override`, `descent-override` and `line-gap-override` tuned by
  measurement so the swap barely moves text. Chrome, Edge, Samsung Internet and Firefox support
  these overrides. Safari never loads Inter.
- Journey font stack: `-apple-system, BlinkMacSystemFont, "Inter Agad", "Inter Agad Fallback",
  system-ui, "Segoe UI", Roboto, sans-serif`. Apple devices match the first two and never request
  the file. Inter is never preloaded.
- `font-size-adjust` on the journey body is retuned so Inter renders at its nominal size (today's
  `.52` would shrink it about 4.8 percent). The exact value is set by measurement.
- The file is referenced by `url()` without `?v`, so the file name carries the version and a new
  version gets a new name.

## 5. The look

### 5.1 Type

| Role | Phones | Computers | Weight |
|---|---|---|---|
| Page title (h1) | 28px | 30px | 600, tracking about -0.02em |
| Section title (h2) | 20px | 20px | 600 |
| Row and card title (h3) | 17px | 16px | 600 |
| Body | 16px, line height 1.5 | 15px, line height 1.5 | 400 |
| Small notes | 15px | 14px | 400 |
| Labels and captions | 12px | 12px | 500 |
| Inputs | 16px | 16px | 400 |

"Computers" means `(hover: hover) and (pointer: fine)`, never width alone, so a phone held
sideways keeps phone sizes. Numbers use tabular figures where they line up (usage, times).

### 5.2 Components

- **Primary button** (`.btn.btn--primary`): background `#0B6BC7`, no background image, white text
  at weight 500, 12px corners, height 44px on phones and 40px on computers. Hover `#0A5AA8`.
  Pressed scales to 0.97 over 200ms with transform only, no translate. Disabled and busy stay
  `#0B6BC7` at opacity 1 with 12px corners, winning over hover. This is the value the frozen
  Activate morph starts from.
- **Secondary button** (`.btn--secondary`): surface background, 1px control edge (section 5.3),
  navy text, same sizes. **Danger** keeps today's red on a surface.
- **Quiet actions** (Edit, Skip for now): text links in the link colour, 44px tap area on phones
  through a `::after` extender on the link, never on `.btn--primary::after` (a test forbids that).
- **Focus**: our 3px blue outline with an offset on every control. Basecoat's shadow ring is
  switched off because it is about 1.5 to 1 and disappears in forced colours.
- **Fields**: label above at 12px weight 500, hint below at small size, input 16px with 8px corners,
  a 1px control edge, a 44px minimum height and `height: auto` so zoomed text never clips.
  The textarea keeps `field-sizing: fixed` and its `rows`. Invalid fields keep amber, never red.
- **Cards and groups**: surface background, 12px corners, a hairline edge, one faint shadow. No
  `overflow: hidden` on groups (it would clip focus rings). The first and last rows take the corners.
- **Grouped rows** (dashboard): label on the left, value or an Edit link on the right, hairline
  dividers between rows, group title above in the label style, group note below in small muted text.
- **Alerts**: today's tones (info, attention, success, danger) restyled flat with a hairline edge.
  The icon stays the alert's first child (frozen stamp). Basecoat's `.alert>svg` row span is
  overridden so no empty strip appears.
- **Badges**: `height: auto`, `overflow: visible`, so "Connected" never clips. No icon inside a badge.
- **Status panel**: 24px corners kept. The live panel stays navy `#0B2545`. In dark mode it gains a
  1px edge at white 12 percent, because navy sits close to the dark ground.
- **Header**: brand on the left, name and Log out on the right, hairline bottom, not sticky, no blur.
  Exactly one `.site-header`, same height on every signed-in page.
- **Footer** on journey pages: light and short. Keeps the Privacy and Terms links and the
  "not affiliated" line.

Basecoat leaks the layer order alone does not stop, each overridden explicitly in `journey.css`:
fixed `height: 36px` on `.btn` and inputs, `.btn svg` at 16px, `outline-style: none`, the
`translate` press, `transition-property: all`, `.btn:disabled { opacity: .5 }`, the focus
box-shadow on buttons and inputs, `.alert>svg` grid span, `.badge` height and overflow,
`field-sizing: content`, and 14px inputs from 768px.

### 5.3 Colour

Light (existing `app.css` tokens where they exist):

| Token | Value | Checked contrast |
|---|---|---|
| Ground | `#F3F6FA` | |
| Surface | `#FFFFFF` | |
| Text | `#0B2545` | 14.20 on ground, 15.39 on surface |
| Muted text | `#4E5E76` | 6.08 on ground, 6.59 on surface |
| Control edge | `#74859D` | 3.47 on ground, 3.76 on surface |
| Link and primary | `#0B6BC7` | 4.91 on ground, 5.33 on surface, white on it 5.33 |
| Hairline (decorative) | navy at about 10 percent, written as `rgba()` | not a control edge |
| Attention | text `#7A4400` on `#FFF6E6` | above 6.9 |
| Success | text `#11663A` on `#EAF7EF` | 6.38 |
| Danger text | `#B3261E` on surface | above 6.5 |

Dark (`@media (prefers-color-scheme: dark)`):

| Token | Value | Checked contrast |
|---|---|---|
| Ground | `#0A111C` | |
| Surface | `#111B2B` | |
| Text | `#E6EDF5` | 16.04 on ground, 14.64 on surface |
| Muted text | `#9DACC0` | 8.20 on ground, 7.48 on surface |
| Control edge | `#6A7B93` | 4.39 on ground, 4.00 on surface |
| Link | `#5CB8F0` | 8.62 on ground, 7.87 on surface |
| Primary button | `#0B6BC7` (frozen value) | white on it 5.33, edge 3.55 on ground, 3.24 on surface |
| Attention | text `#F5C66B` on `#2A2110` | 9.95 |
| Success | text `#6FD39A` on `#10281C` | 8.54 |
| Danger text | `#FF8A80` on surface | 7.57 |

All values sit between hue 4 and hue 217, well clear of the banned band. The sample email preview
(`.mailcard`) keeps its white inbox look in both modes. The Google button stays in its light theme,
which Google allows on dark backgrounds.

### 5.4 Motion

Durations 100 to 300ms on the existing `--ease-land` curve (`cubic-bezier(.16,1,.3,1)`, the same
curve Supabase uses). Transform and opacity only. Every new transition and animation sits under
`prefers-reduced-motion: no-preference`, and the reduced-motion reset also covers
`::details-content`. The frozen onboarding moments are untouched.

## 6. Pages

### 6.1 Login (`login.html`)

One centred card on the ground: `h1` "Sign in to Agad", one short lead, the in-app notice when it
applies, the Google button, the lock note, the invite-only alert, the caption, "What is Agad?". The
brand mark shows once, in the header. The strings "Continue with Google" and `href="/privacy"`
(from the footer) stay contiguous and present.

### 6.2 Onboarding

- Stepper: `nav.stepper > ol.stepper__list > li.stepper__item`, exactly one `.stepper__marker`, phone
  progress bars as each item's `::before`, the desktop rail from 960px. Only colours, sizes and type
  change.
- Step 1, Connect Gmail: headline, the from-to route (the `.gconf__track` stays 96px, the envelope
  node 28px), "What will Google ask me?" (`details.disclose`), one primary `a.btn` to
  `/auth/connect-gmail` with its label in a direct `span`, the quiet skip link to
  `/onboarding/profile`. The retry note stays above the `h1`.
- Step 2, Your details: one card with the four fields, labels above, hints below, the amber
  `#form-error` box at the top linking to fields. The `.gconf` block keeps its exact
  `class="gconf"` attribute and its `.badge--ok`.
- Step 3, Watch words: the add form first (field and Add in one row), saved words as `li.kw` chips
  with `.kw__text` and `data-vt-kw`, quick-add `button.quick` pills below, then Next. Nothing
  clips a chip (no `overflow: hidden` on `.kw`, `.chip-list` or any parent), and no new box-shadow
  on `.kw`.
- Step 4, Preview: sample post and white `.mailcard` side by side from 1100px, stacked below. The
  `form.activate` with one `.btn--primary` labelled "Start watching for jobs" (or "Start watching
  without Gmail").
- Editing mode: `.rail__edit` and the "Back to dashboard" link instead of the stepper, as today.

### 6.3 Dashboard

- Status panel on top, exactly one, chosen as today (Gmail, then no keywords, then daily limit,
  then live). Primary counts stay: one in the Gmail and no-keyword states, none when live.
- Below, one centred column of about 40rem holding three groups, each a direct child of
  `.dash__grid` so the reveal layer needs no change:
  - Watching: the keywords row (chips, Edit to `/onboarding/keywords`), and "Looking for" with
    Edit details to `/onboarding/profile`.
  - Gmail: the address with the Connected or Not connected badge (the group keeps class `sheet` and
    `data-arrive-gmail` when connected), the Disconnect Gmail row as the existing native `details`
    with its CSRF form and that exact label. When Gmail is connected but a reconnect failed, a
    secondary `a.btn` Connect Gmail stays in this group (it is the only place it shows then).
  - Today: "N / M" as one text node, the meter (class-based widths, no `style=`), the reset note as
    the group note, and "daily limit reached" exactly once, never inside the panel.
- "When an email arrives" becomes a plain help note after the groups.
- The duplicate secondary Connect Gmail and Add keywords buttons are removed. Edit links replace them.
- Keywords stay visible on the page in every state (the smoke needs it with Gmail off).

### 6.4 Sign-in didn't finish (D8)

`/auth/callback` failures render `signin_failed.html` with status 400 as `text/html`, the exact CSP,
the OAuth transaction cookie cleared, and one message for every failure reason (no oracle):
"Sign-in didn't finish", a short line ("You can try again, it only takes a moment."), the Google
button again, and a link back to the homepage. The reason stays in the server log only.

### 6.5 Signed-out visits (D9)

GET requests to `/onboarding`, `/onboarding/connect_gmail`, `/onboarding/profile`,
`/onboarding/keywords`, `/onboarding/preview`, `/auth/connect-gmail` and `/auth/gmail-callback` from
a visitor with no session get a 302 to `/login`, through a dedicated dependency, instead of the 401
JSON reply. POST routes keep today's replies. No `next=` parameter is added, because the onboarding
router already sends a signed-in user to the right step.

## 7. Tests changed on purpose

- `tests/test_saas_hero.py:260-275` (fonts): allow `inter-4.1-latin-wght.woff2` in `static/fonts`,
  require the Inter face and the journey stack in `journey.css` only, keep `app.css` on the system
  stack, and fail if any template preloads Inter.
- `tests/test_saas_hero.py:234-245` (gradient): unchanged for `app.css`. A new assertion requires
  the journey `.btn--primary` to have no background image.
- `tests/test_saas_palette.py`: scan `static/**/*.css`, not only `static/css`. Accept `oklch()` only
  with zero chroma, or after converting to sRGB and passing the existing hue test (never compare
  the OKLCH hue itself, because the brand blues sit at OKLCH hue 236 to 255). Accept `color-mix()`
  in exactly three forms: a variable or `currentcolor` with a percentage and `transparent`; the
  literal `color-mix(in lab, red, red)` inside `@supports`; two variables defined in the same file
  with zero chroma. Everything else still fails, and a planted purple in each form must fail.
- `tests/test_saas_gmail_retry.py:99-103` and any smoke check of the callback failure: expect the
  400 HTML page.
- Tests that pin 401 for signed-out GETs on the routes in 6.5 (for example
  `tests/test_saas_onboarding.py:32`, `tests/test_saas_connect_gmail.py:38`): expect 302 to `/login`.
- `tests/test_saas_template_context.py:78-97`: the rendered template set gains `signin_failed.html`.
- `.noxa/redesign-saas-ui/inputs/preserve_smoke.py`: add the Inter file and the two new CSS files to
  the required assets, and update the callback and signed-out expectations.

## 8. New checks

- Vendor pins: sha256 of the upstream source and of the trimmed file; re-running `trim.py` on the
  source reproduces the trimmed file byte for byte; `.gitattributes -text` covers both.
- Trimmed content: no preflight selectors (`*`, `html`, `body`, `a`, `h1` to `h6`, `img`, `details`
  as bare selectors), no `html.dark` or `.dark`, no dialog, menu, popover, select, tabs, toast,
  sidebar or table classes, no infinite animation, and at least one `prefers-color-scheme: dark`.
- Scope: the two new stylesheets load on exactly the seven journey templates and never on `/`,
  `/privacy` or `/terms`. No new file name contains a forbidden M-2 substring.
- Layers: `app.css:6` lists `basecoat` first and `journey` last. Both new files have no unlayered
  rules except `@font-face` and `@property`.
- Frozen values, statically: `journey.css` never sets `background-image`, `opacity` below 1 or a
  radius other than `var(--r-md)` on `.btn--primary` in any state, never touches `.status--live`
  colour or radius, `position` or `isolation` on `.status`, `box-shadow` or `overflow` on `.kw`,
  or `.btn::before`, and never defines `--ease-out`, `--ease-settle`, `--ease-exit` or `--ease-spring`.
- Frozen values, in a browser: the disabled and busy Activate button computes to `#0B6BC7`, 12px,
  opacity 1; the live panel computes to `#0B2545`, 24px.
- Contrast: computed from the real token values in `journey.css` for light and dark, at the ratios
  in section 5.3, the way `tests/test_saas_hero.py` does it today.
- Inputs: every input and textarea rule in `journey.css` resolves to at least 16px.
- Reduced motion: every `transition` and `animation` in `journey.css` sits under
  `prefers-reduced-motion: no-preference`.
- Budgets (gzip 9, LF): trimmed Basecoat at most 7,000 bytes, `journey.css` at most 8,000 bytes,
  render-blocking CSS on `/login` (`app.css` plus both new files, about 15,900 + 6,000 + up to
  8,000 today) at most 30,000 bytes, and the Inter file at most 50,000 raw bytes.

## 9. Frozen hooks (must keep name, structure and count)

`site-header` (one), `data-step` 0 to 4 on `html`, `nav.stepper > ol.stepper__list >
li.stepper__item` with one `span.stepper__marker` first in the current item, the 960px and 1100px
breakpoints, `form.activate[action="/onboarding/activate"]` with one `.btn--primary`,
`a.btn[href="/auth/connect-gmail"]` with a direct `span`, `li.kw[data-vt-kw]` with `.kw__text`,
`button.quick[data-vt-kw]` with the word in the last `span`, `class="gconf"` (exact),
`.gconf__line`, `.gconf__track` (96px), `.fromto__node` (28px), `.badge--ok`,
`.alert--success[data-arrive-gmail] > .icon`, `.mailcard`, `.mailcard__head`, `.letter__part`,
`.copy-row`, `.preview__link`, `details.disclose`, `.status--live` (navy, 24px, `position:
relative`, isolated, opaque), `.live i`, `.status__kw strong` siblings, `.since`, `data-panel`,
`data-fresh`, `data-burst-src`, `data-arrive-gmail` (one on step 2, two on the live dashboard),
`data-copy` with `#preview-letter`, `{% set CELEBRATE = true %}`, `#form-error`, `#gmail-retry`,
the hidden `csrf` input in every POST form, and `.dash__grid > *`.

## 10. Verification

- Both gates green with numbers: `.venv/Scripts/python.exe -m pytest -q` and
  `.venv/Scripts/python.exe .noxa/redesign-saas-ui/inputs/preserve_smoke.py`.
- Every journey state from `/__dev/` at 360, 390, 768 and 1280 wide (scrollbar hidden), in light and
  dark, plus JavaScript off, reduced motion and forced colours, with screenshots and measured values
  for the frozen button and panel.
- One multi-agent review with a skeptic per finding, then a mutation pass that breaks each new check.
- Not provable on Windows: that iPhones and Macs never download Inter. Marked for a check on a real
  Apple device.

## 11. Order of work

1. Foundation: `trim.py` and the trimmed file, the font and its script, `journey.css` tokens and
   components, the layer statement, the `color_scheme` block, licences, and the checks in sections
   7 and 8. No page loads the new look yet.
2. Login.
3. The four onboarding steps.
4. The dashboard.
5. D8 and D9.
6. Verification and review, then DESIGN-HANDOFF.md (font lock, gradient, "nothing is minified",
   "the palette test scans every CSS file") and Handoff.md.

Both gates stay green at the end of every stage.

## 12. Risks

- A Basecoat rule the explicit overrides miss changes a journey page. Mitigated by the trimming,
  the override list in 5.2 and the screenshot pass.
- A journey rule quietly changes a frozen moment mid-animation, which screenshots do not show.
  Mitigated by the `journey` layer sitting below `motion`, the static frozen-value checks and the
  browser measurement.
- Dark mode shows a frozen animation colour that was designed for light (the `.mailcard__head`
  tint animates from `#DCEFFB`). The mailcard stays white in both modes, so the tint still reads.
  Checked in the screenshot pass.
- A first visit on Android downloads 47 KB more. Mitigated by the size cap, no preload, the
  metric-matched fallback and the one-year cache on the CSS.
