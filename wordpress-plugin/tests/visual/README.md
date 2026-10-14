# Visual QA procedure (ENVIRONMENT BLOCKED in the build environment)

## Status

`ENVIRONMENT BLOCKED` — **not** "skipped", and not "passed".

Puppeteer 24 installs fine here, but its Chrome binary is fetched from
`storage.googleapis.com`, which is outside this environment's network
allow-list; the apt `chromium-browser` candidate is a snap package that
cannot run in this container either. So **no screenshot was taken and no
rendered measurement was made.** Nothing in the Phase 9 report claims
otherwise.

What this means concretely: the CSS below has been written against the
accessibility and responsive rules, and reviewed by reading, but the
following remain **unverified by rendering**:

- actual reflow at 375 / 768 / 1024 / 1440
- absence of horizontal overflow
- absence of clipped text
- computed contrast ratios
- visible focus ring rendering
- interactive target heights as rendered

## Reproducing it (2 minutes, any machine with network access)

```bash
cd wordpress-plugin/ai-operating-layer/tests/visual
npm init -y && npm install puppeteer
npx puppeteer browsers install chrome
node shoot.js            # writes out/admin-{375,768,1024,1440}.png + JSON metrics
```

`shoot.js` does not just screenshot. It measures, so the result is a
pass/fail rather than an opinion:

| Metric | Assertion |
|---|---|
| `overflow` | must be `0` at every width — no horizontal scrolling |
| `clipped` | must be `0` — no element whose content exceeds its box |
| `tiny` | must be `0` — no text under 12px |
| `minTarget` | must be `>= 40` — interactive controls stay comfortably tappable |
| `focus.outlineStyle` | must not be `none` — focus ring never removed |

`harness.html` reproduces the real admin markup (status cards, the error
state, the form with an inline field error, the mappings table with
synced/stale/failed rows, and the empty state) against a stylesheet copy of
`assets/css/admin.css` inside an approximation of the wp-admin shell.

## Still required after that

The harness verifies the **design system**. It does not verify WordPress
integration. A human still needs to check, in a real WordPress install:

1. keyboard-only traversal of settings → form → mappings table
2. screen-reader announcement of the `role="alert"` connection error
3. the meta box inside the block editor sidebar
4. admin colour schemes other than the default
5. RTL rendering (`.aiol-table` uses logical properties; unverified)
