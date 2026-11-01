# AIOL apps

| Folder | What it is |
|--------|-----------|
| [`shared/`](shared/) | The single source: user interface, native shell (Rust), tests, release scripts. Edit here. |
| [`windows/`](windows/) | Standalone Windows app folder (NSIS + MSI). Generated from `shared/`. |
| [`macos/`](macos/) | Standalone macOS app folder (`.app` + `.dmg`, universal). Generated from `shared/`. |
| [`android/`](android/) | Standalone Android app folder (APK/AAB, Android Keystore plugin). Generated from `shared/`. |
| [`ios/`](ios/) | Standalone iPhone and iPad app folder. Generated from `shared/`. |

Each platform folder builds on its own — see its README. After changing `shared/`, run

```bash
node apps/shared/scripts/export-platforms.mjs
```

CI (`.github/workflows/clients.yml`) fails if a platform folder and `shared/` disagree.
