"""
Device Intelligence service (ADR-138): challenge, proof of possession, continuity, evidence-only assessment.

PROTOCOL
    1. An authenticated client asks for a challenge: purpose `register`, or `verify` naming a credential.
    2. The server stores the SHA-256 of a 32-byte random nonce, bound to (organization, user, purpose,
       credential), valid for DEVICE_CHALLENGE_TTL_SECONDS, and returns the nonce once.
    3. The client signs `signing_input(...)` with its ES256 (ECDSA P-256 / SHA-256) private key.
    4. The server consumes the challenge (row lock, single use), recomputes the signing input from its own
       record — never from client-supplied ids alone — and verifies the signature against the public key
       being registered (register) or the stored one (verify).

    The account binding is the bearer session, not anything the client says. A client-supplied credential id
    is only ever a lookup key inside the caller's own organization, and a verify challenge is bound to one
    credential, so a signature cannot be replayed against another credential, another user or another tenant.

WHAT A SUCCESSFUL CHECK MEANS
    "This request came from an installation that holds the private key registered earlier." Nothing more. A
    copied key (a restored backup, a cloned VM, an extracted software key) passes too; `key_storage` says what
    the client CLAIMS protects the key, and the admin view shows it as a claim.

ASSESSMENT
    Deterministic, versioned (ALGORITHM_VERSION), evidence-only, never a score (ADR-024) and never "same person".
    Nothing in the codebase enforces on it: there is no free-quota policy engine to feed (ADR-138 "not done").
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import ipaddress
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from fastapi import HTTPException, status
from sqlalchemy import delete, func, or_, select, true
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.device_intelligence import (
    DeviceChallenge, DeviceCredential, DeviceCredentialLink, DeviceObservation,
)
from app.models.user import User
from app.services.audit import record_audit_log

ALGORITHM_VERSION = "di-assess-v1"
SIGNING_DOMAIN = "AIOL-DEVICE-v1"
PLATFORM_PROVENANCE = {"web": "WEB_BROWSER", "windows": "WINDOWS_CLIENT", "macos": "MACOS_CLIENT",
                       "android": "ANDROID_CLIENT", "ios": "IOS_CLIENT"}
_MAX_SPKI_BYTES = 200        # a P-256 SPKI is 91 bytes; anything larger is not one


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _b64decode(value: str, field: str) -> bytes:
    raw = (value or "").strip()
    try:
        # Accept standard and URL-safe alphabets, with or without padding.
        raw = raw.replace("-", "+").replace("_", "/")
        return base64.b64decode(raw + "=" * (-len(raw) % 4), validate=True)
    except (binascii.Error, ValueError):
        raise _bad(f"{field} is not valid base64.", "malformed") from None


def _bad(message: str, code: str, http: int = status.HTTP_422_UNPROCESSABLE_ENTITY) -> HTTPException:
    return HTTPException(http, {"code": code, "message": message})


def _hash_nonce(nonce: bytes) -> str:
    return hashlib.sha256(nonce).hexdigest()


# ---------------------------------------------------------------- pseudonyms
def _pseudonym_key() -> bytes:
    if settings.DEVICE_PSEUDONYM_KEY is not None:
        return settings.DEVICE_PSEUDONYM_KEY.get_secret_value().encode()
    # Domain-separated derivation, so the session-hash key and this one are never the same bytes.
    return hmac.new(settings.SECRET_KEY.encode(), b"aiol-device-pseudonym", hashlib.sha256).digest()


def pseudonym(value: str) -> str:
    return hmac.new(_pseudonym_key(), value.encode(), hashlib.sha256).hexdigest()


def network_prefix(ip: str | None) -> str | None:
    """/24 for IPv4, /48 for IPv6. None for anything that is not an address ("unknown", test clients)."""
    try:
        addr = ipaddress.ip_address((ip or "").strip())
    except ValueError:
        return None
    bits = 24 if addr.version == 4 else 48
    return str(ipaddress.ip_network(f"{addr}/{bits}", strict=False))


def network_fields(ip: str | None) -> dict:
    prefix = network_prefix(ip)
    if prefix is None:
        return {"network_pseudonym": None, "network_prefix_pseudonym": None, "pseudonym_key_version": None}
    return {"network_pseudonym": pseudonym(f"ip:{ipaddress.ip_address(ip.strip())}"),
            "network_prefix_pseudonym": pseudonym(f"net:{prefix}"),
            "pseudonym_key_version": settings.DEVICE_PSEUDONYM_KEY_VERSION}


# ---------------------------------------------------------------- crypto
def load_public_key(spki_b64: str) -> tuple[ec.EllipticCurvePublicKey, bytes]:
    der = _b64decode(spki_b64, "public_key")
    if not der or len(der) > _MAX_SPKI_BYTES:
        raise _bad("public_key is not a P-256 public key.", "unsupported_key")
    try:
        key = serialization.load_der_public_key(der)
    except (ValueError, TypeError):
        raise _bad("public_key is not a DER SubjectPublicKeyInfo.", "unsupported_key") from None
    if not isinstance(key, ec.EllipticCurvePublicKey) or not isinstance(key.curve, ec.SECP256R1):
        raise _bad("Only ES256 (ECDSA P-256) keys are accepted.", "unsupported_key")
    # Re-serialise so the thumbprint is over canonical bytes, not whatever encoding the client chose.
    canonical = key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return key, canonical


def thumbprint(spki_der: bytes) -> str:
    return hashlib.sha256(spki_der).hexdigest()


def _signature_der(sig: bytes) -> bytes:
    """WebCrypto, Windows CNG and Apple CryptoKit emit IEEE P1363 (r||s, 64 bytes); Android and OpenSSL emit
    DER. Both are accepted; P1363 is converted."""
    if len(sig) == 64:
        return encode_dss_signature(int.from_bytes(sig[:32], "big"), int.from_bytes(sig[32:], "big"))
    return sig


def verify_signature(key: ec.EllipticCurvePublicKey, signature_b64: str, message: bytes) -> bool:
    sig = _b64decode(signature_b64, "signature")
    if not sig or len(sig) > 80:
        return False
    try:
        key.verify(_signature_der(sig), message, ec.ECDSA(hashes.SHA256()))
        return True
    except (InvalidSignature, ValueError):
        return False


def signing_input(*, purpose: str, challenge_id: uuid.UUID, nonce_b64: str, organization_id: uuid.UUID,
                  user_id: uuid.UUID, credential_id: uuid.UUID | None) -> bytes:
    """The exact bytes a client signs. Every field comes from the server's own challenge record."""
    return "\n".join([SIGNING_DOMAIN, purpose, str(challenge_id), nonce_b64, str(organization_id), str(user_id),
                      str(credential_id) if credential_id else "-"]).encode("ascii")


# ---------------------------------------------------------------- challenges
def _require_enabled() -> None:
    if not settings.DEVICE_INTELLIGENCE_ENABLED:
        raise _bad("Device Intelligence is turned off for this deployment.", "disabled",
                   status.HTTP_404_NOT_FOUND)


def _credential_in_org(db: Session, organization_id: uuid.UUID, credential_id: uuid.UUID,
                       *, lock: bool = False) -> DeviceCredential:
    stmt = select(DeviceCredential).where(DeviceCredential.id == credential_id,
                                          DeviceCredential.organization_id == organization_id)
    if lock:
        stmt = stmt.with_for_update()
    row = db.execute(stmt).scalar_one_or_none()
    if row is None:
        raise _bad("Device credential not found.", "not_found", status.HTTP_404_NOT_FOUND)
    return row


def _active_link(db: Session, credential_id: uuid.UUID, user_id: uuid.UUID) -> DeviceCredentialLink | None:
    return db.execute(select(DeviceCredentialLink).where(
        DeviceCredentialLink.credential_id == credential_id, DeviceCredentialLink.user_id == user_id,
        DeviceCredentialLink.unlinked_at.is_(None))).scalar_one_or_none()


def issue_challenge(db: Session, *, user: User, purpose: str,
                    credential_id: uuid.UUID | None = None) -> dict:
    _require_enabled()
    if purpose not in ("register", "verify"):
        raise _bad("purpose must be register or verify.", "malformed")
    if purpose == "verify":
        if credential_id is None:
            raise _bad("A verify challenge names the credential it is for.", "malformed")
        cred = _credential_in_org(db, user.organization_id, credential_id)
        if cred.status != "active":
            raise _bad("This device credential has been revoked.", "credential_revoked", status.HTTP_409_CONFLICT)
    else:
        credential_id = None
    nonce = secrets.token_bytes(32)
    nonce_b64 = base64.urlsafe_b64encode(nonce).decode().rstrip("=")
    row = DeviceChallenge(id=uuid.uuid4(), organization_id=user.organization_id, user_id=user.id, purpose=purpose,
                          credential_id=credential_id, nonce_hash=_hash_nonce(nonce),
                          expires_at=_now() + timedelta(seconds=settings.DEVICE_CHALLENGE_TTL_SECONDS))
    db.add(row)
    db.commit()
    return {"challenge_id": str(row.id), "nonce": nonce_b64, "purpose": purpose,
            "credential_id": str(credential_id) if credential_id else None, "expires_at": row.expires_at,
            "algorithm": "ES256",
            "signing_input": signing_input(purpose=purpose, challenge_id=row.id, nonce_b64=nonce_b64,
                                           organization_id=user.organization_id, user_id=user.id,
                                           credential_id=credential_id).decode("ascii")}


@dataclass
class _Consumed:
    challenge: DeviceChallenge
    message: bytes


def _consume(db: Session, *, user: User, challenge_id: uuid.UUID, nonce_b64: str, purpose: str,
             credential_id: uuid.UUID | None) -> _Consumed:
    """Single use, row-locked, bound to the caller. Every failure is the same 409 shape with a code, and a
    consumed challenge stays consumed even when the signature then fails — a wrong signature is not a free
    retry on the same nonce."""
    row = db.execute(select(DeviceChallenge).where(
        DeviceChallenge.id == challenge_id, DeviceChallenge.organization_id == user.organization_id,
        DeviceChallenge.user_id == user.id).with_for_update()).scalar_one_or_none()
    if row is None or row.purpose != purpose or (purpose == "verify" and row.credential_id != credential_id):
        raise _bad("Unknown challenge.", "challenge_invalid", status.HTTP_409_CONFLICT)
    if row.consumed_at is not None:
        raise _bad("This challenge was already used.", "challenge_replayed", status.HTTP_409_CONFLICT)
    now = _now()
    row.consumed_at = now
    if row.expires_at <= now:
        db.commit()
        raise _bad("This challenge has expired. Request a new one.", "challenge_expired", status.HTTP_409_CONFLICT)
    nonce = _b64decode(nonce_b64, "nonce")
    if not hmac.compare_digest(row.nonce_hash, _hash_nonce(nonce)):
        db.commit()
        raise _bad("Unknown challenge.", "challenge_invalid", status.HTTP_409_CONFLICT)
    message = signing_input(purpose=purpose, challenge_id=row.id, nonce_b64=nonce_b64.rstrip("="),
                            organization_id=user.organization_id, user_id=user.id, credential_id=row.credential_id)
    return _Consumed(row, message)


def _observe(db: Session, *, organization_id: uuid.UUID, credential_id: uuid.UUID | None, user_id: uuid.UUID | None,
             provenance: str, kind: str, ip: str | None, reason_code: str | None = None,
             app_version: str | None = None) -> DeviceObservation:
    row = DeviceObservation(organization_id=organization_id, credential_id=credential_id, user_id=user_id,
                            provenance=provenance, kind=kind, reason_code=reason_code,
                            app_version=_trim(app_version, 40), **network_fields(ip))
    db.add(row)
    return row


def _trim(value: str | None, limit: int) -> str | None:
    value = (value or "").strip()
    return value[:limit] or None


# ---------------------------------------------------------------- register / verify
def register(db: Session, *, user: User, challenge_id: uuid.UUID, nonce: str, public_key: str, signature: str,
             platform: str, key_storage: str, app_version: str | None, os_family: str | None,
             os_version: str | None, ip: str | None) -> tuple[DeviceCredential, bool]:
    """Returns (credential, created). Idempotent: the same key registered again by the same account returns the
    existing row; registered by another account in the organization links that account (shared device)."""
    _require_enabled()
    provenance = PLATFORM_PROVENANCE.get(platform)
    if provenance is None:
        raise _bad("Unknown platform.", "malformed")
    key, spki = load_public_key(public_key)          # validate before burning the challenge
    consumed = _consume(db, user=user, challenge_id=challenge_id, nonce_b64=nonce, purpose="register",
                        credential_id=None)
    if not verify_signature(key, signature, consumed.message):
        _observe(db, organization_id=user.organization_id, credential_id=None, user_id=user.id,
                 provenance=provenance, kind="verification_failed", reason_code="bad_signature", ip=ip,
                 app_version=app_version)
        db.commit()
        raise _bad("The signature does not match the public key.", "bad_signature", status.HTTP_401_UNAUTHORIZED)

    now = _now()
    tp = thumbprint(spki)
    cred = db.execute(select(DeviceCredential).where(
        DeviceCredential.organization_id == user.organization_id,
        DeviceCredential.key_thumbprint == tp).with_for_update()).scalar_one_or_none()
    created = False
    if cred is not None and cred.status == "revoked":
        db.commit()
        raise _bad("This key was revoked. Generate a new key and register again.", "credential_revoked",
                   status.HTTP_409_CONFLICT)
    if cred is not None and cred.provenance != provenance:
        # Same key, different claimed platform: not comparable, and suspicious. Recorded, refused.
        _observe(db, organization_id=user.organization_id, credential_id=cred.id, user_id=user.id,
                 provenance=provenance, kind="verification_failed", reason_code="provenance_mismatch", ip=ip,
                 app_version=app_version)
        db.commit()
        raise _bad("This key is registered for a different platform.", "provenance_mismatch",
                   status.HTTP_409_CONFLICT)
    if cred is None:
        cred = DeviceCredential(
            id=uuid.uuid4(), organization_id=user.organization_id, registered_by_user_id=user.id,
            provenance=provenance, algorithm="ES256", public_key_spki=base64.b64encode(spki).decode(),
            key_thumbprint=tp, key_storage=key_storage, app_version=_trim(app_version, 40),
            os_family=_trim(os_family, 40), os_version=_trim(os_version, 40), status="active",
            first_seen_at=now, last_seen_at=now, last_verified_at=now)
        db.add(cred)
        try:
            db.flush()
        except IntegrityError:
            # The same new key registered twice at the same moment; the other request created it.
            db.rollback()
            raise _bad("This key was just registered. Request a new challenge and try again.", "registration_race",
                       status.HTTP_409_CONFLICT) from None
        created = True
        _observe(db, organization_id=user.organization_id, credential_id=cred.id, user_id=user.id,
                 provenance=provenance, kind="registered", ip=ip, app_version=app_version)
        record_audit_log(db, organization_id=user.organization_id, user_id=user.id,
                         action="device.credential_registered", resource_type="device_credential",
                         resource_id=cred.id, new_value={"provenance": provenance, "key_storage": key_storage})
    else:
        cred.last_seen_at = now
        cred.last_verified_at = now
        cred.app_version = _trim(app_version, 40) or cred.app_version
        cred.os_version = _trim(os_version, 40) or cred.os_version

    link = db.execute(select(DeviceCredentialLink).where(
        DeviceCredentialLink.credential_id == cred.id, DeviceCredentialLink.user_id == user.id)
    ).scalar_one_or_none()
    if link is None:
        db.add(DeviceCredentialLink(organization_id=user.organization_id, credential_id=cred.id, user_id=user.id,
                                    first_linked_at=now, last_verified_at=now))
        if not created:
            _observe(db, organization_id=user.organization_id, credential_id=cred.id, user_id=user.id,
                     provenance=provenance, kind="linked", ip=ip, app_version=app_version)
    else:
        link.unlinked_at = None
        link.last_verified_at = now
    db.commit()
    db.refresh(cred)
    return cred, created


def verify(db: Session, *, user: User, credential_id: uuid.UUID, challenge_id: uuid.UUID, nonce: str,
           signature: str, app_version: str | None, ip: str | None) -> DeviceCredential:
    _require_enabled()
    cred = _credential_in_org(db, user.organization_id, credential_id)
    if _active_link(db, cred.id, user.id) is None:
        # Possession is proved per account through `register`; verify is continuity for an existing link.
        raise _bad("Device credential not found.", "not_found", status.HTTP_404_NOT_FOUND)
    consumed = _consume(db, user=user, challenge_id=challenge_id, nonce_b64=nonce, purpose="verify",
                        credential_id=cred.id)
    if cred.status != "active":
        db.commit()
        raise _bad("This device credential has been revoked.", "credential_revoked", status.HTTP_409_CONFLICT)
    key, _ = load_public_key(cred.public_key_spki)
    if not verify_signature(key, signature, consumed.message):
        _observe(db, organization_id=user.organization_id, credential_id=cred.id, user_id=user.id,
                 provenance=cred.provenance, kind="verification_failed", reason_code="bad_signature", ip=ip,
                 app_version=app_version)
        db.commit()
        raise _bad("The signature does not match this device credential.", "bad_signature",
                   status.HTTP_401_UNAUTHORIZED)
    now = _now()
    cred.last_seen_at = now
    cred.last_verified_at = now
    cred.app_version = _trim(app_version, 40) or cred.app_version
    link = _active_link(db, cred.id, user.id)
    link.last_verified_at = now
    _observe(db, organization_id=user.organization_id, credential_id=cred.id, user_id=user.id,
             provenance=cred.provenance, kind="verified", ip=ip, app_version=app_version)
    db.commit()
    db.refresh(cred)
    return cred


# ---------------------------------------------------------------- the user's own view
def credential_out(cred: DeviceCredential) -> dict:
    """What any authorised reader may see. No public key bytes, only a short thumbprint reference."""
    return {"id": str(cred.id), "provenance": cred.provenance, "key_storage_claimed": cred.key_storage,
            "app_version": cred.app_version, "os_family": cred.os_family, "os_version": cred.os_version,
            "status": cred.status, "revoked_reason": cred.revoked_reason, "revoked_at": cred.revoked_at,
            "first_seen_at": cred.first_seen_at, "last_seen_at": cred.last_seen_at,
            "last_verified_at": cred.last_verified_at, "reference": cred.key_thumbprint[:12]}


def list_mine(db: Session, *, user: User) -> list[dict]:
    rows = db.execute(select(DeviceCredential).join(
        DeviceCredentialLink, DeviceCredentialLink.credential_id == DeviceCredential.id).where(
        DeviceCredentialLink.organization_id == user.organization_id, DeviceCredentialLink.user_id == user.id,
        DeviceCredentialLink.unlinked_at.is_(None)).order_by(DeviceCredential.last_seen_at.desc())).scalars().all()
    return [credential_out(r) for r in rows]


def _revoke(cred: DeviceCredential, reason: str, now: datetime) -> None:
    cred.status = "revoked"
    cred.revoked_at = now
    cred.revoked_reason = reason


def unlink_mine(db: Session, *, user: User, credential_id: uuid.UUID, ip: str | None) -> None:
    """The user removes this installation from their account. If no account is left on it, the credential is
    revoked so it can never be silently re-used."""
    _require_enabled()
    cred = _credential_in_org(db, user.organization_id, credential_id, lock=True)
    link = _active_link(db, cred.id, user.id)
    if link is None:
        raise _bad("Device credential not found.", "not_found", status.HTTP_404_NOT_FOUND)
    now = _now()
    link.unlinked_at = now
    _observe(db, organization_id=user.organization_id, credential_id=cred.id, user_id=user.id,
             provenance=cred.provenance, kind="unlinked", ip=ip)
    db.flush()
    remaining = db.execute(select(func.count()).select_from(DeviceCredentialLink).where(
        DeviceCredentialLink.credential_id == cred.id, DeviceCredentialLink.unlinked_at.is_(None))).scalar_one()
    if remaining == 0 and cred.status == "active":
        _revoke(cred, "last_account_unlinked", now)
        _observe(db, organization_id=user.organization_id, credential_id=cred.id, user_id=user.id,
                 provenance=cred.provenance, kind="revoked", reason_code="last_account_unlinked", ip=ip)
    record_audit_log(db, organization_id=user.organization_id, user_id=user.id, action="device.credential_unlinked",
                     resource_type="device_credential", resource_id=cred.id)
    db.commit()


# ---------------------------------------------------------------- admin (tenant-scoped)
def _window_start() -> datetime:
    return _now() - timedelta(days=settings.DEVICE_OBSERVATION_RETENTION_DAYS)


def assess(db: Session, cred: DeviceCredential) -> dict:
    """Evidence categories, not a verdict. The categories this version can produce are exactly the ones its
    evidence supports:

      DEVICE_CREDENTIAL_REVOKED      the credential is revoked (and why)
      SAME_REGISTERED_INSTALLATION   two or more accounts each proved possession of this one key
      CONFLICTING_EVIDENCE           successful and failed signature checks against this key in the window
      SHARED_NETWORK_ONLY            another account was seen on the same network prefix, with no shared key —
                                     weak by itself (offices, families, carrier NAT, VPN exits)
      INSUFFICIENT_EVIDENCE          none of the above
    """
    since = _window_start()
    links = db.execute(select(DeviceCredentialLink).where(
        DeviceCredentialLink.credential_id == cred.id)).scalars().all()
    active_links = [link for link in links if link.unlinked_at is None]
    obs = db.execute(select(DeviceObservation.kind, DeviceObservation.reason_code,
                            DeviceObservation.network_prefix_pseudonym).where(
        DeviceObservation.credential_id == cred.id, DeviceObservation.created_at >= since)).all()
    verified = sum(1 for o in obs if o.kind in ("registered", "linked", "verified"))
    failed = sum(1 for o in obs if o.kind == "verification_failed")
    prefixes = {o.network_prefix_pseudonym for o in obs if o.network_prefix_pseudonym}
    linked_users = {link.user_id for link in links}
    shared_network_accounts = 0
    if prefixes:
        shared_network_accounts = db.execute(select(func.count(func.distinct(DeviceObservation.user_id))).where(
            DeviceObservation.organization_id == cred.organization_id,
            DeviceObservation.network_prefix_pseudonym.in_(prefixes),
            DeviceObservation.created_at >= since,
            DeviceObservation.user_id.is_not(None),
            DeviceObservation.user_id.not_in(linked_users) if linked_users else true(),
        )).scalar_one()

    categories: list[str] = []
    reasons: list[str] = []
    if cred.status == "revoked":
        categories.append("DEVICE_CREDENTIAL_REVOKED")
        reasons.append(f"revoked:{cred.revoked_reason}")
    if len(active_links) >= 2:
        categories.append("SAME_REGISTERED_INSTALLATION")
        reasons.append("multiple_accounts_proved_possession_of_one_key")
    if verified and failed:
        categories.append("CONFLICTING_EVIDENCE")
        reasons.append("failed_signature_checks_against_a_verified_key")
    if shared_network_accounts and len(active_links) < 2:
        categories.append("SHARED_NETWORK_ONLY")
        reasons.append("network_prefix_shared_with_other_accounts")
    if not categories:
        categories.append("INSUFFICIENT_EVIDENCE")
    return {"categories": categories, "reason_codes": reasons, "algorithm_version": ALGORITHM_VERSION,
            "evidence": {"active_linked_accounts": len(active_links), "linked_accounts_ever": len(links),
                         "successful_checks": verified, "failed_checks": failed,
                         "other_accounts_on_shared_network": shared_network_accounts,
                         "window_days": settings.DEVICE_OBSERVATION_RETENTION_DAYS},
            "key_storage_is_client_claimed": True,
            "note": "Installation continuity evidence only. Not an identity of a person, not an enforcement "
                    "decision."}


def admin_list(db: Session, *, organization_id: uuid.UUID, limit: int, offset: int,
               status_filter: str | None = None, sort=None) -> tuple[int, list[dict]]:  # noqa: ANN001
    from app.schemas.common import apply_sort

    where = [DeviceCredential.organization_id == organization_id]
    if status_filter:
        where.append(DeviceCredential.status == status_filter)
    total = db.execute(select(func.count()).select_from(DeviceCredential).where(*where)).scalar_one()
    stmt = apply_sort(select(DeviceCredential).where(*where), DeviceCredential, sort, "last_seen_at")
    rows = db.execute(stmt.limit(limit).offset(offset)).scalars().all()
    return total, [{**credential_out(r), "assessment": assess(db, r)} for r in rows]


def admin_detail(db: Session, *, actor: User, credential_id: uuid.UUID) -> dict:
    cred = _credential_in_org(db, actor.organization_id, credential_id)
    links = db.execute(select(DeviceCredentialLink, User.email).join(
        User, User.id == DeviceCredentialLink.user_id).where(
        DeviceCredentialLink.credential_id == cred.id).order_by(DeviceCredentialLink.first_linked_at)).all()
    obs = db.execute(select(DeviceObservation).where(
        DeviceObservation.credential_id == cred.id).order_by(DeviceObservation.created_at.desc()).limit(100)
    ).scalars().all()
    # Privileged read of security evidence: logged, in the same transaction as nothing else.
    record_audit_log(db, organization_id=actor.organization_id, user_id=actor.id,
                     action="device_intelligence.viewed", resource_type="device_credential", resource_id=cred.id)
    db.commit()
    return {**credential_out(cred), "assessment": assess(db, cred),
            "linked_accounts": [{"user_id": str(link.user_id), "email": email,
                                 "first_linked_at": link.first_linked_at,
                                 "last_verified_at": link.last_verified_at, "unlinked_at": link.unlinked_at}
                                for link, email in links],
            # Network references are truncated pseudonyms: enough to see "same / different network" across
            # rows, useless for locating anyone.
            "observations": [{"kind": o.kind, "reason_code": o.reason_code, "provenance": o.provenance,
                              "network_ref": o.network_prefix_pseudonym[:10] if o.network_prefix_pseudonym else None,
                              "app_version": o.app_version, "at": o.created_at} for o in obs]}


def admin_revoke(db: Session, *, actor: User, credential_id: uuid.UUID) -> dict:
    cred = _credential_in_org(db, actor.organization_id, credential_id, lock=True)
    if cred.status == "revoked":
        raise _bad("Already revoked.", "credential_revoked", status.HTTP_409_CONFLICT)
    now = _now()
    _revoke(cred, "admin_revoked", now)
    _observe(db, organization_id=actor.organization_id, credential_id=cred.id, user_id=actor.id,
             provenance="SERVER_OBSERVATION", kind="revoked", reason_code="admin_revoked", ip=None)
    record_audit_log(db, organization_id=actor.organization_id, user_id=actor.id,
                     action="device.credential_revoked", resource_type="device_credential", resource_id=cred.id,
                     old_value={"status": "active"}, new_value={"status": "revoked", "reason": "admin_revoked"})
    db.commit()
    db.refresh(cred)
    return credential_out(cred)


# ---------------------------------------------------------------- retention
def purge_expired(db: Session, *, now: datetime | None = None) -> dict:
    """Delete observations older than the retention window and challenges that can no longer be used.
    Returns the counts so a scheduler can log them."""
    now = now or _now()
    cutoff = now - timedelta(days=settings.DEVICE_OBSERVATION_RETENTION_DAYS)
    obs = db.execute(delete(DeviceObservation).where(DeviceObservation.created_at < cutoff)).rowcount
    ch = db.execute(delete(DeviceChallenge).where(or_(
        DeviceChallenge.expires_at < now - timedelta(hours=1),
        DeviceChallenge.consumed_at < now - timedelta(hours=1)))).rowcount
    db.commit()
    return {"observations_deleted": obs, "challenges_deleted": ch}
