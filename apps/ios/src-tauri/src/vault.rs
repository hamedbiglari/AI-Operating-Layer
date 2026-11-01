//! Secure storage for the two secrets the client holds: the session refresh secret and the device private key.
//! Backed by the OS credential store (Windows Credential Manager, macOS/iOS Keychain) through `keyring`.
//! Only the names in ALLOWED can be read or written from the WebView.
use thiserror::Error;

pub const SERVICE: &str = "app.aiol.client";
/// The only vault entries the WebView may touch. The device key is NOT here: it is reachable only through the
/// device_key commands, which never return it.
pub const WEBVIEW_ALLOWED: &[&str] = &["aiol.refresh"];

#[derive(Debug, Error)]
pub enum VaultError {
    #[error("secure storage is unavailable")]
    Unavailable,
    #[error("stored value is unreadable")]
    Corrupt,
    #[error("no such entry")]
    Missing,
    #[error("refused")]
    Refused,
}

impl serde::Serialize for VaultError {
    fn serialize<S: serde::Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        s.serialize_str(&self.to_string())
    }
}

pub trait Vault: Send + Sync {
    fn get(&self, name: &str) -> Result<Option<String>, VaultError>;
    fn set(&self, name: &str, value: &str) -> Result<(), VaultError>;
    fn delete(&self, name: &str) -> Result<(), VaultError>;
}

#[cfg(not(target_os = "android"))]
pub struct OsVault;

#[cfg(not(target_os = "android"))]
impl OsVault {
    fn entry(name: &str) -> Result<keyring::Entry, VaultError> {
        keyring::Entry::new(SERVICE, name).map_err(|_| VaultError::Unavailable)
    }
}

#[cfg(not(target_os = "android"))]
impl Vault for OsVault {
    fn get(&self, name: &str) -> Result<Option<String>, VaultError> {
        match Self::entry(name)?.get_password() {
            Ok(v) => Ok(Some(v)),
            Err(keyring::Error::NoEntry) => Ok(None),
            Err(_) => Err(VaultError::Unavailable),
        }
    }
    fn set(&self, name: &str, value: &str) -> Result<(), VaultError> {
        Self::entry(name)?.set_password(value).map_err(|_| VaultError::Unavailable)
    }
    fn delete(&self, name: &str) -> Result<(), VaultError> {
        match Self::entry(name)?.delete_credential() {
            Ok(()) | Err(keyring::Error::NoEntry) => Ok(()),
            Err(_) => Err(VaultError::Unavailable),
        }
    }
}

/// In-memory vault for tests.
#[cfg(test)]
#[derive(Default)]
pub struct MemoryVault(std::sync::Mutex<std::collections::HashMap<String, String>>);

#[cfg(test)]
impl Vault for MemoryVault {
    fn get(&self, name: &str) -> Result<Option<String>, VaultError> {
        Ok(self.0.lock().unwrap().get(name).cloned())
    }
    fn set(&self, name: &str, value: &str) -> Result<(), VaultError> {
        self.0.lock().unwrap().insert(name.into(), value.into());
        Ok(())
    }
    fn delete(&self, name: &str) -> Result<(), VaultError> {
        self.0.lock().unwrap().remove(name);
        Ok(())
    }
}

pub fn webview_may_access(name: &str) -> bool {
    WEBVIEW_ALLOWED.contains(&name)
}

#[cfg(test)]
mod tests {
    #[test]
    fn the_webview_cannot_name_the_device_key() {
        assert!(super::webview_may_access("aiol.refresh"));
        assert!(!super::webview_may_access(crate::device_key::KEY_ENTRY));
        assert!(!super::webview_may_access("anything-else"));
    }
}
