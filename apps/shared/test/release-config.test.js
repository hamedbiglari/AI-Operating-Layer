import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { releaseConfig } from '../scripts/configure-release.mjs';

const conf = JSON.parse(readFileSync(new URL('../src-tauri/tauri.conf.json', import.meta.url), 'utf8'));

test('a release build may connect only to its own API origin', () => {
  const { appConfig, tauriConf } = releaseConfig('https://api.aiol.example/api/v1/', conf);
  assert.deepEqual(appConfig, { apiBaseUrl: 'https://api.aiol.example/api/v1', environment: 'production' });
  const csp = tauriConf.app.security.csp;
  assert.match(csp, /connect-src 'self' ipc: http:\/\/ipc\.localhost https:\/\/api\.aiol\.example;/);
  assert.ok(!/connect-src[^;]*\bhttps:(?!\/\/)/.test(csp), 'the blanket https: source is gone');
  assert.ok(csp.includes("script-src 'self'") && csp.includes("object-src 'none'"), 'nothing else changes');
});

test('the development config is not mutated', () => {
  releaseConfig('https://api.aiol.example/api/v1', conf);
  assert.match(conf.app.security.csp, /connect-src 'self' ipc: http:\/\/ipc\.localhost https:;/);
});

test('anything but a plain https URL is refused', () => {
  for (const bad of ['http://api.aiol.example', 'https://u:p@api.aiol.example', 'https://api.aiol.example/?x=1',
                     'javascript:alert(1)', '', 'https://']) {
    assert.throws(() => releaseConfig(bad, conf), Error, bad);
  }
});
