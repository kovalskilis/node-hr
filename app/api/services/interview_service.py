from typing import Dict
from app.core.models import InterviewState
from app.core.engine import NodeHREngine


class InterviewService:
    def __init__(self, engine: NodeHREngine):
        self.engine = engine
        self.sessions: Dict[str, InterviewState] = {}
    
    def get_initial_state(self) -> InterviewState:
        return {
            "candidate_name": "",
            "candidate_grade": "",
            "candidate_experience": "",
            "conversation_history": [],
            "current_question": "",
            "expert_analysis": {},
            "python_specialist_notes": "",
            "fact_checker_notes": "",
            "hr_agent_notes": "",
            "observer_instructions": "",
            "interviewer_response": "",
            "validator_approved": False,
            "validation_attempts": 0,
            "internal_thoughts": [],
            "metrics": {},
            "is_complete": False,
            "final_report": None
        }
    
    async def start_interview(self, session_id: str) -> InterviewState:
        state = self.get_initial_state()
        self.sessions[session_id] = state
        result = await self.engine.graph.ainvoke(state)
        self.sessions[session_id] = result
        return result
    
    async def process_message(self, session_id: str, message: str) -> InterviewState:
        if session_id not in self.sessions:
            raise ValueError(f"Session {session_id} not found")
        
        state = self.sessions[session_id]
        
        if message.lower().strip() == "стоп игра":
            state["is_complete"] = True
        
        state["conversation_history"].append({
            "role": "user",
            "content": message
        })
        
        if not state.get("candidate_name"):
            state["candidate_name"] = message
        elif not state.get("candidate_grade"):
            state["candidate_grade"] = message
        elif not state.get("candidate_experience"):
            state["candidate_experience"] = message
        
        result = await self.engine.graph.ainvoke(state)
        self.sessions[session_id] = result
        return result
    
    def get_session(self, session_id: str) -> InterviewState | None:
        return self.sessions.get(session_id)
    
    def delete_session(self, session_id: str) -> None:
        if session_id in self.sessions:
            del self.sessions[session_id]
