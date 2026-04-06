"""
JWT Authentication dependency for FastAPI.

Validates Supabase-issued JWTs and extracts workspace_id + role from
app_metadata claims. Raises 401 if token is missing/invalid.
Raises 403 if workspace_id claim is absent (token not provisioned correctly).
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from app.core.config import settings

_bearer = HTTPBearer(auto_error=False)


class AuthContext(BaseModel):
    """Extracted from the validated JWT."""
    user_id: uuid.UUID
    workspace_id: uuid.UUID | None
    role: str = "practitioner"
    is_super_admin: bool = False


def get_auth_context(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> AuthContext:
    """
    FastAPI dependency: validate JWT and return AuthContext.
    Raises 401 on missing/invalid token, 403 on missing workspace claim
    (unless super_admin).
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"verify_aud": False},
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id_str = payload.get("sub")
    if not user_id_str:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing subject.")

    app_meta = payload.get("app_metadata", {})
    role = app_meta.get("role", "practitioner")
    is_super_admin = role == "super_admin"

    workspace_id_str = app_meta.get("workspace_id")
    workspace_id: uuid.UUID | None = None

    if workspace_id_str:
        try:
            workspace_id = uuid.UUID(workspace_id_str)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid workspace_id in token.",
            )

    if not is_super_admin and workspace_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token does not contain a workspace_id. Contact your administrator.",
        )

    return AuthContext(
        user_id=uuid.UUID(user_id_str),
        workspace_id=workspace_id,
        role=role,
        is_super_admin=is_super_admin,
    )


# Shorthand dependency alias
CurrentUser = Annotated[AuthContext, Depends(get_auth_context)]
