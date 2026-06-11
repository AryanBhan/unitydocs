"""
Session store — created on /connect, expires after 1 hour of inactivity.
Each session holds the user's Databricks host and token so the frontend
only needs to send X-Session-ID on every subsequent request.
"""

import time
import uuid
from typing import Optional

SESSION_TTL = 3600  # 1 hour


class Session:
    def __init__(self, host: str, token: str):
        self.session_id = str(uuid.uuid4())
        self.host = host
        self.token = token
        self.created_at = time.time()
        self.last_used = time.time()

    def touch(self):
        """Refresh last used timestamp on every request."""
        self.last_used = time.time()

    def is_expired(self) -> bool:
        return (time.time() - self.last_used) > SESSION_TTL


class SessionStore:
    def __init__(self):
        self._sessions: dict[str, Session] = {}

    def create(self, host: str, token: str) -> Session:
        session = Session(host=host, token=token)
        self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> Optional[Session]:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if session.is_expired():
            del self._sessions[session_id]
            return None
        session.touch()
        return session

    def delete(self, session_id: str) -> bool:
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False


# Single shared instance used across the app
session_store = SessionStore()