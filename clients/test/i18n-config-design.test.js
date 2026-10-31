import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { createI18n, MESSAGES } from '../app/src/core/i18n.js';
import { validateApiBase } from '../app/src/config.js';
import { isSafeExternalUrl } from '../app/src/core/platform.js';

const repo = new URL('../../', import.meta.url);

test('every key exists in both catalogues and no Persian value is empty or an English copy', () => {
  const en = Object.keys(MESSAGES.en).sort();
  assert.deepEqual(Object.keys(MESSAGES.fa).sort(), en);
  const sameAllowed = new Set(['app.name', 'language.en', 'platform.macos']);
  for (const k of en) {
    assert.ok(MESSAGES.fa[k].trim(), k);
    if (!sameAllowed.has(k)) assert.notEqual(MESSAGES.fa[k], MESSAGES.en[k], `untranslated: ${k}`);
    const ph = (s) => (s.match(/\{\w+\}/g) || []).sort().join();
    assert.equal(ph(MESSAGES.fa[k]), ph(MESSAGES.en[k]), `placeholders differ: ${k}`);
  }
});

test('no Persian word in the catalogue is a reversed copy of a project-known word', () => {
  const src = readFileSync(new URL('visual-harness/check-persian.js', repo), 'utf8');
  const block = src.slice(src.indexOf('const KNOWN = ['), src.indexOf('];', src.indexOf('const KNOWN = [')));
  const hexWords = [...block.matchAll(/'([0-9a-f ]+)'/g)].flatMap((m) => m[1].split(' ')).filter((x) => /^([0-9a-f]{4})+$/.test(x));
  const known = new Set(hexWords.map((hw) => String.fromCodePoint(...hw.match(/.{4}/g).map((x) => parseInt(x, 16)))));
  const reversed = new Set([...known].map((w) => [...w].reverse().join('')).filter((r) => !known.has(r)));
  const words = Object.values(MESSAGES.fa).join(' ').match(/[؀-ۿ‌]+/g) || [];
  assert.ok(known.size > 50, 'the KNOWN list was read');
  for (const w of words) assert.ok(!reversed.has(w), `reversed Persian word: ${w}`);
  // Spot-check code points of words the UI depends on (bidi can hide a reversal in an editor).
  assert.equal(MESSAGES.fa['menu.settings'], 'تنظیمات');
  assert.equal(MESSAGES.fa['menu.logout'], 'خروج');
});

test('arguments are bidi-isolated, numbers localised, direction follows language', () => {
  const i = createI18n('fa');
  assert.equal(i.dir, 'rtl');
  const s = i.t('chat.limit', { used: 3, limit: 10 });
  assert.ok(s.includes('⁨۳⁩') && s.includes('⁨۱۰⁩'));
  assert.equal(createI18n('ar').lang, 'en', 'Arabic is not offered: there is no backend preference for it');
});

test('the API base must be https, except loopback http in development', () => {
  assert.equal(validateApiBase('https://api.aiol.example/api/v1/'), 'https://api.aiol.example/api/v1');
  assert.ok(validateApiBase('http://127.0.0.1:8010/api/v1', { environment: 'development' }));
  assert.throws(() => validateApiBase('http://127.0.0.1:8010/api/v1', { environment: 'production' }));
  assert.throws(() => validateApiBase('http://api.aiol.example/api/v1', { environment: 'development' }));
  assert.throws(() => validateApiBase('https://user:pw@api.aiol.example/'));
  assert.throws(() => validateApiBase('javascript:alert(1)'));
});

test('external links: https and mailto only', () => {
  assert.ok(isSafeExternalUrl('https://help.aiol.example/x'));
  assert.ok(isSafeExternalUrl('mailto:support@aiol.example'));
  for (const bad of ['http://evil.example', 'javascript:alert(1)', 'file:///etc/passwd', 'aiol://callback?token=x',
                     'https://u:p@x.example', 'not a url']) assert.ok(!isSafeExternalUrl(bad), bad);
});

test('the vendored design system is byte-identical to frontend/ (no second design system)', () => {
  execFileSync(process.execPath, [new URL('../scripts/sync-design-system.mjs', import.meta.url).pathname, '--check']);
});

test('client styles use tokens only: no colour literals outside rgba scrims', () => {
  const css = readFileSync(new URL('../app/styles/app.css', import.meta.url), 'utf8');
  assert.deepEqual(css.match(/#[0-9a-fA-F]{3,8}\b/g) ?? [], []);
});

test('no screen writes HTML: innerHTML/outerHTML/insertAdjacentHTML/eval are absent from client source', () => {
  const dirs = ['../app/src/', '../app/src/core/', '../app/src/ui/'];
  for (const d of dirs) {
    for (const f of readdirSync(new URL(d, import.meta.url)).filter((x) => x.endsWith('.js'))) {
      const src = readFileSync(new URL(d + f, import.meta.url), 'utf8');
      assert.ok(!/innerHTML|outerHTML|insertAdjacentHTML|\beval\(|new Function\(/.test(src), `${d}${f}`);
    }
  }
});

test('no token or secret is ever written to localStorage', () => {
  for (const f of ['../app/src/main.js', '../app/src/core/session.js', '../app/src/core/device.js']) {
    const src = readFileSync(new URL(f, import.meta.url), 'utf8');
    for (const m of src.matchAll(/localStorage\.setItem\(([^)]*)\)|#set\(([^)]*)\)/g)) {
      assert.ok(!/token|refresh|secret|key\b/i.test(m[0]), `${f}: ${m[0]}`);
    }
  }
});
