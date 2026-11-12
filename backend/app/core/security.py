import uuid
import asyncio
from dataclasses import dataclass
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import httpx
from jose import JWTError, jwt

from app.core.config import get_settings

_bearer = HTTPBearer(auto_error=False)

FALLBACK_JWKS: dict[str, Any] = {
    "17ff08fb-b983-4013-be48-04caa4068c2e": {
        "alg": "ES256",
        "crv": "P-256",
        "ext": True,
        "key_ops": ["verify"],
        "kid": "17ff08fb-b983-4013-be48-04caa4068c2e",
        "kty": "EC",
        "use": "sig",
        "x": "9OrJA9qGH2M1tc0CRzBMYjp0UD3B33GlkYntzS_sYlQ",
        "y": "cDimuXJvOJ0kwiiDJHw-RyzSgIxDlheXlCGhnNSUsME",
    }
}

_jwks_cache: dict[str, Any] = dict(FALLBACK_JWKS)
_jwks_cache_expires = float("inf")
_jwks_lock = asyncio.Lock()


async def _load_jwks(supabase_url: str, force_refresh: bool = False) -> dict[str, Any]:
    global _jwks_cache, _jwks_cache_expires
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.get_event_loop()

    if not force_refresh and _jwks_cache and loop.time() < _jwks_cache_expires:
        return _jwks_cache

    async with _jwks_lock:
        if not force_refresh and _jwks_cache and loop.time() < _jwks_cache_expires:
            return _jwks_cache

        last_error: Exception | None = None
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(f"{supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json")
                response.raise_for_status()
                payload = response.json()
                keys = payload.get("keys") if isinstance(payload, dict) else None
                if isinstance(keys, list):
                    _jwks_cache = {key["kid"]: key for key in keys if isinstance(key, dict) and isinstance(key.get("kid"), str)}
                    _jwks_cache_expires = loop.time() + 86400  # 24h cache
                    return _jwks_cache
            except Exception as error:
                last_error = error
                if attempt == 0:
                    await asyncio.sleep(0.5)

        # If network call failed, fallback to existing cache or known keys
        if _jwks_cache:
            return _jwks_cache
        if FALLBACK_JWKS:
            _jwks_cache = dict(FALLBACK_JWKS)
            _jwks_cache_expires = loop.time() + 86400
            return _jwks_cache

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase signing keys could not be retrieved.",
        ) from last_error


@dataclass(frozen=True)
class AuthenticatedUser:
    id: uuid.UUID
    email: str | None
    claims: dict[str, Any]


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> AuthenticatedUser:
    settings = get_settings()
    secret = settings.supabase_jwt_secret
    if (secret is None or not secret.get_secret_value()) and not settings.supabase_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase JWT verification is not configured. Set SUPABASE_JWT_SECRET or SUPABASE_URL for signing-key verification.",
        )
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="A bearer access token is required.")

    try:
        header = jwt.get_unverified_header(credentials.credentials)
        algorithm = header.get("alg")
        if algorithm == "HS256" and secret is not None and secret.get_secret_value():
            signing_key = secret.get_secret_value()
        elif algorithm in {"RS256", "ES256"} and settings.supabase_url:
            kid = header.get("kid")
            jwks = await _load_jwks(settings.supabase_url)
            signing_key = jwks.get(kid)
            if signing_key is None:
                jwks = await _load_jwks(settings.supabase_url, force_refresh=True)
                signing_key = jwks.get(kid)
            if signing_key is None:
                raise JWTError("No matching Supabase public key.")
        else:
            raise JWTError("Unsupported token signing algorithm.")
        options = {"require_sub": True, "require_exp": True}
        decode_args = {"algorithms": [algorithm], "audience": "authenticated", "options": options}
        if settings.supabase_url:
            decode_args["issuer"] = f"{settings.supabase_url.rstrip('/')}/auth/v1"
        claims = jwt.decode(credentials.credentials, signing_key, **decode_args)
        user_id = uuid.UUID(claims["sub"])
    except (JWTError, KeyError, TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Access token is invalid or expired.") from None

    return AuthenticatedUser(id=user_id, email=claims.get("email"), claims=claims)
