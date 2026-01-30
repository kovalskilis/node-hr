from typing import TypedDict, List, Dict, Any


class CandidateProfile(TypedDict):
    name: str
    position: str
    grade: str
    experience: str
    skills: List[str]
    tech_stack: List[str]


class InterviewState(TypedDict):
    candidate_name: str
    candidate_grade: str
    candidate_experience: str
    candidate_profile: CandidateProfile
    conversation_history: List[Dict[str, str]]
    current_question: str
    expert_analysis: Dict[str, Any]
    python_specialist_notes: str
    fact_checker_notes: str
    hr_agent_notes: str
    observer_instructions: str
    interviewer_response: str
    validator_approved: bool
    validation_attempts: int
    internal_thoughts: List[Dict[str, Any]]
    metrics: Dict[str, Any]
    is_complete: bool
    final_report: Dict[str, Any] | None
