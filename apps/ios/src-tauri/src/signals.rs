//! Optional platform signals for Device Intelligence (master prompt §16.1, ADR-138).
//!
//! * Windows: `HKLM\SOFTWARE\Microsoft\Cryptography\MachineGuid`, read-only, no elevation. It identifies a Windows
//!   *installation*, not hardware and not a person, and it can be changed, copied with a disk image, or missing.
//!   The value is sent once per registration/verification over TLS; Cloud Core turns it into a keyed, versioned
//!   HMAC on arrival and never stores, logs or returns it raw.
//! * GDID: not collected. No documented, verifiable API for it was identified, and the prompt forbids inventing
//!   one or simulating a value; its state is reported as "unsupported".
//! * macOS, iOS, Android: no OS-installation identifier is read (no serials, UDID, IMEI, ANDROID_ID).
//!
//! Nothing here runs unless the user has installation verification turned on (the UI only asks when it is).
use serde::Serialize;

#[derive(Serialize, Debug, Default, PartialEq)]
pub struct Signals {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub machine_guid: Option<String>,
}

#[cfg(target_os = "windows")]
fn machine_guid() -> Option<String> {
    use winreg::enums::{HKEY_LOCAL_MACHINE, KEY_READ, KEY_WOW64_64KEY};
    use winreg::RegKey;
    // KEY_WOW64_64KEY: read the native 64-bit view even from a 32-bit process.
    let key = RegKey::predef(HKEY_LOCAL_MACHINE)
        .open_subkey_with_flags(r"SOFTWARE\Microsoft\Cryptography", KEY_READ | KEY_WOW64_64KEY)
        .ok()?;
    let value: String = key.get_value("MachineGuid").ok()?;
    normalise(&value)
}

#[cfg(not(target_os = "windows"))]
fn machine_guid() -> Option<String> {
    None
}

/// Accept only a well-formed GUID; anything else is treated as unavailable rather than sent.
#[cfg_attr(not(any(target_os = "windows", test)), allow(dead_code))]
pub fn normalise(raw: &str) -> Option<String> {
    let v = raw.trim().trim_matches(|c| c == '{' || c == '}').to_ascii_lowercase();
    let parts: Vec<&str> = v.split('-').collect();
    let lens = [8, 4, 4, 4, 12];
    if parts.len() == 5
        && parts.iter().zip(lens).all(|(p, n)| p.len() == n && p.chars().all(|c| c.is_ascii_hexdigit()))
    {
        Some(v)
    } else {
        None
    }
}

#[tauri::command]
pub fn platform_signals() -> Signals {
    Signals { machine_guid: machine_guid() }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn only_well_formed_guids_are_sent() {
        assert_eq!(
            normalise("{3F2504E0-4F89-11D3-9A0C-0305E82C3301}").as_deref(),
            Some("3f2504e0-4f89-11d3-9a0c-0305e82c3301")
        );
        for bad in ["", "not-a-guid", "3f2504e0-4f89-11d3-9a0c", "zzzzzzzz-4f89-11d3-9a0c-0305e82c3301"] {
            assert_eq!(normalise(bad), None, "{bad}");
        }
    }

    #[test]
    fn non_windows_hosts_send_nothing() {
        if !cfg!(target_os = "windows") {
            assert_eq!(platform_signals(), Signals::default());
            assert_eq!(serde_json::to_string(&platform_signals()).unwrap(), "{}");
        }
    }
}
