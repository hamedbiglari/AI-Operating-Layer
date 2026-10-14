#!/usr/bin/env node
/*
 * Static conformance checks for the UX layer. Runs with no browser and no
 * network, so it works in the same environment that blocks `measure.js`.
 *
 * IMPORTANT — what this does and does not prove.
 *
 * These are SOURCE checks. They prove that the markup and stylesheets obey
 * the rules the checkpoint states: no emoji as icons, no icon name outside
 * the canonical registry, no icon-only control without an accessible name,
 * no hard-coded colour outside tokens.css, no font size below the 12px
 * floor, no table cell that loses its header when the table reflows.
 *
 * They do NOT prove anything about RENDERING: contrast ratios as painted,
 * reflow at a given width, absence of overflow, focus-ring visibility, or
 * bidi behaviour with a real font. Those need a browser. Passing this file
 * is NOT the §95 visual gate and must never be reported as if it were.
 *
 * Usage:  node visual-harness/check.js
 * Exit:   0 all checks pass, 1 otherwise.
 */

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');

const failures = [];
const passes = [];
function check(name, ok, detail) {
  (ok ? passes : failures).push(detail ? `${name} — ${detail}` : name);
}

const registry = JSON.parse(read('frontend/icons/icon-paths.json'));
const tokens = read('frontend/design-system/tokens.css');
const components = read('frontend/design-system/components.css');
const harness = read('visual-harness/index.html');

/* 1. Icon registry integrity ------------------------------------------- */
{
  const names = Object.keys(registry.icons);
  const dupes = names.filter((n, i) => names.indexOf(n) !== i);
  check('icon registry has unique names', dupes.length === 0, dupes.join(', '));

  const missingD = names.filter((n) => !registry.icons[n].d);
  check('every icon has a path', missingD.length === 0, missingD.join(', '));

  const missingCat = names.filter((n) => !registry.icons[n].category);
  check('every icon is categorised', missingCat.length === 0, missingCat.join(', '));

  // §57: one geometry, one stroke width, for everything.
  check('one canonical geometry declared',
    registry.geometry.viewBox === '0 0 24 24' && typeof registry.geometry.strokeWidth === 'number');
}

/* 2. No emoji, no raster, no stray inline SVG -------------------------- */
{
  const emoji = /[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{FE0F}]/u;
  const uiSymbols = /[\u25A0-\u25FF\u2190-\u21FF\u2713\u2717\u2714\u2718]/;
  check('harness uses no emoji', !emoji.test(harness));
  check('harness uses no Unicode box/arrow/tick glyphs as icons', !uiSymbols.test(harness));
  check('harness references no raster image', !/<img\s/i.test(harness));

  // Every <svg> in the harness must carry the canonical class. A bare svg
  // means someone inlined markup instead of using the registry (§56).
  const svgs = harness.match(/<svg[^>]*>/g) || [];
  // "icon" is the canonical single-colour component; "brand-mark" is the
  // one deliberate, documented exception (the Google "G" on the login
  // screen) — third-party brand marks are conventionally exempt from an
  // app's own theming system because the brand owner's guidelines fix
  // the colours, not this design system.
  // "data-viz" (added in the final dashboard audit) is the second documented
  // exception: a chart or map is a drawn data visualisation with role="img"
  // and its own accessible name, not an icon — the icon registry cannot and
  // should not contain it.
  const offenders = svgs.filter((s) => !/class="(icon|brand-mark|data-viz)/.test(s));
  check('no inline SVG outside the icon component', offenders.length === 0,
    `${offenders.length} stray <svg>`);
}

/* 3. Accessibility contracts ------------------------------------------- */
{
  const svgs = harness.match(/<svg[^>]*>/g) || [];
  const unmarked = svgs.filter((s) => !/aria-hidden="true"/.test(s) && !/role="img"/.test(s));
  check('every icon is either hidden or labelled', unmarked.length === 0,
    `${unmarked.length} unmarked`);

  const iconButtons = harness.match(/<button[^>]*class="icon-button"[^>]*>/g) || [];
  const unlabelled = iconButtons.filter((b) => !/aria-label="[^"]+"/.test(b));
  check('every icon-only button has an accessible name', unlabelled.length === 0,
    `${unlabelled.length} unlabelled`);
  check('icon-only buttons exist to test', iconButtons.length > 0, `${iconButtons.length} found`);

  check('focus ring is never removed',
    !/outline\s*:\s*(none|0)/.test(components + tokens));
  check('focus-visible styling is defined', /:focus-visible/.test(components));
  check('reduced motion is honoured', /prefers-reduced-motion/.test(tokens));
  check('forced-colors mode is handled', /forced-colors/.test(tokens));

  // "class=\"table\"" alone, or with any additional class tokens appended
  // (e.g. "table sortable") — matching on the "table" class token, not an
  // exact attribute string, so adding a legitimate new modifier class
  // doesn't silently zero out this count.
  const tables = (harness.match(/<table[^>]*class="[^"]*\btable\b[^"]*"/g) || []).length;
  const captions = (harness.match(/<caption/g) || []).length;
  check('data tables have a caption', tables > 0 && captions >= tables,
    `${captions} captions for ${tables} tables`);

  // §84: a cell that loses its header in the stacked mobile layout is a
  // cell whose meaning is gone.
  const bodyCells = harness.match(/<td(?![^>]*data-label)[^>]*>/g) || [];
  check('every table cell carries data-label for the stacked layout',
    bodyCells.length === 0, `${bodyCells.length} cells without data-label`);
}

/* 4. Token discipline --------------------------------------------------- */
{
  // Hex colours may appear ONLY in tokens.css. Anywhere else is a hard-coded
  // colour, which §34 forbids.
  const hexInComponents = (components.match(/#[0-9a-fA-F]{3,8}\b/g) || []);
  check('components.css contains no hard-coded colour', hexInComponents.length === 0,
    hexInComponents.join(' '));

  // The harness body may not either — only its own chrome, which is marked.
  const harnessBody = harness.split('===== harness chrome').pop().split('</style>')[0];
  const styleBlock = harness.split('<style>')[1].split('</style>')[0];
  const inlineStyles = harness.replace(styleBlock, '')
    // Same brand-mark exception as the stray-<svg> check above: Google's
    // own fixed brand colours inside that one glyph aren't "a hard-coded
    // colour in this app's markup" in the sense this rule exists to
    // catch (a colour that should have been a design token but wasn't).
    .replace(/<svg[^>]*data-brand="[^"]*"[\s\S]*?<\/svg>/g, '');
  const hexInline = (inlineStyles.match(/#[0-9a-fA-F]{3,8}\b/g) || [])
    .filter((h) => !/^#[0-9a-f]{0,2}$/i.test(h));
  check('no hard-coded colour in harness markup', hexInline.length === 0, hexInline.join(' '));
  check('harness chrome is separated from the design system', harnessBody.length > 0);

  const semantic = ['--success', '--warning', '--danger', '--info', '--processing', '--archived', '--unknown'];
  const missing = semantic.filter((t) => !tokens.includes(t + ':'));
  check('every semantic status category from §34 has a token', missing.length === 0, missing.join(', '));

  check('dark theme is defined for every status token',
    semantic.every((t) => (tokens.match(new RegExp(t + '\\s*:', 'g')) || []).length >= 3));
}

/* 5. Typography floor and Persian support ------------------------------ */
{
  const px = [...(components + tokens).matchAll(/font-size:\s*([\d.]+)px/g)].map((m) => parseFloat(m[1]));
  const tooSmall = px.filter((v) => v < 12);
  check('no declared font-size below 12px', tooSmall.length === 0, tooSmall.join(', '));

  check('a real Persian face is first in the Persian stack', /--font-fa:\s*"Vazirmatn"/.test(tokens));
  check('Persian is selected by lang, not by dir', /\[lang="fa"\]/.test(tokens));
  check('identifiers are bidi-isolated', /unicode-bidi:\s*isolate/.test(tokens));
  check('harness isolates identifiers with <bdi>', /<bdi class="identifier"/.test(harness));
}

/* 6. Logical properties (RTL without a second stylesheet) --------------- */
{
  const physical = [...components.matchAll(/(?:^|[;{\s])(margin-left|margin-right|padding-left|padding-right|left|right)\s*:/g)]
    .map((m) => m[1]);
  check('components use logical properties, not physical sides',
    physical.length === 0, physical.join(', '));
  check('only registry-marked icons are mirrored in RTL',
    /\[dir="rtl"\]\s*\.icon--mirror/.test(components) &&
    !/\[dir="rtl"\]\s*\.icon\s*\{/.test(components));
}

/* 7. Honesty rules ------------------------------------------------------ */
{
  // §10: unknown must read "Not available", never 0.
  check('a distinct "not available" treatment exists', /\.not-available/.test(components));
  check('the harness actually uses it', /class="not-available"/.test(harness));
  // §16 / §59 / §92: no invented composite scores anywhere in the UI.
  const banned = /(Trust Score|Evidence score|UX score|Confidence:\s*\d+%)/i;
  check('no invented composite score in the UI', !banned.test(harness));
  // §42: no fabricated percentage on an unmeasured process.
  check('no fake progress percentage', !/aria-valuenow|width:\s*\d+%\s*"/.test(harness));
}

/* ---------------------------------------------------------------------- */

console.log('\nStatic UX conformance — source checks only, NOT the §95 visual gate.\n');
passes.forEach((p) => console.log('  PASS  ' + p));
if (failures.length) {
  console.log('');
  failures.forEach((f) => console.log('  FAIL  ' + f));
}
console.log(`\n${passes.length} passed, ${failures.length} failed.`);
console.log('Rendered verification (contrast, reflow, overflow, focus ring, bidi):');
console.log('  ENVIRONMENT BLOCKED unless `node visual-harness/measure.js` can launch a browser.\n');
process.exit(failures.length ? 1 : 0);
