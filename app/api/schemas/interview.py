from typing import Dict, Any, List
from pydantic import BaseModel


class InterviewStartRequest(BaseModel):
    session_id: str | None = None


class InterviewMessageRequest(BaseModel):
    session_id: str
    message: str


class InterviewStateResponse(BaseModel):
    session_id: str
    interviewer_response: str
    current_question: str | None = None
    internal_thoughts: List[Dict[str, Any]] = []
    expert_analysis: Dict[str, Any] = {}
    is_complete: bool = False
    final_report: Dict[str, Any] | None = None


class FinalReportResponse(BaseModel):
    session_id: str
    report: Dict[str, Any]
    grade: str
    hiring_recommendation: str
    skills_matrix: Dict[str, Any]
    roadmap: Dict[str, Any]
