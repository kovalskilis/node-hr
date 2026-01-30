from app.core.engine import NodeHREngine
from app.core.use_case import InterviewUseCase
from app.storages.session_storage import SessionStorage

_engine: NodeHREngine | None = None
_storage: SessionStorage | None = None
_use_case: InterviewUseCase | None = None


def get_engine() -> NodeHREngine:
    global _engine
    if _engine is None:
        _engine = NodeHREngine()
    return _engine


def get_storage() -> SessionStorage:
    global _storage
    if _storage is None:
        _storage = SessionStorage()
    return _storage


def get_use_case() -> InterviewUseCase:
    global _use_case
    if _use_case is None:
        _use_case = InterviewUseCase(get_engine(), get_storage())
    return _use_case
