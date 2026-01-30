from typing import Dict
from app.core.models import InterviewState


class SessionStorage:
    def __init__(self):
        self._sessions: Dict[str, InterviewState] = {}
    
    def save(self, session_id: str, state: InterviewState) -> None:
        self._sessions[session_id] = state
    
    def get(self, session_id: str) -> InterviewState | None:
        return self._sessions.get(session_id)
    
    def delete(self, session_id: str) -> None:
        if session_id in self._sessions:
            del self._sessions[session_id]
    
    def exists(self, session_id: str) -> bool:
        return session_id in self._sessions
