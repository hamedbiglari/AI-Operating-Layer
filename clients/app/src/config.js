// Where Cloud Core is. One file, written by the release pipeline (clients/README.md §release), validated here.
//
// Production builds must point at https. Plain http is accepted only for loopback, i.e. a developer's own
// Cloud Core. In a browser on a loopback origin, ?api=<url> may override it for local testing; a packaged app
// and any non-loopback origin ignore the parameter, so a crafted link cannot redirect a user's session.

const LOOPBACK = new Set(['localhost', '127.0.0.1', '[::1]']);

export function validateApiBase(raw, { environment = 'production' } = {}) {
  let u;
  try { u = new URL(raw); } catch { throw new Error('apiBaseUrl is not a URL'); }
  if (u.username || u.password || u.search || u.hash) throw new Error('apiBaseUrl must be a plain origin + path');
  if (u.protocol === 'https:') return u.href.replace(/\/+$/, '');
  if (u.protocol === 'http:' && LOOPBACK.has(u.hostname) && environment !== 'production') {
    return u.href.replace(/\/+$/, '');
  }
  throw new Error('apiBaseUrl must be https (http is allowed only for loopback in development)');
}

export async function loadConfig({ bridgeKind, location = globalThis.location, fetchImpl = globalThis.fetch } = {}) {
  const res = await fetchImpl(new URL('../app-config.json', import.meta.url));
  const cfg = await res.json();
  let base = cfg.apiBaseUrl;
  if (bridgeKind === 'web' && location && LOOPBACK.has(location.hostname)) {
    const override = new URLSearchParams(location.search).get('api');
    if (override) base = override;
  }
  return { ...cfg, apiBaseUrl: validateApiBase(base, cfg) };
}
