# AIOL for Windows

> GENERATED from apps/shared by apps/shared/scripts/export-platforms.mjs — do not edit here; edit apps/shared and re-run it.

This folder is complete on its own: the user interface (`app/`), the native shell (`src-tauri/`), the
Windows configuration and icons, and the scripts it needs. Copy or hand over just this folder and it builds.

## Build

Host: Windows 10/11 x64, Rust (MSVC toolchain), Node 22. WebView2 is installed by the bundled bootstrapper if missing.

```bash
npm ci
node scripts/configure-release.mjs https://YOUR-CLOUD-CORE/api/v1   # production API; pins the CSP to it
npm run build
```

Output: `src-tauri/target/release/bundle/{nsis,msi}/`

Without the configure step the app points at a development Cloud Core on `http://127.0.0.1:8010`.

## Signing

An Authenticode code-signing certificate (set bundle.windows.certificateThumbprint or a signCommand). Never commit keys, certificates, keystores or provisioning profiles.

## Updates

With `AIOL_UPDATER_PUBKEY` (a minisign public key from `npx tauri signer generate`) set when running
`configure-release.mjs` and building, and `TAURI_SIGNING_PRIVATE_KEY` set for `tauri build`, the app carries the
official Tauri updater: it checks Cloud Core's `/clients/updates`, verifies every package against the built-in key
and refuses downgrades. Without the key the app has no updater.

## Where the source lives

Edit `apps/shared`, then run `node apps/shared/scripts/export-platforms.mjs` to refresh this folder. CI fails if this
folder and apps/shared disagree.
