//! Which URLs the app may hand to the system browser (ADR-137 §security). The same rule as
//! `isSafeExternalUrl` in app/src/core/platform.js, enforced again here because the WebView is not trusted to
//! have checked: https with a host and no credentials, or a plain mailto address. Nothing else — no file:,
//! javascript:, custom schemes or http.
use url::Url;

pub fn is_safe_external(raw: &str) -> bool {
    let Ok(u) = Url::parse(raw) else { return false };
    if !u.username().is_empty() || u.password().is_some() {
        return false;
    }
    match u.scheme() {
        "https" => u.host_str().is_some_and(|h| !h.is_empty()),
        "mailto" => {
            let p = u.path();
            let mut parts = p.split('@');
            matches!((parts.next(), parts.next(), parts.next()), (Some(a), Some(b), None)
                if !a.is_empty() && !b.is_empty() && !p.contains(char::is_whitespace))
        }
        _ => false,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn allows_https_and_mailto_only() {
        assert!(is_safe_external("https://help.aiol.example/a?b=c"));
        assert!(is_safe_external("mailto:support@aiol.example"));
        for bad in [
            "http://aiol.example",
            "javascript:alert(1)",
            "file:///etc/passwd",
            "aiol://callback?token=x",
            "https://user:pw@aiol.example",
            "mailto:not-an-address",
            "",
            "https://",
        ] {
            assert!(!is_safe_external(bad), "{bad}");
        }
    }
}
