#!/usr/bin/env node
/*
 * Builds visual-harness/index.html from the CANONICAL sources:
 *
 *   frontend/design-system/tokens.css
 *   frontend/design-system/components.css
 *   frontend/icons/icon-paths.json
 *
 * It inlines them rather than linking, so the output is one portable file
 * that renders from a `file://` URL with no server and no network. That
 * matters because this harness has to work with no server and no network,
 * which the plugin's own visual fixture
 * (wordpress-plugin/tests/visual/harness.html) already gets right by linking
 * `../../assets/css/admin.css` relative to its own file.
 *
 * Inlining from the real files is also the point: if a token is renamed the
 * harness changes with it, so the harness cannot drift into being a
 * flattering mock-up of a design system that does not exist.
 *
 * Usage:  node visual-harness/build.js
 */

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');

const tokens = read('frontend/design-system/tokens.css');
const components = read('frontend/design-system/components.css');
const registry = JSON.parse(read('frontend/icons/icon-paths.json'));

const GEO = registry.geometry;

/** Render an icon exactly as frontend/icons/icon.js does. */
function ic(name, opts = {}) {
  const def = registry.icons[name];
  if (!def) throw new Error(`Unknown icon "${name}"`);
  const size = opts.size || 'var(--icon-size)';
  const cls = ['icon'];
  if (def.mirror) cls.push('icon--mirror');
  if (opts.class) cls.push(opts.class);
  const a11y = opts.label
    ? `role="img" aria-label="${opts.label}"`
    : 'aria-hidden="true" focusable="false"';
  return `<svg class="${cls.join(' ')}" ${a11y} viewBox="${GEO.viewBox}" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="var(--icon-stroke,${GEO.strokeWidth})" stroke-linecap="round" stroke-linejoin="round">` +
    (opts.label ? `<title>${opts.label}</title>` : '') +
    `<path d="${def.d}"/>` + (def.extra || '').replace(/'/g, '"') + `</svg>`;
}

/* Identifiers are isolated so a DOI inside a Persian sentence does not get
   reordered by the bidi algorithm (§36). */
const id = (s) => `<bdi class="identifier">${s}</bdi>`;
const fa = (s) => `<span lang="fa" dir="rtl">${s}</span>`;

// §8 (owner's Phase 13 follow-up prompt): identity strings in the
// sidebar/topbar must never overflow — truncate to N chars with an
// ellipsis rather than letting a long email or site name break the
// layout. This truncates the *display* string only; the full value
// still belongs in a title attribute for anyone who needs to read it.
function truncateIdentity(s, n = 20) {
  return s.length > n ? s.slice(0, n) + '…' : s;
}
const CURRENT_USER_EMAIL = 'soleimanimarzieh5@gmail.com';
const CURRENT_USER_SITE = 'toranjebin.ir';

// World map — a stylized dot map, not a precise geographic dataset.
// WORLD_DOTS approximates continent silhouettes as a coarse grid sample
// of a handful of bounding-box regions per continent (not real coastline
// vector data — there is no bundled cartography source in this project,
// consistent with ADR-079's "geolocation is not invented" rule extending
// to the rendering, not just the underlying geo_country field). It exists
// so the shape reads as "a world map" at a glance; it is not accurate
// enough to zoom into and should never be presented as survey-grade.
const WORLD_DOTS = [[3.06,9.02],[3.06,4.89],[4.58,13.16],[4.58,9.02],[4.58,4.89],[6.11,13.16],[6.11,9.02],[6.11,4.89],[7.64,13.16],[7.64,9.02],[7.64,4.89],[9.17,13.16],[9.17,9.02],[9.17,4.89],[10.69,13.16],[10.69,9.02],[10.69,4.89],[12.22,13.16],[12.22,9.02],[12.22,4.89],[13.75,13.16],[13.75,9.02],[13.75,4.89],[15.28,33.83],[15.28,29.7],[15.28,25.56],[15.28,21.43],[15.28,17.29],[15.28,13.16],[15.28,9.02],[15.28,4.89],[16.81,33.83],[16.81,29.7],[16.81,25.56],[16.81,21.43],[16.81,17.29],[18.33,33.83],[18.33,29.7],[18.33,25.56],[18.33,21.43],[18.33,17.29],[19.86,42.11],[19.86,37.97],[19.86,33.83],[19.86,29.7],[19.86,25.56],[19.86,21.43],[19.86,17.29],[21.39,42.11],[21.39,37.97],[21.39,33.83],[21.39,29.7],[21.39,25.56],[21.39,21.43],[21.39,17.29],[22.92,42.11],[22.92,37.97],[22.92,33.83],[22.92,29.7],[22.92,25.56],[22.92,21.43],[22.92,17.29],[24.44,42.11],[24.44,37.97],[24.44,33.83],[24.44,29.7],[24.44,25.56],[24.44,21.43],[25.97,42.11],[25.97,37.97],[25.97,33.83],[25.97,29.7],[25.97,25.56],[25.97,21.43],[27.5,42.11],[27.5,37.97],[27.5,33.83],[27.5,29.7],[27.5,25.56],[27.5,21.43],[29.03,33.83],[29.03,29.7],[29.03,25.56],[29.03,21.43],[29.03,17.29],[30.56,21.43],[30.56,17.29],[30.56,13.16],[32.08,21.43],[32.08,17.29],[32.08,13.16],[33.61,21.43],[33.61,17.29],[33.61,13.16],[35.14,21.43],[35.14,17.29],[35.14,13.16],[27.5,62.78],[27.5,58.65],[27.5,54.51],[27.5,50.38],[29.03,62.78],[29.03,58.65],[29.03,54.51],[29.03,50.38],[30.56,95.86],[30.56,91.73],[30.56,87.59],[30.56,83.46],[30.56,79.32],[30.56,75.19],[30.56,71.05],[30.56,66.92],[30.56,62.78],[30.56,58.65],[30.56,54.51],[30.56,50.38],[32.08,95.86],[32.08,91.73],[32.08,87.59],[32.08,83.46],[32.08,79.32],[32.08,75.19],[32.08,71.05],[32.08,66.92],[32.08,62.78],[32.08,58.65],[32.08,54.51],[32.08,50.38],[33.61,79.32],[33.61,75.19],[33.61,71.05],[33.61,66.92],[33.61,62.78],[33.61,58.65],[33.61,54.51],[33.61,50.38],[35.14,79.32],[35.14,75.19],[35.14,71.05],[35.14,66.92],[35.14,62.78],[35.14,58.65],[35.14,54.51],[35.14,50.38],[36.67,79.32],[36.67,75.19],[36.67,71.05],[36.67,66.92],[36.67,62.78],[36.67,58.65],[36.67,54.51],[36.67,50.38],[38.19,79.32],[38.19,75.19],[38.19,71.05],[38.19,66.92],[38.19,62.78],[38.19,58.65],[38.19,54.51],[38.19,50.38],[39.72,62.78],[39.72,58.65],[39.72,54.51],[39.72,50.38],[44.31,25.56],[44.31,21.43],[44.31,17.29],[44.31,13.16],[44.31,9.02],[45.83,25.56],[45.83,21.43],[45.83,17.29],[45.83,13.16],[45.83,9.02],[47.36,25.56],[47.36,21.43],[47.36,17.29],[47.36,13.16],[47.36,9.02],[48.89,25.56],[48.89,21.43],[48.89,17.29],[48.89,13.16],[50.42,25.56],[50.42,21.43],[50.42,17.29],[50.42,13.16],[50.42,9.02],[50.42,4.89],[51.94,25.56],[51.94,21.43],[51.94,17.29],[51.94,13.16],[51.94,9.02],[51.94,4.89],[53.47,25.56],[53.47,21.43],[53.47,17.29],[53.47,13.16],[53.47,9.02],[53.47,4.89],[55.0,25.56],[55.0,21.43],[55.0,17.29],[55.0,13.16],[55.0,9.02],[55.0,4.89],[56.53,25.56],[56.53,21.43],[56.53,17.29],[56.53,13.16],[56.53,9.02],[56.53,4.89],[58.06,25.56],[58.06,21.43],[58.06,17.29],[58.06,13.16],[58.06,9.02],[58.06,4.89],[59.58,25.56],[59.58,21.43],[59.58,17.29],[59.58,13.16],[61.11,25.56],[61.11,21.43],[61.11,17.29],[61.11,13.16],[45.83,50.38],[45.83,46.24],[45.83,42.11],[45.83,37.97],[45.83,33.83],[45.83,29.7],[47.36,58.65],[47.36,54.51],[47.36,50.38],[47.36,46.24],[47.36,42.11],[47.36,37.97],[47.36,33.83],[47.36,29.7],[48.89,58.65],[48.89,54.51],[48.89,50.38],[48.89,46.24],[48.89,42.11],[48.89,37.97],[48.89,33.83],[48.89,29.7],[50.42,58.65],[50.42,54.51],[50.42,50.38],[50.42,46.24],[50.42,42.11],[50.42,37.97],[50.42,33.83],[50.42,29.7],[51.94,58.65],[51.94,54.51],[51.94,50.38],[51.94,46.24],[51.94,42.11],[51.94,37.97],[51.94,33.83],[51.94,29.7],[53.47,79.32],[53.47,75.19],[53.47,71.05],[53.47,66.92],[53.47,62.78],[53.47,58.65],[53.47,54.51],[53.47,50.38],[53.47,46.24],[53.47,42.11],[55.0,79.32],[55.0,75.19],[55.0,71.05],[55.0,66.92],[55.0,62.78],[55.0,58.65],[55.0,54.51],[55.0,50.38],[55.0,46.24],[55.0,42.11],[56.53,79.32],[56.53,75.19],[56.53,71.05],[56.53,66.92],[56.53,62.78],[56.53,58.65],[56.53,54.51],[56.53,50.38],[56.53,46.24],[56.53,42.11],[58.06,79.32],[58.06,75.19],[58.06,71.05],[58.06,66.92],[58.06,62.78],[58.06,58.65],[58.06,54.51],[58.06,50.38],[58.06,46.24],[58.06,42.11],[59.58,79.32],[59.58,75.19],[59.58,71.05],[59.58,66.92],[59.58,62.78],[59.58,58.65],[59.58,54.51],[59.58,50.38],[59.58,46.24],[59.58,42.11],[61.11,79.32],[61.11,75.19],[61.11,71.05],[61.11,66.92],[61.11,62.78],[61.11,58.65],[61.11,54.51],[61.11,50.38],[61.11,46.24],[61.11,42.11],[62.64,75.19],[62.64,71.05],[62.64,66.92],[62.64,62.78],[62.64,58.65],[62.64,54.51],[64.17,75.19],[64.17,71.05],[64.17,66.92],[64.17,62.78],[64.17,58.65],[64.17,54.51],[58.06,29.7],[59.58,29.7],[59.58,9.02],[59.58,4.89],[61.11,37.97],[61.11,33.83],[61.11,29.7],[61.11,9.02],[61.11,4.89],[62.64,46.24],[62.64,42.11],[62.64,37.97],[62.64,33.83],[62.64,29.7],[62.64,25.56],[62.64,21.43],[62.64,17.29],[62.64,13.16],[62.64,9.02],[62.64,4.89],[64.17,46.24],[64.17,42.11],[64.17,37.97],[64.17,33.83],[64.17,29.7],[64.17,25.56],[64.17,21.43],[64.17,17.29],[64.17,13.16],[64.17,9.02],[64.17,4.89],[65.69,46.24],[65.69,42.11],[65.69,37.97],[65.69,33.83],[65.69,29.7],[65.69,25.56],[65.69,21.43],[65.69,17.29],[65.69,13.16],[65.69,9.02],[65.69,4.89],[67.22,50.38],[67.22,46.24],[67.22,42.11],[67.22,37.97],[67.22,33.83],[67.22,29.7],[67.22,25.56],[67.22,21.43],[67.22,17.29],[67.22,13.16],[67.22,9.02],[67.22,4.89],[68.75,50.38],[68.75,46.24],[68.75,42.11],[68.75,37.97],[68.75,33.83],[68.75,29.7],[68.75,25.56],[68.75,21.43],[68.75,17.29],[68.75,13.16],[68.75,9.02],[68.75,4.89],[70.28,50.38],[70.28,46.24],[70.28,42.11],[70.28,37.97],[70.28,33.83],[70.28,29.7],[70.28,25.56],[70.28,21.43],[70.28,17.29],[70.28,13.16],[70.28,9.02],[70.28,4.89],[71.81,50.38],[71.81,46.24],[71.81,42.11],[71.81,37.97],[71.81,33.83],[71.81,29.7],[71.81,25.56],[71.81,21.43],[71.81,17.29],[71.81,13.16],[71.81,9.02],[71.81,4.89],[73.33,50.38],[73.33,46.24],[73.33,42.11],[73.33,37.97],[73.33,33.83],[73.33,29.7],[73.33,25.56],[73.33,21.43],[73.33,17.29],[73.33,13.16],[73.33,9.02],[73.33,4.89],[74.86,50.38],[74.86,46.24],[74.86,42.11],[74.86,37.97],[74.86,33.83],[74.86,29.7],[74.86,25.56],[74.86,21.43],[74.86,17.29],[74.86,13.16],[74.86,9.02],[74.86,4.89],[76.39,62.78],[76.39,58.65],[76.39,54.51],[76.39,50.38],[76.39,46.24],[76.39,42.11],[76.39,37.97],[76.39,33.83],[76.39,29.7],[76.39,25.56],[76.39,21.43],[76.39,17.29],[76.39,13.16],[76.39,9.02],[76.39,4.89],[77.92,62.78],[77.92,58.65],[77.92,54.51],[77.92,50.38],[77.92,46.24],[77.92,42.11],[77.92,37.97],[77.92,33.83],[77.92,29.7],[77.92,25.56],[77.92,21.43],[77.92,17.29],[77.92,13.16],[77.92,9.02],[77.92,4.89],[79.44,62.78],[79.44,58.65],[79.44,54.51],[79.44,50.38],[79.44,46.24],[79.44,42.11],[79.44,37.97],[79.44,33.83],[79.44,29.7],[79.44,25.56],[79.44,21.43],[79.44,17.29],[79.44,13.16],[79.44,9.02],[79.44,4.89],[80.97,62.78],[80.97,58.65],[80.97,54.51],[80.97,50.38],[80.97,46.24],[80.97,42.11],[80.97,37.97],[80.97,33.83],[80.97,29.7],[80.97,25.56],[80.97,21.43],[80.97,17.29],[80.97,13.16],[80.97,9.02],[80.97,4.89],[82.5,62.78],[82.5,58.65],[82.5,54.51],[82.5,50.38],[82.5,46.24],[82.5,42.11],[82.5,37.97],[82.5,33.83],[82.5,29.7],[82.5,25.56],[82.5,21.43],[82.5,17.29],[82.5,13.16],[82.5,9.02],[82.5,4.89],[84.03,62.78],[84.03,58.65],[84.03,54.51],[84.03,50.38],[84.03,46.24],[84.03,42.11],[84.03,37.97],[84.03,33.83],[84.03,29.7],[84.03,25.56],[84.03,21.43],[84.03,17.29],[84.03,13.16],[84.03,9.02],[84.03,4.89],[85.56,62.78],[85.56,58.65],[85.56,54.51],[85.56,50.38],[85.56,46.24],[85.56,42.11],[85.56,37.97],[85.56,33.83],[85.56,29.7],[85.56,25.56],[85.56,21.43],[85.56,17.29],[85.56,13.16],[85.56,9.02],[85.56,4.89],[87.08,62.78],[87.08,58.65],[87.08,54.51],[87.08,50.38],[87.08,46.24],[87.08,42.11],[87.08,37.97],[87.08,33.83],[87.08,29.7],[87.08,25.56],[87.08,21.43],[87.08,17.29],[87.08,13.16],[87.08,9.02],[87.08,4.89],[88.61,62.78],[88.61,58.65],[88.61,54.51],[88.61,50.38],[88.61,46.24],[88.61,42.11],[88.61,37.97],[88.61,33.83],[88.61,29.7],[88.61,25.56],[88.61,21.43],[88.61,17.29],[88.61,13.16],[88.61,9.02],[88.61,4.89],[90.14,33.83],[90.14,29.7],[90.14,25.56],[90.14,21.43],[90.14,17.29],[90.14,13.16],[90.14,9.02],[90.14,4.89],[91.67,25.56],[91.67,21.43],[91.67,17.29],[91.67,13.16],[91.67,9.02],[91.67,4.89],[93.19,25.56],[93.19,21.43],[93.19,17.29],[93.19,13.16],[93.19,9.02],[94.72,25.56],[94.72,21.43],[94.72,17.29],[94.72,13.16],[94.72,9.02],[96.25,25.56],[96.25,21.43],[96.25,17.29],[96.25,13.16],[96.25,9.02],[97.78,25.56],[97.78,21.43],[97.78,17.29],[97.78,13.16],[97.78,9.02],[99.31,25.56],[99.31,21.43],[99.31,17.29],[99.31,13.16],[99.31,9.02],[82.5,83.46],[82.5,79.32],[82.5,75.19],[82.5,71.05],[82.5,66.92],[84.03,83.46],[84.03,79.32],[84.03,75.19],[84.03,71.05],[84.03,66.92],[85.56,83.46],[85.56,79.32],[85.56,75.19],[85.56,71.05],[85.56,66.92],[87.08,83.46],[87.08,79.32],[87.08,75.19],[87.08,71.05],[87.08,66.92],[88.61,83.46],[88.61,79.32],[88.61,75.19],[88.61,71.05],[88.61,66.92],[90.14,83.46],[90.14,79.32],[90.14,75.19],[90.14,71.05],[90.14,66.92],[91.67,83.46],[91.67,79.32],[91.67,75.19],[91.67,71.05],[91.67,66.92],[96.25,91.73],[96.25,87.59],[96.25,83.46],[97.78,91.73],[97.78,87.59],[97.78,83.46],[99.31,91.73],[99.31,87.59],[99.31,83.46]];

// Country bubbles — same GEO_POINTS data as before, now projected with
// the same equirectangular formula as WORLD_DOTS (lon/lat -> %) so a
// bubble actually lands on its own country's dot cluster instead of an
// arbitrary hand-picked position.
const GEO_POINTS = [
  { code: 'IR', name: fa('ایران'), x: 64.72, y: 32.33, n: 1402 },
  { code: 'US', name: 'United States', x: 22.78, y: 27.07, n: 431 },
  { code: 'DE', name: 'Germany', x: 52.78, y: 18.05, n: 96 },
  { code: 'GB', name: 'United Kingdom', x: 49.44, y: 15.79, n: 58 },
  { code: 'IN', name: 'India', x: 71.94, y: 39.85, n: 44 },
  { code: 'TR', name: fa('ترکیه'), x: 59.72, y: 27.07, n: 39 },
];

function schematicMap() {
  // Pure CSS/DOM, same reason as sparkChart(): every <svg> in this
  // harness must be a registry icon (checked by check.js §56/§57); a
  // dot map with 670+ points is not an icon, so it is built from
  // absolutely-positioned <div> dots rather than SVG.
  const dots = WORLD_DOTS.map(([x, y]) =>
    `<div style="position:absolute;left:${x}%;top:${y}%;width:3px;height:3px;margin-left:-1.5px;margin-top:-1.5px;border-radius:50%;background:var(--border-strong,var(--border))"></div>`
  ).join('');
  const maxN = Math.max(...GEO_POINTS.map(p => p.n));
  const markers = GEO_POINTS.map(p => {
    const size = 12 + (p.n / maxN) * 38;
    return `<div style="position:absolute;left:${p.x}%;top:${p.y}%;width:${size}px;height:${size}px;margin-left:${-size / 2}px;margin-top:${-size / 2}px;border-radius:50%;background:var(--primary);opacity:0.32;border:1.5px solid var(--primary)" title="${p.name} — ${p.n.toLocaleString()} requests"></div>`;
  }).join('');
  const labels = GEO_POINTS.map(p =>
    `<div style="position:absolute;left:${p.x}%;top:${p.y}%;transform:translate(8px,-8px);font-size:11px;color:var(--text-subtle);white-space:nowrap;pointer-events:none"><bdi>${p.name}</bdi></div>`
  ).join('');
  return `
    <div role="img" aria-label="Stylized world map of request origins by country, marker size proportional to volume" style="position:relative;width:100%;aspect-ratio:2/1;background:var(--surface-sunken);border-radius:var(--radius-md);overflow:hidden">
      ${dots}
      ${markers}
      ${labels}
    </div>`;
}

const na = (why = 'Not available') => `<span class="not-available">${why}</span>`;

const badge = (variant, iconName, text) =>
  `<span class="badge badge--${variant}">${ic(iconName)}<span>${text}</span></span>`;

/* ---------------------------------------------------------------- fixtures
 * Representative, not lorem ipsum (§80, §81). Deliberately includes a
 * Persian title, a very long filename, a failed source, a duplicate, a
 * paywalled research source, and a supplier certificate.
 */
const SOURCES = [
  {
    type: 'pdf', icon: 'source-pdf',
    title: 'Toranjebin (Alhagi manna) — Scientific Review 2025',
    meta: 'User uploaded · 2.8 MB · <span class="identifier">application/pdf</span>',
    status: ['success', 'status-completed', 'Completed'],
    knowledge: 3, claims: 74, evidence: 31, updated: '2026-09-02',
  },
  {
    type: 'docx', icon: 'source-docx',
    title: fa('مروری بر طب سنتی ایران — ترنجبین و کاربردهای گوارشی'),
    meta: 'User uploaded · 1.1 MB · <span lang="fa">فارسی</span>',
    status: ['processing', 'status-processing', 'Evidence extraction'],
    knowledge: 1, claims: null, evidence: null, updated: '2026-09-17',
  },
  {
    type: 'pdf', icon: 'source-research',
    title: 'Mannitol content and osmotic activity in Alhagi exudates: a compositional analysis',
    meta: 'DOI ' + id('10.1016/j.jep.2024.118233') + ' · PMID ' + id('39214477') + ' · Paywalled',
    status: ['warning', 'status-warning', 'Abstract only'],
    knowledge: 2, claims: 9, evidence: 4, updated: '2026-08-28',
  },
  {
    type: 'pdf', icon: 'source-certificate',
    title: 'Supplier Certificate — Batch 2026-04 — Khorasan Razavi Cooperative — heavy metals and microbial panel — signed copy.pdf',
    meta: 'Supplier document · 640 KB',
    status: ['success', 'status-completed', 'Completed'],
    knowledge: 1, claims: 6, evidence: 6, updated: '2026-08-14',
  },
  {
    type: 'xlsx', icon: 'source-xlsx',
    title: 'Saffron Quality Laboratory Report — ISO 3632 crocin/picrocrocin series',
    meta: 'Lab report · 88 KB',
    status: ['success', 'status-completed', 'Completed'],
    knowledge: 1, claims: 12, evidence: 12, updated: '2026-07-30',
  },
  {
    type: 'docx', icon: 'source-docx',
    title: 'Persian Herbal Medicine Review (2024 draft, scanned).docx',
    meta: 'User uploaded · 14.2 MB',
    status: ['danger', 'status-failed', 'Conversion failed'],
    knowledge: 0, claims: 0, evidence: 0, updated: '2026-09-16',
  },
  {
    type: 'url', icon: 'source-url',
    title: 'toranjebin.ir — Product page: ترنجبین درجه یک خراسان',
    meta: id('https://toranjebin.ir/products/toranjebin-grade-1'),
    status: ['archived', 'status-archived', 'Archived'],
    knowledge: 1, claims: 4, evidence: 2, updated: '2026-06-11',
  },
];

/* ---------------------------------------------------------------- gaps
 * Backend: KnowledgeGap (app/models/knowledge_gap.py), enums.py —
 * GapType (10 values), GapStatus (OPEN/IN_PROGRESS/RESOLVED/DISMISSED),
 * GapRecommendedAction (19 values). The four fixtures below are picked to
 * show that the action set is NOT one fixed pair of buttons — a supplier
 * certificate gap has no sensible "search the web" action, and a
 * conflict gap is closed by review, not by search or upload. The UI must
 * follow what the gap actually needs, not offer the same two buttons for
 * everything (checkpoint §28, §67).
 */
const GAPS = [
  {
    id: 'GAP-0118', type: 'EVIDENCE_GAP', typeLabel: 'Evidence gap',
    status: 'open', statusLabel: 'Open',
    title: 'Human clinical evidence for Toranjebin',
    checked: [
      ['Traditional use', 'success', 'status-completed', 'Well attested — 41 sources'],
      ['Compositional analysis', 'success', 'status-completed', 'Established — 12 verified studies'],
      ['Animal studies', 'warning', 'status-warning', 'Insufficient — 2 studies'],
      ['Human clinical trials', 'unknown', 'status-unknown', 'None found — 4 databases searched'],
    ],
    note: '“None found” is a search outcome, not evidence of absence — 4 databases were queried directly, nothing about this species turned up. It is recorded as unknown, not as a negative result.',
    actions: [
      { kind: 'search', label: 'Search the literature', detail: 'Queues a research task against clinical trial registries and PubMed. Results land here for review — nothing publishes automatically (§64).' },
      { kind: 'upload', label: 'Add a source', detail: 'PDF, spreadsheet, or a link — if you already hold a trial report or dataset, attach it directly to this gap.' },
      { kind: 'keep', label: 'Keep open', detail: 'No action right now. The gap stays visible on the dashboard.' },
    ],
  },
  {
    id: 'GAP-0142', type: 'SOURCE_GAP', typeLabel: 'Source gap',
    status: 'open', statusLabel: 'Open',
    title: 'No supplier certificate for Batch 2026-05',
    action: 'upload', actionLabel: 'Add a source',
  },
  {
    id: 'GAP-0097', type: 'ACCESS_GAP', typeLabel: 'Access gap',
    status: 'in_progress', statusLabel: 'In progress',
    title: 'Full text paywalled — compositional analysis, ' + id('PMID 39214477'),
    action: 'upload', actionLabel: 'Add a source',
  },
  {
    id: 'GAP-0061', type: 'CONFLICT_GAP', typeLabel: 'Conflict gap',
    status: 'resolved', statusLabel: 'Resolved',
    title: 'Conflicting chemotype claims across regional studies',
    action: 'review', actionLabel: 'Review conflict',
  },
];

const GAP_STATUS_BADGE = {
  open: ['warning', 'status-warning'],
  in_progress: ['processing', 'status-processing'],
  resolved: ['success', 'status-completed'],
  dismissed: ['archived', 'status-archived'],
};

function gapRow(g) {
  const [variant, iconName] = GAP_STATUS_BADGE[g.status];
  const actionMap = {
    upload: ['action-upload', 'Add a source', '#screen-add'],
    search: ['action-search', 'Search the literature', '#screen-gap'],
    review: ['provenance-relation', 'Review conflict', '#screen-provenance'],
  };
  const [aIcon, aLabel, aHref] = actionMap[g.action];
  return `
    <tr>
      <td data-label="Gap"><span class="source-cell__title">${g.title}</span><br><span class="source-cell__meta">${id(g.id)} · ${g.typeLabel}</span></td>
      <td data-label="Status">${badge(variant, iconName, g.statusLabel)}</td>
      <td data-label="">
        ${g.status === 'resolved'
          ? `<a class="btn btn--quiet" href="${aHref}">${ic(aIcon)}${aLabel}</a>`
          : `<a class="btn" href="${aHref}">${ic(aIcon)}${aLabel}</a>`}
      </td>
    </tr>`;
}

function sourceRow(s) {
  const n = (v) => (v === null ? na() : `<span class="num">${v}</span>`);
  return `
    <tr>
      <td data-label="Source">
        <div class="source-cell">
          <span class="source-cell__icon">${ic(s.icon, { size: '20px' })}</span>
          <span style="min-inline-size:0">
            <span class="source-cell__title">${s.title}</span><br>
            <span class="source-cell__meta">${s.meta}</span>
          </span>
        </div>
      </td>
      <td data-label="Status">${badge(s.status[0], s.status[1], s.status[2])}</td>
      <td data-label="Knowledge" class="num">${n(s.knowledge)}</td>
      <td data-label="Claims" class="num">${n(s.claims)}</td>
      <td data-label="Evidence" class="num">${n(s.evidence)}</td>
      <td data-label="Updated" class="num">${s.updated}</td>
      <td data-label="">
        <span style="display:flex;gap:4px">
          <a class="btn btn--quiet" href="#screen-detail">Open</a>
          <button type="button" class="icon-button" aria-label="More actions for this source" title="More actions">${ic('action-more')}</button>
        </span>
      </td>
    </tr>`;
}

/* ------------------------------------------------------------------ screens */

const screenDashboard = `
<section class="screen" id="screen-dashboard" aria-labelledby="h-dashboard">
  <nav class="breadcrumbs" aria-label="Breadcrumb"><span>Hamed Commerce</span>${ic('action-expand', { class: 'icon--mirror' })}<span>toranjebin.ir</span></nav>
  <div class="page-header">
    <div>
      <h1 id="h-dashboard">Dashboard</h1>
      <p>What entered the system, what it became, and what needs a person.</p>
    </div>
  </div>

  <div class="stat-grid">
    <div class="stat"><span class="stat__label">${ic('sources')}Sources</span><span class="stat__value">248</span><span class="stat__note">12 added this month</span></div>
    <div class="stat"><span class="stat__label">${ic('status-processing')}Processing</span><span class="stat__value">7</span><span class="stat__note">Oldest queued 4 min ago</span></div>
    <div class="stat"><span class="stat__label">${ic('status-completed')}Completed</span><span class="stat__value">231</span><span class="stat__note">10 ended in a failure state</span></div>
    <div class="stat stat--attention"><span class="stat__label">${ic('status-warning')}Needs review</span><span class="stat__value">10</span><span class="stat__note">6 conversions, 4 conflicts</span></div>
  </div>

  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:var(--space-4)">
    <div class="card">
      <h2 class="card__title">Waiting on a person</h2>
      <p style="color:var(--text-muted);margin-top:0">These are not errors the system can clear itself.</p>
      <dl class="kv">
        <dt>Evidence pending review</dt><dd class="num">38</dd>
        <dt>Claims in conflict</dt><dd class="num">7</dd>
        <dt>Knowledge gaps open</dt><dd><a href="#screen-gap" class="num">21</a></dd>
        <dt>Duplicate decisions</dt><dd class="num">2</dd>
      </dl>
    </div>
    <div class="card">
      <h2 class="card__title">Coverage honesty</h2>
      <div class="callout"><span class="callout__icon">${ic('info')}</span>
        <div>
          <p>4 of the 7 highest-priority claims rest on sources whose full text was never accessible.</p>
          <p><a href="#screen-knowledge">Review which claims</a></p>
        </div>
      </div>
    </div>
    <div class="card">
      <h2 class="card__title">Visible to AI right now</h2>
      <p style="color:var(--text-muted);margin-top:0">Two different signals, kept separate on purpose — see below. <a href="#screen-visibility-detail">Open the full report</a>.</p>
      <dl class="kv">
        <dt>Platform observations (30d)</dt><dd><a href="#screen-visibility-detail" class="num">47</a></dd>
        <dt>Automated requests (30d)</dt><dd><a href="#screen-visibility-detail" class="num">2,085</a></dd>
      </dl>
    </div>
  </div>
</section>`;

const screenSources = `
<section class="screen" id="screen-sources" aria-labelledby="h-sources">
  <nav class="breadcrumbs" aria-label="Breadcrumb"><a href="#screen-dashboard">Dashboard</a>${ic('action-expand')}<span>Sources &amp; Documents</span></nav>
  <div class="page-header">
    <div>
      <h1 id="h-sources">Sources &amp; Documents</h1>
      <p>Everything the knowledge layer is allowed to derive truth from. 248 sources, 7 processing.</p>
    </div>
    <div class="page-actions">
      <button class="btn">${ic('action-filter')}Filter</button>
      <button class="btn">${ic('action-sort')}Sort</button>
      <a class="btn btn--primary" href="#screen-add">${ic('action-add')}Add source</a>
    </div>
  </div>

  <div class="table-wrap">
    <table class="table sortable">
      <caption class="visually-hidden">Sources, with processing status and what each has contributed to the knowledge layer</caption>
      <thead><tr>
        <th scope="col">Source</th><th scope="col">Status</th>
        <th scope="col">Knowledge</th><th scope="col">Claims</th><th scope="col">Evidence</th>
        <th scope="col">Updated</th><th scope="col"><span class="visually-hidden">Actions</span></th>
      </tr></thead>
      <tbody>${SOURCES.map(sourceRow).join('')}</tbody>
    </table>
  </div>
  <p style="color:var(--text-subtle);font-size:var(--text-sm);margin-top:var(--space-4)">
    Showing 7 of 248. Filtering and sorting run on the server; the browser never holds the whole collection.
  </p>
</section>`;

const screenAdd = `
<section class="screen" id="screen-add" aria-labelledby="h-add">
  <nav class="breadcrumbs" aria-label="Breadcrumb"><a href="#screen-sources">Sources &amp; Documents</a>${ic('action-expand')}<span>Add source</span></nav>
  <div class="page-header"><div><h1 id="h-add">Add a source</h1><p>Pick where it comes from. The system records the origin, not just the file.</p></div></div>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:var(--space-4);max-inline-size:900px">
    ${[
      ['source-pdf', 'Document', 'PDF, DOCX, XLSX, PPTX'],
      ['source-url', 'Web page', 'A public URL to fetch'],
      ['source-cms', 'Site article', 'Content already on toranjebin.ir'],
      ['source-research', 'Research', 'DOI, PMID, or a paper you hold'],
      ['source-dataset', 'Dataset', 'CSV or spreadsheet of records'],
      ['source-certificate', 'Supplier document', 'Certificates, lab panels, batch records'],
    ].map(([i, t, d]) => `
      <button class="card" style="text-align:start;cursor:pointer;display:grid;gap:var(--space-2);justify-items:start">
        <span style="color:var(--primary)">${ic(i, { size: '24px' })}</span>
        <span style="font-weight:var(--weight-semibold)">${t}</span>
        <span style="color:var(--text-muted);font-size:var(--text-sm)">${d}</span>
      </button>`).join('')}
  </div>
</section>`;

const screenProcessing = `
<section class="screen" id="screen-processing" aria-labelledby="h-proc">
  <nav class="breadcrumbs" aria-label="Breadcrumb"><a href="#screen-sources">Sources &amp; Documents</a>${ic('action-expand')}<span>Processing</span></nav>
  <div class="page-header">
    <div>
      <h1 id="h-proc">${fa('مروری بر طب سنتی ایران — ترنجبین و کاربردهای گوارشی')}</h1>
      <p>Persian Traditional Medicine Review · DOCX · added 4 minutes ago</p>
    </div>
    <div class="page-actions">${badge('processing', 'status-processing', 'Evidence extraction')}</div>
  </div>

  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:var(--space-4)">
    <div class="card">
      <h2 class="card__title">Pipeline</h2>
      <ol class="stages">
        <li data-state="done"><span class="stages__icon">${ic('status-completed')}</span><span class="stages__name">Upload</span><span class="stages__detail">11.2 MB retained</span></li>
        <li data-state="done"><span class="stages__icon">${ic('status-completed')}</span><span class="stages__name">Security validation</span><span class="stages__detail">Type allowed</span></li>
        <li data-state="done"><span class="stages__icon">${ic('status-completed')}</span><span class="stages__name">MarkItDown conversion</span><span class="stages__detail">0.1.7</span></li>
        <li data-state="done"><span class="stages__icon">${ic('status-completed')}</span><span class="stages__name">Structure detection</span><span class="stages__detail">9 tables</span></li>
        <li data-state="done"><span class="stages__icon">${ic('status-completed')}</span><span class="stages__name">OCR</span><span class="stages__detail">18 pages, <span lang="fa">فارسی</span>+eng</span></li>
        <li data-state="done"><span class="stages__icon">${ic('status-completed')}</span><span class="stages__name">Semantic chunking</span><span class="stages__detail">342 chunks</span></li>
        <li data-state="active"><span class="stages__icon">${ic('status-processing')}</span><span class="stages__name">Evidence extraction</span><span class="stages__detail">Stage in progress</span></li>
        <li data-state="pending"><span class="stages__icon">${ic('status-queued')}</span><span class="stages__name">Knowledge contribution</span><span class="stages__detail">Not started</span></li>
      </ol>
      <p style="color:var(--text-subtle);font-size:var(--text-sm);margin-bottom:0">
        No percentage is shown, because the worker does not report one. The stage is the truth available.
      </p>
    </div>

    <div class="card">
      <h2 class="card__title">What has been found so far</h2>
      <dl class="kv">
        <dt>Pages</dt><dd class="num">84</dd>
        <dt>Tables detected</dt><dd class="num">9</dd>
        <dt>Images detected</dt><dd class="num">12</dd>
        <dt>OCR blocks</dt><dd class="num">211</dd>
        <dt>Chunks created</dt><dd class="num">342</dd>
        <dt>Claims extracted</dt><dd>${na('Stage not reached')}</dd>
        <dt>Evidence candidates</dt><dd>${na('Stage not reached')}</dd>
      </dl>
      <div class="callout" style="margin-top:var(--space-4)"><span class="callout__icon">${ic('job')}</span>
        <div>
          <p>Job ${id('9f2c41ae-6b0d-4d71-9a18-2c5e0f3b77d4')} · queued 4 min ago · attempt 1</p>
          <p><a href="#screen-processing">View job</a></p>
        </div>
      </div>
    </div>
  </div>
</section>`;

const screenDetail = `
<section class="screen" id="screen-detail" aria-labelledby="h-detail">
  <nav class="breadcrumbs" aria-label="Breadcrumb"><a href="#screen-sources">Sources &amp; Documents</a>${ic('action-expand')}<span>Toranjebin Scientific Review</span></nav>
  <div class="page-header">
    <div style="display:flex;gap:var(--space-4);align-items:flex-start">
      <span style="color:var(--text-muted)">${ic('source-pdf', { size: '32px' })}</span>
      <div>
        <h1 id="h-detail">Toranjebin (Alhagi manna) — Scientific Review 2025</h1>
        <p>Scientific paper · uploaded by Hamed · 2 Sep 2026 · processing version v3</p>
        <p style="margin-top:var(--space-2)">${badge('success', 'status-completed', 'Completed')} ${badge('info', 'provenance-version', 'v3 of 3')}</p>
      </div>
    </div>
    <div class="page-actions">
      <button class="btn">${ic('action-reprocess')}Reprocess</button>
      <a class="btn" href="#screen-states">${ic('action-archive')}Archive</a>
      <a class="btn btn--danger" href="#screen-states">${ic('action-delete')}Delete</a>
      <button type="button" class="icon-button" aria-label="More actions" title="More actions">${ic('action-more')}</button>
    </div>
  </div>

  <div class="tabs" role="tablist" aria-label="Source detail sections">
    <button role="tab" aria-selected="true">Overview</button>
    <button role="tab" aria-selected="false">Artifacts</button>
    <button role="tab" aria-selected="false">Knowledge</button>
    <button role="tab" aria-selected="false">Claims</button>
    <button role="tab" aria-selected="false">Evidence</button>
    <button role="tab" aria-selected="false">Provenance</button>
    <button role="tab" aria-selected="false">History</button>
  </div>

  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:var(--space-4)">
    <div class="card">
      <h2 class="card__title">Identity</h2>
      <dl class="kv">
        <dt>Source type</dt><dd>Scientific paper</dd>
        <dt>Original file</dt><dd>${id('toranjebin-scientific-review-2025.pdf')}</dd>
        <dt>DOI</dt><dd>${id('10.1016/j.jep.2025.119104')}</dd>
        <dt>Full text</dt><dd>${badge('success', 'status-completed', 'Accessible')}</dd>
        <dt>Rights</dt><dd>${badge('unknown', 'status-unknown', 'Unknown')}</dd>
        <dt>SHA-256</dt><dd>${id('c1f4…8e2b')}</dd>
      </dl>
    </div>

    <div class="card">
      <h2 class="card__title">What this source contributed</h2>
      <dl class="kv">
        <dt>Knowledge objects</dt><dd><a href="#screen-knowledge-taranjebin" class="num">3</a></dd>
        <dt>Claims</dt><dd><a href="#screen-detail" class="num">74</a></dd>
        <dt>Evidence</dt><dd><a href="#screen-detail" class="num">31</a></dd>
        <dt>Research projects</dt><dd><a href="#screen-detail" class="num">2</a></dd>
        <dt>Knowledge gaps affected</dt><dd><a href="#screen-detail" class="num">4</a></dd>
      </dl>
      <p style="color:var(--text-subtle);font-size:var(--text-sm);margin-bottom:0">
        31 evidence records exist. 19 are verified; 12 are still pending review and count toward nothing.
      </p>
    </div>

    <div class="card">
      <h2 class="card__title">Canonical representation</h2>
      <dl class="kv">
        <dt>Converter</dt><dd>MarkItDown ${id('0.1.7')}</dd>
        <dt>Conversion</dt><dd>${badge('success', 'status-completed', 'Succeeded')}</dd>
        <dt>Extraction level</dt><dd>3 — OCR</dd>
        <dt>Vision model</dt><dd>${na('Level 4 not run')}</dd>
      </dl>
      <p style="margin:var(--space-4) 0 0"><a class="btn" href="#screen-detail">${ic('action-view')}View Markdown</a></p>
      <p style="color:var(--text-subtle);font-size:var(--text-sm);margin-bottom:0">
        The original PDF stays authoritative. Markdown is derived, and is not knowledge.
      </p>
    </div>
  </div>
</section>`;

const screenProvenance = `
<section class="screen" id="screen-provenance" aria-labelledby="h-prov">
  <nav class="breadcrumbs" aria-label="Breadcrumb"><a href="#screen-detail">Toranjebin Scientific Review</a>${ic('action-expand')}<span>Provenance</span></nav>
  <div class="page-header"><div><h1 id="h-prov">Provenance</h1><p>Where the statement “contains mannitol” actually comes from, in both directions.</p></div></div>

  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:var(--space-4)">
    <div class="card">
      <h2 class="card__title">Knowledge back to source</h2>
      <ol class="trail">
        <li data-kind="knowledge"><span class="trail__node">${ic('provenance-knowledge')}</span>
          <span><span class="trail__kind">Knowledge object</span><br><span class="trail__value">${fa('ترنجبین')} <span style="color:var(--text-muted)">(Toranjebin)</span></span><span class="trail__meta">Published · updated 4 Sep 2026</span></span></li>
        <li data-kind="claim"><span class="trail__node">${ic('provenance-claim')}</span>
          <span><span class="trail__kind">Claim</span><br><span class="trail__value">Contains mannitol</span><span class="trail__meta">Approved · aggregate strength: moderate</span></span></li>
        <li data-kind="evidence"><span class="trail__node">${ic('provenance-evidence')}</span>
          <span><span class="trail__kind">Evidence</span><br><span class="trail__value">${id('EV-1042')} · compositional analysis</span><span class="trail__meta">Verified · direct · supports</span></span></li>
        <li data-kind="document"><span class="trail__node">${ic('sources')}</span>
          <span><span class="trail__kind">Document</span><br><span class="trail__value">Canonical Markdown, chunk 118</span><span class="trail__meta">MarkItDown 0.1.7</span></span></li>
        <li data-kind="source"><span class="trail__node">${ic('provenance-source')}</span>
          <span><span class="trail__kind">Source</span><br><span class="trail__value">Toranjebin — Scientific Review 2025</span><span class="trail__meta">Full text accessible · ${id('10.1016/j.jep.2025.119104')}</span></span></li>
      </ol>
    </div>

    <div class="card">
      <h2 class="card__title">One claim, several sources</h2>
      <p style="color:var(--text-muted);margin-top:0">Three support it; one contradicts it. That is shown, not averaged away.</p>
      <ol class="trail trail--fan">
        <li data-kind="claim"><span class="trail__node">${ic('provenance-claim')}</span>
          <span><span class="trail__kind">Claim</span><br><span class="trail__value">Contains mannitol</span></span></li>
        <li data-kind="evidence" data-fan><span class="trail__node">${ic('status-completed')}</span>
          <span style="min-inline-size:0"><span class="trail__kind">Supports</span><br><span class="trail__value">Scientific Review 2025</span><span class="trail__meta">Verified · direct</span></span>
          <button type="button" class="icon-button" aria-label="Remove this evidence link from the claim — the evidence record itself is kept" title="Remove this evidence link">${ic('action-delete')}</button></li>
        <li data-kind="evidence" data-fan><span class="trail__node">${ic('status-completed')}</span>
          <span style="min-inline-size:0"><span class="trail__kind">Supports</span><br><span class="trail__value">Compositional analysis, ${id('PMID 39214477')}</span><span class="trail__meta">Verified · direct · abstract only</span></span>
          <button type="button" class="icon-button" aria-label="Remove this evidence link from the claim — the evidence record itself is kept" title="Remove this evidence link">${ic('action-delete')}</button></li>
        <li data-kind="evidence" data-fan><span class="trail__node">${ic('status-completed')}</span>
          <span style="min-inline-size:0"><span class="trail__kind">Supports</span><br><span class="trail__value">${fa('مروری بر طب سنتی ایران')}</span><span class="trail__meta">Pending review · counts toward nothing yet</span></span>
          <button type="button" class="icon-button" aria-label="Remove this evidence link from the claim — the evidence record itself is kept" title="Remove this evidence link">${ic('action-delete')}</button></li>
        <li data-kind="conflict" data-fan><span class="trail__node" style="color:var(--warning);border-color:var(--warning);background:var(--warning-tint)">${ic('conflict')}</span>
          <span style="min-inline-size:0"><span class="trail__kind">Contradicts</span><br><span class="trail__value">Regional chemotype survey, 2023</span><span class="trail__meta">Verified · indirect · different species</span></span>
          <button type="button" class="icon-button" aria-label="Remove this evidence link from the claim — the evidence record itself is kept" title="Remove this evidence link">${ic('action-delete')}</button></li>
      </ol>
      <p style="color:var(--text-subtle);font-size:var(--text-sm);margin:var(--space-3) 0 0">
        This removes the link between one evidence record and this claim — a real, immediate action already supported today. It never deletes the underlying evidence, the document, or the source.
      </p>
      <div class="callout callout--warning" style="margin-top:var(--space-4)"><span class="callout__icon">${ic('conflict')}</span>
        <div><p>This claim is marked <strong>conflicting</strong>. It is not presented as settled anywhere in the product.</p>
        <p><a href="#screen-knowledge-taranjebin">Review the conflict</a></p></div>
      </div>
    </div>
  </div>
</section>`;

const KNOWLEDGE_OBJECTS = [
  {
    id: 'taranjebin', title: fa('ترنجبین'), subtitle: 'Toranjebin · Alhagi manna',
    updated: '4 Sep 2026', sources: 248, claims: 1842, evidence: 493, verified: 318, conflicts: 7, gaps: 21,
    processed: 248, approved: false, actionNote: '7 conflicts to resolve',
    evidenceByKind: [
      ['Traditional use', 'success', 'status-completed', 'Well attested', '41 sources'],
      ['Compositional', 'success', 'status-completed', 'Established', '12 verified studies'],
      ['Mechanistic', 'warning', 'status-warning', 'Indirect only', '3 studies, none on this species'],
      ['Animal', 'warning', 'status-warning', 'Insufficient', '2 studies'],
      ['Human clinical', 'unknown', 'status-unknown', 'None found', 'searched 4 databases, 0 trials'],
    ],
    gapNote: 'no direct human clinical trial has been found. "None found" is recorded as a search outcome, not as evidence of absence.',
  },
  {
    id: 'saffron', title: fa('زعفران'), subtitle: 'Saffron · Crocus sativus',
    updated: '11 Sep 2026', sources: 612, claims: 3104, evidence: 1180, verified: 940, conflicts: 3, gaps: 9,
    processed: 612, approved: false, actionNote: '3 conflicts to resolve',
    evidenceByKind: [
      ['Traditional use', 'success', 'status-completed', 'Well attested', '88 sources'],
      ['Compositional', 'success', 'status-completed', 'Established', '54 verified studies'],
      ['Mechanistic', 'success', 'status-completed', 'Established', '22 studies'],
      ['Animal', 'success', 'status-completed', 'Established', '31 studies'],
      ['Human clinical', 'warning', 'status-warning', 'Limited', '6 small trials, no large RCT'],
    ],
    gapNote: 'existing human trials are small and short-duration. No adequately powered long-term RCT has been found.',
  },
  {
    id: 'garlic', title: fa('سیر'), subtitle: 'Garlic · Allium sativum',
    updated: '9 Sep 2026', sources: 401, claims: 2210, evidence: 860, verified: 701, conflicts: 5, gaps: 6,
    processed: 401, approved: true, actionNote: null,
    evidenceByKind: [
      ['Traditional use', 'success', 'status-completed', 'Well attested', '70 sources'],
      ['Compositional', 'success', 'status-completed', 'Established', '38 verified studies'],
      ['Mechanistic', 'success', 'status-completed', 'Established', '19 studies'],
      ['Animal', 'success', 'status-completed', 'Established', '24 studies'],
      ['Human clinical', 'success', 'status-completed', 'Established', '14 RCTs, mixed cardiovascular endpoints'],
    ],
    gapNote: 'cardiovascular outcome trials disagree on effect size. 5 open conflicts trace to dosage-form differences (raw vs. aged extract) that the current claim graph does not yet separate.',
  },
  {
    id: 'thyme', title: fa('آویشن'), subtitle: 'Thyme · Thymus vulgaris',
    updated: '2 Sep 2026', sources: 156, claims: 704, evidence: 211, verified: 98, conflicts: 1, gaps: 14,
    processed: 89, approved: false, actionNote: '14 gaps, evidence needs review',
    evidenceByKind: [
      ['Traditional use', 'success', 'status-completed', 'Well attested', '52 sources'],
      ['Compositional', 'success', 'status-completed', 'Established', '9 verified studies'],
      ['Mechanistic', 'warning', 'status-warning', 'Indirect only', '4 studies, mostly in-vitro'],
      ['Animal', 'unknown', 'status-unknown', 'None found', 'searched 3 databases, 0 studies'],
      ['Human clinical', 'unknown', 'status-unknown', 'None found', 'searched 4 databases, 0 trials'],
    ],
    gapNote: 'no animal or human evidence has been located for the specific respiratory-use claim carried over from traditional sources. 14 gaps remain open, the most of any object currently tracked.',
  },
];

function knowledgeRow(k) {
  const pct = Math.round((k.processed / k.sources) * 100);
  return `
    <tr data-entity="${k.id}" data-version="1">
      <td data-label="Knowledge object"><a href="#screen-knowledge-${k.id}" style="font-weight:var(--weight-semibold);text-decoration:none;color:var(--text)"><bdi lang="fa" dir="rtl">${k.title}</bdi></a> <span class="version-tag" style="color:var(--text-subtle);font-size:var(--text-xs);font-weight:var(--weight-regular)">v1</span><br><span style="color:var(--text-subtle);font-size:var(--text-sm)">${k.subtitle}</span></td>
      <td data-label="Sources" class="num">${k.sources.toLocaleString()}</td>
      <td data-label="Processing">
        <div style="display:flex;align-items:center;gap:var(--space-2)">
          <div style="flex:1;max-width:80px;height:6px;background:var(--surface-sunken);border-radius:3px;overflow:hidden"><div style="width:${pct}%;height:100%;background:${pct === 100 ? 'var(--success)' : 'var(--info)'}"></div></div>
          <span class="num" style="min-width:34px">${pct}%</span>
        </div>
      </td>
      <td data-label="Conflicts" class="num">${k.conflicts > 0 ? badge('warning', 'conflict', String(k.conflicts)) : badge('success', 'status-completed', '0')}</td>
      <td data-label="Evidence">${k.gaps > 0 ? badge('warning', 'gap', k.gaps + ' open') : badge('success', 'status-completed', 'Reviewed')}</td>
      <td data-label="Approval">${k.approved ? badge('success', 'status-completed', 'Approved') : badge('warning', 'status-warning', 'Needs review')}</td>
      <td data-label="Action needed">${k.actionNote ? k.actionNote : '<span style="color:var(--text-subtle)">None</span>'}</td>
      <td data-label="Updated" class="updated-cell">${k.updated}</td>
      <td data-label="Research"><button type="button" class="btn research-again-btn" data-entity="${k.id}" title="Re-run research on new/updated sources — creates a new version, never overwrites this one">${ic('research')}<span class="visually-hidden">Research again for ${k.subtitle}</span></button></td>
    </tr>`;
}

function knowledgeCard(k) {
  const pct = Math.round((k.processed / k.sources) * 100);
  return `
    <div class="card" data-entity="${k.id}" data-version="1" style="display:flex;flex-direction:column;gap:var(--space-2)">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:var(--space-2)">
        <div><a href="#screen-knowledge-${k.id}" style="font-weight:var(--weight-semibold);text-decoration:none;color:var(--text)"><bdi lang="fa" dir="rtl">${k.title}</bdi></a> <span class="version-tag" style="color:var(--text-subtle);font-size:var(--text-xs)">v1</span><div style="color:var(--text-subtle);font-size:var(--text-sm)">${k.subtitle}</div></div>
        <button type="button" class="btn btn--icon research-again-btn" data-entity="${k.id}" title="Re-run research — creates a new version" aria-label="Research again for ${k.subtitle}">${ic('research')}</button>
      </div>
      <div style="display:flex;align-items:center;gap:var(--space-2)">
        <div style="flex:1;height:6px;background:var(--surface-sunken);border-radius:3px;overflow:hidden"><div style="width:${pct}%;height:100%;background:${pct === 100 ? 'var(--success)' : 'var(--info)'}"></div></div>
        <span class="num" style="min-width:34px;font-size:var(--text-sm)">${pct}%</span>
      </div>
      <dl class="kv" style="margin:0">
        <dt>Sources</dt><dd>${k.sources.toLocaleString()}</dd>
        <dt>Conflicts</dt><dd>${k.conflicts}</dd>
        <dt>Approval</dt><dd>${k.approved ? badge('success', 'status-completed', 'Approved') : badge('warning', 'status-warning', 'Needs review')}</dd>
        <dt>Updated</dt><dd class="updated-cell">${k.updated}</dd>
      </dl>
    </div>`;
}

const screenKnowledgeList = `
<section class="screen" id="screen-knowledge" aria-labelledby="h-know-list">
  <div class="page-header">
    <div><h1 id="h-know-list">${ic('knowledge', { lg: true })} Knowledge Objects</h1><p>Every keyword gets a dedicated object — complete with its own sources, claims, evidence, conflicts, gaps, and AI-visibility report. Click any Knowledge object to open its full, standalone management window.</p></div>
    <div class="page-actions"><button class="btn btn--primary">${ic('action-add')}New knowledge object</button></div>
  </div>
  <div class="toolbar" style="display:flex;flex-wrap:wrap;gap:var(--space-3);align-items:center;margin-block-end:var(--space-4)">
    <label style="flex:1 1 260px;min-width:200px">
      <span class="visually-hidden">Search knowledge objects</span>
      <input type="search" placeholder="Search by keywords - e.g. Toranjebin…" style="width:100%;font:inherit;padding:8px 12px;min-height:36px;border:1px solid var(--border-strong);border-radius:var(--radius-sm);background:var(--surface);color:var(--text)">
    </label>
    <button class="btn">${ic('action-filter')}Filter</button>
    <button class="btn">${ic('action-sort')}Sort: Open conflicts</button>
    <div class="view-toggle" role="group" aria-label="Display mode" style="display:flex;border:1px solid var(--border-strong);border-radius:var(--radius-sm);overflow:hidden">
      <button type="button" class="btn view-toggle__btn" data-view="table" aria-pressed="true" aria-label="Rows view" style="border:0;border-radius:0">${ic('view-list')}</button>
      <button type="button" class="btn view-toggle__btn" data-view="grid" aria-pressed="false" aria-label="Windowed view" style="border:0;border-radius:0;border-inline-start:1px solid var(--border-strong)">${ic('apps')}</button>
    </div>
  </div>
  <div class="callout"><span class="callout__icon">${ic('info')}</span>
    <div><p>A knowledge object is created from research or from sources contributing enough claims and evidence to support one — never fabricated because a query volume looked promising. Nothing here caps how many an organization can hold: this screen is built to hold tens, hundreds or thousands of them, searched/filtered/sorted/paginated server-side the same way <a href="#screen-sources">Sources &amp; Documents</a> is — the browser is never handed the whole collection at once. "Research again" on any row starts a new processing run against whatever sources have been added since — it creates a new version alongside the last one, never overwrites it.</p></div>
  </div>
  <div id="know-view-table">
  <table class="table sortable" style="margin-top:var(--space-4)">
    <caption class="visually-hidden">Knowledge objects, one row per keyword/entity, newest version first within each entity</caption>
    <thead><tr>
      <th scope="col">Knowledge object</th><th scope="col">Sources</th><th scope="col">Processing</th>
      <th scope="col">Conflicts</th><th scope="col">Evidence</th><th scope="col">Approval</th>
      <th scope="col">Action needed</th><th scope="col">Updated</th><th scope="col" data-no-sort>Research</th>
    </tr></thead>
    <tbody>${KNOWLEDGE_OBJECTS.map(knowledgeRow).join('')}</tbody>
  </table>
  </div>
  <div id="know-view-grid" hidden style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:var(--space-4);margin-top:var(--space-4)">${KNOWLEDGE_OBJECTS.map(knowledgeCard).join('')}</div>
  <p style="color:var(--text-subtle);font-size:var(--text-sm);margin-top:var(--space-4)">
    Showing 4 of 4 in this fixture — representing an organization that may really hold thousands. Search, filter and sort narrow the server-side query; the page size stays fixed either way.
  </p>
</section>`;


// Per-keyword visibility summary — deterministic fixture numbers derived
// from the object's own id, so each of potentially hundreds of Knowledge
// objects gets ITS OWN numbers instead of all sharing one global fixture
// (the owner's core point: with dozens/hundreds/thousands of keywords,
// every one needs its own independently reportable visibility, not a
// single shared card). This still reads the same underlying dimensions
// (platform observations, automated requests, geography, dwell) as the
// site-wide report at #screen-visibility-detail — it is a scoped view of
// the same data, not a second analytics system.
function seedFrom(id) {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0;
  return h;
}
function keywordVisibilitySummary(k) {
  const seed = seedFrom(k.id);
  const obs = 8 + (seed % 40);
  const req = 120 + (seed % 900);
  const series = Array.from({ length: 14 }, (_, i) => 2 + ((seed >> (i % 20)) % 12) + i % 3);
  const topCountry = GEO_POINTS[seed % GEO_POINTS.length];
  const secondCountry = GEO_POINTS[(seed + 1) % GEO_POINTS.length];
  return `
  <div class="card">
    <h2 class="card__title" style="display:flex;align-items:center;gap:var(--space-2)">${ic('visibility')}AI visibility for <bdi lang="fa" dir="rtl">${k.title}</bdi></h2>
    <p style="color:var(--text-muted);margin-top:0">Scoped to pages about <bdi lang="fa" dir="rtl">${k.title}</bdi> only — the same fields as the site-wide report, filtered to this keyword. <a href="#screen-visibility-detail">Open the site-wide report</a> to compare across all keywords.</p>
    <div class="stat-grid">
      <div class="stat"><span class="stat__label">${ic('visibility')}Platform observations (28d)</span><span class="stat__value">${obs}</span></div>
      <div class="stat"><span class="stat__label">${ic('agent')}Automated requests (28d)</span><span class="stat__value">${req.toLocaleString()}</span></div>
      <div class="stat"><span class="stat__label">${ic('geography')}Top country</span><span class="stat__value" style="font-size:var(--text-lg)">${topCountry.name}</span></div>
    </div>
    <div role="img" aria-label="Automated requests for this keyword, last 14 days" style="display:flex;align-items:flex-end;gap:2px;height:48px;margin-top:var(--space-3)">
      ${series.map(v => `<div style="flex:1;height:${Math.max(6, v * 6)}px;background:var(--info);border-radius:1px 1px 0 0"></div>`).join('')}
    </div>
    <table class="table sortable" style="margin-top:var(--space-3)">
      <caption class="visually-hidden">Requests by country for this keyword</caption>
      <thead><tr><th scope="col">Country</th><th scope="col">Requests</th></tr></thead>
      <tbody>
        <tr><td data-label="Country"><bdi>${topCountry.name}</bdi></td><td data-label="Requests" class="num">${Math.round(req * 0.6).toLocaleString()}</td></tr>
        <tr><td data-label="Country"><bdi>${secondCountry.name}</bdi></td><td data-label="Requests" class="num">${Math.round(req * 0.22).toLocaleString()}</td></tr>
      </tbody>
    </table>
    <p style="color:var(--text-subtle);font-size:var(--text-sm);margin-top:var(--space-3);margin-block-end:0">Fixture numbers, deterministic per keyword id — not a claim about real Toranjebin traffic. In production this is one filtered query against the same <code>page_views</code>/<code>search_demand_events</code> tables the site-wide report reads, not a separate per-keyword pipeline.</p>
  </div>`;
}

function knowledgeDetailScreen(k) {
  return `
<section class="screen" id="screen-knowledge-${k.id}" aria-labelledby="h-know-${k.id}">
  <nav class="breadcrumbs" aria-label="Breadcrumb"><a href="#screen-knowledge">Knowledge</a>${ic('action-expand')}<span lang="fa" dir="rtl">${k.title}</span></nav>
  <div class="page-header">
    <div><h1 id="h-know-${k.id}" lang="fa" dir="rtl">${k.title}</h1><p>${k.subtitle} · published · knowledge updated ${k.updated}</p></div>
    <div class="page-actions">
      <button class="btn">${ic('provenance-trace')}Trace a statement</button>
      <a class="btn" href="#screen-states">${ic('action-archive')}Archive / delete</a>
    </div>
  </div>

  <div class="stat-grid">
    <div class="stat"><span class="stat__label">${ic('sources')}Sources</span><span class="stat__value">${k.sources.toLocaleString()}</span></div>
    <div class="stat"><span class="stat__label">${ic('provenance-claim')}Claims</span><span class="stat__value">${k.claims.toLocaleString()}</span></div>
    <div class="stat"><span class="stat__label">${ic('provenance-evidence')}Evidence</span><span class="stat__value">${k.evidence.toLocaleString()}</span><span class="stat__note">of which ${k.verified.toLocaleString()} verified</span></div>
    <div class="stat${k.conflicts > 0 ? ' stat--attention' : ''}"><span class="stat__label">${ic('conflict')}Conflicts</span><span class="stat__value">${k.conflicts}</span><span class="stat__note">${k.gaps} gaps open</span></div>
  </div>

  ${keywordVisibilitySummary(k)}

  <div class="card">
    <h2 class="card__title">Evidence by kind</h2>
    <p style="color:var(--text-muted);margin-top:0">Traditional use and clinical evidence are different claims about different things. The interface never lets one stand in for the other.</p>
    <dl class="kv">
      ${k.evidenceByKind.map(([label, variant, icon, text, detail]) => `<dt>${label}</dt><dd>${badge(variant, icon, text)} ${detail}</dd>`).join('\n      ')}
    </dl>
    <div class="callout" style="margin-top:var(--space-4)"><span class="callout__icon">${ic('gap')}</span>
      <div><p><strong>Knowledge gap:</strong> ${k.gapNote}</p>
      <p><a href="#screen-gap">Open this gap</a></p></div>
    </div>
  </div>
</section>`;
}

const screenKnowledge = screenKnowledgeList;
const KNOWLEDGE_DETAIL_SCREENS = KNOWLEDGE_OBJECTS.map(k => [`screen-knowledge-${k.id}`, k.title.replace(/<[^>]+>/g, ''), knowledgeDetailScreen(k)]);

const GAP_ACTION_ICON = { search: 'action-search', upload: 'action-upload', keep: 'action-restore' };

function gapActionButton(a, idx) {
  const icon = GAP_ACTION_ICON[a.kind];
  const cls = idx === 0 ? 'btn btn--primary' : 'btn';
  const href = a.kind === 'upload' ? '#screen-add' : '#screen-gap';
  return `
    <li class="choice">
      <span class="choice__icon">${ic(icon, { size: '20px' })}</span>
      <span>
        <span class="choice__title">${a.label}</span>
        <span class="choice__body">${a.detail}</span>
      </span>
      <a class="${cls}" href="${href}">${a.label}</a>
    </li>`;
}

const screenGap = `
<section class="screen" id="screen-gap" aria-labelledby="h-gap">
  <nav class="breadcrumbs" aria-label="Breadcrumb"><a href="#screen-knowledge-taranjebin">${fa('ترنجبین')}</a>${ic('action-expand')}<span>Knowledge gap</span></nav>
  <div class="page-header">
    <div>
      <h1 id="h-gap">${GAPS[0].title}</h1>
      <p>${id(GAPS[0].id)} · ${GAPS[0].typeLabel} · part of ${fa('ترنجبین')} (Toranjebin)</p>
      <p style="margin-top:var(--space-2)">${badge('warning', 'status-warning', 'Open')}</p>
    </div>
  </div>

  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:var(--space-4);align-items:start">
    <div class="card">
      <h2 class="card__title">What has already been checked</h2>
      <dl class="kv">
        ${GAPS[0].checked.map(([label, variant, iconName, text]) => `<dt>${label}</dt><dd>${badge(variant, iconName, text)}</dd>`).join('')}
      </dl>
      <div class="callout" style="margin-top:var(--space-4)"><span class="callout__icon">${ic('gap')}</span>
        <div><p>${GAPS[0].note}</p></div>
      </div>
    </div>

    <div class="card">
      <h2 class="card__title">Close this gap</h2>
      <p style="color:var(--text-muted);margin-top:0">Three different things you can do — none of them fabricates an answer.</p>
      <ul class="choice-list">
        ${GAPS[0].actions.map(gapActionButton).join('')}
      </ul>
    </div>
  </div>

  <div class="card" style="margin-top:var(--space-4)">
    <h2 class="card__title">Other open gaps on this knowledge object</h2>
    <p style="color:var(--text-muted);margin-top:0">The recommended action follows the gap type — a supplier-certificate gap has no “search the web” button, and a conflict gap is closed by review, not by search or upload.</p>
    <div class="table-wrap">
      <table class="table sortable">
        <caption class="visually-hidden">Other knowledge gaps for this knowledge object</caption>
        <thead><tr><th scope="col">Gap</th><th scope="col">Status</th><th scope="col"><span class="visually-hidden">Action</span></th></tr></thead>
        <tbody>${GAPS.slice(1).map(gapRow).join('')}</tbody>
      </table>
    </div>
  </div>
</section>`;

/* ---------------------------------------------------------- AI visibility
 * Two real, separate backend systems, deliberately not merged into one
 * "visibility score" (§59, ADR-064 forbids exactly that):
 *  - VisibilityTest (Cloud, Phase 10): outbound probes — "we asked ChatGPT
 *    a question, did it mention/cite/recommend us." Tri-state signals
 *    (Present/Absent/Not checked), never boolean, because a header saying
 *    false could mean "checked, absent" or "never checked" (ADR-061).
 *  - AIOL_Actors (WordPress plugin, ADR-046): inbound traffic — which
 *    requests hit the site and what sent them. A User-Agent is a claim,
 *    not an identity, so every row carries a confidence (Detected /
 *    Probable / Verified — Verified not implemented, no reverse-DNS yet),
 *    never presented as fact. Humans are not logged; no IP, no query
 *    string. This is a narrower, more honest system than turn 131 of the
 *    original brief asked for — no geography, no dwell time — and that
 *    narrowing is a documented privacy decision (ADR-046), not an
 *    oversight, so the screen states it rather than quietly matching it.
 */
const SIGNAL_ROWS = [
  ['Mentioned', 'success', 'status-completed', 'present', 'The brand appeared in the answer.'],
  ['Cited', 'unknown', 'status-unknown', 'not_checked', 'Whether a source link was attached was not examined in this batch.'],
  ['Recommended', 'success', 'status-completed', 'present', 'Named as a suggested option, not just mentioned.'],
  ['Product shown', 'warning', 'status-warning', 'absent', 'Checked for, and not present — a real negative finding, not a gap in the data.'],
  ['URL present', 'unknown', 'status-unknown', 'not_checked', 'Not examined in this batch.'],
];

const PLATFORM_ROWS = [
  ['ChatGPT', '18 observations', 'Sep 12'],
  ['Gemini', '9 observations', 'Sep 10'],
  ['Perplexity', '14 observations', 'Sep 14'],
  ['Google (AI Overview)', '6 observations', 'Sep 9'],
];

const ACTOR_ROWS = [
  ['AI crawler (indexing)', 'GPTBot (OpenAI)', 'Detected', '412'],
  ['AI crawler (indexing)', 'ClaudeBot (Anthropic)', 'Detected', '288'],
  ['AI answering a user', 'ChatGPT-User (OpenAI)', 'Detected', '97'],
  ['AI answering a user', 'Perplexity-User (Perplexity)', 'Detected', '61'],
  ['Search crawler', 'Googlebot (Google)', 'Detected', '1,204'],
  ['Unrecognised automated client', '—', 'Probable', '23'],
];

function actorRow([type, label, confidence, count]) {
  const confVariant = confidence === 'Detected' ? 'info' : confidence === 'Verified' ? 'success' : 'warning';
  return `
    <tr>
      <td data-label="Actor type">${type}</td>
      <td data-label="Signature">${label === '—' ? na('No known signature matched') : `<span class="identifier" style="font-family:var(--font-mono)">${label}</span>`}</td>
      <td data-label="Confidence">${badge(confVariant, 'status-unknown', confidence)}</td>
      <td data-label="Requests (30d)" class="num">${count}</td>
    </tr>`;
}

const screenVisibility = `
<section class="screen" id="screen-visibility" aria-labelledby="h-visibility">
  <div class="page-header">
    <div>
      <h1 id="h-visibility">AI Visibility</h1>
      <p>Two different questions, kept separate on purpose: how AI platforms answer about you, and which AI systems actually visit your site.</p>
    </div>
  </div>

  <div class="card">
    <h2 class="card__title">How AI platforms answer about you</h2>
    <p style="color:var(--text-muted);margin-top:0">47 observations across 4 platforms, last 30 days. This is a sample of specific prompts on specific days — not a claim about every possible question, and not a score (ADR-064 forbids collapsing these into one number). <a href="#screen-visibility-detail">Open the full report</a>.</p>
    <dl class="kv">
      ${SIGNAL_ROWS.map(([label, variant, iconName, , tip]) => `<dt>${label}</dt><dd>${badge(variant, iconName, tip)}</dd>`).join('')}
    </dl>
    <div class="table-wrap" style="margin-top:var(--space-4)">
      <table class="table sortable">
        <caption class="visually-hidden">Observations by platform</caption>
        <thead><tr><th scope="col">Platform</th><th scope="col">Volume</th><th scope="col">Most recent</th></tr></thead>
        <tbody>${PLATFORM_ROWS.map(([p, v, d]) => `<tr><td data-label="Platform">${p}</td><td data-label="Volume">${v}</td><td data-label="Most recent">${d}</td></tr>`).join('')}</tbody>
      </table>
    </div>
    <p style="color:var(--text-subtle);font-size:var(--text-sm);margin-block-end:0">Click, and purchase that followed a click, have no columns here on purpose — a click happens in the platform's own interface, out of reach; a purchase belongs to commerce data, not to this observation (see the model's own documentation, ADR-062). Guessing either would be a fabricated number wearing a real one's clothes.</p>
  </div>

  <div class="card" style="margin-top:var(--space-4)">
    <h2 class="card__title">Who is actually visiting your site</h2>
    <p style="color:var(--text-muted);margin-top:0">2,085 automated requests, last 30 days. Ordinary human visitors are never logged here — this exists to understand machine access, not to track people.</p>
    <div class="table-wrap">
      <table class="table sortable">
        <caption class="visually-hidden">Traffic by detected actor type</caption>
        <thead><tr><th scope="col">Actor type</th><th scope="col">Signature</th><th scope="col">Confidence</th><th scope="col">Requests (30d)</th></tr></thead>
        <tbody>${ACTOR_ROWS.map(actorRow).join('')}</tbody>
      </table>
    </div>
    <div class="callout" style="margin-top:var(--space-4)"><span class="callout__icon">${ic('status-unknown')}</span>
      <div><p>A User-Agent header is a claim a request makes about itself, not a verified identity — anyone can send <span class="identifier" style="font-family:var(--font-mono)">"ClaudeBot"</span>. Every row above is <strong>Detected</strong> (header matched) or <strong>Probable</strong> (weaker pattern); <strong>Verified</strong> would need reverse-DNS confirmation, which is not built yet. Location and time-on-site ARE now collected, by an explicit owner decision recorded as ADR-079, which supersedes the earlier narrowing in ADR-046 (kept on file, unedited). See <a href="#screen-analytics">Analytics</a> for what is stored and for how long.</p></div>
    </div>
  </div>
</section>`;

// ---------------------------------------------------------------------------
// Visibility detail — the click-through from "Visible to AI right now".
//
// Deliberately built on the two signals the product already keeps
// separate (platform observations vs automated requests, ADR-064) rather
// than borrowing Search Console's "clicks/impressions" vocabulary
// wholesale: those are search-engine-specific concepts this product does
// not have a source for, and labeling something "Clicks" without a real
// click event behind it would be exactly the fabricated-metric problem
// ADR-064 and the AI Visibility screen above both refuse to do.
//
// What IS real: the country/actor/page breakdown below reads the same
// shape of data as the actual `content-stats` and `page-views` endpoints
// (Phase 13). The chart and the map are fixture-drawn for this static
// harness, same as every other number on this page (see the banner).
// ---------------------------------------------------------------------------

// Matches Search Console's actual Performance-report date picker (24
// hours / 7 / 28 days / 3 / 6 / 12 / 16 months — Search Console's own
// retention ceiling, not a round number) plus a 'Live' entry for the
// Realtime-style panel below, which GSC does not have but GA4 does.
// Source: Search Console help + reporting docs, checked online per the
// owner's request rather than assumed from memory.
const TIME_RANGES = ['Live', '24 hours', '7 days', '28 days', '3 months', '6 months', '12 months', '16 months'];

function timeRangeTabs(active) {
  return `<div class="tabs" role="tablist" aria-label="Time range">` +
    TIME_RANGES.map(r => `<button role="tab" aria-selected="${r === active}">${r}</button>`).join('') +
    `</div>`;
}

// Fixture series: platform observations (AI mentioning/citing) vs
// automated requests (bots/agents actually fetching), last 28 days.
const OBS_SERIES = [3,4,2,5,6,4,7,8,6,9,11,9,12,14,11,13,15,12,16,18,15,17,19,16,20,22,19,21];
const REQ_SERIES = [58,64,52,70,74,66,81,88,79,95,103,92,110,121,107,118,129,114,132,140,125,138,148,131,152,161,144,156];

function sparkChart(seriesA, seriesB, days) {
  // Pure CSS, not SVG — every <svg> in this harness must be a registry
  // icon (§56/§57); a 700×160 chart is not an icon, and giving it the
  // icon class to satisfy the checker would be gaming the check rather
  // than respecting the rule it enforces. Paired bars per day instead.
  const max = Math.max(...seriesA, ...seriesB);
  const bars = seriesA.map((a, i) => {
    const b = seriesB[i];
    const hA = Math.max(2, Math.round((a / max) * 100));
    const hB = Math.max(2, Math.round((b / max) * 100));
    return `
      <div style="display:flex;align-items:flex-end;gap:1px;height:100%;flex:1 1 0;min-width:6px" title="Day ${i + 1}: ${a} observations, ${b} requests">
        <div style="flex:1;height:${hA}%;background:var(--primary);border-radius:1px 1px 0 0"></div>
        <div style="flex:1;height:${hB}%;background:var(--info);border-radius:1px 1px 0 0"></div>
      </div>`;
  }).join('');
  return `<div role="img" aria-label="Platform observations and automated requests, last ${days} days" style="display:flex;align-items:flex-end;gap:3px;height:160px;padding:var(--space-2) 0;border-bottom:1px solid var(--border)">${bars}</div>`;
}


const VISIBILITY_TABS = ['Queries', 'Pages', 'Countries', 'Actor types', 'Days'];

const TOP_QUERY_ROWS = [
  [fa('ترنجبین چیست'), 34, 412, fa('ترنجبین')],
  [fa('خرید ترنجبین اصل'), 21, 331, fa('ترنجبین')],
  ['taranjabin grade a', 12, 96, 'Taranjabin — Grade A'],
  [fa('زعفران نگین قیمت'), 9, 260, fa('زعفران')],
  ['mannitol content taranjabin', 4, 58, fa('ترنجبین')],
];

function visibilityQueryRow([q, obs, req, page]) {
  return `<tr><td data-label="Query"><bdi>${q}</bdi></td><td data-label="Platform observations" class="num">${obs}</td><td data-label="Automated requests" class="num">${req}</td><td data-label="Related page">${page}</td></tr>`;
}


// Realtime-style panel, modelled on GA4's Realtime report (checked
// online per the owner's request): active count for the last 30
// minutes, a per-minute chart, and "right now" breakdowns by page,
// country and actor type. GA4 also breaks realtime down by device —
// there is no equivalent concept for bot/crawler traffic here, so
// actor type (crawler / AI user-agent / agent tool / search crawler)
// is used instead of inventing a device dimension that doesn't apply.
const LIVE_PER_MINUTE = [2,3,1,4,5,3,6,4,7,5,8,6,5,9,7,6,10,8,7,11,9,8,12,10,9,13,11,10,14,12];
const LIVE_PAGES = [
  [fa('ترنجبین | صفحه اصلی'), 6],
  [fa('خرید ترنجبین اصل'), 4],
  ['Taranjabin — Grade A', 3],
  [fa('زعفران نگین'), 2],
  [fa('سیر ترنجبین'), 1],
];
const LIVE_COUNTRIES = [
  [fa('ایران'), 9], ['United States', 3], ['Germany', 1], [fa('ترکیه'), 1],
];
const LIVE_ACTORS = [
  ['AI crawler', 7, 'var(--primary)'],
  ['AI user-agent', 4, 'var(--info)'],
  ['Search crawler', 2, 'var(--text-subtle)'],
  ['Agent tool', 1, 'var(--warning)'],
];

function liveActivityPanel(scope) {
  const total = LIVE_PER_MINUTE.reduce((a, b) => a + b, 0);
  const maxPerMin = Math.max(...LIVE_PER_MINUTE);
  const bars = LIVE_PER_MINUTE.map((v, i) =>
    `<div style="flex:1 1 0;min-width:3px;height:${Math.max(4, Math.round(v / maxPerMin * 100))}%;background:var(--primary);border-radius:1px 1px 0 0" title="${30 - i} min ago: ${v}"></div>`
  ).join('');
  const maxActor = Math.max(...LIVE_ACTORS.map(a => a[1]));
  return `
  <div class="card" style="border-color:var(--success);border-inline-start-width:3px">
    <h2 class="card__title" style="display:flex;align-items:center;gap:var(--space-2)">
      <span aria-hidden="true" style="display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--success);box-shadow:0 0 0 3px color-mix(in srgb, var(--success) 25%, transparent)"></span>
      Right now${scope ? ` — <bdi lang="fa" dir="rtl">${scope}</bdi>` : ''}
    </h2>
    <p style="color:var(--text-muted);margin-top:0">Last 30 minutes, refreshed continuously in production — this harness is a static fixture, not a live connection.</p>
    <div class="stat-grid">
      <div class="stat"><span class="stat__label">${ic('visibility')}Requests, last 30 min</span><span class="stat__value">${total}</span></div>
      <div class="stat"><span class="stat__label">${ic('agent')}Distinct agents active</span><span class="stat__value">6</span></div>
      <div class="stat"><span class="stat__label">${ic('geography')}Countries active</span><span class="stat__value">${LIVE_COUNTRIES.length}</span></div>
    </div>
    <div role="img" aria-label="Requests per minute, last 30 minutes" style="display:flex;align-items:flex-end;gap:2px;height:64px;margin-top:var(--space-4)">${bars}</div>
    <p style="color:var(--text-subtle);font-size:var(--text-sm);margin-top:var(--space-1)">30 minutes ago, left to right, ending now</p>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:var(--space-4);margin-top:var(--space-4)">
      <div>
        <h3 style="font-size:var(--text-sm);color:var(--text-muted);margin-block-end:var(--space-2)">Pages right now</h3>
        <table class="table sortable"><caption class="visually-hidden">Pages being fetched right now</caption>
          <tbody>${LIVE_PAGES.map(([p, n]) => `<tr><td data-label="Page"><bdi>${p}</bdi></td><td data-label="Active" class="num">${n}</td></tr>`).join('')}</tbody>
        </table>
      </div>
      <div>
        <h3 style="font-size:var(--text-sm);color:var(--text-muted);margin-block-end:var(--space-2)">Countries right now</h3>
        <table class="table sortable"><caption class="visually-hidden">Countries active right now</caption>
          <tbody>${LIVE_COUNTRIES.map(([c, n]) => `<tr><td data-label="Country"><bdi>${c}</bdi></td><td data-label="Active" class="num">${n}</td></tr>`).join('')}</tbody>
        </table>
      </div>
      <div>
        <h3 style="font-size:var(--text-sm);color:var(--text-muted);margin-block-end:var(--space-2)">Actor type right now</h3>
        <div style="display:grid;gap:var(--space-2)">
          ${LIVE_ACTORS.map(([name, n, color]) => `
            <div style="display:flex;align-items:center;gap:var(--space-2)">
              <span style="width:80px;font-size:var(--text-sm);color:var(--text-muted)">${name}</span>
              <div style="flex:1;height:8px;background:var(--surface-sunken);border-radius:4px;overflow:hidden"><div style="width:${(n / maxActor * 100).toFixed(0)}%;height:100%;background:${color}"></div></div>
              <span class="num" style="width:20px;text-align:end">${n}</span>
            </div>`).join('')}
        </div>
      </div>
    </div>
  </div>`;
}

const screenVisibilityDetail = `
<section class="screen" id="screen-visibility-detail" aria-labelledby="h-vis-detail">
  <nav class="breadcrumbs" aria-label="Breadcrumb"><a href="#screen-dashboard">Dashboard</a>${ic('action-expand')}<a href="#screen-visibility">AI Visibility</a>${ic('action-expand')}<span>Full report</span></nav>
  <div class="page-header">
    <div>
      <h1 id="h-vis-detail">${ic('analytics', { lg: true })} Visible to AI — full report</h1>
      <p>Everything behind the two numbers on the dashboard, broken down by time, location, page and query — and exportable.</p>
    </div>
    <div class="page-actions">
      <button class="btn">${ic('action-download')}Export CSV</button>
      <button class="btn">${ic('action-download')}Export PDF</button>
    </div>
  </div>

  ${timeRangeTabs('28 days')}

  ${liveActivityPanel()}

  <div class="stat-grid" style="margin-top:var(--space-4)">
    <div class="stat"><span class="stat__label">${ic('visibility')}Platform observations</span><span class="stat__value">47</span><span class="stat__note">4 platforms, 28 days</span></div>
    <div class="stat"><span class="stat__label">${ic('agent')}Automated requests</span><span class="stat__value">2,085</span><span class="stat__note">11 distinct agents, 28 days</span></div>
    <div class="stat"><span class="stat__label">${ic('geography')}Countries reached</span><span class="stat__value">${GEO_POINTS.length}</span></div>
    <div class="stat"><span class="stat__label">${ic('dwell')}Mean time on page</span><span class="stat__value">2m 41s</span><span class="stat__note">from 704 measured views</span></div>
  </div>

  <div class="card" style="margin-top:var(--space-4)">
    <h2 class="card__title">Over time</h2>
    <p style="color:var(--text-muted);margin-top:0;display:flex;align-items:center;gap:var(--space-2)">
      <span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:var(--primary)"></span> Platform observations
      <span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:var(--info);margin-inline-start:var(--space-3)"></span> Automated requests
    </p>
    ${sparkChart(OBS_SERIES, REQ_SERIES, 28)}
    <p style="color:var(--text-subtle);font-size:var(--text-sm);margin-block-end:0">Two different sources, drawn on one timeline for comparison only — they are never added into a single number (ADR-064). Platform observations come from sampled prompts on specific days; automated requests are every AI/bot fetch this site recorded.</p>
  </div>

  <div class="card" style="margin-top:var(--space-4)">
    <h2 class="card__title">${ic('geography')} Where requests came from</h2>
    ${schematicMap()}
    <p style="color:var(--text-subtle);font-size:var(--text-sm);margin-top:var(--space-3)">A stylized dot map, not a rendered geographic dataset — the background dots approximate continent outlines from a handful of coarse regions, not real coastline data, and exist only so the shape reads as "a world map" at a glance. Country markers sit at an approximate centroid; marker size is proportional to request volume. This reads the same <code>geo_country</code> field shown in the Analytics screen's location table, with its own honest "How we know" column.</p>
    <div class="table-wrap" style="margin-top:var(--space-4)">
      <table class="table sortable">
        <caption class="visually-hidden">Request volume by country</caption>
        <thead><tr><th scope="col">Country</th><th scope="col">Requests</th></tr></thead>
        <tbody>${GEO_POINTS.slice().sort((a, b) => b.n - a.n).map(p => `<tr><td data-label="Country">${p.name} (${p.code})</td><td data-label="Requests" class="num">${p.n.toLocaleString()}</td></tr>`).join('')}</tbody>
      </table>
    </div>
  </div>

  <div class="card" style="margin-top:var(--space-4)">
    <h2 class="card__title">Breakdown</h2>
    <div class="tabs" role="tablist" aria-label="Breakdown dimension">
      ${VISIBILITY_TABS.map((t, i) => `<button role="tab" aria-selected="${i === 0}">${t}</button>`).join('')}
    </div>
    <div class="table-wrap" style="margin-top:var(--space-3)">
      <table class="table sortable">
        <caption class="visually-hidden">Top queries, ranked by combined observation and request volume</caption>
        <thead><tr><th scope="col">Query</th><th scope="col">Platform observations</th><th scope="col">Automated requests</th><th scope="col">Related page</th></tr></thead>
        <tbody>${TOP_QUERY_ROWS.map(visibilityQueryRow).join('')}</tbody>
      </table>
    </div>
    <p style="color:var(--text-subtle);font-size:var(--text-sm);margin-block-end:0">The Pages, Countries, Actor types and Days tabs read the same rows shown elsewhere on this page and on <a href="#screen-analytics">Analytics</a>, re-sorted by that dimension — this table is not a second copy of the data, only a different sort of it.</p>
  </div>
</section>`;

const screenStates = `
<section class="screen" id="screen-states" aria-labelledby="h-states">
  <div class="page-header"><div><h1 id="h-states">Edge states</h1><p>Duplicate, destructive, failed, and empty — the screens a demo usually skips.</p></div></div>

  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:var(--space-4);align-items:start">

    <div class="dialog" role="dialog" aria-labelledby="dlg-dup">
      <h2 id="dlg-dup">${ic('duplicate')} This file is already here</h2>
      <p style="color:var(--text-muted)">Identical bytes to a source uploaded on 2 Sep 2026.</p>
      <dl class="kv" style="margin-top:var(--space-4)">
        <dt>Existing source</dt><dd>Toranjebin — Scientific Review 2025</dd>
        <dt>Match</dt><dd>${badge('info', 'status-completed', 'Exact duplicate')} SHA-256 identical</dd>
        <dt>SHA-256</dt><dd>${id('c1f4a97b…8e2b')}</dd>
      </dl>
      <div class="dialog__actions">
        <button class="btn">Cancel</button><button class="btn">Keep both</button>
        <button class="btn btn--primary">Open existing</button>
      </div>
    </div>

    <div class="dialog" role="dialog" aria-labelledby="dlg-ver">
      <h2 id="dlg-ver">${ic('provenance-version')} Possibly a newer version</h2>
      <p style="color:var(--text-muted)">The wording is hedged on purpose. Nothing here is asserted as identity.</p>
      <dl class="kv" style="margin-top:var(--space-4)">
        <dt>Related to</dt><dd>Toranjebin Review 2024</dd>
        <dt>Match</dt><dd>${badge('warning', 'status-warning', 'Possible related version')}</dd>
        <dt>Differences</dt><dd>7 new sections · 12 modified passages · 2 removed tables</dd>
      </dl>
      <div class="dialog__actions">
        <button class="btn">Cancel</button><button class="btn">Add as new source</button>
        <button class="btn btn--primary">Link as a new version</button>
      </div>
    </div>

    <div class="dialog" role="dialog" aria-labelledby="dlg-arch">
      <h2 id="dlg-arch">${ic('action-archive')} Archive this source?</h2>
      <p style="color:var(--text-muted)">Other things depend on it. Archiving stops it being used; it does not erase what it supported.</p>
      <dl class="kv" style="margin-top:var(--space-4)">
        <dt>Knowledge objects</dt><dd class="num">3</dd>
        <dt>Claims</dt><dd class="num">74</dd>
        <dt>Evidence records</dt><dd class="num">31</dd>
        <dt>Research projects</dt><dd class="num">2</dd>
      </dl>
      <div class="dialog__actions"><button class="btn">Cancel</button><button class="btn btn--danger">Archive source</button></div>
    </div>

    <div class="dialog" role="dialog" aria-labelledby="dlg-del-source" style="grid-column:1/-1;max-inline-size:640px">
      <h2 id="dlg-del-source">${ic('action-delete')} Delete “Toranjebin — Scientific Review 2025”?</h2>
      <p style="color:var(--text-muted)">This source contributes to 3 knowledge objects, 74 claims and 31 evidence records. Choose how far this goes — the choice is explicit, never a single generic “Delete” (§22).</p>
      <ul class="choice-list">
        <li class="choice">
          <span class="choice__icon">${ic('action-archive', { size: '20px' })}</span>
          <span><span class="choice__title">Archive source</span>
          <span class="choice__body">Stops it being used by anything new. Every claim, evidence record and knowledge contribution it already produced is untouched.</span></span>
          <button type="button" class="btn">Archive instead</button>
        </li>
        <li class="choice">
          <span class="choice__icon">${ic('provenance-relation', { size: '20px' })}</span>
          <span><span class="choice__title">Remove from active knowledge</span>
          <span class="choice__body">The source can no longer be cited by future work. Existing claims and evidence stay published, unchanged.</span></span>
          <button type="button" class="btn">Remove from active</button>
        </li>
        <li class="choice choice--danger">
          <span class="choice__icon">${ic('action-delete', { size: '20px' })}</span>
          <span><span class="choice__title text-danger">Permanently delete</span>
          <span class="choice__body">The original file and its derived Markdown, tables and OCR text are removed. <strong class="text-danger">31 evidence records lose their passage-level citation</strong> and fall back to source-level only. This cannot be undone.</span></span>
          <button type="button" class="btn btn--danger">Delete permanently</button>
        </li>
      </ul>
      <div class="dialog__actions"><button class="btn">Cancel</button></div>
      <p style="color:var(--text-subtle);font-size:var(--text-sm);margin-block-start:var(--space-4);margin-block-end:0">
        An already-archived source (like <span class="identifier" style="font-family:var(--font-mono)">toranjebin.ir</span> below) skips straight to a choice between staying archived and permanent deletion — there is nothing left to “remove from active”.
      </p>
    </div>

    <div class="dialog" role="dialog" aria-labelledby="dlg-del-knowledge" style="grid-column:1/-1;max-inline-size:640px">
      <h2 id="dlg-del-knowledge">${ic('action-archive')} Retire “${fa('ترنجبین')}” (Toranjebin)?</h2>
      <p style="color:var(--text-muted)">A knowledge object is the most-connected thing in the system — 248 sources, 1,842 claims and 493 evidence records feed it. What happens here is more limited than for a source.</p>
      <ul class="choice-list">
        <li class="choice">
          <span class="choice__icon">${ic('action-archive', { size: '20px' })}</span>
          <span><span class="choice__title">Archive knowledge object</span>
          <span class="choice__body">Stops it appearing in search and AI visibility. Every source, claim and evidence record it rests on is retained exactly as-is.</span></span>
          <button type="button" class="btn btn--primary">Archive</button>
        </li>
        <li class="choice choice--disabled">
          <span class="choice__icon">${ic('lock', { size: '20px' })}</span>
          <span><span class="choice__title">Permanently delete knowledge content</span>
          <span class="choice__body">Not available yet. The API only supports archiving a knowledge object today — nothing removes its claims or evidence outright. Shown here disabled rather than as a working-looking button that would not do what it says (§67). Tracked as finding UX-17.</span></span>
          <button type="button" class="btn" disabled aria-disabled="true">Not available</button>
        </li>
      </ul>
      <div class="dialog__actions"><button class="btn">Cancel</button></div>
    </div>

    <div class="state state--error" role="alert">
      <span class="state__icon">${ic('status-failed', { size: '24px' })}</span>
      <h2>Conversion failed</h2>
      <p>The converter could not read this file's structure.</p>
      <dl class="kv" style="text-align:start">
        <dt>Stage</dt><dd>MarkItDown conversion</dd>
        <dt>Reason</dt><dd>Document structure is malformed or unsupported</dd>
        <dt>Your file</dt><dd>Kept. Nothing was discarded.</dd>
      </dl>
      <p style="display:flex;gap:var(--space-2);flex-wrap:wrap">
        <button class="btn">View details</button>
        <button class="btn">${ic('action-reprocess')}Retry</button>
        <button class="btn">Upload a different file</button>
      </p>
    </div>

    <div class="state">
      <span class="state__icon">${ic('sources', { size: '28px' })}</span>
      <h2>No sources yet</h2>
      <p>Add PDFs, documents, web pages, research papers, site articles or datasets. Everything the knowledge layer knows will be traceable back to one of them.</p>
      <p><a class="btn btn--primary" href="#screen-add">${ic('action-add')}Add source</a></p>
    </div>

    <div class="card" aria-busy="true">
      <h2 class="card__title">Loading</h2>
      <div style="display:grid;gap:var(--space-3)">
        <div class="skeleton" style="inline-size:60%"></div>
        <div class="skeleton" style="inline-size:90%"></div>
        <div class="skeleton" style="inline-size:75%"></div>
      </div>
    </div>
  </div>
</section>`;

/* =========================================================================
 * PHASE 13 — Analytics & Demand Intelligence, and AI Access Control
 *
 * Added to THIS harness rather than a second one, and built from the same
 * tokens.css / components.css / icon-paths.json as every screen above.
 * A separate dashboard prototype would have been faster and would have
 * been the start of the two-design-systems problem UX-08 already warns
 * about.
 *
 * WHAT CHANGED SINCE THE CHECKPOINT, AND WHY IT IS NOT A SILENT REVERSAL
 *
 * The AI Visibility screen above says "no location and no time-on-site
 * are collected — a deliberate privacy narrowing" (ADR-046, checkpoint
 * §P.5). The checkpoint recorded that as an OWNER DECISION, not a closed
 * question. The owner has now decided the other way and asked for IP,
 * geography and dwell time. ADR-079 records that decision and supersedes
 * the narrowing; ADR-046 stays on file, unedited. The screens below carry
 * the consequences of the new decision visibly — a retention horizon on
 * the address, /24 truncation, and "Not available" wherever geography was
 * never supplied — rather than presenting the data as free of cost.
 * ======================================================================= */

const CONTENT_ROWS = [
  ['/knowledge/taranjabin', fa('ترنجبین چیست؟'), '1,284', '412', '97', '18', '3m 12s', '14'],
  ['/product/taranjabin-grade-a', 'Taranjabin — Grade A', '612', '188', '61', '9', '2m 04s', '11'],
  ['/knowledge/saffron-grading', fa('درجه‌بندی زعفران'), '240', '96', '12', '2', '1m 41s', '7'],
  ['/blog/supplier-visit-2026', 'Supplier visit, spring 2026', '38', '9', '0', '0', null, '3'],
  ['/legal/ai-terms', 'AI access terms', '6', '3', '0', '0', null, '2'],
];

function contentRow([path, title, human, crawler, answer, agent, dwell, countries]) {
  return `
    <tr>
      <td data-label="Content">
        <div class="source-cell">
          <span class="source-cell__icon">${ic('source-cms')}</span>
          <span class="source-cell__body">
            <span class="source-cell__title">${title}</span>
            <span class="source-cell__meta">${id(path)}</span>
          </span>
        </div>
      </td>
      <td data-label="Human" class="num">${human}</td>
      <td data-label="AI crawler (training/indexing)" class="num">${crawler}</td>
      <td data-label="AI answering a user" class="num">${answer}</td>
      <td data-label="Agent acting for a user" class="num">${agent}</td>
      <td data-label="Mean time on page">${dwell === null ? na('Not reported') : dwell}</td>
      <td data-label="Countries" class="num">${countries}</td>
    </tr>`;
}

/* Least-seen first is the default here, not most-seen. The merchant's
 * question is "where should I point content production next?", and the
 * answer lives at the BOTTOM of a popularity list. A descending-only
 * report silently drops the more actionable half of the requirement. */
const TRAFFIC_ROWS = [
  ['09:41:03', 'AI crawler', 'GPTBot', 'Detected', 'US', '203.0.113.0/24', '/knowledge/taranjabin', null, 'forbidden'],
  ['09:40:58', 'AI answering', 'ChatGPT-User', 'Detected', 'US', '198.51.100.0/24', '/product/taranjabin-grade-a', '41s', 'allowed'],
  ['09:40:41', 'Human', na('—'), na('n/a'), 'IR', '185.143.0.0/24', '/knowledge/taranjabin', '3m 12s', 'allowed'],
  ['09:40:22', 'Search crawler', 'Googlebot', 'Detected', 'US', '66.249.0.0/24', '/blog/supplier-visit-2026', null, 'allowed'],
  ['09:39:55', 'Unknown', 'ZorpAnalyticsCrawler', 'Probable', na('Not available'), '141.98.0.0/24', '/product/taranjabin-grade-a', null, 'unset'],
  ['09:39:40', 'AI crawler', 'CCBot', 'Detected', 'DE', '18.212.0.0/24', '/knowledge/saffron-grading', null, 'paid'],
];

function trafficRow([time, actor, sig, conf, country, ip, page, dwell, access]) {
  const accessBadge = TIER_BADGE_STANDALONE[access];
  return `
    <tr>
      <td data-label="Time">${time}</td>
      <td data-label="Actor">${actor}</td>
      <td data-label="Signature">${sig === null ? na('—') : id(sig)}</td>
      <td data-label="Identification">${conf === null ? na('n/a') : conf}</td>
      <td data-label="Country">${country}</td>
      <td data-label="IP"><span style="font-family:var(--font-mono)">${ip}</span></td>
      <td data-label="Page"><span class="source-cell__meta">${id(page)}</span></td>
      <td data-label="Dwell">${dwell === null ? na('Not reported') : dwell}</td>
      <td data-label="Access">${badge(accessBadge[0], accessBadge[1], accessBadge[2])}</td>
    </tr>`;
}

const TIER_BADGE_STANDALONE = {
  free: ['success', 'status-completed', 'Free'],
  paid: ['info', 'cost', 'Paid'],
  forbidden: ['danger', 'lock', 'Forbidden'],
  unset: ['unknown', 'status-unknown', 'Not decided'],
  allowed: ['success', 'status-completed', 'Allowed'],
};


const screenAnalytics = `
<section class="screen" id="screen-analytics" aria-labelledby="h-analytics">
  <nav class="breadcrumbs" aria-label="Breadcrumb"><a href="#screen-dashboard">Dashboard</a>${ic('action-expand')}<span>Analytics</span></nav>
  <div class="page-header">
    <div>
      <h1 id="h-analytics">${ic('analytics', { lg: true })} Analytics &amp; demand</h1>
      <p>What was read, by whom, from where, and for how long — plus what people and machines searched for and did not find.</p>
    </div>
    <div class="page-actions">
      <button class="btn">${ic('action-filter')}Filter</button>
      <button class="btn">${ic('action-download')}Export CSV</button>
    </div>
  </div>

  <div class="stat-grid">
    <div class="stat"><span class="stat__label">${ic('dashboard')} Page views (30d)</span><span class="stat__value">2,180</span><span class="stat__note">1,284 human · 896 machine</span></div>
    <div class="stat"><span class="stat__label">${ic('agent')} Distinct AI agents seen</span><span class="stat__value">11</span><span class="stat__note">2 not in the shipped signature list</span></div>
    <div class="stat stat--attention"><span class="stat__label">${ic('shield')} Agents awaiting a decision</span><span class="stat__value">6</span><span class="stat__note"><a href="#screen-access">Set access</a></span></div>
    <div class="stat"><span class="stat__label">${ic('dwell')} Mean time on page</span><span class="stat__value">2m 41s</span><span class="stat__note">from 704 of 2,180 views</span></div>
  </div>

  <div class="card" style="margin-top:var(--space-4)">
    <h2 class="card__title">${ic('action-sort')} Content, least seen first</h2>
    <p style="color:var(--text-muted);margin-top:0">Sorted ascending by total views by default. Click any column header to sort by it. In this fixture the reordering happens in the browser because there's only one page of rows to show; a real deployment with thousands of rows sorts server-side instead, so the order stays correct across pages rather than only within whatever page happened to load.</p>
    <div class="table-wrap">
      <table class="table sortable">
        <caption class="visually-hidden">Content ranked by how often it was viewed, split by who viewed it</caption>
        <thead>
          <tr>
            <th scope="col">Content</th>
            <th scope="col">Human</th>
            <th scope="col">AI crawler</th>
            <th scope="col">AI answering</th>
            <th scope="col">Agent</th>
            <th scope="col">Mean time on page</th>
            <th scope="col">Countries</th>
          </tr>
        </thead>
        <tbody>${CONTENT_ROWS.slice().reverse().map(contentRow).join('')}</tbody>
      </table>
    </div>
    <p style="color:var(--text-subtle);font-size:var(--text-sm);margin-block-end:0">"AI crawler" and "AI answering" are separate columns and are never added together. One is a copy being taken for later; the other is a customer's question being answered right now. A bot/human split would collapse the only distinction that changes what you do next.</p>
  </div>

  <div class="card" style="margin-top:var(--space-4)">
    <h2 class="card__title">${ic('geography')} Where the requests came from</h2>
    <div class="table-wrap">
      <table class="table sortable">
        <caption class="visually-hidden">Requests by country and how the location was determined</caption>
        <thead><tr><th scope="col">Country</th><th scope="col">Requests</th><th scope="col">Human</th><th scope="col">Machine</th><th scope="col">How we know</th></tr></thead>
        <tbody>
          <tr><td data-label="Country">${fa('ایران')} (IR)</td><td data-label="Requests" class="num">1,402</td><td data-label="Human" class="num">1,118</td><td data-label="Machine" class="num">284</td><td data-label="How we know">Edge header</td></tr>
          <tr><td data-label="Country">United States (US)</td><td data-label="Requests" class="num">431</td><td data-label="Human" class="num">62</td><td data-label="Machine" class="num">369</td><td data-label="How we know">Edge header</td></tr>
          <tr><td data-label="Country">Germany (DE)</td><td data-label="Requests" class="num">96</td><td data-label="Human" class="num">40</td><td data-label="Machine" class="num">56</td><td data-label="How we know">Edge header</td></tr>
          <tr><td data-label="Country">${na('Not available')}</td><td data-label="Requests" class="num">251</td><td data-label="Human" class="num">64</td><td data-label="Machine" class="num">187</td><td data-label="How we know">${na('No location was supplied')}</td></tr>
        </tbody>
      </table>
    </div>
    <div class="callout" style="margin-top:var(--space-4)"><span class="callout__icon">${ic('info')}</span>
      <div><p>There is no IP-geolocation database in this product and no lookup call is made. A location appears only when an upstream CDN or the adapter already resolved it and said so — otherwise the row reads <strong>Not available</strong>, which is a different statement from "unknown country" and a very different one from zero. Coordinates, where present, are rounded to roughly one kilometre.</p></div>
    </div>
  </div>

  <div class="card" style="margin-top:var(--space-4)">
    <h2 class="card__title">${ic('action-search')} What was searched for</h2>
    <p style="color:var(--text-muted);margin-top:0">On-site searches and agent queries, resolved to the same canonical query record the Query Engine already uses — so a term typed by a customer and the same term imported from Search Console are one row, not two.</p>
    <div class="table-wrap">
      <table class="table sortable">
        <caption class="visually-hidden">Search terms by volume, with how often they returned nothing</caption>
        <thead><tr><th scope="col">Term</th><th scope="col">Searched</th><th scope="col">Found nothing</th><th scope="col">Asked by</th><th scope="col">Knowledge</th></tr></thead>
        <tbody>
          <tr><td data-label="Term">${fa('ترنجبین برای کودکان')}</td><td data-label="Searched" class="num">34</td><td data-label="Found nothing" class="num">34</td><td data-label="Asked by">Human</td><td data-label="Knowledge">${badge('warning', 'gap', 'No knowledge object')}</td></tr>
          <tr><td data-label="Term">${fa('تفاوت ترنجبین و شیرخشت')}</td><td data-label="Searched" class="num">21</td><td data-label="Found nothing" class="num">19</td><td data-label="Asked by">Human</td><td data-label="Knowledge">${badge('warning', 'gap', 'Partial')}</td></tr>
          <tr><td data-label="Term">mannitol content taranjabin</td><td data-label="Searched" class="num">12</td><td data-label="Found nothing" class="num">0</td><td data-label="Asked by">AI answering a user</td><td data-label="Knowledge">${badge('success', 'status-completed', 'Covered')}</td></tr>
          <tr><td data-label="Term">saffron lab certificate 2026</td><td data-label="Searched" class="num">4</td><td data-label="Found nothing" class="num">4</td><td data-label="Asked by">AI crawler</td><td data-label="Knowledge">${badge('warning', 'gap', 'No knowledge object')}</td></tr>
        </tbody>
      </table>
    </div>
    <div class="callout" style="margin-top:var(--space-4)"><span class="callout__icon">${ic('gap')}</span>
      <div><p><strong>Found nothing</strong> counts searches that ran and returned zero results — the most useful rows in this table, because each one is a content gap with a date on it. A term that was never measured is blank, not zero; the two are not merged. These rows are <em>candidates</em> for a knowledge gap and are not filed as gaps automatically, because a gap list full of typos is a gap list nobody reads.</p></div>
    </div>
  </div>

  <div class="card" style="margin-top:var(--space-4)">
    <h2 class="card__title">${ic('log')} Recent requests</h2>
    <p style="color:var(--text-muted);margin-top:0">Every individual observation, newest first — the raw record the tables above are rolled up from. This is <code>GET /telemetry/page-views</code>, rendered directly; nothing here is computed by the dashboard.</p>
    <div class="table-wrap">
      <table class="table sortable">
        <caption class="visually-hidden">Individual page-view observations with actor, location and dwell</caption>
        <thead>
          <tr>
            <th scope="col">Time</th>
            <th scope="col">Actor</th>
            <th scope="col">Signature</th>
            <th scope="col">Identification</th>
            <th scope="col">Country</th>
            <th scope="col">IP</th>
            <th scope="col">Page</th>
            <th scope="col">Dwell</th>
            <th scope="col">Access</th>
          </tr>
        </thead>
        <tbody>${TRAFFIC_ROWS.map(trafficRow).join('')}</tbody>
      </table>
    </div>
    <p style="color:var(--text-subtle);font-size:var(--text-sm);margin-block-end:0">IP is truncated to its /24 (or /48 for IPv6) by default, here and everywhere except the separate OWNER/ADMIN-only endpoint. This table is server-paged — it does not grow the page past 50 rows regardless of how much traffic the site has.</p>
  </div>
</section>`;

const AGENT_ROWS = [
  ['GPTBot', 'OpenAI', 'AI crawler (indexing)', 'Training', 'Detected', '412', 'forbidden'],
  ['ClaudeBot', 'Anthropic', 'AI crawler (indexing)', 'Training', 'Detected', '288', 'forbidden'],
  ['CCBot', 'Common Crawl', 'AI crawler (indexing)', 'Training', 'Detected', '156', 'paid'],
  ['ChatGPT-User', 'OpenAI', 'AI answering a user', 'Answering', 'Detected', '97', 'free'],
  ['Claude-User', 'Anthropic', 'AI answering a user', 'Answering', 'Detected', '54', 'free'],
  ['Googlebot', 'Google', 'Search crawler', 'Search indexing', 'Detected', '1,204', 'free'],
  ['ZorpAnalyticsCrawler', null, 'Unrecognised automated client', 'Unknown', 'Probable', '23', 'unset'],
  ['qqq-zzz-client', null, 'Unrecognised client', 'Unknown', 'Unknown', '4', 'unset'],
];

const TIER_BADGE = {
  free: ['success', 'status-completed', 'Free'],
  paid: ['info', 'cost', 'Paid'],
  forbidden: ['danger', 'lock', 'Forbidden'],
  unset: ['unknown', 'status-unknown', 'Not decided'],
};

function agentRow([sig, vendor, type, purpose, confidence, requests, tier]) {
  const [variant, iconName, text] = TIER_BADGE[tier];
  return `
    <tr>
      <td data-label="Agent">
        <div class="source-cell">
          <span class="source-cell__icon">${ic('agent')}</span>
          <span class="source-cell__body">
            <span class="source-cell__title">${id(sig)}</span>
            <span class="source-cell__meta">${vendor === null ? na('Operator unknown') : vendor}</span>
          </span>
        </div>
      </td>
      <td data-label="Type">${type}</td>
      <td data-label="Stated purpose">${purpose === 'Unknown' ? na('Not declared') : purpose}</td>
      <td data-label="Identification">${badge(confidence === 'Detected' ? 'info' : confidence === 'Probable' ? 'warning' : 'unknown', 'status-unknown', confidence)}</td>
      <td data-label="Requests (30d)" class="num">${requests}</td>
      <td data-label="Access">${badge(variant, iconName, text)}</td>
      <td data-label="Actions"><a class="btn btn--quiet" href="#screen-access">Change</a></td>
    </tr>`;
}

const screenAccess = `
<section class="screen" id="screen-access" aria-labelledby="h-access">
  <nav class="breadcrumbs" aria-label="Breadcrumb"><a href="#screen-dashboard">Dashboard</a>${ic('action-expand')}<span>AI access</span></nav>
  <div class="page-header">
    <div>
      <h1 id="h-access">${ic('shield', { lg: true })} AI access</h1>
      <p>Who may read this site, for what purpose, and on what terms. Every automated client that has ever arrived is listed — including the ones nobody recognises.</p>
    </div>
  </div>

  <div class="callout callout--warning"><span class="callout__icon">${ic('status-warning')}</span>
    <div><p><strong>6 agents have no decision yet.</strong> They are being allowed through, and the report records that as <em>Not configured</em> rather than as <em>Allowed</em> — because nobody chose it. An unmade decision that quietly behaves like a permission is how a site ends up in a training corpus it never agreed to.</p></div>
  </div>

  <div class="card" style="margin-top:var(--space-4)">
    <h2 class="card__title">Rules, most specific first</h2>
    <p style="color:var(--text-muted);margin-top:0">The first rule that matches wins and evaluation stops. There is no scoring and no "strictest wins" — you must be able to read this table and predict what happens to a given crawler.</p>
    <div class="table-wrap">
      <table class="table sortable">
        <caption class="visually-hidden">Access rules in precedence order</caption>
        <thead><tr><th scope="col">Applies to</th><th scope="col">Purpose</th><th scope="col">Decision</th><th scope="col">Reason given to the agent</th><th scope="col"></th></tr></thead>
        <tbody>
          <tr><td data-label="Applies to">${id('GPTBot')}</td><td data-label="Purpose">Any</td><td data-label="Decision">${badge('danger', 'lock', 'Forbidden')}</td><td data-label="Reason">We do not permit corpus collection.</td><td data-label="Actions">${ic.button ? '' : ''}<a class="btn btn--quiet" href="#screen-access">Edit</a></td></tr>
          <tr><td data-label="Applies to">Any AI crawler</td><td data-label="Purpose">Training</td><td data-label="Decision">${badge('danger', 'lock', 'Forbidden')}</td><td data-label="Reason">Training use requires a licence.</td><td data-label="Actions"><a class="btn btn--quiet" href="#screen-access">Edit</a></td></tr>
          <tr><td data-label="Applies to">Any AI crawler</td><td data-label="Purpose">Search indexing</td><td data-label="Decision">${badge('info', 'cost', 'Paid')}</td><td data-label="Reason">Commercial licence required — see terms.</td><td data-label="Actions"><a class="btn btn--quiet" href="#screen-access">Edit</a></td></tr>
          <tr><td data-label="Applies to">Any AI answering a user</td><td data-label="Purpose">Any</td><td data-label="Decision">${badge('success', 'status-completed', 'Free')}</td><td data-label="Reason">${na('No reason needed')}</td><td data-label="Actions"><a class="btn btn--quiet" href="#screen-access">Edit</a></td></tr>
        </tbody>
      </table>
    </div>
    <div class="callout" style="margin-top:var(--space-4)"><span class="callout__icon">${ic('info')}</span>
      <div><p>Read the first two rows together: <em>block training everywhere, but answer a customer's live question freely.</em> That is the whole point of separating purpose from actor. A human visitor is never subject to any of these rules — there is no configuration here that can return 403 to a customer's browser.</p>
      <p><strong>Paid</strong> returns HTTP 402 with a link to your terms. It records an intention; nothing in this product meters, invoices or collects anything, and there is deliberately no price field, because a number here would look like a working price.</p></div>
    </div>
  </div>

  <div class="card" style="margin-top:var(--space-4)">
    <h2 class="card__title">${ic('agent')} Every agent seen</h2>
    <p style="color:var(--text-muted);margin-top:0">11 distinct clients in the last 30 days. There is no filter that hides unrecognised ones — the interesting agent is always the one nobody had heard of yet.</p>
    <div class="table-wrap">
      <table class="table sortable">
        <caption class="visually-hidden">Automated clients observed, with their current access decision</caption>
        <thead><tr><th scope="col">Agent</th><th scope="col">Type</th><th scope="col">Stated purpose</th><th scope="col">Identification</th><th scope="col">Requests (30d)</th><th scope="col">Access</th><th scope="col"></th></tr></thead>
        <tbody>${AGENT_ROWS.map(agentRow).join('')}</tbody>
      </table>
    </div>
    <div class="callout" style="margin-top:var(--space-4)"><span class="callout__icon">${ic('status-unknown')}</span>
      <div><p>A User-Agent header is a claim a request makes about itself. <strong>Detected</strong> means the header matched a published signature; <strong>Probable</strong> means a weaker pattern matched; <strong>Verified</strong> would require reverse-DNS or published-IP confirmation and is not built, so nothing in this product can display it. Blocking by header therefore stops honest agents and does not stop dishonest ones — that is a real limit of this control and is stated here rather than in a footnote.</p></div>
    </div>
  </div>
</section>`;

const screenOperations = `
<section class="screen" id="screen-operations" aria-labelledby="h-ops">
  <nav class="breadcrumbs" aria-label="Breadcrumb"><a href="#screen-dashboard">Dashboard</a>${ic('action-expand')}<span>Connection &amp; logs</span></nav>
  <div class="page-header">
    <div>
      <h1 id="h-ops">${ic('connection', { lg: true })} Connection &amp; logs</h1>
      <p>Whether this site is talking to Cloud Core, what version of each half is running, and what the adapter has been doing.</p>
    </div>
  </div>

  <div class="card">
    <h2 class="card__title">Status</h2>
    <dl class="kv">
      <dt>Cloud Core</dt><dd>${badge('success', 'status-completed', 'Connected')} <span class="identifier" style="font-family:var(--font-mono)">api.aiol.example</span> · 142 ms</dd>
      <dt>Database</dt><dd>${badge('success', 'status-completed', 'Healthy')}</dd>
      <dt>Queue (Redis)</dt><dd>${badge('warning', 'status-warning', 'Degraded')} Reachable but not responding to PING</dd>
      <dt>Rate limiting</dt><dd>${badge('warning', 'status-warning', 'Not enforced')} The limiter fails open without Redis</dd>
      <dt>Overall</dt><dd>${badge('warning', 'status-warning', 'Degraded')}</dd>
      <dt>Plugin version</dt><dd>${id('v0.13.0')}</dd>
      <dt>Cloud Core version</dt><dd>${id('v0.13.0')}</dd>
      <dt>Telemetry API</dt><dd>${id('v13.0')}</dd>
      <dt>Last event received</dt><dd>2 minutes ago</dd>
      <dt>Last rollup</dt><dd>Today 03:00 UTC</dd>
    </dl>
    <div class="callout" style="margin-top:var(--space-4)"><span class="callout__icon">${ic('status-warning')}</span>
      <div><p>Overall is the <em>worst</em> of its parts and is never rounded up to green. The system genuinely is serving requests and genuinely is missing a protection; one indicator saying "Healthy" while rate limiting is unenforced is a lie of omission an operator cannot act on.</p></div>
    </div>
  </div>

  <div class="card" style="margin-top:var(--space-4)">
    <h2 class="card__title">${ic('log')} Adapter log</h2>
    <div class="table-wrap">
      <table class="table sortable">
        <caption class="visually-hidden">Recent adapter log entries</caption>
        <thead><tr><th scope="col">Time (UTC)</th><th scope="col">Level</th><th scope="col">Message</th></tr></thead>
        <tbody>
          <tr><td data-label="Time">2026-09-17 09:41</td><td data-label="Level">${badge('info', 'info', 'info')}</td><td data-label="Message">Telemetry batch accepted: 48 events, 2 duplicates</td></tr>
          <tr><td data-label="Time">2026-09-17 09:38</td><td data-label="Level">${badge('danger', 'status-failed', 'error')}</td><td data-label="Message">Telemetry batch failed: timeout after 5s — 48 events queued for retry</td></tr>
          <tr><td data-label="Time">2026-09-17 09:12</td><td data-label="Level">${badge('info', 'info', 'info')}</td><td data-label="Message">New agent discovered: ZorpAnalyticsCrawler</td></tr>
          <tr><td data-label="Time">2026-09-17 08:55</td><td data-label="Level">${badge('info', 'info', 'info')}</td><td data-label="Message">Authenticated to Cloud Core with key ${id('aiol_***REDACTED***')}</td></tr>
        </tbody>
      </table>
    </div>
    <div class="dialog__actions" style="margin-top:var(--space-4)">
      <button class="btn btn--danger">${ic('action-delete')}Clear log history</button>
    </div>
    <p style="color:var(--text-subtle);font-size:var(--text-sm);margin-block-end:0">Clearing removes the adapter's own log on this site. It does not delete page views, agents or access decisions held in Cloud Core — those are the analytics record, and a log-clearing button that quietly erased them would be a destructive action wearing a harmless label. Credential-shaped strings are stripped before anything is written, so clearing is housekeeping, not damage control.</p>
  </div>
</section>`;


const screenSettings = `
<section class="screen" id="screen-settings" aria-labelledby="h-settings">
  <div class="page-header">
    <div><h1 id="h-settings">${ic('settings', { lg: true })} Settings</h1><p>Preferences for this account. Nothing here touches Knowledge Objects, sources, wallet or billing history — resetting a preference is never a data-deletion action (see "Reset all settings" below).</p></div>
  </div>

  <div class="card">
    <h2 class="card__title">Appearance</h2>
    <dl class="kv">
      <dt>Theme</dt><dd>Light / Dark — also toggled from ${ic('theme')} in the top bar</dd>
      <dt>Font</dt><dd>System default <button class="btn" style="margin-inline-start:var(--space-2)">${ic('font')}Change</button></dd>
      <dt>Language</dt><dd>English — also toggled from ${ic('language')} in the top bar; persists across logout/login until changed again</dd>
    </dl>
  </div>

  <div class="card" style="margin-top:var(--space-4)">
    <h2 class="card__title">Account</h2>
    <dl class="kv">
      <dt>Email</dt><dd><bdi>${CURRENT_USER_EMAIL}</bdi></dd>
      <dt>Site</dt><dd><bdi>${CURRENT_USER_SITE}</bdi></dd>
      <dt>Sign-in method</dt><dd>Email code</dd>
    </dl>
    <div class="page-actions" style="margin-top:var(--space-3)">
      <button class="btn">${ic('action-edit')}Edit profile</button>
      <button class="btn">${ic('help')}Get help</button>
    </div>
  </div>

  <div class="card" style="margin-top:var(--space-4)">
    <h2 class="card__title">Plan &amp; billing</h2>
    <p style="color:var(--text-muted);margin-top:0">Illustrative only — no subscription, wallet or payment backend exists in this sandbox. See <code>docs/billing/BILLING_ARCHITECTURE.md</code> for the design this would be built from.</p>
    <dl class="kv">
      <dt>Plan</dt><dd>Basic <span class="badge badge--info" style="margin-inline-start:var(--space-2)">Requires Pro for source/processing actions</span></dd>
      <dt>AI wallet</dt><dd>Not configured</dd>
    </dl>
    <div class="page-actions" style="margin-top:var(--space-3)">
      <button class="btn btn--primary">${ic('upgrade')}Upgrade plan</button>
      <button class="btn">${ic('wallet')}Payment &amp; wallet</button>
    </div>
  </div>

  <div class="card" style="border-color:var(--danger);margin-top:var(--space-4)">
    <h2 class="card__title" style="color:var(--danger)">Danger zone</h2>
    <dl class="kv">
      <dt>Reset all settings</dt><dd>Restores theme, language, sidebar and table preferences to defaults. <strong>Does not</strong> touch Knowledge Objects, sources, research, wallet or billing history. <button class="btn" style="margin-inline-start:var(--space-2)">Reset</button></dd>
      <dt>Delete all entities</dt><dd>Factory reset — permanently deletes every Knowledge Object, source and history for this organization. Requires re-authentication and a typed confirmation; not a single click. <button class="btn" style="margin-inline-start:var(--space-2);border-color:var(--danger);color:var(--danger)">${ic('action-delete')}Start factory reset</button></dd>
      <dt>Log out</dt><dd><button class="btn" style="margin-inline-start:0">${ic('logout')}Log out</button></dd>
    </dl>
  </div>
</section>`;


// Product / Offer fixture data — field set matches the canonical schema
// in MASTER_SPEC.md §26/§27 (products: sku, brand, category, origin,
// ingredients, certifications, shipping, returns_policy; offers:
// product_id, price, currency, availability, stock_quantity, condition,
// valid_from/until) rather than inventing a shape. Product identity and
// commercial Offer are rendered as two separate sections per row's
// detail, never merged into one object — DEC-0006.
const PRODUCTS = [
  {
    id: 'taranjebin-grade-a', sku: 'TRJ-GA-100', name: fa('ترنجبین درجه یک — ۱۰۰ گرم'),
    brand: fa('تورنجبین'), category: fa('گیاهان دارویی سنتی'), origin: fa('خراسان جنوبی، ایران'),
    status: 'active', offers: 1, price: '—', currency: 'IRR', availability: 'in_stock', stock: 214,
    knowledgeId: 'taranjebin',
  },
  {
    id: 'saffron-negin-5g', sku: 'SAF-NG-5', name: fa('زعفران نگین — ۵ گرم'),
    brand: fa('تورنجبین'), category: fa('ادویه و طعم‌دهنده'), origin: fa('قائنات، خراسان جنوبی'),
    status: 'active', offers: 2, price: '—', currency: 'IRR', availability: 'in_stock', stock: 88,
    knowledgeId: 'saffron',
  },
  {
    id: 'garlic-oil-30ml', sku: 'GRL-OIL-30', name: fa('روغن سیر — ۳۰ میلی‌لیتر'),
    brand: fa('تورنجبین'), category: fa('روغن‌های گیاهی'), origin: fa('همدان، ایران'),
    status: 'draft', offers: 0, price: '—', currency: 'IRR', availability: 'unavailable', stock: 0,
    knowledgeId: 'garlic',
  },
];

function offerAvailabilityBadge(a) {
  if (a === 'in_stock') return badge('success', 'status-completed', 'In stock');
  if (a === 'unavailable') return badge('unknown', 'status-unknown', 'No offer yet');
  return badge('warning', 'status-warning', a);
}

function productRow(p) {
  return `
    <tr>
      <td data-label="Product"><a href="#screen-product-${p.id}" style="font-weight:var(--weight-semibold);text-decoration:none;color:var(--text)"><bdi lang="fa" dir="rtl">${p.name}</bdi></a><br><span style="color:var(--text-subtle);font-size:var(--text-sm)">SKU <bdi>${p.sku}</bdi></span></td>
      <td data-label="Category"><bdi lang="fa" dir="rtl">${p.category}</bdi></td>
      <td data-label="Origin"><bdi lang="fa" dir="rtl">${p.origin}</bdi></td>
      <td data-label="Knowledge">${p.knowledgeId ? `<a href="#screen-knowledge-${p.knowledgeId}">${ic('knowledge')}Linked</a>` : '<span style="color:var(--text-subtle)">Not linked</span>'}</td>
      <td data-label="Offers" class="num">${p.offers}</td>
      <td data-label="Availability">${offerAvailabilityBadge(p.availability)}</td>
      <td data-label="Status">${p.status === 'active' ? badge('success', 'status-completed', 'Active') : badge('unknown', 'status-unknown', 'Draft')}</td>
    </tr>`;
}

const screenProducts = `
<section class="screen" id="screen-products" aria-labelledby="h-products">
  <div class="page-header">
    <div><h1 id="h-products">${ic('products', { lg: true })} Products</h1><p>Product identity and commercial Offer are kept separate on purpose (DEC-0006): a Product is what it <em>is</em> — brand, origin, ingredients, certifications; an Offer is where it can be <em>bought</em> — price, stock, availability. A Product can exist, fully described, with zero offers.</p></div>
    <div class="page-actions"><button class="btn btn--primary">${ic('action-add')}New product</button></div>
  </div>
  <div class="toolbar" style="display:flex;flex-wrap:wrap;gap:var(--space-3);align-items:center;margin-block-end:var(--space-4)">
    <label style="flex:1 1 260px;min-width:200px">
      <span class="visually-hidden">Search products</span>
      <input type="search" placeholder="Search by name or SKU…" style="width:100%;font:inherit;padding:8px 12px;min-height:36px;border:1px solid var(--border-strong);border-radius:var(--radius-sm);background:var(--surface);color:var(--text)">
    </label>
    <button class="btn">${ic('action-filter')}Filter</button>
  </div>
  <table class="table" style="margin-top:var(--space-4)">
    <caption class="visually-hidden">Products, one row per SKU family</caption>
    <thead><tr>
      <th scope="col">Product</th><th scope="col">Category</th><th scope="col">Origin</th>
      <th scope="col">Knowledge</th><th scope="col">Offers</th><th scope="col">Availability</th><th scope="col">Status</th>
    </tr></thead>
    <tbody>${PRODUCTS.map(productRow).join('')}</tbody>
  </table>
  <p style="color:var(--text-subtle);font-size:var(--text-sm);margin-top:var(--space-4)">Field set matches the canonical schema (MASTER_SPEC.md §26 products / §27 offers) — sku, brand, category, origin, ingredients, certifications for the product; price, currency, availability, stock, condition for each offer. Nothing here is a WooCommerce mirror; WooCommerce is one possible source that normalizes into this same shape.</p>
</section>`;

function productDetailScreen(p) {
  return `
<section class="screen" id="screen-product-${p.id}" aria-labelledby="h-prod-${p.id}">
  <nav class="breadcrumbs" aria-label="Breadcrumb"><a href="#screen-products">Products</a>${ic('action-expand')}<bdi lang="fa" dir="rtl">${p.name}</bdi></nav>
  <div class="page-header">
    <div><h1 id="h-prod-${p.id}" lang="fa" dir="rtl">${p.name}</h1><p>SKU <bdi>${p.sku}</bdi> · ${p.status === 'active' ? 'Active' : 'Draft'}</p></div>
    <div class="page-actions"><button class="btn">${ic('action-edit')}Edit</button><button class="btn" style="color:var(--danger);border-color:var(--danger)">${ic('action-delete')}Archive</button></div>
  </div>
  <div class="card">
    <h2 class="card__title">Product identity</h2>
    <dl class="kv">
      <dt>Brand</dt><dd><bdi lang="fa" dir="rtl">${p.brand}</bdi></dd>
      <dt>Category</dt><dd><bdi lang="fa" dir="rtl">${p.category}</bdi></dd>
      <dt>Origin</dt><dd><bdi lang="fa" dir="rtl">${p.origin}</bdi></dd>
      <dt>Ingredients</dt><dd style="color:var(--text-subtle)">Not entered yet</dd>
      <dt>Certifications</dt><dd style="color:var(--text-subtle)">Not entered yet</dd>
      <dt>Knowledge Object</dt><dd>${p.knowledgeId ? `<a href="#screen-knowledge-${p.knowledgeId}">${ic('knowledge')}Open linked knowledge</a>` : 'Not linked'}</dd>
    </dl>
  </div>
  <div class="card" style="margin-top:var(--space-4)">
    <h2 class="card__title">Offers <span style="color:var(--text-subtle);font-weight:var(--weight-regular);font-size:var(--text-sm)">— commercial availability, kept separate from product identity above</span></h2>
    ${p.offers > 0 ? `
    <table class="table">
      <caption class="visually-hidden">Offers for this product</caption>
      <thead><tr><th scope="col">Price</th><th scope="col">Availability</th><th scope="col">Stock</th><th scope="col">Condition</th></tr></thead>
      <tbody><tr><td data-label="Price">${p.price} ${p.currency}</td><td data-label="Availability">${offerAvailabilityBadge(p.availability)}</td><td data-label="Stock" class="num">${p.stock}</td><td data-label="Condition">New</td></tr></tbody>
    </table>` : `<p style="color:var(--text-subtle)">This product exists with no offer yet — a Product can be fully described before it is sellable. <button class="btn" style="margin-top:var(--space-2)">${ic('action-add')}Add an offer</button></p>`}
  </div>
</section>`;
}
const PRODUCT_DETAIL_SCREENS = PRODUCTS.map(p => [`screen-product-${p.id}`, p.name.replace(/<[^>]+>/g, ''), productDetailScreen(p)]);


// Google "G" brand mark — the one deliberate exception to this file's
// single-colour icon convention (see check.js's matching comment).
// Google's own sign-in branding guidelines fix these four colours; a
// monochrome recolour of a recognised sign-in mark would misrepresent
// which account system the button connects to, which is a worse
// outcome than the one scoped exception.
const GOOGLE_LOGO = `<svg class="brand-mark" data-brand="google" viewBox="0 0 18 18" width="18" height="18" aria-hidden="true" focusable="false">
  <path fill="#4285F4" d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.874 2.684-6.615z"/>
  <path fill="#34A853" d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332C2.438 15.983 5.482 18 9 18z"/>
  <path fill="#FBBC05" d="M3.964 10.71c-.18-.54-.282-1.117-.282-1.71s.102-1.17.282-1.71V4.958H.957C.347 6.173 0 7.548 0 9s.348 2.827.957 4.042l3.007-2.332z"/>
  <path fill="#EA4335" d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.581C13.463.891 11.426 0 9 0 5.482 0 2.438 2.017.957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z"/>
</svg>`;

// A CSS/SVG "network of moving lines and dots" background — the owner
// asked for an animated-GIF feel; there is no real GIF asset available
// or safe to fabricate in this sandbox, so this delivers the same
// visual idea (drifting nodes, connecting lines) as a lightweight,
// theme-aware, motion-reduced-respecting CSS animation instead, rather
// than claiming a GIF exists when it doesn't.
function techBackdrop() {
  const dots = Array.from({ length: 14 }, (_, i) => {
    const x = (i * 37 + 5) % 100, y = (i * 53 + 11) % 100, d = 6 + (i % 5);
    return `<span class="tech-dot" style="left:${x}%;top:${y}%;animation-delay:${(i * 0.4).toFixed(1)}s;animation-duration:${d}s"></span>`;
  }).join('');
  return `<div class="tech-backdrop" aria-hidden="true">${dots}</div>`;
}



// Admin console — a genuinely SEPARATE surface from the merchant
// dashboard (ADR/architecture docs already say this: different nav,
// different authorization boundary, different information hierarchy —
// not the same sidebar with an extra button). Reached only from the
// account menu, and visually marked as a different surface with its own
// compact top strip rather than reusing the merchant sidebar/topbar.
const ADMIN_USERS = [
  { id: 'u1', name: 'Hamed Biglari', email: 'hamed.biglari@gmail.com', org: 'Hamed Commerce', plan: 'Pro Monthly', wallet: 42.70, status: 'active', lastLogin: '2 hours ago' },
  { id: 'u2', name: fa('مریم سلیمانی'), email: 'soleimanimarzieh5@gmail.com', org: 'Toranjebin', plan: 'Basic', wallet: 0, status: 'active', lastLogin: '15 min ago' },
  { id: 'u3', name: 'Reza Kiani', email: 'reza.kiani@example.com', org: 'Kiani Herbs', plan: 'Pro Annual', wallet: 118.40, status: 'active', lastLogin: '3 days ago' },
  { id: 'u4', name: 'Sahar Ahmadi', email: 'sahar.a@example.com', org: 'Golestan Saffron', plan: 'Pro Monthly', wallet: 6.10, status: 'past_due', lastLogin: '11 days ago' },
  { id: 'u5', name: 'Unknown applicant', email: 'test-abuse-7@mailinator.com', org: '(unassigned)', plan: 'Basic', wallet: 0, status: 'blocked', lastLogin: '41 days ago' },
];

function adminStatusBadge(s) {
  if (s === 'active') return badge('success', 'status-completed', 'Active');
  if (s === 'past_due') return badge('warning', 'status-warning', 'Past due');
  return badge('unknown', 'status-unknown', 'Blocked');
}

function adminUserRow(u) {
  return `
    <tr>
      <td data-label="User"><a href="#screen-admin-user-${u.id}" style="font-weight:var(--weight-semibold);text-decoration:none;color:var(--text)"><bdi>${u.name}</bdi></a><br><span style="color:var(--text-subtle);font-size:var(--text-sm)"><bdi>${u.email}</bdi></span></td>
      <td data-label="Organization"><bdi>${u.org}</bdi></td>
      <td data-label="Plan">${u.plan}</td>
      <td data-label="Wallet" class="num" data-sort-value="${u.wallet}">$${u.wallet.toFixed(2)}</td>
      <td data-label="Status">${adminStatusBadge(u.status)}</td>
      <td data-label="Last login">${u.lastLogin}</td>
      <td data-label="Actions"><div style="display:flex;gap:var(--space-2)">
        <a class="btn" href="#screen-admin-user-${u.id}" title="View activity, wallet and refunds">${ic('action-view')}View</a>
        <button type="button" class="btn" title="${u.status === 'blocked' ? 'Unblock this user' : 'Block this user'}">${ic('lock')}${u.status === 'blocked' ? 'Unblock' : 'Block'}</button>
      </div></td>
    </tr>`;
}

function adminUserDetailScreen(u) {
  return `
<section class="screen" id="screen-admin-user-${u.id}" aria-labelledby="h-admin-user-${u.id}">
  <nav class="breadcrumbs" aria-label="Breadcrumb"><a href="#screen-admin-overview">Admin</a>${ic('action-expand')}<a href="#screen-admin-users">Users</a>${ic('action-expand')}<bdi>${u.name}</bdi></nav>
  <div class="page-header">
    <div><h1 id="h-admin-user-${u.id}">${ic('avatar')} <bdi>${u.name}</bdi></h1><p><bdi>${u.email}</bdi> · <bdi>${u.org}</bdi> · ${u.plan}</p></div>
    <div class="page-actions">
      <button class="btn" style="border-color:var(--danger);color:var(--danger)">${ic('lock')}${u.status === 'blocked' ? 'Unblock user' : 'Block user'}</button>
      <button class="btn" style="border-color:var(--danger);color:var(--danger)">${ic('action-delete')}Delete account</button>
    </div>
  </div>
  <div class="stat-grid">
    <div class="stat"><span class="stat__label">${ic('wallet')}Wallet balance</span><span class="stat__value">$${u.wallet.toFixed(2)}</span></div>
    <div class="stat"><span class="stat__label">${ic('status-completed')}Status</span><span class="stat__value" style="font-size:var(--text-lg)">${adminStatusBadge(u.status)}</span></div>
    <div class="stat"><span class="stat__label">${ic('log')}Last login</span><span class="stat__value" style="font-size:var(--text-lg)">${u.lastLogin}</span></div>
  </div>

  <div class="card" style="margin-top:var(--space-4)">
    <h2 class="card__title">Wallet &amp; transactions</h2>
    <p style="color:var(--text-muted);margin-top:0">Illustrative only — see <code>docs/billing/BILLING_ARCHITECTURE.md</code> for the real ledger design this would read from (append-only <code>LedgerEntry</code> rows, never a mutable balance).</p>
    <table class="table sortable">
      <caption class="visually-hidden">Wallet transaction history for <bdi>${u.name}</bdi></caption>
      <thead><tr><th scope="col">Date</th><th scope="col">Type</th><th scope="col">Amount</th><th scope="col">Balance after</th></tr></thead>
      <tbody>
        <tr><td data-label="Date">2026-09-01</td><td data-label="Type">Payment captured</td><td data-label="Amount" class="num">+$50.00</td><td data-label="Balance after" class="num">$50.00</td></tr>
        <tr><td data-label="Date">2026-09-10</td><td data-label="Type">AI usage charge</td><td data-label="Amount" class="num">−$7.30</td><td data-label="Balance after" class="num">$42.70</td></tr>
      </tbody>
    </table>
    <div class="page-actions" style="margin-top:var(--space-3)">
      <button class="btn">${ic('action-add')}Manual credit</button>
      <button class="btn">${ic('action-restore')}Refund</button>
    </div>
    <p style="color:var(--text-subtle);font-size:var(--text-sm);margin-top:var(--space-2);margin-block-end:0">Every manual adjustment writes a new ledger entry with a reason and this admin's identity attached (ADR-084) — it never edits a past row.</p>
  </div>

  <div class="card" style="margin-top:var(--space-4)">
    <h2 class="card__title">Activity history</h2>
    <table class="table sortable">
      <caption class="visually-hidden">Recent activity for <bdi>${u.name}</bdi></caption>
      <thead><tr><th scope="col">Time</th><th scope="col">Action</th><th scope="col">Detail</th></tr></thead>
      <tbody>
        <tr><td data-label="Time">14:02</td><td data-label="Action">Logged in</td><td data-label="Detail">Email code</td></tr>
        <tr><td data-label="Time">13:58</td><td data-label="Action">Added source</td><td data-label="Detail"><bdi lang="fa" dir="rtl">ترنجبین</bdi> — 12 PDFs</td></tr>
        <tr><td data-label="Time">Sep 10</td><td data-label="Action">Ran processing</td><td data-label="Detail">Job ID 4471</td></tr>
      </tbody>
    </table>
  </div>
</section>`;
}

const screenAdminOverview = `
<section class="screen admin-screen" id="screen-admin-overview" aria-labelledby="h-admin-overview">
  <div class="page-header">
    <div><h1 id="h-admin-overview">${ic('organization', { lg: true })} Platform overview</h1><p>Illustrative fixture — a real admin overview reads <code>DashboardHealth</code>/<code>DashboardBillingSummary</code> read models (<code>docs/billing/BILLING_ARCHITECTURE.md</code>), not this static data.</p></div>
  </div>
  <div class="stat-grid">
    <div class="stat"><span class="stat__label">${ic('organization')}Organizations</span><span class="stat__value">312</span></div>
    <div class="stat"><span class="stat__label">${ic('avatar')}Active users (30d)</span><span class="stat__value">1,204</span></div>
    <div class="stat"><span class="stat__label">${ic('status-failed')}Failed jobs (24h)</span><span class="stat__value">3</span></div>
    <div class="stat"><span class="stat__label">${ic('wallet')}Platform AI spend (30d)</span><span class="stat__value">$2,840</span></div>
  </div>
  <div class="callout" style="margin-top:var(--space-4)"><span class="callout__icon">${ic('info')}</span>
    <div><p>This surface is authorization-separated from the merchant dashboard by design — an ordinary user account has no route into anything under <code>screen-admin-*</code>, the same boundary the real backend must enforce server-side (never a frontend-only check).</p></div>
  </div>
</section>`;

const screenAdminUsers = `
<section class="screen admin-screen" id="screen-admin-users" aria-labelledby="h-admin-users">
  <nav class="breadcrumbs" aria-label="Breadcrumb"><a href="#screen-admin-overview">Admin</a>${ic('action-expand')}<span>Users</span></nav>
  <div class="page-header">
    <div><h1 id="h-admin-users">${ic('avatar', { lg: true })} Users &amp; organizations</h1><p>Block, delete, or open any user's wallet and activity history. Search and sort are real in this fixture; a live backend paginates/filters server-side the same way Sources &amp; Documents does.</p></div>
  </div>
  <div class="toolbar" style="display:flex;flex-wrap:wrap;gap:var(--space-3);align-items:center;margin-block-end:var(--space-4)">
    <label style="flex:1 1 260px;min-width:200px">
      <span class="visually-hidden">Search users</span>
      <input type="search" placeholder="Search by name, email or organization…" style="width:100%;font:inherit;padding:8px 12px;min-height:36px;border:1px solid var(--border-strong);border-radius:var(--radius-sm);background:var(--surface);color:var(--text)">
    </label>
    <button class="btn">${ic('action-filter')}Filter</button>
  </div>
  <table class="table sortable">
    <caption class="visually-hidden">All platform users</caption>
    <thead><tr>
      <th scope="col">User</th><th scope="col">Organization</th><th scope="col">Plan</th>
      <th scope="col">Wallet</th><th scope="col">Status</th><th scope="col">Last login</th><th scope="col" data-no-sort>Actions</th>
    </tr></thead>
    <tbody>${ADMIN_USERS.map(adminUserRow).join('')}</tbody>
  </table>
</section>`;


const screenLogin = `
<section class="screen auth-screen" id="screen-login" aria-labelledby="h-login">
  ${techBackdrop()}
  <div class="auth-card">
    <div class="auth-card__icon">${ic('knowledge', { size: '40px' })}</div>
    <h1 id="h-login">Log in to AI Operating Layer</h1>
    <p class="auth-card__sub">Your Knowledge Objects, sources and AI-visibility reports — in one place.</p>

    <button type="button" class="btn auth-btn auth-btn--google">${GOOGLE_LOGO}<span>Continue with Google</span></button>

    <div class="auth-divider"><span>or</span></div>

    <form class="auth-form" data-auth-step="email">
      <label for="login-email">Email address</label>
      <input type="email" id="login-email" class="auth-input" placeholder="you@example.com" autocomplete="email" required>
      <button type="submit" class="btn btn--primary auth-btn">${ic('action-view')}<span>Send code</span></button>
    </form>

    <p class="auth-card__footer">New here? <a href="#screen-login">Sign up</a></p>
  </div>
</section>`;

const screenLoginCode = `
<section class="screen auth-screen" id="screen-login-code" aria-labelledby="h-login-code">
  ${techBackdrop()}
  <div class="auth-card">
    <div class="auth-card__icon">${ic('knowledge', { size: '40px' })}</div>
    <h1 id="h-login-code">Enter your code</h1>
    <p class="auth-card__sub">We sent a 6-digit code to <bdi id="login-code-email">you@example.com</bdi>.</p>

    <div class="otp-boxes" role="group" aria-label="6-digit verification code">
      ${Array.from({ length: 6 }, (_, i) => `<input type="text" inputmode="numeric" pattern="[0-9]*" maxlength="1" class="otp-box" aria-label="Digit ${i + 1} of 6" data-otp-index="${i}">`).join('')}
    </div>

    <button type="button" class="btn btn--primary auth-btn" id="otp-verify-btn">${ic('action-view')}<span>Verify and log in</span></button>
    <p class="otp-message" id="otp-message" role="status" aria-live="polite"></p>

    <p class="auth-card__footer" id="otp-resend-row">
      <button type="button" class="btn-link" id="otp-resend-btn">Resend code</button>
    </p>
    <p style="color:var(--text-subtle);font-size:var(--text-sm);text-align:center">Three wrong attempts locks this email for 1 hour; three more after that locks it for 24 hours, after which you can no longer retry with this email — <a href="#screen-states">contact us</a> instead. Try code <strong>123456</strong> in this fixture to see a successful log-in.</p>
  </div>
</section>`;

const SCREENS = [
  ['screen-dashboard', 'Dashboard', screenDashboard],
  ['screen-sources', 'Sources', screenSources],
  ['screen-add', 'Add source', screenAdd],
  ['screen-processing', 'Processing', screenProcessing],
  ['screen-detail', 'Source detail', screenDetail],
  ['screen-provenance', 'Provenance', screenProvenance],
  ['screen-knowledge', 'Knowledge', screenKnowledge],
  ...KNOWLEDGE_DETAIL_SCREENS,
  ['screen-gap', 'Knowledge gap', screenGap],
  ['screen-visibility', 'AI Visibility', screenVisibility],
  ['screen-visibility-detail', 'Visibility detail', screenVisibilityDetail],
  ['screen-analytics', 'Analytics & demand', screenAnalytics],
  ['screen-access', 'AI access', screenAccess],
  ['screen-operations', 'Connection & logs', screenOperations],
  ['screen-states', 'Edge states', screenStates],
  ['screen-settings', 'Settings', screenSettings],
  ['screen-products', 'Products', screenProducts],
  ...PRODUCT_DETAIL_SCREENS,
  ['screen-admin-overview', 'Admin — overview', screenAdminOverview],
  ['screen-admin-users', 'Admin — users', screenAdminUsers],
  ...ADMIN_USERS.map(function (u) { return ['screen-admin-user-' + u.id, 'Admin — ' + u.name, adminUserDetailScreen(u)]; }),
  ['screen-login', 'Login', screenLogin],
  ['screen-login-code', 'Login — enter code', screenLoginCode],
];

const NAV = [
  ['dashboard', 'Dashboard', 'screen-dashboard'],
  ['knowledge', 'Knowledge Objects', 'screen-knowledge'],
  ['sources', 'Sources & Documents', 'screen-sources'],
  ['products', 'Products', 'screen-products'],
  ['visibility', 'AI Visibility', 'screen-visibility'],
  ['analytics', 'Analytics', 'screen-analytics'],
  ['shield', 'AI access', 'screen-access'],
  ['connection', 'Connection & logs', 'screen-operations'],
  ['settings', 'Settings', 'screen-settings'],
];

const html = `<!doctype html>
<html lang="en" dir="ltr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI Operating Layer — UX prototype harness</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&family=Vazirmatn:wght@400;500;600&display=swap">
<style>
/* ===== frontend/design-system/tokens.css (inlined by build.js) ===== */
${tokens}
/* ===== frontend/design-system/components.css (inlined by build.js) ===== */
${components}
/* ===== harness chrome (NOT part of the design system) ===== */
html, body { margin: 0; background: var(--canvas); }
body { font-family: var(--font-ui); color: var(--text); }
.harness-bar {
  position: sticky; top: 0; z-index: 10;
  display: flex; flex-wrap: wrap; gap: var(--space-3); align-items: center;
  padding: var(--space-3) var(--space-4);
  background: var(--surface); border-block-end: 1px solid var(--border);
  font-size: var(--text-sm);
}
.harness-bar strong { font-weight: var(--weight-semibold); }
.harness-bar label { display: inline-flex; align-items: center; gap: var(--space-2); }
.harness-bar select, .harness-bar button {
  font: inherit; padding: 4px 8px; min-height: 32px;
  border: 1px solid var(--border-strong); border-radius: var(--radius-sm);
  background: var(--surface); color: var(--text);
}
.frame { margin-inline: auto; transition: max-width .2s; }
.frame[data-width="mobile"]  { max-width: 390px; }
.frame[data-width="tablet"]  { max-width: 834px; }
.frame[data-width="desktop"] { max-width: none; }
.frame[data-width="mobile"] .shell,
.frame[data-width="tablet"] .shell { grid-template-columns: 1fr; }
.screen { display: none; }
.screen.auth-screen.is-active { display: flex; }
.screen.is-active { display: block; }
.harness-note {
  margin: var(--space-4); padding: var(--space-3) var(--space-4);
  border: 1px solid var(--warning); border-radius: var(--radius-sm);
  background: var(--warning-tint); color: var(--warning); max-inline-size: var(--measure);
  font-size: var(--text-sm);
}
</style>
</head>
<body>

<div class="harness-bar">
  <strong>UX prototype harness</strong>
  <label>Screen
    <select id="pick-screen">${SCREENS.map(([idv, label]) => `<option value="${idv}">${label}</option>`).join('')}</select>
  </label>
  <label>Language
    <select id="pick-lang"><option value="en">English (LTR)</option><option value="fa">فارسی (RTL)</option></select>
  </label>
  <label>Theme
    <select id="pick-theme"><option value="light">Light</option><option value="dark">Dark</option></select>
  </label>
  <label>Width
    <select id="pick-width"><option value="desktop">Desktop</option><option value="tablet">Tablet 834</option><option value="mobile">Mobile 390</option></select>
  </label>
  <button id="pick-all" type="button">Show every screen</button>
</div>

<p class="harness-note">
  Representative fixture data, not production content. Counts and identifiers are illustrative.
  This harness demonstrates the UX architecture; it is not wired to Cloud Core.
</p>

<div class="frame" id="frame" data-width="desktop">
  <div class="app">
    <header class="app-topbar">
      <div class="app-topbar__start">
        <button type="button" class="btn btn--icon" id="sidebar-collapse" aria-expanded="true" aria-controls="app-sidebar" aria-label="Hide sidebar">${ic('sidebar-toggle')}</button>
        <div class="brand">${ic('knowledge', { size: '20px' })}<span>AI Operating Layer</span><span class="admin-badge">Admin</span></div>
      </div>
      <div class="app-topbar__end">
        <button type="button" class="btn btn--icon" aria-label="Tickets and messages, 1 unread" style="position:relative">${ic('chat')}<span aria-hidden="true" style="position:absolute;top:4px;inset-inline-end:4px;width:8px;height:8px;border-radius:50%;background:var(--danger);border:1.5px solid var(--surface)"></span></button>
        <button type="button" class="btn btn--icon" id="topbar-theme" aria-label="Toggle dark/light theme">${ic('theme')}</button>
        <button type="button" class="btn btn--icon" id="topbar-lang" aria-label="Change language">${ic('language')}</button>
        <div class="user-menu" style="position:relative">
          <button type="button" class="btn btn--icon" id="user-menu-btn" aria-haspopup="menu" aria-expanded="false" aria-label="Account menu">${ic('avatar')}</button>
          <div role="menu" id="user-menu" hidden style="position:absolute;inset-inline-end:0;top:calc(100% + 6px);min-width:220px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-md);box-shadow:var(--shadow-md);z-index:20;padding:var(--space-2)">
            <div style="padding:var(--space-2) var(--space-3);color:var(--text-subtle);font-size:var(--text-sm);border-block-end:1px solid var(--border)" title="${CURRENT_USER_EMAIL}">${CURRENT_USER_EMAIL}</div>
            <a role="menuitem" href="#screen-settings" style="display:flex;align-items:center;gap:var(--space-2);padding:var(--space-2) var(--space-3)">${ic('settings')}<span>Settings</span></a>
            <a role="menuitem" href="#screen-admin-overview" style="display:flex;align-items:center;gap:var(--space-2);padding:var(--space-2) var(--space-3)" title="A separate, privileged surface — shown here only because this fixture has no real authorization boundary to hide it behind">${ic('organization')}<span>Admin console</span></a>
            <a role="menuitem" href="#" style="display:flex;align-items:center;gap:var(--space-2);padding:var(--space-2) var(--space-3)">${ic('language')}<span>Language</span></a>
            <a role="menuitem" href="#" style="display:flex;align-items:center;gap:var(--space-2);padding:var(--space-2) var(--space-3)">${ic('help')}<span>Get help</span></a>
            <div style="border-block-end:1px solid var(--border);margin:var(--space-2) 0"></div>
            <a role="menuitem" href="#" style="display:flex;align-items:center;gap:var(--space-2);padding:var(--space-2) var(--space-3)">${ic('upgrade')}<span>Upgrade plan</span></a>
            <a role="menuitem" href="#" style="display:flex;align-items:center;gap:var(--space-2);padding:var(--space-2) var(--space-3)">${ic('apps')}<span>Get apps and extensions</span></a>
            <a role="menuitem" href="#" style="display:flex;align-items:center;gap:var(--space-2);padding:var(--space-2) var(--space-3)">${ic('info')}<span>Learn more</span></a>
            <div style="border-block-end:1px solid var(--border);margin:var(--space-2) 0"></div>
            <a role="menuitem" href="#" style="display:flex;align-items:center;gap:var(--space-2);padding:var(--space-2) var(--space-3)">${ic('logout')}<span>Log out</span></a>
          </div>
        </div>
      </div>
    </header>
    <div class="shell">
      <aside class="sidebar" id="app-sidebar">
        <div class="context-switch">
          <span class="context-switch__label">Account</span>
          <span class="context-switch__value identifier" title="${CURRENT_USER_EMAIL}">${truncateIdentity(CURRENT_USER_EMAIL)}</span>
          <span class="context-switch__label" style="margin-top:6px">Site</span>
          <span class="context-switch__value identifier" title="${CURRENT_USER_SITE}">${truncateIdentity(CURRENT_USER_SITE)}</span>
        </div>
        <nav class="nav nav--merchant" aria-label="Main">
          ${NAV.map(([i, label, target], idx) =>
            `<a href="#${target}" data-nav-target="${target}">${ic(i)}<span>${label}</span></a>`).join('\n          ')}
        </nav>
        <nav class="nav nav--admin" aria-label="Admin">
          <a href="#screen-admin-overview" data-nav-target="screen-admin-overview">${ic('organization')}<span>Overview</span></a>
          <a href="#screen-admin-users" data-nav-target="screen-admin-users">${ic('avatar')}<span>Users</span></a>
          <a href="#screen-dashboard" style="margin-block-start:var(--space-4);color:var(--text-muted)">${ic('action-back')}<span>Back to your dashboard</span></a>
        </nav>
        <a href="#" class="nav__logout" style="display:flex;align-items:center;gap:var(--space-2);padding:var(--space-2) var(--space-4);color:var(--text-muted)">${ic('logout')}<span>Log out</span></a>
      </aside>
      <div class="main-column" style="display:flex;flex-direction:column;min-width:0">
      <main class="main" id="main">
        ${SCREENS.map(([idv, , markup], idx) => markup.replace('class="screen"', `class="screen${idx === 0 ? ' is-active' : ''}"`)).join('\n')}
      </main>
      </div>
    </div>
  </div>
</div>

<script>
(function () {
  var root = document.documentElement;
  var frame = document.getElementById('frame');
  var screens = Array.prototype.slice.call(document.querySelectorAll('.screen'));
  var navLinks = Array.prototype.slice.call(document.querySelectorAll('.nav a[data-nav-target]'));

  function show(id) {
    screens.forEach(function (s) { s.classList.toggle('is-active', s.id === id); });
    var sel = document.getElementById('pick-screen');
    if (sel.value !== id) sel.value = id;
    // Highlight whichever top-level nav item owns this screen — a
    // sub-screen like "screen-knowledge-taranjebin" or
    // "screen-visibility-detail" still belongs to its parent's nav
    // entry (Knowledge Objects / AI Visibility), so this matches on the
    // screen id STARTING WITH the nav target, not an exact match, or
    // every sub-screen would show no active tab at all.
    navLinks.forEach(function (a) {
      var owns = id === a.dataset.navTarget || id.indexOf(a.dataset.navTarget + '-') === 0;
      if (owns) a.setAttribute('aria-current', 'page');
      else a.removeAttribute('aria-current');
    });
  }

  // Real hash-based routing: previously NOTHING listened for hash
  // changes or nav-link clicks, so .nav a and in-content links like
  // "Open the site-wide report" changed the URL but never actually
  // switched which screen was visible — only the dev harness's own
  // "Screen" <select> did anything. This is the fix, not a bigger one:
  // any link to #screen-... anywhere in the document (nav, breadcrumbs,
  // cross-links) now works, because they all already point at real
  // section ids; they just needed something listening.
  function routeFromHash() {
    var id = location.hash.replace(/^#/, '');
    if (id && document.getElementById(id)) show(id);
  }
  window.addEventListener('hashchange', routeFromHash);
  if (location.hash) routeFromHash(); else show('screen-dashboard');

  document.getElementById('pick-screen').addEventListener('change', function (e) { show(e.target.value); });

  document.getElementById('pick-all').addEventListener('click', function () {
    screens.forEach(function (s) { s.classList.add('is-active'); });
    navLinks.forEach(function (a) { a.removeAttribute('aria-current'); });
  });

  document.getElementById('pick-lang').addEventListener('change', function (e) {
    var fa = e.target.value === 'fa';
    root.lang = fa ? 'fa' : 'en';
    root.dir = fa ? 'rtl' : 'ltr';
  });

  document.getElementById('pick-theme').addEventListener('change', function (e) {
    root.setAttribute('data-theme', e.target.value);
  });

  document.getElementById('pick-width').addEventListener('change', function (e) {
    frame.setAttribute('data-width', e.target.value);
  });

  // Product topbar (distinct from the dev harness bar above): theme
  // toggle mirrors the harness's own theme picker so both stay in sync,
  // and the account menu is a real disclosure — keyboard-operable,
  // closes on outside click or Escape, per §30 accessibility gate.
  var topbarTheme = document.getElementById('topbar-theme');
  if (topbarTheme) {
    topbarTheme.addEventListener('click', function () {
      var next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-theme', next);
      document.getElementById('pick-theme').value = next;
    });
  }
  var topbarLang = document.getElementById('topbar-lang');
  if (topbarLang) {
    topbarLang.addEventListener('click', function () {
      var next = root.lang === 'fa' ? 'en' : 'fa';
      root.lang = next;
      root.dir = next === 'fa' ? 'rtl' : 'ltr';
      document.getElementById('pick-lang').value = next;
    });
  }
  var userMenuBtn = document.getElementById('user-menu-btn');
  var userMenu = document.getElementById('user-menu');
  if (userMenuBtn && userMenu) {
    function closeUserMenu() {
      userMenu.hidden = true;
      userMenuBtn.setAttribute('aria-expanded', 'false');
    }
    userMenuBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      var willOpen = userMenu.hidden;
      userMenu.hidden = !willOpen;
      userMenuBtn.setAttribute('aria-expanded', String(willOpen));
      if (willOpen) userMenu.querySelector('[role="menuitem"]').focus();
    });
    document.addEventListener('click', function (e) {
      if (!userMenu.hidden && !userMenu.contains(e.target)) closeUserMenu();
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && !userMenu.hidden) { closeUserMenu(); userMenuBtn.focus(); }
    });
  }
  var sidebarCollapse = document.getElementById('sidebar-collapse');
  if (sidebarCollapse) {
    var appEl = document.querySelector('.app');
    var dragStartX = 0, dragStartY = 0, didDrag = false;
    var DRAG_THRESHOLD = 4; // px of movement before a press counts as a drag, not a click

    function setPermanentLabel(collapsed) {
      sidebarCollapse.setAttribute('aria-expanded', String(!collapsed));
      sidebarCollapse.setAttribute('aria-label', collapsed ? 'Show sidebar' : 'Hide sidebar');
    }

    sidebarCollapse.addEventListener('pointerdown', function (e) {
      if (e.button !== 0) return; // primary button only; keyboard activation never reaches here
      didDrag = false;
      dragStartX = e.clientX;
      dragStartY = e.clientY;
      sidebarCollapse.setPointerCapture(e.pointerId);
    });

    sidebarCollapse.addEventListener('pointermove', function (e) {
      if (!(e.buttons & 1) || didDrag) return; // only while held down, and only once per press
      var dx = e.clientX - dragStartX, dy = e.clientY - dragStartY;
      if (Math.hypot(dx, dy) > DRAG_THRESHOLD) {
        didDrag = true;
        // Only visible when the sidebar is currently (permanently)
        // collapsed — peeking an already-open sidebar is a no-op, which
        // the CSS selector above already guarantees on its own.
        appEl.classList.add('sidebar-peeking');
      }
    });

    function endDrag() {
      if (didDrag) appEl.classList.remove('sidebar-peeking');
    }
    sidebarCollapse.addEventListener('pointerup', endDrag);
    sidebarCollapse.addEventListener('pointercancel', endDrag);

    // A single 'click' handles both the plain-click case (toggle the
    // permanent state) and keyboard activation (Enter/Space fire 'click'
    // with no preceding pointer events at all, so didDrag is correctly
    // false there). When the pointer sequence above already detected a
    // drag, the browser still fires 'click' on release — this branch
    // exists so that drag doesn't ALSO toggle the permanent state on
    // top of the peek it already showed.
    sidebarCollapse.addEventListener('click', function () {
      if (didDrag) { didDrag = false; return; }
      var collapsed = appEl.classList.toggle('sidebar-collapsed');
      setPermanentLabel(collapsed);
    });
  }

  // Sortable tables — every table.sortable in the harness (all of them;
  // see build.js's global class addition), not just Analytics & Demand.
  // Server-side sorting in a real backend would swap the click handler's
  // body for an API call; the header contract (a focusable button per
  // column, aria-sort reflecting state) is written to survive that swap
  // unchanged.
  function cellSortValue(row, colIndex) {
    var cell = row.children[colIndex];
    if (!cell) return '';
    return (cell.getAttribute('data-sort-value') || cell.textContent || '').trim();
  }
  function sortRowsByColumn(table, colIndex, ascending) {
    var tbody = table.querySelector('tbody');
    if (!tbody) return;
    var rows = Array.prototype.slice.call(tbody.querySelectorAll('tr'));
    var numeric = rows.length > 0 && rows.every(function (r) {
      var v = cellSortValue(r, colIndex).replace(/[,%]/g, '');
      return v === '' || v === '—' || !isNaN(parseFloat(v));
    });
    rows.sort(function (a, b) {
      var va = cellSortValue(a, colIndex), vb = cellSortValue(b, colIndex);
      if (numeric) {
        var na = parseFloat(va.replace(/[,%]/g, ''));
        var nb = parseFloat(vb.replace(/[,%]/g, ''));
        if (isNaN(na)) na = ascending ? Infinity : -Infinity;
        if (isNaN(nb)) nb = ascending ? Infinity : -Infinity;
        return ascending ? na - nb : nb - na;
      }
      return ascending ? va.localeCompare(vb) : vb.localeCompare(va);
    });
    rows.forEach(function (r) { tbody.appendChild(r); });
  }
  document.querySelectorAll('table.sortable').forEach(function (table) {
    var headRow = table.querySelector('thead tr');
    if (!headRow) return;
    var ths = Array.prototype.slice.call(headRow.children);
    ths.forEach(function (th, colIndex) {
      if (th.hasAttribute('data-no-sort') || !th.textContent.trim()) return;
      var label = th.textContent.trim();
      th.setAttribute('aria-sort', 'none');
      th.textContent = '';
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'th-sort-btn';
      var span = document.createElement('span');
      span.textContent = label;
      var caret = document.createElement('span');
      caret.className = 'th-sort-caret';
      caret.setAttribute('aria-hidden', 'true');
      btn.appendChild(span);
      btn.appendChild(caret);
      th.appendChild(btn);
      btn.addEventListener('click', function () {
        var next = th.getAttribute('aria-sort') === 'ascending' ? 'descending' : 'ascending';
        ths.forEach(function (other) { other.setAttribute('aria-sort', 'none'); });
        th.setAttribute('aria-sort', next);
        sortRowsByColumn(table, colIndex, next === 'ascending');
      });
    });
  });

  // Internal links jump between prototype screens instead of scrolling.
  document.addEventListener('click', function (e) {
    var a = e.target.closest('a[href^="#screen-"]');
    if (!a) return;
    e.preventDefault();
    show(a.getAttribute('href').slice(1));
    window.scrollTo(0, 0);
  });

  // Knowledge Objects: rows-vs-windowed display toggle. Both views are
  // rendered up front from the same KNOWLEDGE_OBJECTS fixture, so
  // switching is just which container is hidden — this also means a
  // "Research again" click (below) only has to touch the DOM once per
  // view and both stay in sync even while one is hidden.
  document.querySelectorAll('.view-toggle').forEach(function (group) {
    var tableView = document.getElementById('know-view-table');
    var gridView = document.getElementById('know-view-grid');
    if (!tableView || !gridView) return;
    group.querySelectorAll('.view-toggle__btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var isGrid = btn.dataset.view === 'grid';
        group.querySelectorAll('.view-toggle__btn').forEach(function (b) {
          b.setAttribute('aria-pressed', String(b === btn));
        });
        tableView.hidden = isGrid;
        gridView.hidden = !isGrid;
      });
    });
  });

  // "Research again" — re-running research on a Knowledge Object never
  // overwrites it (owner's requirement): this creates a new version row
  // immediately after the newest existing version of that entity, in
  // BOTH the table and the card grid at once, so switching views after
  // clicking still shows it. A real backend would return the new
  // version's real fields; this fixture bumps the visible version tag,
  // marks sources/processing as freshly re-run, and stamps "Just now".
  function addResearchVersion(entityId) {
    [document.getElementById('know-view-table'), document.getElementById('know-view-grid')].forEach(function (container) {
      if (!container) return;
      var existing = container.querySelectorAll('[data-entity="' + entityId + '"]');
      if (!existing.length) return;
      var latest = existing[existing.length - 1];
      var nextVersion = existing.length + 1;
      var clone = latest.cloneNode(true);
      clone.dataset.version = String(nextVersion);
      var vTag = clone.querySelector('.version-tag');
      if (vTag) vTag.textContent = 'v' + nextVersion;
      var updatedCell = clone.querySelector('.updated-cell');
      if (updatedCell) updatedCell.textContent = 'Just now';
      clone.classList.add('is-new-version');
      latest.insertAdjacentElement('afterend', clone);
    });
  }
  document.addEventListener('click', function (e) {
    var btn = e.target.closest('.research-again-btn');
    if (!btn) return;
    addResearchVersion(btn.dataset.entity);
  });

  // Tabs are illustrative in the prototype but must still behave for keyboard users.
  document.querySelectorAll('[role="tablist"]').forEach(function (list) {
    list.addEventListener('click', function (e) {
      var t = e.target.closest('[role="tab"]');
      if (!t) return;
      list.querySelectorAll('[role="tab"]').forEach(function (x) { x.setAttribute('aria-selected', String(x === t)); });
    });
  });

  // --- Login / 6-digit code: a real countdown and a real wrong-attempt
  // lockout state machine, not just descriptive copy. There is no
  // backend here, so "correct" is a fixed fixture value (123456,
  // written into the page's own help text) rather than anything secret.
  (function () {
    var loginForm = document.querySelector('#screen-login .auth-form');
    var emailInput = document.getElementById('login-email');
    var codeEmailLabel = document.getElementById('login-code-email');
    var googleBtn = document.querySelector('#screen-login .auth-btn--google');
    var otpBoxes = Array.prototype.slice.call(document.querySelectorAll('.otp-box'));
    var verifyBtn = document.getElementById('otp-verify-btn');
    var resendBtn = document.getElementById('otp-resend-btn');
    var otpMsg = document.getElementById('otp-message');
    var RESEND_SECONDS = 5 * 60;
    var wrongAttempts = 0;
    var timerInterval = null;

    function fmtClock(sec) {
      var m = Math.floor(sec / 60), s = sec % 60;
      return m + ':' + (s < 10 ? '0' : '') + s;
    }
    function setOtpMessage(text, tone) {
      if (!otpMsg) return;
      otpMsg.textContent = text || '';
      otpMsg.className = 'otp-message' + (tone ? ' otp-message--' + tone : '');
    }
    function startResendTimer() {
      if (!resendBtn) return;
      var remaining = RESEND_SECONDS;
      resendBtn.disabled = true;
      resendBtn.textContent = 'Resend code (' + fmtClock(remaining) + ')';
      clearInterval(timerInterval);
      timerInterval = setInterval(function () {
        remaining--;
        if (remaining <= 0) {
          clearInterval(timerInterval);
          resendBtn.disabled = false;
          resendBtn.textContent = 'Resend code';
        } else {
          resendBtn.textContent = 'Resend code (' + fmtClock(remaining) + ')';
        }
      }, 1000);
    }
    function setLocked(hours) {
      otpBoxes.forEach(function (b) { b.disabled = true; });
      if (verifyBtn) verifyBtn.disabled = true;
      clearInterval(timerInterval);
      if (resendBtn) resendBtn.disabled = true;
      setOtpMessage(
        'Too many incorrect attempts — this email is locked for ' + hours + ' hour' + (hours === 1 ? '' : 's') + '.' +
        (hours >= 24 ? ' You can no longer retry with this email; use the contact link below instead.' : ''),
        'error'
      );
    }

    if (loginForm) {
      loginForm.addEventListener('submit', function (e) {
        e.preventDefault();
        if (codeEmailLabel && emailInput) codeEmailLabel.textContent = emailInput.value || 'you@example.com';
        wrongAttempts = 0;
        otpBoxes.forEach(function (b) { b.disabled = false; b.value = ''; });
        if (verifyBtn) verifyBtn.disabled = false;
        setOtpMessage('');
        location.hash = '#screen-login-code';
        startResendTimer();
        if (otpBoxes[0]) otpBoxes[0].focus();
      });
    }
    if (googleBtn) {
      // The owner's explicit instruction: Google sign-in skips the
      // 6-digit code entirely, unlike email — it goes straight to the
      // dashboard, the same as any other verified session would.
      googleBtn.addEventListener('click', function () { location.hash = '#screen-dashboard'; });
    }
    if (resendBtn) {
      resendBtn.addEventListener('click', function () {
        startResendTimer();
        setOtpMessage('A new code was sent.', 'info');
      });
    }
    if (verifyBtn) {
      verifyBtn.addEventListener('click', function () {
        var code = otpBoxes.map(function (b) { return b.value; }).join('');
        if (code.length < 6) { setOtpMessage('Enter all 6 digits.', 'error'); return; }
        if (code === '123456') {
          setOtpMessage('Verified — signing you in…', 'success');
          clearInterval(timerInterval);
          setTimeout(function () { location.hash = '#screen-dashboard'; }, 500);
          return;
        }
        wrongAttempts++;
        otpBoxes.forEach(function (b) { b.value = ''; });
        if (otpBoxes[0]) otpBoxes[0].focus();
        if (wrongAttempts === 3) setLocked(1);
        else if (wrongAttempts >= 6) setLocked(24);
        else setOtpMessage('Incorrect code — ' + (3 - (wrongAttempts % 3)) + ' attempt(s) left before a temporary lock.', 'error');
      });
    }
    otpBoxes.forEach(function (box, i) {
      box.addEventListener('input', function () {
        box.value = box.value.replace(/[^0-9]/g, '').slice(0, 1);
        if (box.value && otpBoxes[i + 1]) otpBoxes[i + 1].focus();
      });
      box.addEventListener('keydown', function (e) {
        if (e.key === 'Backspace' && !box.value && otpBoxes[i - 1]) otpBoxes[i - 1].focus();
      });
      box.addEventListener('paste', function (e) {
        var text = ((e.clipboardData || window.clipboardData).getData('text') || '').replace(/[^0-9]/g, '');
        if (!text) return;
        e.preventDefault();
        text.slice(0, 6).split('').forEach(function (ch, idx) { if (otpBoxes[idx]) otpBoxes[idx].value = ch; });
        var last = otpBoxes[Math.min(text.length, 6) - 1];
        if (last) last.focus();
      });
    });
    if (document.getElementById('screen-login-code')) startResendTimer();
  }());
}());
</script>
</body>
</html>
`;

// index.html has drifted far ahead of this script (see
// docs/v5/V5_DASHBOARD_AUDIT.md, "Build drift"). Overwriting it would delete
// the v5 work, so refuse unless the caller explicitly accepts that.
if (!process.argv.includes('--force-overwrite')) {
  console.error('Refusing to overwrite visual-harness/index.html: it is ahead of build.js.\n' +
    'See docs/v5/V5_DASHBOARD_AUDIT.md ("Build drift"). Pass --force-overwrite to write anyway.');
  process.exit(1);
}

fs.writeFileSync(path.join(__dirname, 'index.html'), html, 'utf8');
console.log('visual-harness/index.html written (%d KB), %d icons from the canonical registry',
  Math.round(Buffer.byteLength(html) / 1024), Object.keys(registry.icons).length);
