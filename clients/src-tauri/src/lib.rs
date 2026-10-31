//! AIOL client shell (ADR-137). A thin native wrapper around the shared UI in ../app.
//!
//! The WebView gets exactly six commands. It cannot read files, spawn processes, open arbitrary URLs or read the
//! device private key: there is no command for any of that, and the capability file grants nothing else.
//!
//!   app_info                       version + platform, for display and for device registration metadata
//!   vault_get / vault_set / vault_delete   ONLY the names in vault::WEBVIEW_ALLOWED (the refresh secret)
//!   device_key_public              create-or-load the installation key; returns the PUBLIC key only
//!   device_key_sign                sign a server challenge (domain-tagged input only)
//!   device_key_delete
//!   open_external                  https / mailto only, validated here as well as in the UI
mod device_key;
mod links;
mod vault;

use serde::Serialize;
use vault::VaultError;

#[cfg(not(target_os = "android"))]
use vault::{OsVault, Vault};

#[derive(Serialize)]
struct AppInfo {
    version: String,
    platform: &'static str,
    os_family: &'static str,
    os_version: String,
}

const fn platform() -> &'static str {
    if cfg!(target_os = "windows") {
        "windows"
    } else if cfg!(target_os = "macos") {
        "macos"
    } else if cfg!(target_os = "android") {
        "android"
    } else if cfg!(target_os = "ios") {
        "ios"
    } else {
        // Linux development builds only; Linux is not a release target. Registered as a web-like client so its
        // evidence is never mistaken for one of the four supported platforms.
        "web"
    }
}

#[tauri::command]
fn app_info(app: tauri::AppHandle) -> AppInfo {
    let info = os_info::get();
    AppInfo {
        version: app.package_info().version.to_string(),
        platform: platform(),
        os_family: platform(),
        // Coarse OS version only (e.g. "10.0.22631", "14.5"); no hardware model, no serials.
        os_version: info.version().to_string().chars().take(40).collect(),
    }
}

fn guard(name: &str) -> Result<(), VaultError> {
    if vault::webview_may_access(name) { Ok(()) } else { Err(VaultError::Refused) }
}

#[cfg(not(target_os = "android"))]
mod commands {
    use super::*;

    #[tauri::command]
    pub fn vault_get(key: String) -> Result<Option<String>, VaultError> {
        guard(&key)?;
        OsVault.get(&key)
    }

    #[tauri::command]
    pub fn vault_set(key: String, value: String) -> Result<(), VaultError> {
        guard(&key)?;
        if value.len() > 512 {
            return Err(VaultError::Refused);
        }
        OsVault.set(&key, &value)
    }

    #[tauri::command]
    pub fn vault_delete(key: String) -> Result<(), VaultError> {
        guard(&key)?;
        OsVault.delete(&key)
    }

    #[tauri::command]
    pub fn device_key_public(create: bool) -> Result<Option<device_key::PublicKeyOut>, VaultError> {
        device_key::public_key(&OsVault, create)
    }

    #[tauri::command]
    pub fn device_key_sign(message: String) -> Result<String, VaultError> {
        device_key::sign(&OsVault, &message)
    }

    #[tauri::command]
    pub fn device_key_delete() -> Result<(), VaultError> {
        device_key::delete(&OsVault)
    }
}

/// Android: the vault and the device key live in Android Keystore, implemented by the Kotlin plugin
/// (mobile/android/VaultPlugin.kt). These commands forward to it with the same guards.
#[cfg(target_os = "android")]
mod commands {
    use super::*;
    use serde::de::DeserializeOwned;
    use tauri::{plugin::PluginHandle, Manager, Runtime, State, Wry};

    pub struct Mobile<R: Runtime>(pub PluginHandle<R>);

    fn call<T: DeserializeOwned>(m: &Mobile<Wry>, cmd: &str, args: serde_json::Value) -> Result<T, VaultError> {
        m.0.run_mobile_plugin(cmd, args).map_err(|_| VaultError::Unavailable)
    }

    #[tauri::command]
    pub fn vault_get(m: State<'_, Mobile<Wry>>, key: String) -> Result<Option<String>, VaultError> {
        guard(&key)?;
        #[derive(serde::Deserialize)]
        struct R { value: Option<String> }
        Ok(call::<R>(&m, "vaultGet", serde_json::json!({ "key": key }))?.value)
    }

    #[tauri::command]
    pub fn vault_set(m: State<'_, Mobile<Wry>>, key: String, value: String) -> Result<(), VaultError> {
        guard(&key)?;
        if value.len() > 512 {
            return Err(VaultError::Refused);
        }
        call::<serde_json::Value>(&m, "vaultSet", serde_json::json!({ "key": key, "value": value })).map(|_| ())
    }

    #[tauri::command]
    pub fn vault_delete(m: State<'_, Mobile<Wry>>, key: String) -> Result<(), VaultError> {
        guard(&key)?;
        call::<serde_json::Value>(&m, "vaultDelete", serde_json::json!({ "key": key })).map(|_| ())
    }

    #[derive(serde::Deserialize, serde::Serialize)]
    pub struct AndroidKey {
        public_key: String,
        storage: String,
    }

    #[tauri::command]
    pub fn device_key_public(m: State<'_, Mobile<Wry>>, create: bool) -> Result<Option<AndroidKey>, VaultError> {
        #[derive(serde::Deserialize)]
        struct R { key: Option<AndroidKey> }
        Ok(call::<R>(&m, "deviceKeyPublic", serde_json::json!({ "create": create }))?.key)
    }

    #[tauri::command]
    pub fn device_key_sign(m: State<'_, Mobile<Wry>>, message: String) -> Result<String, VaultError> {
        if !message.starts_with("AIOL-DEVICE-v1\n") || !message.is_ascii() || message.len() > 512 {
            return Err(VaultError::Refused);
        }
        #[derive(serde::Deserialize)]
        struct R { signature: String }
        Ok(call::<R>(&m, "deviceKeySign", serde_json::json!({ "message": message }))?.signature)
    }

    #[tauri::command]
    pub fn device_key_delete(m: State<'_, Mobile<Wry>>) -> Result<(), VaultError> {
        call::<serde_json::Value>(&m, "deviceKeyDelete", serde_json::json!({})).map(|_| ())
    }

    pub fn plugin<R: Runtime>() -> tauri::plugin::TauriPlugin<R> {
        tauri::plugin::Builder::new("aiol-vault")
            .setup(|app, api| {
                let handle = api.register_android_plugin("app.aiol.client", "VaultPlugin")?;
                app.manage(Mobile(handle));
                Ok(())
            })
            .build()
    }
}

#[tauri::command]
fn open_external(app: tauri::AppHandle, url: String) -> Result<(), String> {
    use tauri_plugin_opener::OpenerExt;
    if !links::is_safe_external(&url) {
        return Err("refused".into());
    }
    app.opener().open_url(url, None::<&str>).map_err(|_| "could not open the link".into())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let builder = tauri::Builder::default().plugin(tauri_plugin_opener::init());
    #[cfg(target_os = "android")]
    let builder = builder.plugin(commands::plugin());
    builder
        .invoke_handler(tauri::generate_handler![
            app_info,
            open_external,
            commands::vault_get,
            commands::vault_set,
            commands::vault_delete,
            commands::device_key_public,
            commands::device_key_sign,
            commands::device_key_delete,
        ])
        .run(tauri::generate_context!())
        .expect("error while running the AIOL client");
}
