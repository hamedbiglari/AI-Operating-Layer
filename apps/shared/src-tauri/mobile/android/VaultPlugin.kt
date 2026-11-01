// AIOL Android vault + device key (ADR-137, ADR-138). Copied into the generated Android project by
// clients/scripts/mobile-setup.sh; registered from Rust as ("app.aiol.client", "VaultPlugin").
//
// * Device key: EC P-256 generated INSIDE Android Keystore (hardware-backed where the device has a TEE or
//   StrongBox). The private key is not exportable; this class can only ask Keystore to sign. Reported storage is
//   "hardware" only when KeyInfo says the key is inside secure hardware, otherwise "os_keystore".
// * Vault: values are encrypted with an AES-256-GCM key that also lives in Android Keystore, and the ciphertext is
//   kept in app-private SharedPreferences (excluded from backup in the manifest, see mobile-setup.sh).
// * No hardware identifiers are read: no IMEI, serial, ANDROID_ID, MAC, phone number.
//
// NOT VERIFIED: this file has not been compiled in the build environment (the Android SDK could not be
// downloaded). See docs/clients/CLIENT_SUITE_REPORT.md.
package app.aiol.client

import android.app.Activity
import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyInfo
import android.security.keystore.KeyProperties
import android.util.Base64
import app.tauri.annotation.Command
import app.tauri.annotation.InvokeArg
import app.tauri.annotation.TauriPlugin
import app.tauri.plugin.Invoke
import app.tauri.plugin.JSObject
import app.tauri.plugin.Plugin
import java.security.KeyFactory
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.PrivateKey
import java.security.Signature
import java.security.spec.ECGenParameterSpec
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

@InvokeArg class KeyArgs { lateinit var key: String }
@InvokeArg class SetArgs { lateinit var key: String; lateinit var value: String }
@InvokeArg class CreateArgs { var create: Boolean = true }
@InvokeArg class SignArgs { lateinit var message: String }

@TauriPlugin
class VaultPlugin(private val activity: Activity) : Plugin(activity) {
    private val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
    private val prefs = activity.getSharedPreferences("aiol.vault", Context.MODE_PRIVATE)
    private val deviceAlias = "aiol.device.es256"
    private val wrapAlias = "aiol.vault.aes"

    private fun wrapKey(): SecretKey {
        (store.getKey(wrapAlias, null) as? SecretKey)?.let { return it }
        val gen = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        gen.init(KeyGenParameterSpec.Builder(wrapAlias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setKeySize(256).build())
        return gen.generateKey()
    }

    private fun allowed(name: String) = name == "aiol.refresh"

    @Command
    fun vaultGet(invoke: Invoke) {
        val a = invoke.parseArgs(KeyArgs::class.java)
        if (!allowed(a.key)) return invoke.reject("refused")
        val stored = prefs.getString(a.key, null)
        val out = JSObject()
        if (stored == null) { out.put("value", null); return invoke.resolve(out) }
        try {
            val raw = Base64.decode(stored, Base64.NO_WRAP)
            val c = Cipher.getInstance("AES/GCM/NoPadding")
            c.init(Cipher.DECRYPT_MODE, wrapKey(), GCMParameterSpec(128, raw, 0, 12))
            out.put("value", String(c.doFinal(raw, 12, raw.size - 12), Charsets.UTF_8))
        } catch (e: Exception) {
            prefs.edit().remove(a.key).apply()   // unreadable (e.g. restored to another device): forget it
            out.put("value", null)
        }
        invoke.resolve(out)
    }

    @Command
    fun vaultSet(invoke: Invoke) {
        val a = invoke.parseArgs(SetArgs::class.java)
        if (!allowed(a.key) || a.value.length > 512) return invoke.reject("refused")
        val c = Cipher.getInstance("AES/GCM/NoPadding")
        c.init(Cipher.ENCRYPT_MODE, wrapKey())
        val ct = c.doFinal(a.value.toByteArray(Charsets.UTF_8))
        prefs.edit().putString(a.key, Base64.encodeToString(c.iv + ct, Base64.NO_WRAP)).apply()
        invoke.resolve()
    }

    @Command
    fun vaultDelete(invoke: Invoke) {
        val a = invoke.parseArgs(KeyArgs::class.java)
        if (!allowed(a.key)) return invoke.reject("refused")
        prefs.edit().remove(a.key).apply()
        invoke.resolve()
    }

    @Command
    fun deviceKeyPublic(invoke: Invoke) {
        val a = invoke.parseArgs(CreateArgs::class.java)
        if (!store.containsAlias(deviceAlias)) {
            if (!a.create) { val o = JSObject(); o.put("key", null); return invoke.resolve(o) }
            val gen = KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, "AndroidKeyStore")
            gen.initialize(KeyGenParameterSpec.Builder(deviceAlias, KeyProperties.PURPOSE_SIGN)
                .setAlgorithmParameterSpec(ECGenParameterSpec("secp256r1"))
                .setDigests(KeyProperties.DIGEST_SHA256).build())
            gen.generateKeyPair()
        }
        val cert = store.getCertificate(deviceAlias)
        val priv = store.getKey(deviceAlias, null) as PrivateKey
        val info = KeyFactory.getInstance(priv.algorithm, "AndroidKeyStore").getKeySpec(priv, KeyInfo::class.java)
        @Suppress("DEPRECATION")
        val hardware = info.isInsideSecureHardware
        val key = JSObject()
        key.put("public_key", Base64.encodeToString(cert.publicKey.encoded, Base64.NO_WRAP)) // X.509 SPKI DER
        key.put("storage", if (hardware) "hardware" else "os_keystore")
        val o = JSObject(); o.put("key", key)
        invoke.resolve(o)
    }

    @Command
    fun deviceKeySign(invoke: Invoke) {
        val a = invoke.parseArgs(SignArgs::class.java)
        if (!a.message.startsWith("AIOL-DEVICE-v1\n") || a.message.length > 512) return invoke.reject("refused")
        val priv = store.getKey(deviceAlias, null) as? PrivateKey ?: return invoke.reject("missing")
        val s = Signature.getInstance("SHA256withECDSA")
        s.initSign(priv)
        s.update(a.message.toByteArray(Charsets.US_ASCII))
        val o = JSObject()
        o.put("signature", Base64.encodeToString(s.sign(), Base64.NO_WRAP)) // DER; the server accepts DER
        invoke.resolve(o)
    }

    @Command
    fun deviceKeyDelete(invoke: Invoke) {
        if (store.containsAlias(deviceAlias)) store.deleteEntry(deviceAlias)
        invoke.resolve()
    }
}
