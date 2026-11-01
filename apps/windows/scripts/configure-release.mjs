// Release configuration (ADR-137, debt CLIENT-csp-connect-src). Writes app/app-config.json with the production
// AI Core URL and narrows the shell's Content-Security-Policy `connect-src` from any https origin to exactly
// that one, so a packaged app cannot be made to talk to anything else even by script injected into the WebView.
//
// Usage: node scripts/configure-release.mjs https://api.example.com/api/v1
// Refuses anything but an https URL with a host and no credentials, query or fragment.
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

export function releaseConfig(apiBaseUrl, tauriConf, { updaterPubkey = '' } = {}) {
  let u;
  try { u = new URL(apiBaseUrl); } catch { throw new Error('not a URL'); }
  if (u.protocol !== 'https:' || !u.hostname || u.username || u.password || u.search || u.hash) {
    throw new Error('the production API must be a plain https URL');
  }
  const base = u.href.replace(/\/+$/, '');
  const conf = JSON.parse(JSON.stringify(tauriConf));
  const csp = conf.app.security.csp;
  const narrowed = csp.replace(/connect-src [^;]*/, `connect-src 'self' ipc: http://ipc.localhost ${u.origin}`);
  if (narrowed === csp && !csp.includes(`connect-src 'self' ipc: http://ipc.localhost ${u.origin}`)) {
    throw new Error('tauri.conf.json has no connect-src directive to narrow');
  }
  conf.app.security.csp = narrowed;
  // ADR-140: with a minisign public key, desktop builds carry the official updater, verify every package against
  // that key, and refuse a genuine but older package announced under a newer version (requireSignedVersion).
  // `tauri build` then also writes the signed update artifacts (needs TAURI_SIGNING_PRIVATE_KEY).
  if (updaterPubkey) {
    if (!/^[A-Za-z0-9+/=]{40,}$/.test(updaterPubkey)) throw new Error('AIOL_UPDATER_PUBKEY is not a minisign public key');
    conf.plugins = { ...(conf.plugins ?? {}), updater: { pubkey: updaterPubkey, endpoints: [], requireSignedVersion: true } };
    conf.bundle = { ...conf.bundle, createUpdaterArtifacts: true };
  }
  return { appConfig: { apiBaseUrl: base, environment: 'production' }, tauriConf: conf };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const root = new URL('../', import.meta.url);
  const confPath = new URL('src-tauri/tauri.conf.json', root);
  const out = releaseConfig(process.argv[2] ?? '', JSON.parse(readFileSync(confPath, 'utf8')),
                            { updaterPubkey: process.env.AIOL_UPDATER_PUBKEY ?? '' });
  writeFileSync(new URL('app/app-config.json', root), JSON.stringify(out.appConfig, null, 2) + '\n');
  writeFileSync(confPath, JSON.stringify(out.tauriConf, null, 2) + '\n');
  console.log(`release configured for ${out.appConfig.apiBaseUrl}`);
}
