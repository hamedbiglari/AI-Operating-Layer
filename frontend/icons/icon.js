/*
 * AI Operating Layer — canonical icon abstraction (checkpoint §56, §57).
 *
 * ONE renderer. Pages call `icon('status-completed')`; pages never write
 * <svg> markup themselves. That is the whole point: geometry, stroke width,
 * accessibility and RTL behaviour are decided here once, not re-decided in
 * every screen.
 *
 * ACCESSIBILITY CONTRACT
 *   - Default is decorative: aria-hidden="true", focusable="false". This is
 *     correct whenever the icon sits beside its own label, which is the
 *     normal case in this product because §34 forbids colour/icon-only state.
 *   - An icon that carries meaning alone MUST be given a `label`. It then
 *     renders role="img" with a <title>. There is no third option, and an
 *     icon-only button without a label is a review failure, not a style
 *     preference.
 *
 * RTL CONTRACT (§36, §57)
 *   Only icons marked `mirror` in icon-paths.json are flipped, and they are
 *   flipped by CSS (`[dir="rtl"] .icon--mirror { transform: scaleX(-1) }`),
 *   not by a second set of paths. A magnifier, a back arrow and an
 *   external-link glyph are directional. A clock, a shield and a flask are
 *   not — mechanically mirroring everything is the RTL failure this rule
 *   exists to prevent.
 */

import REGISTRY from './icon-paths.json' with { type: 'json' };

const { geometry, icons } = REGISTRY;

export const ICON_NAMES = Object.freeze(Object.keys(icons));

export function hasIcon(name) {
  return Object.prototype.hasOwnProperty.call(icons, name);
}

/**
 * @param {string} name   a key from icon-paths.json
 * @param {object} [opts]
 * @param {string} [opts.label]  accessible name; omit for decorative icons
 * @param {string} [opts.size]   CSS length; defaults to var(--icon-size)
 * @param {string} [opts.class]  extra class names
 * @returns {string} SVG markup
 */
export function icon(name, opts = {}) {
  const def = icons[name];
  if (!def) {
    // Fail loudly in development rather than silently rendering nothing:
    // a missing icon that renders as empty space is how "random icon"
    // drift starts (§94).
    throw new Error(
      `Unknown icon "${name}". Add it to frontend/icons/icon-paths.json ` +
      `rather than inlining SVG at the call site.`
    );
  }

  const size = opts.size || 'var(--icon-size)';
  const classes = ['icon'];
  if (def.mirror) classes.push('icon--mirror');
  if (opts.class) classes.push(opts.class);

  const labelled = typeof opts.label === 'string' && opts.label.length > 0;
  const a11y = labelled
    ? `role="img" aria-label="${escapeAttr(opts.label)}"`
    : 'aria-hidden="true" focusable="false"';

  return (
    `<svg class="${classes.join(' ')}" ${a11y} ` +
    `viewBox="${geometry.viewBox}" width="${size}" height="${size}" ` +
    `fill="${geometry.fill}" stroke="${geometry.stroke}" ` +
    `stroke-width="var(--icon-stroke, ${geometry.strokeWidth})" ` +
    `stroke-linecap="${geometry.strokeLinecap}" ` +
    `stroke-linejoin="${geometry.strokeLinejoin}">` +
    (labelled ? `<title>${escapeText(opts.label)}</title>` : '') +
    `<path d="${def.d}"/>` +
    (def.extra || '').replace(/'/g, '"') +
    `</svg>`
  );
}

/**
 * Icon-only control. Exists so that "button with an icon and no visible
 * text" has exactly one implementation which cannot be built without a
 * label (§7: every icon-only action requires an accessible label/tooltip).
 */
export function iconButton(name, { label, ...rest } = {}) {
  if (!label) {
    throw new Error(`iconButton("${name}") requires a label. Icon-only controls without an accessible name are not permitted.`);
  }
  const attrs = Object.entries(rest)
    .map(([k, v]) => `${k}="${escapeAttr(String(v))}"`)
    .join(' ');
  return (
    `<button type="button" class="icon-button" aria-label="${escapeAttr(label)}" ` +
    `title="${escapeAttr(label)}" ${attrs}>${icon(name)}</button>`
  );
}

/* ---- Semantic resolvers ----------------------------------------------
 * The mapping from a DOMAIN VALUE to an icon lives here, not in screens.
 * Every key below is a literal value from cloud-core's enums; there is no
 * invented vocabulary and no default branch that silently swallows an
 * unrecognised state. An unknown state resolves to `status-unknown`, which
 * is the honest answer, and is logged.
 */

const EXTRACTION_STATUS_ICONS = {
  pending: 'status-queued',
  extracting: 'status-processing',
  extracted: 'status-completed',
  failed: 'status-failed',
};

const CONVERSION_STATUS_ICONS = {
  pending: 'status-queued',
  succeeded: 'status-completed',
  empty: 'status-warning',
  unsupported: 'status-warning',
  failed: 'status-failed',
};

const JOB_STATUS_ICONS = {
  queued: 'status-queued',
  running: 'status-processing',
  retrying: 'status-processing',
  succeeded: 'status-completed',
  partial: 'status-warning',
  failed: 'status-failed',
  dead_letter: 'status-failed',
  cancelled: 'status-archived',
};

const SOURCE_TYPE_ICONS = {
  pdf: 'source-pdf',
  docx: 'source-docx',
  xlsx: 'source-xlsx',
  website: 'source-url',
  wordpress_article: 'source-cms',
  dataset: 'source-dataset',
  scientific_paper: 'source-research',
  book: 'source-research',
  certificate: 'source-certificate',
  lab_report: 'source-lab',
  supplier_document: 'source-certificate',
  image: 'source-image',
  user_upload: 'source-generic',
  first_party: 'source-generic',
  government: 'source-generic',
  review: 'source-generic',
  news: 'source-generic',
};

export function extractionStatusIcon(v) { return EXTRACTION_STATUS_ICONS[v] || 'status-unknown'; }
export function conversionStatusIcon(v) { return CONVERSION_STATUS_ICONS[v] || 'status-unknown'; }
export function jobStatusIcon(v) { return JOB_STATUS_ICONS[v] || 'status-unknown'; }
export function sourceTypeIcon(v) { return SOURCE_TYPE_ICONS[v] || 'source-generic'; }

function escapeAttr(s) {
  return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
}
function escapeText(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
