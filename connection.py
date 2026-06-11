# """
# Resolves Databricks connection credentials per-request.

# Priority:
# 1. X-Databricks-Host / X-Databricks-Token request headers (user-supplied workspace)
# 2. Backend environment credentials (DATABRICKS_HOST / DATABRICKS_TOKEN)

# Falls back silently to env credentials when headers are absent — no errors raised.
# """

# from typing import Optional
# from fastapi import Header


# class WorkspaceConn:
#     def __init__(self, host: Optional[str] = None, token: Optional[str] = None):
#         # None means "use environment defaults" — db_client handles the fallback
#         self.host = host
#         self.token = token

#     def kwargs(self) -> dict:
#         return {"host": self.host, "token": self.token}


# async def get_workspace_conn(
#     x_databricks_host: Optional[str] = Header(default=None),
#     x_databricks_token: Optional[str] = Header(default=None),
# ) -> WorkspaceConn:
#     # Both must be present to override; otherwise fall back to env (no partial overrides)
#     if x_databricks_host and x_databricks_token:
#         return WorkspaceConn(host=x_databricks_host, token=x_databricks_token)
#     return WorkspaceConn()

"""
Resolves Databricks connection credentials per-request using session ID.

Flow:
1. User calls POST /connect with host + token
2. Backend validates and returns session_id (UUID)
3. Frontend stores session_id and sends it as X-Session-ID header
4. Every subsequent request resolves host + token from the session store

Falls back to env credentials when no session header is present
(useful for local testing without a frontend).
"""

from typing import Optional
from fastapi import Header, HTTPException

from session import session_store
from config import settings


class WorkspaceConn:
    def __init__(self, session_id: str, host: str, token: str):
        self.session_id = session_id
        self.host = host
        self.token = token

    def kwargs(self) -> dict:
        return {"host": self.host, "token": self.token}


async def get_workspace_conn(
    x_session_id: Optional[str] = Header(default=None),
) -> WorkspaceConn:
    if x_session_id:
        session = session_store.get(x_session_id)
        if session is None:
            raise HTTPException(
                status_code=401,
                detail="Session expired or invalid. Please reconnect via POST /connect."
            )
        return WorkspaceConn(
            session_id=session.session_id,
            host=session.host,
            token=session.token
        )

    # No session header — fall back to env credentials (local dev / CLI use)
    return WorkspaceConn(
        session_id="env-default",
        host=settings.DATABRICKS_HOST,
        token=settings.DATABRICKS_TOKEN
    )