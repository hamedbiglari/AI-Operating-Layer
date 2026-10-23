#!/usr/bin/env node
/*
 * Source character check. A \uXXXX escape that turned into the raw character
 * on its way into a file changes behaviour silently (it happened twice), so:
 *   1. No non-ASCII character in code or inside a regex literal.
 *   2. No invisible bidi/format character anywhere: direction marks,
 *      embeddings, overrides, isolates, BOM, zero-width space, word joiner.
 *      ZWNJ and ZWJ are allowed; Persian text needs them.
 *   3. ASCII_ONLY files must be pure ASCII, strings and comments included.
 * Scans visual-harness/*.js and the inline <script> blocks of index.html;
 * rule 2 also covers index.html's markup. Elsewhere, strings and comments may
 * hold non-ASCII: the Persian UI lives in them.
 * This file uses no escapes on purpose: special characters are compared by
 * code (charCodeAt), so the conversion it guards against cannot reach it.
 * Usage: node visual-harness/check-source-chars.js [dir] [--report]
 *   --report counts non-ASCII characters per file and context.
 * Exit: 0 ok, 1 otherwise.
 */
const fs = require('fs');
const path = require('path');

const ASCII_ONLY = new Set(['check-persian.js', 'i18n-coverage.js', 'check-source-chars.js']);
const INVISIBLE = new Set([0x061c, 0x200b, 0x200e, 0x200f, 0x202a, 0x202b, 0x202c, 0x202d, 0x202e,
  0x2060, 0x2066, 0x2067, 0x2068, 0x2069, 0xfeff]);
const NL = 10, BACKSLASH = 92, SLASH = 47, STAR = 42, QUOTE = 39, DQUOTE = 34, TICK = 96;
const REGEX_AFTER = '(,=:[!&|?{};+-*%<>~^';
const REGEX_KEYWORDS = new Set(['return', 'typeof', 'case', 'do', 'else', 'in', 'of', 'new', 'delete',
  'void', 'throw', 'yield', 'await']);
const isIdent = (k) => (k >= 48 && k <= 57) || (k >= 65 && k <= 90) || (k >= 97 && k <= 122) || k === 95 || k === 36;
const hex = (k) => 'U+' + k.toString(16).toUpperCase().padStart(4, '0');

// The context of every UTF-16 unit of a JavaScript source:
// code, comment, string, template or regex.
function contexts(src) {
  const ctx = new Array(src.length).fill('code');
  const at = (j) => src.charCodeAt(j);
  const templates = [];        // brace depth at each open ${
  let depth = 0, last = 0, word = '', gap = false;
  for (let i = 0; i < src.length; i++) {
    const k = at(i), n = at(i + 1);
    if (k === SLASH && n === SLASH) {
      while (i < src.length && at(i) !== NL) ctx[i++] = 'comment';
      continue;
    }
    if (k === SLASH && n === STAR) {
      const e = src.indexOf('*/', i + 2), end = e < 0 ? src.length : e + 2;
      while (i < end) ctx[i++] = 'comment';
      i--; continue;
    }
    if (k === QUOTE || k === DQUOTE) {
      ctx[i++] = 'string';
      while (i < src.length && at(i) !== k && at(i) !== NL) { if (at(i) === BACKSLASH) ctx[i++] = 'string'; ctx[i++] = 'string'; }
      ctx[i] = 'string'; last = k; word = ''; continue;
    }
    if (k === TICK || (k === 125 && templates.length && templates[templates.length - 1] === depth)) {
      if (k === 125) templates.pop();
      ctx[i++] = 'template';
      while (i < src.length && at(i) !== TICK && !(at(i) === 36 && at(i + 1) === 123)) { if (at(i) === BACKSLASH) ctx[i++] = 'template'; ctx[i++] = 'template'; }
      if (at(i) === 36) { ctx[i++] = 'template'; ctx[i] = 'template'; templates.push(depth); } else ctx[i] = 'template';
      last = TICK; word = ''; continue;
    }
    if (k === SLASH && (last === 0 || REGEX_AFTER.includes(String.fromCharCode(last)) || REGEX_KEYWORDS.has(word))) {
      ctx[i++] = 'regex';
      let inClass = false;
      while (i < src.length && at(i) !== NL && (inClass || at(i) !== SLASH)) {
        if (at(i) === BACKSLASH) ctx[i++] = 'regex';
        else if (at(i) === 91) inClass = true;
        else if (at(i) === 93) inClass = false;
        ctx[i++] = 'regex';
      }
      ctx[i] = 'regex'; last = 41; word = ''; continue;
    }
    if (k === 123) depth++; else if (k === 125) depth--;
    if (k <= 32) { gap = true; continue; }
    word = isIdent(k) ? (isIdent(last) && !gap ? word : '') + String.fromCharCode(k) : '';
    last = k; gap = false;
  }
  return ctx;
}

const dir = process.argv.slice(2).find((a) => !a.startsWith('--')) || __dirname;
const report = process.argv.includes('--report');
const failures = [], counts = {};

function check(file, src, ctx, asciiOnly) {
  let line = 1;
  for (let i = 0; i < src.length; i++) {
    const k = src.codePointAt(i);
    if (k === NL) line++;
    if (k <= 127) continue;
    const where = file + ':' + line + ' ' + hex(k) + ' in ' + ctx[i];
    counts[file + ' ' + ctx[i]] = (counts[file + ' ' + ctx[i]] || 0) + 1;
    if (INVISIBLE.has(k)) failures.push(where + ' (invisible bidi/format character)');
    else if (ctx[i] === 'code' || ctx[i] === 'regex') failures.push(where + ' (raw character outside a string or comment)');
    else if (asciiOnly) failures.push(where + ' (file must be pure ASCII)');
    if (k > 0xffff) i++;
  }
}

for (const f of fs.readdirSync(dir).filter((x) => x.endsWith('.js')).sort()) {
  const src = fs.readFileSync(path.join(dir, f), 'utf8');
  check(f, src, contexts(src), ASCII_ONLY.has(f));
}
const htmlPath = path.join(dir, 'index.html');
if (fs.existsSync(htmlPath)) {
  const html = fs.readFileSync(htmlPath, 'utf8');
  const ctx = new Array(html.length).fill('markup');
  for (const m of html.matchAll(/<script\b[^>]*>([^]*?)<\/script>/g)) {
    const start = m.index + m[0].indexOf('>') + 1, inner = contexts(m[1]);
    for (let j = 0; j < inner.length; j++) ctx[start + j] = inner[j];
  }
  check('index.html', html, ctx, false);
}

if (report) Object.keys(counts).sort().forEach((k) => console.log(k.padEnd(40) + counts[k]));
failures.forEach((f) => console.log('FAIL  ' + f));
console.log(failures.length ? failures.length + ' failed.' : 'Source characters OK.');
process.exit(failures.length ? 1 : 0);
