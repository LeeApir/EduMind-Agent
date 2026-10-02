"""Explicit deployment scope; a missing/invalid value fails closed to catalog."""

from os import getenv

from fastapi import Depends

from app.core.auth import AuthenticatedSession, AuthFailure, require_authenticated_session


def catalog_only() -> bool:
    return getenv("EDUMIND_PRODUCT_MODE", "catalog_only") != "dynamic"


async def require_dynamic_mode(
    current: AuthenticatedSession = Depends(require_authenticated_session),
) -> None:
    if catalog_only():
        raise AuthFailure(409, "FEATURE_UNAVAILABLE", "Feature is unavailable in this course.")
