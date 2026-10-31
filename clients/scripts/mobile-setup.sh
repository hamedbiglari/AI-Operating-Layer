#!/usr/bin/env bash
# Generates the Tauri mobile projects and installs the AIOL native pieces into them (ADR-137).
#   Android: needs Android SDK + NDK (ANDROID_HOME, NDK_HOME) and a JDK 17.
#   iOS:     needs macOS with Xcode and CocoaPods; run with `ios`.
# Usage: scripts/mobile-setup.sh android|ios
set -euo pipefail
cd "$(dirname "$0")/.."
case "${1:-}" in
  android)
    npx tauri android init --ci
    dest=src-tauri/gen/android/app/src/main/java/app/aiol/client
    mkdir -p "$dest"
    cp src-tauri/mobile/android/VaultPlugin.kt "$dest/VaultPlugin.kt"
    manifest=src-tauri/gen/android/app/src/main/AndroidManifest.xml
    # The encrypted vault must not be copied to a backup and restored elsewhere: its Keystore key would not come
    # with it. Disable backup for the app.
    if ! grep -q 'android:allowBackup="false"' "$manifest"; then
      sed -i.bak 's/<application /<application android:allowBackup="false" android:fullBackupContent="false" /' "$manifest"
      rm -f "$manifest.bak"
    fi
    echo "Android project ready: npx tauri android build --aab"
    ;;
  ios)
    npx tauri ios init --ci
    echo "iOS project ready: set the Apple team in src-tauri/gen/apple, then npx tauri ios build --export-method app-store-connect"
    ;;
  *) echo "usage: $0 android|ios" >&2; exit 2 ;;
esac
