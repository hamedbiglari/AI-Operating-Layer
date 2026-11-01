//! Signed desktop updates (ADR-140). The official Tauri updater, never a custom one:
//! * every downloaded package is verified against the minisign public key compiled into this build
//!   (`AIOL_UPDATER_PUBKEY` at build time) before anything is installed;
//! * `requireSignedVersion` (written by scripts/configure-release.mjs) also rejects a genuine but older package
//!   announced under a newer version number (downgrade protection);
//! * the endpoint is AI Core's `GET /clients/updates/{target}/{arch}/{current_version}`, https only.
//! A build without the public key has no updater at all and says so; it never checks or installs anything.
use serde::Serialize;

pub const PUBKEY: Option<&str> = option_env!("AIOL_UPDATER_PUBKEY");

#[derive(Serialize, Debug, PartialEq)]
pub struct UpdateStatus {
    pub state: &'static str, // "unavailable" | "none" | "available"
    #[serde(skip_serializing_if = "Option::is_none")]
    pub version: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub notes: Option<String>,
}

/// `https://host[/path]` only; returns the endpoint template the updater expands.
pub fn endpoint(api_base: &str) -> Option<String> {
    let u = url::Url::parse(api_base).ok()?;
    if u.scheme() != "https" || u.host_str().is_none() || !u.username().is_empty() || u.password().is_some()
        || u.query().is_some() || u.fragment().is_some()
    {
        return None;
    }
    let base = u.as_str().trim_end_matches('/');
    Some(format!("{base}/clients/updates/{{{{target}}}}/{{{{arch}}}}/{{{{current_version}}}}"))
}

#[cfg(desktop)]
pub mod imp {
    use super::*;
    use tauri_plugin_updater::UpdaterExt;

    fn updater(app: &tauri::AppHandle, api_base: &str) -> Result<Option<tauri_plugin_updater::Updater>, String> {
        let (Some(key), Some(ep)) = (PUBKEY, endpoint(api_base)) else { return Ok(None) };
        let url = url::Url::parse(&ep).map_err(|_| "bad endpoint".to_string())?;
        app.updater_builder()
            .pubkey(key)
            .endpoints(vec![url])
            .map_err(|_| "bad endpoint".to_string())?
            .build()
            .map(Some)
            .map_err(|_| "updater unavailable".to_string())
    }

    #[tauri::command]
    pub async fn update_check(app: tauri::AppHandle, api_base: String) -> Result<UpdateStatus, String> {
        let Some(u) = updater(&app, &api_base)? else {
            return Ok(UpdateStatus { state: "unavailable", version: None, notes: None });
        };
        match u.check().await.map_err(|_| "check failed".to_string())? {
            Some(update) => Ok(UpdateStatus { state: "available", version: Some(update.version.clone()), notes: update.body.clone() }),
            None => Ok(UpdateStatus { state: "none", version: None, notes: None }),
        }
    }

    #[tauri::command]
    pub async fn update_install(app: tauri::AppHandle, api_base: String) -> Result<(), String> {
        let Some(u) = updater(&app, &api_base)? else { return Err("unavailable".into()) };
        let Some(update) = u.check().await.map_err(|_| "check failed".to_string())? else { return Ok(()) };
        // Verification failure (bad or missing signature, wrong signed version) aborts here: nothing is installed.
        update.download_and_install(|_, _| {}, || {}).await.map_err(|_| "install failed".to_string())?;
        app.restart();
    }
}

#[cfg(mobile)]
pub mod imp {
    use super::*;

    #[tauri::command]
    pub async fn update_check(_api_base: String) -> Result<UpdateStatus, String> {
        // Store-distributed apps update through the store.
        Ok(UpdateStatus { state: "unavailable", version: None, notes: None })
    }

    #[tauri::command]
    pub async fn update_install(_api_base: String) -> Result<(), String> {
        Err("unavailable".into())
    }
}


#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_endpoint_is_https_cloud_core_only() {
        assert_eq!(
            endpoint("https://api.aiol.example/api/v1/").as_deref(),
            Some("https://api.aiol.example/api/v1/clients/updates/{{target}}/{{arch}}/{{current_version}}")
        );
        for bad in ["http://api.aiol.example/api/v1", "https://u:p@api.aiol.example", "https://api.aiol.example/?x=1",
                    "file:///etc", "nonsense"] {
            assert_eq!(endpoint(bad), None, "{bad}");
        }
    }

    #[test]
    fn a_build_without_a_public_key_has_no_updater() {
        if PUBKEY.is_none() {
            assert_eq!(serde_json::to_string(&UpdateStatus { state: "unavailable", version: None, notes: None }).unwrap(),
                       r#"{"state":"unavailable"}"#);
        }
    }
}
