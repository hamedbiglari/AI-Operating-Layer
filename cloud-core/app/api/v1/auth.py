"""
Authentication endpoints.

POST /auth/register-organization  — bootstrap a brand-new tenant
POST /auth/login                  — OAuth2 password flow (email as username)
POST /auth/login-code/request     — email a 6-digit sign-in code (owner rules)
POST /auth/login-code/verify      — exchange the code for a token
GET  /auth/me                     — current user + their organization
POST /auth/session                — open a browser session (code sign-in + HttpOnly refresh cookie)
POST /auth/session/refresh        — rotate the cookie, hand back a short-lived access token
DELETE /auth/session              — sign out of the browser session
"""

from datetime import timedelta

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.security.client_ip import client_ip
from app.core.config import settings
from app.db.session import get_db
from app.models.organization import Organization
from app.models.user import User
from app.schemas.auth import (
    MeResponse,
    RegisterOrganizationRequest,
    RegisterOrganizationResponse,
    TokenResponse,
)
from app.security.dependencies import get_current_user
from app.security.tokens import create_access_token
from app.services import auth_service, auth_session_service, signup_code_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _issue_token(user: User) -> TokenResponse:
    token = create_access_token(
        user_id=str(user.id),
        organization_id=str(user.organization_id),
        role=user.role.value,
    )
    return TokenResponse(access_token=token, expires_in_minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)


@router.post(
    "/register-organization",
    response_model=RegisterOrganizationResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_organization(
    payload: RegisterOrganizationRequest, request: Request, db: Session = Depends(get_db)
) -> RegisterOrganizationResponse:
    # Password registration creates a tenant without proving the e-mail address. It is off in production
    # unless explicitly enabled; the public path is /auth/signup/request + /verify (security audit SEC-03).
    if not settings.password_registration_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    _throttle(f"register-ip:{client_ip(request)}", settings.REGISTRATION_IP_LIMIT_PER_HOUR, 3600,
              "Too many registrations from this address. Try again later.")
    try:
        organization, owner = auth_service.register_organization(
            db,
            organization_name=payload.organization_name,
            owner_email=payload.owner_email,
            owner_name=payload.owner_name,
            owner_password=payload.owner_password,
        )
    except auth_service.EmailAlreadyRegisteredError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email is already registered"
        ) from None

    return RegisterOrganizationResponse(
        organization=organization, user=owner, token=_issue_token(owner)
    )


class SignupRequest(BaseModel):
    organization_name: str = Field(min_length=2, max_length=200)
    owner_email: EmailStr
    owner_name: str = Field(min_length=1, max_length=200)


class SignupVerifyRequest(BaseModel):
    owner_email: EmailStr
    code: str = Field(min_length=6, max_length=6)


@router.post("/signup/request", status_code=status.HTTP_202_ACCEPTED)
def signup_request(payload: SignupRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    """Start a passwordless sign-up: emails a 6-digit code. The answer never reveals whether the
    address already has an account."""
    ip = client_ip(request)
    out = signup_code_service.request_signup(db, email=payload.owner_email, organization_name=payload.organization_name,
                                             owner_name=payload.owner_name, ip=ip)
    if out.kind == "cooldown":
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "A code was just sent. Wait before asking for another.",
                            headers={"Retry-After": str(out.retry_after_seconds or 60)})
    if out.kind == "rate_limited":
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many sign-up attempts. Try again later.",
                            headers={"Retry-After": str(out.retry_after_seconds or 3600)})
    if out.kind == "delivery_unavailable":
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Email delivery is not configured on this server, so a sign-up code cannot be sent.")
    return {"status": "code_sent", "resend_available_in_seconds": out.retry_after_seconds,
            "expires_in_seconds": signup_code_service.TTL_SECONDS,
            "detail": "If that address can be registered, a 6-digit code is on its way."}


@router.post("/signup/verify", response_model=RegisterOrganizationResponse, status_code=status.HTTP_201_CREATED)
def signup_verify(payload: SignupVerifyRequest, db: Session = Depends(get_db)) -> RegisterOrganizationResponse:
    """Finish the passwordless sign-up: creates the organization and its owner, once."""
    out = signup_code_service.verify_signup(db, email=payload.owner_email, code=payload.code)
    if out.kind == "ok":
        return RegisterOrganizationResponse(organization=out.organization, user=out.user, token=_issue_token(out.user))
    if out.kind == "expired":
        raise HTTPException(status.HTTP_410_GONE, "That code has expired. Request a new one.")
    if out.kind == "too_many_attempts":
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many wrong codes. Request a new one.")
    if out.kind == "conflict":
        raise HTTPException(status.HTTP_409_CONFLICT, "That email address is already registered.")
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "That code is not valid.")


def _throttle(key: str, limit: int, window_seconds: int, message: str) -> None:
    from app.security.rate_limit import check_rate_limit

    result = check_rate_limit(installation_id=key, limit=limit, window_seconds=window_seconds)
    if not result.allowed:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=message,
                            headers={"Retry-After": str(result.retry_after)})


@router.post("/login", response_model=TokenResponse)
def login(
    request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
) -> TokenResponse:
    # Online password guessing is throttled per address and per account (security audit SEC-02). The account
    # key is a hash so the limiter never stores the address in clear.
    import hashlib

    _throttle(f"login-pw-ip:{client_ip(request)}", settings.LOGIN_PASSWORD_IP_LIMIT_PER_MINUTE, 60,
              "Too many sign-in attempts. Try again later.")
    acct = hashlib.sha256(form_data.username.strip().lower().encode()).hexdigest()[:32]
    _throttle(f"login-pw-acct:{acct}", settings.LOGIN_PASSWORD_ACCOUNT_LIMIT_PER_15_MIN, 900,
              "Too many sign-in attempts for this account. Try again in 15 minutes, or sign in with an emailed code.")
    user = auth_service.authenticate(db, email=form_data.username, password=form_data.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _issue_token(user)


@router.get("/me", response_model=MeResponse)
def read_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> MeResponse:
    organization = db.get(Organization, current_user.organization_id)
    return MeResponse(user=current_user, organization=organization)



# --- Email one-time login code (owner requirement, phases 1/13) -------------------

class LoginCodeRequest(BaseModel):
    email: EmailStr


class LoginCodeVerify(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6)


def _ip_limit(request: Request) -> None:
    from app.security.rate_limit import check_rate_limit

    ip = client_ip(request)
    result = check_rate_limit(installation_id=f"login-code-ip:{ip}",
                              limit=settings.LOGIN_CODE_IP_LIMIT_PER_MINUTE)
    if not result.allowed:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many requests.",
                            headers={"Retry-After": str(result.retry_after)})


def _lock_error(outcome) -> HTTPException:  # noqa: ANN001
    message = ("Too many wrong codes. Sign-in is locked for 24 hours; contact support."
               if outcome.contact_support else "Too many wrong codes. Sign-in is locked for 1 hour.")
    return HTTPException(status_code=status.HTTP_423_LOCKED, detail=message,
                         headers={"Retry-After": str(outcome.retry_after_seconds or 0)})


@router.post("/login-code/request", status_code=status.HTTP_202_ACCEPTED)
def request_login_code(payload: LoginCodeRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    from app.services import login_code_service

    _ip_limit(request)
    outcome = login_code_service.request_code(db, email=payload.email)
    if outcome.kind == "delivery_unavailable":
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Email delivery is not available; no code was sent.")
    if outcome.kind == "locked":
        raise _lock_error(outcome)
    if outcome.kind == "cooldown":
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail="A code was sent recently. Try again later.",
                            headers={"Retry-After": str(outcome.retry_after_seconds)})
    # "sent" and "unknown" are deliberately indistinguishable.
    return {"status": "code_sent_if_account_exists", "resend_after_seconds": settings.LOGIN_CODE_RESEND_SECONDS}


@router.post("/login-code/verify", response_model=TokenResponse)
def verify_login_code(payload: LoginCodeVerify, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    from app.services import login_code_service

    _ip_limit(request)
    outcome = login_code_service.verify_code(db, email=payload.email, code=payload.code)
    if outcome.kind == "ok":
        return _issue_token(outcome.user)
    if outcome.kind == "locked":
        raise _lock_error(outcome)
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired code.")


# --- Browser session: refresh cookie + in-memory access token (ADR-129) ----------
#
# The website keeps its access token in a JavaScript variable, never in localStorage or
# sessionStorage, so a cross-site script has nothing durable to read. What survives a reload is this
# HttpOnly cookie, which a page script cannot touch at all, and which is scoped to these three routes
# so it is never attached to a chat or knowledge request.
#
# These routes are additive. /login, /login-code/verify and /signup/verify are untouched and still
# return a bearer token to API and dashboard clients that never wanted a cookie.


def _set_session_cookie(response: Response, cookie: str) -> None:
    response.set_cookie(
        settings.SESSION_COOKIE_NAME,
        cookie,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        path=settings.session_cookie_path,
        domain=settings.SESSION_COOKIE_DOMAIN,
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite=settings.SESSION_COOKIE_SAMESITE.lower(),
    )


def _clear_session_cookie(response: Response) -> None:
    # Same path/domain as the cookie was set with, or the browser deletes nothing.
    response.delete_cookie(
        settings.SESSION_COOKIE_NAME,
        path=settings.session_cookie_path,
        domain=settings.SESSION_COOKIE_DOMAIN,
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite=settings.SESSION_COOKIE_SAMESITE.lower(),
    )


def _browser_token(user: User) -> TokenResponse:
    """Deliberately shorter-lived than the API token: this one is replaceable at any moment by a
    cookie the page cannot read, so there is no reason to make it last an hour."""
    minutes = settings.BROWSER_ACCESS_TOKEN_EXPIRE_MINUTES
    token = create_access_token(
        user_id=str(user.id),
        organization_id=str(user.organization_id),
        role=user.role.value,
        expires_delta=timedelta(minutes=minutes),
    )
    return TokenResponse(access_token=token, expires_in_minutes=minutes)


@router.post("/session", response_model=TokenResponse)
def open_session(payload: LoginCodeVerify, request: Request, response: Response,
                 db: Session = Depends(get_db)) -> TokenResponse:
    """Verify an emailed code and open a browser session. Same verification, lockout and
    indistinguishable-failure rules as /login-code/verify — only the delivery differs."""
    from app.services import login_code_service

    _ip_limit(request)
    outcome = login_code_service.verify_code(db, email=payload.email, code=payload.code)
    if outcome.kind == "locked":
        raise _lock_error(outcome)
    if outcome.kind != "ok":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired code.")
    started = auth_session_service.start(
        db, user=outcome.user, user_agent=request.headers.get("user-agent"), ip=client_ip(request),
    )
    _set_session_cookie(response, started.cookie)
    return _browser_token(outcome.user)


_SESSION_GONE = {
    "invalid": "No browser session.",
    "expired": "This session has expired. Sign in again.",
    "revoked": "This session was signed out. Sign in again.",
    "reuse_detected": "This session was ended because an old session cookie was presented. Sign in again.",
    "user_inactive": "This account is no longer active.",
}


@router.post("/session/refresh", response_model=TokenResponse)
def refresh_session(request: Request, response: Response, db: Session = Depends(get_db),
                    session_cookie: str | None = Cookie(default=None,
                                                        alias=settings.SESSION_COOKIE_NAME)) -> TokenResponse:
    """Rotate the session cookie and issue the next access token. Every failure clears the cookie, so a
    browser is never left holding one that cannot work."""
    outcome = auth_session_service.rotate(
        db, cookie=session_cookie, user_agent=request.headers.get("user-agent"), ip=client_ip(request),
    )
    if outcome.kind != "ok":
        _clear_session_cookie(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail=_SESSION_GONE.get(outcome.kind, _SESSION_GONE["invalid"]))
    _set_session_cookie(response, outcome.cookie)
    return _browser_token(outcome.user)


@router.delete("/session", status_code=status.HTTP_204_NO_CONTENT)
def close_session(response: Response, db: Session = Depends(get_db),
                  session_cookie: str | None = Cookie(default=None,
                                                      alias=settings.SESSION_COOKIE_NAME)) -> None:
    """Sign out. Succeeds whether or not there was a session to end, so a signed-out browser is never
    told that its cookie was already worthless."""
    auth_session_service.end(db, cookie=session_cookie)
    _clear_session_cookie(response)
