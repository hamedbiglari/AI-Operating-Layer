// Renders icons from the canonical registry (frontend/icons/icon-paths.json, synced to vendor/icon-paths.js),
// with the same contract as frontend/icons/icon.js: decorative by default, role="img" + <title> when labelled,
// mirrored in RTL only when the registry marks the glyph directional.
import REGISTRY from '../../vendor/icon-paths.js';

const NS = 'http://www.w3.org/2000/svg';
const { geometry, icons } = REGISTRY;

export function icon(name, { label, size } = {}) {
  const def = icons[name];
  if (!def) throw new Error(`Unknown icon: ${name}`);
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', geometry.viewBox);
  svg.setAttribute('fill', geometry.fill);
  svg.setAttribute('stroke', geometry.stroke);
  svg.setAttribute('stroke-width', String(geometry.strokeWidth));
  svg.setAttribute('stroke-linecap', geometry.strokeLinecap);
  svg.setAttribute('stroke-linejoin', geometry.strokeLinejoin);
  svg.setAttribute('class', `icon${def.mirror ? ' icon--mirror' : ''}`);
  if (size) { svg.setAttribute('width', size); svg.setAttribute('height', size); }
  if (label) {
    svg.setAttribute('role', 'img');
    const title = document.createElementNS(NS, 'title');
    title.textContent = label;
    svg.append(title);
  } else {
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
  }
  const p = document.createElementNS(NS, 'path');
  p.setAttribute('d', def.d);
  svg.append(p);
  if (def.extra) {
    // `extra` is SVG geometry from the repository's own registry (a build input, never network data), parsed
    // as XML in the SVG namespace — the same source frontend/icons/icon.js renders.
    const doc = new DOMParser().parseFromString(`<svg xmlns="${NS}">${def.extra}</svg>`, 'image/svg+xml');
    for (const node of [...doc.documentElement.childNodes]) svg.append(document.importNode(node, true));
  }
  return svg;
}
