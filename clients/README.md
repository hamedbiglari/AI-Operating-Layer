# AIOL official clients

One shared UI (`app/`) and one native shell (`src-tauri/`, Tauri 2) for **Windows, macOS, Android and
iOS** (ADR-137). Linux is not a release target. All four talk to the same Cloud Core: one identity
system, one conversation history, one Device Intelligence registry (ADR-138).

```
clients/
  app/                  shared UI — plain ES modules, no bundler (the repository's convention)
    src/core/           http, errors, session, conversations, device, i18n, platform bridge
    src/ui/             sign-in, shell + account menu, chat, settings/usage/language/apps/upgrade
    vendor/, brand/     GENERATED copies of frontend/design-system, the icon registry and the logo
    app-config.json     the Cloud Core URL (written by the release pipeline)
  src-tauri/            native shell: OS vault, ES256 device key, validated external links
    mobile/android/     Android Keystore plugin (Kotlin)
  test/                 unit tests (node:test, no dependencies)
  e2e/run.mjs           the real UI in Chromium against a live Cloud Core
  scripts/              design-system sync, dev server, mobile project setup
```

## What the client holds, and where

| Item | Where | Lifetime |
|------|-------|----------|
| Access token | JavaScript memory only | 15 min (`NATIVE_ACCESS_TOKEN_EXPIRE_MINUTES`) |
| Refresh secret | Windows Credential Manager · macOS/iOS Keychain · Android Keystore-encrypted prefs. Browser dev mode: memory only | until sign-out, reuse detection, or 14 days absolute |
| Device private key | same OS stores (Android: inside Keystore, non-exportable). Browser: non-extractable WebCrypto key in IndexedDB | until the user turns verification off, or the server revokes it |
| Conversations, drafts | memory only — nothing is written to disk | dropped on sign-out and account switch |
| Language/theme, device-verification on/off, credential id | `localStorage` (not secrets) | per installation |

## Develop

```bash
cd clients
npm ci
npm test                         # unit tests
npm run check:sync               # vendored design system == frontend/
npm run serve                    # http://127.0.0.1:5174/?api=http://127.0.0.1:8010/api/v1
```

Cloud Core must allow the dev origin: `CORS_ALLOWED_ORIGINS=http://127.0.0.1:5174`. Optional links:
`CLIENT_HELP_URL`, `CLIENT_LEARN_MORE_URL`, `CLIENT_PRIVACY_URL`, `CLIENT_TERMS_URL`,
`CLIENT_UPGRADE_URL`, `CLIENT_RELEASES_JSON` (see `cloud-core/app/core/config.py`).

After editing anything in `frontend/`, run `npm run sync`; never edit `app/vendor/` by hand.

### End-to-end

```bash
# Cloud Core in development mode, on a migrated database:
cd cloud-core && APP_ENV=development CORS_ALLOWED_ORIGINS=http://127.0.0.1:5174 \
  CLIENT_HELP_URL=https://help.aiol.example/ CLIENT_PRIVACY_URL=https://aiol.example/privacy \
  uvicorn app.main:app --host 127.0.0.1 --port 8010
```

```bash
cd clients && node e2e/run.mjs   # PLAYWRIGHT_CORE=<path to playwright-core> as in visual-harness/e2e
```

### Native shell tests (any host with Rust; Linux also needs libwebkit2gtk-4.1-dev)

```bash
cd clients/src-tauri && cargo test --locked
```

## Build and release

The production API endpoint is written into `app/app-config.json`
(`{"apiBaseUrl": "https://…/api/v1", "environment": "production"}`); the client refuses a non-https
URL in production. `.github/workflows/clients.yml` does this from the `AIOL_API_BASE_URL` repository
variable.

| Platform | Host + toolchain | Command | Output | Signing prerequisites |
|----------|------------------|---------|--------|-----------------------|
| Windows | Windows 10/11, Rust (MSVC), Node 22, WebView2 (bootstrapper is bundled) | `npx tauri build` | `src-tauri/target/release/bundle/nsis/*.exe`, `msi/*.msi` | Authenticode certificate; set `bundle.windows.certificateThumbprint` or a `signCommand` in CI. Installs per-user, no admin rights. |
| macOS | macOS 11+, Xcode CLT, Rust (both Apple targets) | `npx tauri build --target universal-apple-darwin` | `.app`, `.dmg` | Developer ID Application certificate; `APPLE_CERTIFICATE`, `APPLE_CERTIFICATE_PASSWORD`, `APPLE_SIGNING_IDENTITY`; notarization: `APPLE_ID`, `APPLE_PASSWORD` (app-specific), `APPLE_TEAM_ID`. |
| Android | Android SDK + NDK 27, JDK 17, Rust Android targets | `scripts/mobile-setup.sh android` then `npx tauri android build --aab` | `gen/android/app/build/outputs/bundle/universalRelease/*.aab` | Upload keystore via `gen/android/keystore.properties` (never committed); Play App Signing. |
| iOS / iPadOS | macOS + Xcode 15+, CocoaPods, Rust iOS targets | `scripts/mobile-setup.sh ios` then `npx tauri ios build --export-method app-store-connect` | `.ipa` | Apple Developer team, distribution certificate, provisioning profile, `APPLE_DEVELOPMENT_TEAM`. |

Never commit signing keys, keystores, provisioning profiles or `.env` files. There is no in-app updater
(debt `CLIENT-updater`): an update is a newer signed package. Store publication has not happened.

**Before a store submission:** Apple privacy manifest and App Store privacy labels (data: email,
user content, device ID = the app-scoped key thumbprint, coarse network pseudonym); Google Play Data
safety form; review of the in-app Device Intelligence disclosure by counsel; Apple/Google billing
policy review before any purchase link is enabled on mobile (`CLIENT_UPGRADE_PLATFORMS`).

## Known limitations

See `docs/clients/CLIENT_SUITE_REPORT.md` §19–21 and the `CLIENT-*` rows in
`docs/ai-context/DEBT_REGISTER.md`.
