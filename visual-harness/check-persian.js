#!/usr/bin/env node
/*
 * Persian letter-order check. Bidi rendering hides a reversed string in an
 * editor or chat, so this compares code points, not what the text looks like.
 *   1. Every Persian word in i18n-glossary.md must be in KNOWN below.
 *   2. No word in index.html's FA dictionary may be a KNOWN word reversed.
 *   3. No word in the FA dictionary may be the reverse of another word in it.
 * KNOWN is written in hex so it cannot be reversed by rendering. A new
 * glossary word is added here deliberately, after checking its code points.
 * Two real words that happen to be each other's reverse go in
 * check-persian-allow.json ({ pair: [hex, hex], reason }), never by
 * changing a translation; listed pairs are skipped silently.
 * Usage: node visual-harness/check-persian.js   Exit: 0 ok, 1 otherwise.
 */
const fs = require('fs');
const path = require('path');

const KNOWN = [
  '067e063106480646062f0647 062f062706460634 067e063106480646062f0647200c0647062706cc',
  '06450648062c0648062f06cc062a 0627062f06390627 0634064806270647062f 063406270647062f',
  '0645064606280639 06330646062f 062a0628062f06cc0644 063406a906270641 062a0639062706310636',
  '0645062a0639062706310636 0645064606340623 06460633062e0647 067e0698064806470634',
  '0627062c0631062706cc 0645062c062f062f 062f0633062a0647 0628062e0634 06450627062a063106cc0633',
  '0645064506cc063206cc 067e064806340634 06270633062a06460627062f 06270646062a063406270631',
  '0645062a0646 06a9062706450644 0642062706280644 06270639062a06450627062f 06280648062f0646',
  '067e06cc0634200c0646064806cc0633 062f0631 062d06270644 062806310631063306cc',
  '062a062306cc06cc062f0634062f0647 06450646062a063406310634062f0647',
  '0628062706cc06af0627064606cc200c0634062f0647 06350641 067e0631062f062706320634',
  '062a064406270634 062f06480628062706310647 0645064806410642 064606270645064806410642',
  '0644063a06480634062f0647 064606cc0627063206450646062f 0627064606330627064606cc',
  '06270646062a063806270631 062806270632 062d0644200c0634062f0647 0631062f0634062f0647',
  '062f0627062f06470654 06460645064806460647 06320646062f0647 0645062a06350644 064606cc0633062a',
  '064706480634 0645063506460648063906cc 062f06cc062f0647200c0634062f0646',
  '06270631062706260647200c062f06470646062f0647 0645062f0644 0639062706450644',
  '063306cc06270633062a 0645063306cc063106cc0627062806cc 062d0627064106380647 064506cc0632',
  '06a906270631 06a9064406cc062f0648062706980647 0639062806270631062a',
  '062c0633062a200c0648062c0648 0647062f0641 062e06320646062f0647 063306270632064506270646',
  '06a90627063106280631 06450627064406a9 06a906cc0641 067e06480644 062f0641062a0631',
  '062a0631062706a906460634200c06470627 067e0631062f0627062e062a 0645062d063506480644',
  '067e06cc0634064606470627062f 0641063106480634 06a9062f 06a9062706440627 06450634062a063106a9',
  '064606480634062a06470654 064806280644062706af 0627062f0639062706470627 063406450627',
].join(' ').split(' ').map((h) => String.fromCodePoint(...h.match(/.{4}/g).map((x) => parseInt(x, 16))));

const WORD = /[\u0600-\u06FF\u200C]+/g;
const words = (s) => (s.match(WORD) || []).map((w) => w.replace(/^\u200C+|\u200C+$/g, '')).filter((w) => w.length > 1);
const hex = (w) => [...w].map((c) => c.codePointAt(0).toString(16).padStart(4, '0')).join(' ');
const read = (f) => fs.readFileSync(path.join(__dirname, f), 'utf8');
const known = new Set(KNOWN);
const failures = [];
const allow = new Set(JSON.parse(read('check-persian-allow.json')).map((p) => [...p.pair].sort().join('|')));
const allowed = (a, b) => allow.has([hex(a), hex(b)].sort().join('|'));

for (const w of new Set(words(read('i18n-glossary.md')))) {
  if (!known.has(w)) failures.push(`glossary word not in KNOWN (reversed or new?): ${hex(w)}`);
}
const html = read('index.html');
const fa = html.slice(html.indexOf('var FA = {'), html.indexOf('};', html.indexOf('var FA = {')));
const reversed = new Set(KNOWN.map((w) => [...w].reverse().join('')).filter((r) => !known.has(r)));
const faWords = new Set(words(fa));
for (const w of faWords) {
  if (reversed.has(w) && !allowed(w, [...w].reverse().join(''))) failures.push(`FA dictionary has a reversed glossary word: ${hex(w)}`);
  // Outside the glossary: a word whose reverse is another word in the
  // dictionary is a likely bidi reversal (a valid-word collision).
  const r = [...w].reverse().join('');
  if (!known.has(w) && r !== w && faWords.has(r) && w < r && !allowed(w, r)) failures.push(`FA dictionary has a word and its reverse: ${hex(w)} / ${hex(r)}`);
}

failures.forEach((f) => console.log('FAIL  ' + f));
console.log(failures.length ? `${failures.length} failed.` : `Persian letter order OK (${known.size} known words).`);
process.exit(failures.length ? 1 : 0);
