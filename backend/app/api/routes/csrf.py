"""CSRF cookie endpoint (used by pre-login forms and guest flows)."""

from fastapi import APIRouter, Response

from app.core.cookies import set_csrf_cookie

router = APIRouter(tags=["csrf"])


@router.get("/api/csrf", status_code=204)
def get_csrf(response: Response):
    set_csrf_cookie(response)
