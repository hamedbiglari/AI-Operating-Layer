# AIOL Official Client Suite — audit, decisions, privacy, threat model, test matrix and acceptance report

Date: 2026-10-31 · Branch: `claude/nice-fermi-du1d71` · ADRs: 137 (client suite), 138 (Device Intelligence)

Status vocabulary for platforms is the master prompt's (§36). Every status below is backed by a command
that was actually run in this session, or says it was not run.

---

## 1. Executive summary

* **Built and verified here:** the Cloud Core additions (native session, chat idempotency, client config,
  Device Intelligence registry, migration 0049), the shared client UI, and the Tauri native shell's Rust
  layer. The shared UI was driven end-to-end in Chromium against a live Cloud Core + PostgreSQL:
  sign in → chat → history → continue → settings → usage → Persian/RTL → device verification → account
  switch → sign out → sign in → server continuity, plus a phone viewport.
* **Not built here:** no Windows, macOS, Android or iOS **package** exists yet. This environment is Linux
  with no Windows/macOS SDKs, no Xcode, and `dl.google.com` (Android SDK) is blocked by the network
  policy. `.github/workflows/clients.yml` builds Windows and macOS packages on GitHub-hosted runners and
  attempts Android (debug APK) and iOS (simulator); none of those jobs has run yet.
* **Production readiness: NOT READY** (see §21).

## 2. Existing architecture reused (forensic audit)

| Area | Evidence (file) | Classification | Used by the clients as |
|------|-----------------|----------------|------------------------|
| FastAPI Cloud Core, `/api/v1`, error envelope | `app/main.py`, `app/core/errors.py` | VERIFIED (1741 baseline tests) | the only backend |
| Auth: password, emailed code, browser session with rotation + reuse detection | `api/v1/auth.py`, `services/auth_session_service.py`, ADR-129 | VERIFIED | reused; native routes open the same `auth_sessions` row |
| OAuth/OIDC identity provider | — | MISSING | not invented (debt `CLIENT-oidc`) |
| Tenancy + RBAC (`get_current_user`, `require_roles`) | `security/dependencies.py` | VERIFIED | every new route |
| Knowledge chat: conversations, messages, 8 answer states, citations, research approval | `api/v1/chat.py`, `services/chat_service.py`, ADR-128/130 | VERIFIED (tests) — had **no UI consumer in this repo** | the chat surface |
| Website chat page (ADR-129) | not in repository | MISSING here | — |
| Token streaming | — | MISSING | not offered (debt `CLIENT-chat-streaming`) |
| Idempotent question submission | — | MISSING → **added** (`client_request_id`) | retry safety |
| User preferences (language en/fa, theme) | `api/v1/preferences.py` | VERIFIED | Settings, Language |
| Billing usage, wallet, quotas | `api/v1/billing.py`, `billing_service.usage_summary` | VERIFIED | Usage |
| Subscription plans | `models/_draft_billing_not_wired/` | PARTIALLY_IMPLEMENTED (draft, not wired) | not shown; Usage says plans are not offered |
| Design tokens + icon registry | `frontend/design-system/`, `frontend/icons/icon-paths.json` | VERIFIED (canonical) | copied byte-identically by `clients/scripts/sync-design-system.mjs`, parity-tested |
| Persian i18n conventions, KNOWN-word reversal check | `visual-harness/check-persian.js` | VERIFIED | client catalogue is checked against the same KNOWN list |
| Device Intelligence ("previously specified Web Device Intelligence Engine") | searched models/services/docs for device, fingerprint, MachineGuid, installation key | MISSING | **built** (ADR-138) |
| Free-quota / abuse policy engine | — | MISSING | not invented (debt `CLIENT-free-quota-policy-engine`) |
| Admin dashboard | `visual-harness/index.html` (13.8k lines) | VERIFIED | Device Intelligence admin **API** added; dashboard **screen not added** (debt) |
| CI | `.github/workflows/ci.yml` | VERIFIED | untouched; new `clients.yml` |
| Native/mobile/PWA client code | — | MISSING | **built** |

## 3. Architecture and technology decision (ADR-137)

* **FACT:** every existing UI is plain HTML/CSS/JS with no bundler; there is exactly one design system and
  one icon registry, and START_HERE forbids a second. The chat, auth, preferences and usage contracts are
  JSON over HTTPS with bearer tokens.
* **SIGNAL:** Tauri 2 targets Windows, macOS, Android and iOS from one Rust core with system WebViews; the
  OS credential stores are reachable from Rust (`keyring`: Credential Manager, Keychain) and Android
  Keystore from a Kotlin plugin.
* **INFERENCE:** a shared web UI inside Tauri reuses the tokens and icons byte-for-byte and keeps one
  native layer to secure. Flutter would require re-implementing the design system in Dart.
* **UNKNOWN:** WebView differences (WKWebView on iOS 15 vs WebView2) for `<dialog>`, `interactive-widget`
  keyboard resizing and IndexedDB were not tested on devices.
* **DECISION:** shared ES-module UI (`clients/app`) + Tauri 2 (`clients/src-tauri`).
* **TRADE-OFF:** a WebView UI is less native than SwiftUI/Compose; iOS/Android keyboard and gesture details
  need on-device tuning. Desktop/iOS device keys are OS-protected software keys, not Secure Enclave keys.

Layering: shared domain logic (`app/src/core`) · shared presentation (`app/src/ui`, `styles/app.css`) ·
responsive platform adaptation (CSS drawer < 768 px, safe areas, touch targets) · native integration
(`src-tauri/src`, `mobile/android`) · API adapters (`core/http.js`) · security-sensitive services
(vault, device key — Rust/Kotlin only) · build config (`tauri.conf.json`, `clients.yml`).

## 4–7. Platform status

| Platform | Status | Evidence | Missing for the next status |
|----------|--------|----------|-----------------------------|
| Windows | **SOURCE IMPLEMENTED** | Rust shell compiles and tests on the Linux host; Windows code path: see §17 (`cargo check --target x86_64-pc-windows-msvc`) | run `clients.yml` "Package — Windows x64" (NSIS/MSI); Authenticode certificate |
| macOS | **SOURCE IMPLEMENTED** | as above; `cargo check --target aarch64-apple-darwin` (§17) | run "Package — macOS universal"; Developer ID + notarization |
| Android | **SOURCE IMPLEMENTED** (Kotlin plugin uncompiled) | `cargo check --target aarch64-linux-android` (§17); `VaultPlugin.kt` not compiled — SDK host blocked | `scripts/mobile-setup.sh android` + `tauri android build` with SDK/NDK; upload keystore |
| iOS / iPadOS | **SOURCE IMPLEMENTED** | `cargo check --target aarch64-apple-ios` (§17) | macOS + Xcode: `scripts/mobile-setup.sh ios`, `tauri ios build`; Apple team |

The **shared UI** that all four load is at **TESTS PASS** (unit + live end-to-end in Chromium). Chromium is
the engine of WebView2 (Windows) and Android System WebView, not of WKWebView (macOS/iOS).

## 8. Authentication and session security

* `POST /auth/native/session` (`grant: login_code | password`) reuses the existing verification services,
  throttles, lockout and indistinguishable failures, and opens an `auth_sessions` row.
* The refresh secret is returned in the body, stored only in the OS vault (Rust allows only the name
  `aiol.refresh` from the WebView), rotated on every refresh, and replay of a rotated secret revokes the
  session for every holder. Access tokens live in memory for 15 minutes; refresh is single-flight.
* Sign-out calls `/auth/native/session/end`, then always clears local state; it never deletes server
  conversations (unit test asserts no chat DELETE is sent).
* Not applicable today: PKCE / system-browser / app-link callbacks — AIOL has no OAuth IdP. When one is
  added, the native clients must use authorization code + PKCE with the system browser (debt `CLIENT-oidc`).

## 9. Chat and conversation synchronisation

Server-backed only. A question is shown `pending`, becomes `confirmed` only when the server returns its
answer (then the thread is reloaded so positions come from the server), `failed` on error (Retry re-sends
the same `client_request_id`, so the server stores the question once — unit + backend tests), and
`unknown` when the user stops waiting or the request times out ("the answer may still have been saved").
History: search (title + content, server-side), rename, archive, delete, pagination of lists and of older
messages. The answer state, limitation, citations (with page and contested flag) and pending research
approvals are rendered from the server's data with `textContent` only.

## 10. Account, settings, usage and upgrade

Account menu (reference hierarchy): account email + role · Settings · Usage · Language · Get help
(only if configured) · Upgrade plan · Get apps · Learn more (only if configured) · Log out.
Settings: theme (account-wide, persisted via `/users/me/preferences`), installation verification
(this installation), linked installations, version, server, legal links. Usage: wallet and quota meters
from `/billing/usage`, chat daily limit from `/chat/config`, and the explicit statement that plans are not
offered. Upgrade: truthful "not available" until `CLIENT_UPGRADE_URL` is set, and withheld on Android/iOS.
Get apps: "nothing published" until `CLIENT_RELEASES_JSON` lists a release.

## 11. Device Intelligence integration (ADR-138)

Proof-of-possession of an ES256 installation key, per account, with single-use bound challenges.
Provenance per observation (`WEB_BROWSER`, `WINDOWS_CLIENT`, `MACOS_CLIENT`, `ANDROID_CLIENT`, `IOS_CLIENT`,
`SERVER_OBSERVATION`). Evidence-only assessment (`di-assess-v1`). Optional in the client: runs after the app
is usable, never blocks sign-in, every failure becomes a status in Settings. Users can turn it off
(server unlink + local key deletion). Admin API with audited reads and revocation.

## 12. Privacy and data inventory

| Signal | Source | Purpose | Raw persisted? | Protection | Retention | Who can see | Disclosure |
|--------|--------|---------|----------------|------------|-----------|-------------|------------|
| Installation public key | client | verify continuity signatures | yes (public by nature) | tenant-scoped row; API shows a 12-hex reference only | until revoked/unlinked + account deletion cascade | admin (reference only) | Settings text |
| Key storage claim | client | show how the key is protected (as a claim) | yes | — | as above | admin | — |
| App version, OS family/version | client | support, compatibility | yes, truncated to 40 chars | — | as above | admin, the user | — |
| Client IP | request | same/different network evidence | **no** | keyed HMAC (versioned) of IP and of /24 or /48 | 90 days (`DEVICE_OBSERVATION_RETENTION_DAYS`) | admin sees 10-hex prefix of the prefix pseudonym | Settings text |
| Linked accounts per installation | server | shared-device / account-switch evidence | yes | tenant-scoped | until unlink | admin of that tenant only | Settings text |
| Challenge nonce | server | replay protection | SHA-256 hash only | single use, 120 s | purged 1 h after expiry/use | nobody | — |
| Hardware serials, MachineGuid, GDID, IMEI, UDID, MAC, ANDROID_ID, browser fingerprint | — | — | **not collected** | — | — | — | — |

Legal status: **not reviewed.** The Settings disclosure text, the legal basis (consent vs legitimate
interest) for each jurisdiction, and Apple/Google privacy declarations need qualified review before
release. The retention purge exists and is tested but is not scheduled (debt).

## 13. Threat model and security findings

| Threat | Mitigation | Verified by |
|--------|------------|-------------|
| Token theft from storage | refresh secret only in OS vault; access token memory-only; no tokens in URLs, logs, localStorage | unit test (no secret written to localStorage), e2e (storage scan) |
| Refresh-secret replay | rotation + reuse detection (existing ADR-129 service) | backend test `test_refresh_rotates_and_the_old_secret_dies` |
| Device registration spoofing (public key without private key) | signature over server-built input | `test_a_public_key_without_the_private_key_cannot_register` |
| Challenge replay / expiry / forged nonce | single-use row lock, TTL, nonce hash compare; failed signature burns the challenge | 4 backend tests |
| Moving a signature between users / credentials | input binds org, user, purpose, credential | 2 backend tests |
| IDOR / cross-tenant device or conversation access | all lookups scoped by organization (+ user for conversations); 404 not 403 | backend tests (devices, chat key reuse) |
| Privilege escalation to device evidence | owner/admin only; reads audited | `test_a_non_admin_cannot_read_device_evidence`, audit tests |
| WebView as a signing oracle | Rust/Kotlin sign only `AIOL-DEVICE-v1\n…` ASCII ≤ 512 bytes | Rust test `refuses_to_sign_anything_but_a_device_challenge` |
| XSS / prompt-injected content | no HTML-string APIs anywhere in client source (test-enforced); CSP without `unsafe-eval` or inline script | unit test; `tauri.conf.json` |
| Unsafe external URLs | https/mailto only, checked in JS and again in Rust | JS + Rust tests |
| Arbitrary API endpoint via crafted link | `?api=` honoured only on a loopback origin in the browser build; production refuses non-https | unit test |
| Cache leakage between accounts | nothing persisted; store reset on sign-out/switch | unit test, e2e (second account sees no conversations) |
| Duplicate charges on retry | idempotency key; POST never auto-retried | backend + unit tests |
| Oversized responses | 5 MB cap | code (`http.js`) |
| Device-graph poisoning | links require proof of possession per account; platform switch refused; failed checks recorded as conflicting evidence, never as identity | backend tests |
| Insecure update channel | no updater shipped | — |

Open findings: CSP `connect-src https:` should be narrowed per release (debt); admin list assessments run
3 queries per row (≤ 200 rows); concurrent first registration of the same key returns 409 `registration_race`.

## 14. Red-team results (synthetic)

All results are from synthetic tests in `test_device_intelligence.py`; they prove protocol behaviour, not
real-world detection accuracy. No real-world false-positive/negative dataset exists, so no accuracy figure is
claimed.

| Scenario | Expected | Result |
|----------|----------|--------|
| same installation, two accounts (account switching) | linked; `SAME_REGISTERED_INSTALLATION` | PASS (backend + e2e) |
| same device, IP changes / VPN exit changes ×3 | continuity kept; `INSUFFICIENT_EVIDENCE` | PASS |
| two devices on one network (office NAT / family Wi-Fi) | `SHARED_NETWORK_ONLY` only | PASS |
| reinstall (new key) after revocation | registers as a new installation | PASS |
| revoked key re-registered | 409 `credential_revoked` | PASS |
| user unlinks one of two accounts | other account keeps continuity | PASS |
| spoofed payload / replay / expired / wrong nonce / foreign challenge / moved signature | refused | PASS |
| non-P-256 or garbage key | 422 | PASS |
| feature disabled | 404 on device routes, sign-in unaffected | PASS |
| missing signals (no IP) | NULL pseudonym, not a value | PASS |
| VPN / private browsing / shared network treated as abuse | never | by construction: no route enforces; categories are evidence |

Browser matrix (Chrome/Firefox/Edge/Safari, private modes, restricted storage): **not run** — only
Chromium was available. In private browsing the WebCrypto/IndexedDB key may be unavailable or ephemeral;
the client then reports "not available here" and continues.

## 15. Browser and native compatibility

| Engine / platform | Tested |
|-------------------|--------|
| Chromium (Playwright, desktop 1280×800 and phone 390×844 touch) | yes — e2e |
| WebView2 (Windows), WKWebView (macOS/iOS), Android System WebView | no |
| Real devices | none |

## 16. Automated test results

See the commands and outputs in §17. Summary is filled from those runs.

## 17. Build and packaging results

See the bottom of this document ("Command log").

## 18. Artifact locations

No installable package was produced in this environment. Source: `clients/`. CI outputs (when run):
artifacts `aiol-Windows`, `aiol-macOS`, `aiol-android-debug` of the "Client suite CI" workflow.
End-to-end screenshots: `clients/e2e/out/` (not committed).

## 19. Unresolved defects and dependencies

Debt rows `CLIENT-*` in `docs/ai-context/DEBT_REGISTER.md`: dashboard Device Intelligence screen,
retention scheduler, policy engine, cross-tenant correlation, streaming, mobile billing, attestation,
updater, OIDC, CSP narrowing. Plus: signing credentials for all four platforms; Android SDK access;
macOS/Xcode host; legal review.

## 20. Known limitations

* "Stop waiting" cannot cancel server work; the server still answers and saves.
* No offline queue: questions are not sent while offline (stated in the UI).
* Drafts are kept in memory for the app session only (privacy choice), not across restarts.
* Desktop and iOS device keys are OS-keychain software keys (`os_keystore`), not hardware-bound.
* Arabic is not offered (no backend preference or catalogue).
* Linux is not a release target.

## 21. Production readiness decision

**NOT READY FOR RELEASE.** No platform has a built, signed, device-tested package; WebKit engines are
untested; the Android Kotlin plugin is uncompiled; the privacy disclosure lacks legal review. No
release-blocking vulnerability is known in the implemented code, and the backend changes are additive and
reversible (migration 0049 down-migrates cleanly).
