# AIOL for iPhone and iPad

> GENERATED from apps/shared by apps/shared/scripts/export-platforms.mjs — do not edit here; edit apps/shared and re-run it.

This folder is complete on its own: the user interface (`app/`), the native shell (`src-tauri/`), the
iPhone and iPad configuration and icons, and the scripts it needs. Copy or hand over just this folder and it builds.

## Build

Host: macOS with Xcode 15+, CocoaPods, Rust iOS targets, Node 22.

```bash
npm ci
node scripts/configure-release.mjs https://YOUR-CLOUD-CORE/api/v1   # production API; pins the CSP to it
npm run setup && npm run build
```

Output: `src-tauri/gen/apple/build/`

Without the configure step the app points at a development Cloud Core on `http://127.0.0.1:8010`.

## Signing

An Apple Developer team, distribution certificate and provisioning profile (APPLE_DEVELOPMENT_TEAM). Never commit keys, certificates, keystores or provisioning profiles.

## Where the source lives

Edit `apps/shared`, then run `node apps/shared/scripts/export-platforms.mjs` to refresh this folder. CI fails if this
folder and apps/shared disagree.
