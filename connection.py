"""
Resolves Databricks connection credentials per-request.

Priority:
1. X-Databricks-Host / X-Databricks-Token request headers (user-supplied workspace)
2. Backend environment credentials (DATABRICKS_HOST / DATABRICKS_TOKEN)

Falls back silently to env credentials when headers are absent — no errors raised.
"""

from typing import Optional
from fastapi import Header


class WorkspaceConn:
    def __init__(self, host: Optional[str] = None, token: Optional[str] = None):
        # None means "use environment defaults" — db_client handles the fallback
        self.host = host
        self.token = token

    def kwargs(self) -> dict:
        return {"host": self.host, "token": self.token}


async def get_workspace_conn(
    x_databricks_host: Optional[str] = Header(default=None),
    x_databricks_token: Optional[str] = Header(default=None),
) -> WorkspaceConn:
    # Both must be present to override; otherwise fall back to env (no partial overrides)
    if x_databricks_host and x_databricks_token:
        return WorkspaceConn(host=x_databricks_host, token=x_databricks_token)
    return WorkspaceConn()