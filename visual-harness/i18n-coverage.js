#!/usr/bin/env node
/*
 * Persian translation coverage. Static: reads index.html, no browser.
 *
 *   Per screen: English UI strings (text, aria-label, title, placeholder)
 *   with no entry in the FA dictionary. Text inside <bdi>, <code>, <svg>,
 *   <script>, <style> and any class="identifier" element is skipped, as the
 *   Persian layer skips it.
 *   Templates: every literal template passed to AIOL_I18N.set must have an
 *   FA entry, unless it has no words of its own ('{n}').
 *
 * It does NOT see strings the live modules build at runtime outside
 * AIOL_I18N.set; those are found by switching to Persian in a browser.
 *
 * Usage:
 *   node visual-harness/i18n-coverage.js                  per-screen table
 *   node visual-harness/i18n-coverage.js --screen ID      list that screen's untranslated strings
 *   node visual-harness/i18n-coverage.js --require A,B    exit 1 unless screens A and B are complete
 *                                       (--require A --require B is the same)
 * Exit: 1 if a template has no entry or a required screen is incomplete, else 0.
 */
const fs = require('fs');
const path = require('path');

const html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8');
const arg = (name) => { const i = process.argv.indexOf(name); return i > 0 ? process.argv[i + 1] : null; };
// Every value of a flag that may repeat (--require A --require B).
const args = (name) => process.argv.flatMap((a, i) => (a === name && i + 1 < process.argv.length ? [process.argv[i + 1]] : []));

const faStart = html.indexOf('var FA = {');
const faBlock = html.slice(faStart, html.indexOf('};', faStart));
const FA = new Set([...faBlock.matchAll(/^\s*"((?:[^"\\]|\\.)*)":\s*"/gm)].map((m) => JSON.parse('"' + m[1] + '"')));

const ENTITIES = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: '\u00A0', mdash: '\u2014', ndash: '\u2013', hellip: '\u2026', middot: '\u00B7', rarr: '\u2192', larr: '\u2190', times: '\u00D7' };
const decode = (s) => s.replace(/&(#x[0-9a-f]+|#\d+|\w+);/gi, (m, e) =>
  e[0] === '#' ? String.fromCodePoint(parseInt(e.slice(e[1] === 'x' ? 2 : 1), e[1] === 'x' ? 16 : 10)) : (ENTITIES[e] ?? m));
const norm = (s) => decode(s).replace(/\s+/g, ' ').trim();
// URLs, paths, emails and bare domains are data, not UI text.
const isUiText = (s) => /[A-Za-z]{2}/.test(s) && !/^(https?:\/\/|\/|[\w.+-]+@[\w.-]+$|[\w-]+(\.[\w-]+)+$)/.test(s);

// Removes each [data-debt-hidden] element with everything inside it. Same-name
// tags are counted, so a hidden card holding its own <div>s is removed whole,
// not cut at its first </div>.
function dropDebtHidden(s) {
  const open = /<(\w+)\b[^>]*\bdata-debt-hidden\b[^>]*>/;
  for (let m = s.match(open); m; m = s.match(open)) {
    const tag = new RegExp('<(/?)' + m[1] + '\\b[^>]*>', 'g');
    tag.lastIndex = m.index + m[0].length;
    let depth = 1, t;
    while (depth && (t = tag.exec(s))) depth += t[1] ? -1 : 1;
    s = s.slice(0, m.index) + ' ' + (t ? s.slice(tag.lastIndex) : '');
  }
  return s;
}

const screens = [];
const starts = [...html.matchAll(/<section class="screen[^"]*" id="(screen-[^"]+)"/g)];
starts.forEach((m, i) => {
  const end = i + 1 < starts.length ? starts[i + 1].index : html.indexOf('<script', m.index);
  const body = dropDebtHidden(html.slice(m.index, end).replace(/<(script|style|svg|code|bdi)\b[\s\S]*?<\/\1>/g, ' '))
    .replace(/<(\w+)\b[^>]*\bclass="(?:[^"]*\s)?identifier(?:\s[^"]*)?"[^>]*>[\s\S]*?<\/\1>/g, ' ');
  const found = new Set();
  for (const t of body.matchAll(/>([^<>]+)</g)) found.add(norm(t[1]));
  for (const a of body.matchAll(/\b(?:aria-label|title|placeholder)="([^"]*)"/g)) found.add(norm(a[1]));
  const english = [...found].filter(isUiText);
  screens.push({ id: m[1], english: english.length, missing: english.filter((s) => !FA.has(s)) });
});

const templates = [...html.matchAll(/AIOL_I18N\.set\([^,]+,\s*'((?:[^'\\]|\\.)*)'/g)].map((m) => m[1]);
const badTemplates = [...new Set(templates)].filter((t) => /[A-Za-z]/.test(t.replace(/\{[^}]*\}/g, '')) && !FA.has(t));

const only = arg('--screen');
if (only) {
  const s = screens.find((x) => x.id === only);
  if (!s) { console.log('No such screen: ' + only); process.exit(1); }
  s.missing.forEach((m) => console.log(m));
  console.log(`${s.missing.length} of ${s.english} untranslated on ${only}.`);
} else {
  screens.forEach((s) => console.log(`${s.id.padEnd(36)} ${String(s.english - s.missing.length).padStart(4)} / ${String(s.english).padEnd(4)} translated`));
  const total = screens.reduce((a, s) => a + s.english, 0), missing = screens.reduce((a, s) => a + s.missing.length, 0);
  console.log(`\nAll screens: ${total - missing} of ${total} strings translated. Templates without an entry: ${badTemplates.length}.`);
}
badTemplates.forEach((t) => console.log('FAIL  template has no FA entry: ' + t));
const required = [...new Set(args('--require').join(',').split(',').filter(Boolean))];
const incomplete = required.filter((id) => { const s = screens.find((x) => x.id === id); return !s || s.missing.length > 0; });
incomplete.forEach((id) => console.log('FAIL  screen missing or not fully translated: ' + id));
process.exit(badTemplates.length || incomplete.length ? 1 : 0);
