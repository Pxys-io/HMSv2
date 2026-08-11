"""Cookie helpers: refresh + CSRF cookies (Plan/02 §3)."""

from fastapi import Response

from app.core.config import get_settings
from app.core.security import generate_csrf_token


def set_auth_cookies(response: Response, refresh_token: str) -> str:
    settings = get_settings()
    csrf = generate_csrf_token()
    response.set_cookie(
        settings.REFRESH_COOKIE_NAME,
        refresh_token,
        max_age=settings.REFRESH_TOKEN_DAYS_STAFF * 86400,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        path="/",
    )
    response.set_cookie(
        settings.CSRF_COOKIE_NAME,
        csrf,
        max_age=settings.REFRESH_TOKEN_DAYS_STAFF * 86400,
        httponly=False,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        path="/",
    )
    return csrf


def clear_auth_cookies(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(settings.REFRESH_COOKIE_NAME, path="/")
    response.delete_cookie(settings.CSRF_COOKIE_NAME, path="/")


def set_csrf_cookie(response: Response) -> str:
    settings = get_settings()
    csrf = generate_csrf_token()
    response.set_cookie(
        settings.CSRF_COOKIE_NAME,
        csrf,
        httponly=False,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        path="/",
    )
    return csrf
