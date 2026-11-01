// Writes the four standalone app folders — apps/windows, apps/macos, apps/android, apps/ios — from apps/shared.
//
// WHY COPIES: each platform folder must be complete on its own (its own package.json, UI, native shell, platform
// config, icons and build instructions), so it can be built, handed over or moved without the others. One
// codebase is still the source of truth: these folders are GENERATED, the same rule the repository already
// applies to the plugin's design-system copies. `--check` (CI and test/export-platforms.test.js) fails when a
// folder differs from what this script would write, so a hand edit in a platform folder becomes a red build
// instead of a silent fork.
//
// Usage:  node scripts/export-platforms.mjs           write all four
//         node scripts/export-platforms.mjs --check   verify, change nothing
import { cpSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const shared = join(dirname(fileURLToPath(import.meta.url)), '..');
const appsDir = join(shared, '..');

export const PLATFORMS = {
  windows: { title: 'Windows', bundle: ['nsis', 'msi'], mobile: false, icons: ['32x32.png', '128x128.png', '128x128@2x.png', 'icon.ico', 'icon.png'],
             build: 'npm run build', output: 'src-tauri/target/release/bundle/{nsis,msi}/',
             host: 'Windows 10/11 x64, Rust (MSVC toolchain), Node 22. WebView2 is installed by the bundled bootstrapper if missing.',
             signing: 'An Authenticode code-signing certificate (set bundle.windows.certificateThumbprint or a signCommand).' },
  macos: { title: 'macOS', bundle: ['app', 'dmg'], mobile: false, icons: ['32x32.png', '128x128.png', '128x128@2x.png', 'icon.icns', 'icon.png'],
           build: 'npm run build -- --target universal-apple-darwin', output: 'src-tauri/target/universal-apple-darwin/release/bundle/{macos,dmg}/',
           host: 'macOS 11+, Xcode command line tools, Rust with aarch64-apple-darwin and x86_64-apple-darwin, Node 22.',
           signing: 'Developer ID Application certificate (APPLE_CERTIFICATE, APPLE_CERTIFICATE_PASSWORD, APPLE_SIGNING_IDENTITY) and notarization (APPLE_ID, APPLE_PASSWORD, APPLE_TEAM_ID).' },
  android: { title: 'Android', bundle: [], mobile: true, icons: ['icon.png', 'android'],
             build: 'npm run setup && npm run build', output: 'src-tauri/gen/android/app/build/outputs/',
             host: 'Android SDK + NDK 27 (ANDROID_HOME, NDK_HOME), JDK 17, Rust Android targets, Node 22.',
             signing: 'An upload keystore referenced from src-tauri/gen/android/keystore.properties (never committed); Play App Signing.' },
  ios: { title: 'iPhone and iPad', bundle: [], mobile: true, icons: ['icon.png', 'ios'],
         build: 'npm run setup && npm run build', output: 'src-tauri/gen/apple/build/',
         host: 'macOS with Xcode 15+, CocoaPods, Rust iOS targets, Node 22.',
         signing: 'An Apple Developer team, distribution certificate and provisioning profile (APPLE_DEVELOPMENT_TEAM).' },
};

const HEADER = 'GENERATED from apps/shared by apps/shared/scripts/export-platforms.mjs — do not edit here; edit apps/shared and re-run it.';

function filesUnder(dir, base = dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) out.push(...filesUnder(p, base));
    else out.push(relative(base, p));
  }
  return out.sort();
}

/** Every file of one platform folder, as {relativePath: Buffer|string}. Pure: reads apps/shared only. */
export function platformFiles(name) {
  const p = PLATFORMS[name];
  const files = {};
  const read = (rel) => readFileSync(join(shared, rel));
  // The UI, complete (minus the development API config, replaced below).
  for (const rel of filesUnder(join(shared, 'app'))) files[`app/${rel}`] = read(`app/${rel}`);
  files['app/app-config.json'] = JSON.stringify({ apiBaseUrl: 'http://127.0.0.1:8010/api/v1', environment: 'development' }, null, 2) + '\n';
  // The native shell.
  for (const rel of ['Cargo.toml', 'Cargo.lock', 'build.rs', 'capabilities/default.json']) files[`src-tauri/${rel}`] = read(`src-tauri/${rel}`);
  for (const rel of filesUnder(join(shared, 'src-tauri/src'))) files[`src-tauri/src/${rel}`] = read(`src-tauri/src/${rel}`);
  if (name === 'android') files['src-tauri/mobile/android/VaultPlugin.kt'] = read('src-tauri/mobile/android/VaultPlugin.kt');
  for (const icon of p.icons) {
    const full = join(shared, 'src-tauri/icons', icon);
    if (statSync(full).isDirectory()) for (const rel of filesUnder(full)) files[`src-tauri/icons/${icon}/${rel}`] = readFileSync(join(full, rel));
    else files[`src-tauri/icons/${icon}`] = readFileSync(full);
  }
  // Platform-specific shell configuration: only this platform's bundles and icons.
  const conf = JSON.parse(read('src-tauri/tauri.conf.json'));
  conf.productName = 'AIOL';
  conf.bundle.targets = p.mobile ? 'all' : p.bundle;
  conf.bundle.icon = p.icons.filter((i) => /\.(png|ico|icns)$/.test(i)).map((i) => `icons/${i}`);
  if (name !== 'windows') delete conf.bundle.windows;
  if (name !== 'macos') delete conf.bundle.macOS;
  if (name !== 'ios') delete conf.bundle.iOS;
  if (name !== 'android') delete conf.bundle.android;
  files['src-tauri/tauri.conf.json'] = JSON.stringify(conf, null, 2) + '\n';
  // Scripts this folder needs to build itself.
  files['scripts/configure-release.mjs'] = read('scripts/configure-release.mjs');
  if (p.mobile) files['scripts/mobile-setup.sh'] = read('scripts/mobile-setup.sh');
  // package.json + lockfile under this folder's own name.
  const pkg = JSON.parse(read('package.json'));
  const scripts = { tauri: 'tauri', dev: 'tauri dev', 'configure-release': 'node scripts/configure-release.mjs' };
  if (p.mobile) {
    scripts.setup = `bash scripts/mobile-setup.sh ${name}`;
    scripts.build = name === 'android' ? 'tauri android build --aab' : 'tauri ios build --export-method app-store-connect';
  } else {
    scripts.build = 'tauri build';
  }
  files['package.json'] = JSON.stringify({ name: `aiol-${name}`, private: true, version: pkg.version,
    description: `AIOL for ${p.title} — standalone build folder. ${HEADER}`, type: 'module', scripts,
    devDependencies: pkg.devDependencies }, null, 2) + '\n';
  const lock = JSON.parse(read('package-lock.json'));
  lock.name = `aiol-${name}`;
  if (lock.packages?.['']) { lock.packages[''].name = `aiol-${name}`; delete lock.packages[''].description; }
  files['package-lock.json'] = JSON.stringify(lock, null, 2) + '\n';
  files['.gitignore'] = 'node_modules/\nsrc-tauri/target/\nsrc-tauri/gen/\n';
  files['README.md'] = readme(name, p);
  return files;
}

function readme(name, p) {
  return `# AIOL for ${p.title}

> ${HEADER}

This folder is complete on its own: the user interface (\`app/\`), the native shell (\`src-tauri/\`), the
${p.title} configuration and icons, and the scripts it needs. Copy or hand over just this folder and it builds.

## Build

Host: ${p.host}

\`\`\`bash
npm ci
${p.mobile ? '' : ''}node scripts/configure-release.mjs https://YOUR-CLOUD-CORE/api/v1   # production API; pins the CSP to it
${p.build}
\`\`\`

Output: \`${p.output}\`

Without the configure step the app points at a development Cloud Core on \`http://127.0.0.1:8010\`.

## Signing

${p.signing} Never commit keys, certificates, keystores or provisioning profiles.
${p.mobile ? '' : `
## Updates

With \`AIOL_UPDATER_PUBKEY\` (a minisign public key from \`npx tauri signer generate\`) set when running
\`configure-release.mjs\` and building, and \`TAURI_SIGNING_PRIVATE_KEY\` set for \`tauri build\`, the app carries the
official Tauri updater: it checks Cloud Core's \`/clients/updates\`, verifies every package against the built-in key
and refuses downgrades. Without the key the app has no updater.
`}
## Where the source lives

Edit \`apps/shared\`, then run \`node apps/shared/scripts/export-platforms.mjs\` to refresh this folder. CI fails if this
folder and apps/shared disagree.
`;
}

function same(a, b) {
  const x = Buffer.isBuffer(a) ? a : Buffer.from(a);
  const y = Buffer.isBuffer(b) ? b : Buffer.from(b);
  return x.equals(y);
}

export function exportPlatforms({ check = false } = {}) {
  const drift = [];
  for (const name of Object.keys(PLATFORMS)) {
    const dir = join(appsDir, name);
    const want = platformFiles(name);
    const have = existsSync(dir) ? filesUnder(dir).filter((f) => !/^(node_modules|src-tauri\/target|src-tauri\/gen)\//.test(f)) : [];
    for (const rel of have) if (!(rel in want)) drift.push(`apps/${name}/${rel} (not generated)`);
    for (const [rel, content] of Object.entries(want)) {
      const path = join(dir, rel);
      if (existsSync(path) && same(readFileSync(path), content)) continue;
      drift.push(`apps/${name}/${rel}`);
    }
    if (!check) {
      for (const rel of have) if (!(rel in want)) rmSync(join(dir, rel));
      for (const [rel, content] of Object.entries(want)) {
        mkdirSync(dirname(join(dir, rel)), { recursive: true });
        writeFileSync(join(dir, rel), content);
      }
    }
  }
  return drift;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const check = process.argv.includes('--check');
  const drift = exportPlatforms({ check });
  if (check) {
    if (drift.length) { console.error(`Platform folders out of date (${drift.length}):\n  ` + drift.slice(0, 20).join('\n  ')); process.exit(1); }
    console.log('Platform folders match apps/shared.');
  } else {
    console.log(`Wrote apps/windows, apps/macos, apps/android, apps/ios (${drift.length} file(s) changed).`);
  }
}
