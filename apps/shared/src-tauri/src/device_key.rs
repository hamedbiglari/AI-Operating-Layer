//! The installation's ES256 key (ADR-138). Generated here, stored in the OS credential store as PKCS#8, and never
//! returned to JavaScript: the WebView can ask for the public key and for a signature, nothing else.
//!
//! On Windows (Credential Manager), macOS and iOS (Keychain) the private key is protected by the operating system
//! but is a software key, so `storage` is reported as "os_keystore", never "hardware". Android uses the Kotlin
//! plugin instead, whose key lives in Android Keystore.
use base64::{engine::general_purpose::STANDARD as B64, Engine};
use p256::ecdsa::{signature::Signer, Signature, SigningKey};
use p256::pkcs8::{DecodePrivateKey, EncodePrivateKey, EncodePublicKey};
use p256::SecretKey;
use zeroize::Zeroizing;

use crate::vault::{Vault, VaultError};

pub const KEY_ENTRY: &str = "aiol.device.es256";

#[derive(serde::Serialize, Debug, PartialEq)]
pub struct PublicKeyOut {
    /// base64 DER SubjectPublicKeyInfo
    pub public_key: String,
    pub storage: &'static str,
}

fn load(vault: &dyn Vault) -> Result<Option<SigningKey>, VaultError> {
    let Some(b64) = vault.get(KEY_ENTRY)? else { return Ok(None) };
    let der = Zeroizing::new(B64.decode(b64.as_bytes()).map_err(|_| VaultError::Corrupt)?);
    let secret = SecretKey::from_pkcs8_der(&der).map_err(|_| VaultError::Corrupt)?;
    Ok(Some(SigningKey::from(secret)))
}

pub fn public_key(vault: &dyn Vault, create: bool) -> Result<Option<PublicKeyOut>, VaultError> {
    let key = match load(vault)? {
        Some(k) => k,
        None if create => {
            let secret = SecretKey::random(&mut rand_core::OsRng);
            let der = secret.to_pkcs8_der().map_err(|_| VaultError::Corrupt)?;
            vault.set(KEY_ENTRY, &B64.encode(der.as_bytes()))?;
            SigningKey::from(secret)
        }
        None => return Ok(None),
    };
    let spki = key.verifying_key().to_public_key_der().map_err(|_| VaultError::Corrupt)?;
    Ok(Some(PublicKeyOut { public_key: B64.encode(spki.as_bytes()), storage: "os_keystore" }))
}

/// Signs exactly the bytes the server's challenge told the client to sign. Returns base64 IEEE P1363 (r||s).
pub fn sign(vault: &dyn Vault, message: &str) -> Result<String, VaultError> {
    // The server's signing input is ASCII and starts with its domain tag; refuse anything else so this command
    // cannot be turned into a general-purpose signing oracle by script in the WebView.
    if !message.starts_with("AIOL-DEVICE-v1\n") || !message.is_ascii() || message.len() > 512 {
        return Err(VaultError::Refused);
    }
    let key = load(vault)?.ok_or(VaultError::Missing)?;
    let sig: Signature = key.sign(message.as_bytes());
    Ok(B64.encode(sig.to_bytes()))
}

pub fn delete(vault: &dyn Vault) -> Result<(), VaultError> {
    vault.delete(KEY_ENTRY)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::vault::MemoryVault;
    use p256::ecdsa::{signature::Verifier, VerifyingKey};
    use p256::pkcs8::DecodePublicKey;

    #[test]
    fn create_sign_verify_roundtrip() {
        let v = MemoryVault::default();
        assert_eq!(public_key(&v, false).unwrap(), None, "no key until asked to create one");
        let pk = public_key(&v, true).unwrap().unwrap();
        assert_eq!(pk.storage, "os_keystore");
        assert_eq!(public_key(&v, true).unwrap().unwrap(), pk, "the same key on every launch");
        let msg = "AIOL-DEVICE-v1\nregister\nid\nnonce\norg\nuser\n-";
        let sig = B64.decode(sign(&v, msg).unwrap()).unwrap();
        assert_eq!(sig.len(), 64);
        let vk = VerifyingKey::from_public_key_der(&B64.decode(pk.public_key).unwrap()).unwrap();
        vk.verify(msg.as_bytes(), &Signature::from_slice(&sig).unwrap()).unwrap();
    }

    #[test]
    fn refuses_to_sign_anything_but_a_device_challenge() {
        let v = MemoryVault::default();
        public_key(&v, true).unwrap();
        assert!(matches!(sign(&v, "transfer $100"), Err(VaultError::Refused)));
        assert!(matches!(sign(&v, "AIOL-DEVICE-v1\n\u{2028}"), Err(VaultError::Refused)));
    }

    #[test]
    fn delete_means_a_new_key_next_time() {
        let v = MemoryVault::default();
        let a = public_key(&v, true).unwrap().unwrap();
        delete(&v).unwrap();
        assert!(matches!(sign(&v, "AIOL-DEVICE-v1\nx"), Err(VaultError::Missing)));
        let b = public_key(&v, true).unwrap().unwrap();
        assert_ne!(a.public_key, b.public_key);
    }
}
