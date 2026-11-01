import { test } from 'node:test';
import assert from 'node:assert/strict';
import { exportPlatforms, platformFiles, PLATFORMS } from '../scripts/export-platforms.mjs';

test('the four platform folders are exactly what apps/shared generates (no hand edits, no drift)', () => {
  assert.deepEqual(exportPlatforms({ check: true }), []);
});

test('each platform folder is complete on its own', () => {
  for (const name of Object.keys(PLATFORMS)) {
    const f = platformFiles(name);
    for (const need of ['package.json', 'package-lock.json', 'README.md', 'app/index.html', 'app/src/main.js',
                        'app/vendor/tokens.css', 'src-tauri/Cargo.toml', 'src-tauri/Cargo.lock', 'src-tauri/src/lib.rs',
                        'src-tauri/tauri.conf.json', 'scripts/configure-release.mjs']) {
      assert.ok(need in f, `${name}: ${need}`);
    }
    assert.equal(JSON.parse(f['package.json']).name, `aiol-${name}`);
    assert.equal(JSON.parse(f['app/app-config.json']).environment, 'development', 'no production URL is baked in');
  }
});

test('each folder bundles only its own platform', () => {
  assert.deepEqual(JSON.parse(platformFiles('windows')['src-tauri/tauri.conf.json']).bundle.targets, ['nsis', 'msi']);
  assert.deepEqual(JSON.parse(platformFiles('macos')['src-tauri/tauri.conf.json']).bundle.targets, ['app', 'dmg']);
  assert.ok('src-tauri/mobile/android/VaultPlugin.kt' in platformFiles('android'));
  assert.ok(!('src-tauri/mobile/android/VaultPlugin.kt' in platformFiles('ios')));
  assert.ok(!('scripts/mobile-setup.sh' in platformFiles('windows')));
});
