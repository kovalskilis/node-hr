import copy
import json
from typing import Dict

from app.core.engine import NodeHREngine
from app.core.models import InterviewState
from app.storages.session_storage import SessionStorage


class InterviewUseCase:
    def __init__(self, engine: NodeHREngine, storage: SessionStorage):
        self.engine = engine
        self.storage = storage

    async def start_interview(self, session_id: str) -> InterviewState:
        self.engine.logger.reset()
        self.engine.logger.log_data["session_id"] = session_id
        self.engine.logger._turn_counter = 0

        state = self._get_initial_state()
        self.storage.save(session_id, state)
        result = await self.engine.graph.ainvoke(state)
        self.storage.save(session_id, result)
        self.engine.logger._turn_counter = 1
        self.engine.logger.save_turn(result, turn_number=1)
        
        result_copy = copy.deepcopy(result)
        result["internal_thoughts"] = []
        self.storage.save(session_id, result)
        
        return result_copy

    async def process_message(self, session_id: str, message: str) -> InterviewState:
        state = self.storage.get(session_id)
        if not state:
            raise ValueError(f"Session {session_id} not found")

        if message.lower().strip() == "стоп игра":
            state["is_complete"] = True

        state["conversation_history"].append({"role": "user", "content": message})
        result = await self.engine.graph.ainvoke(state)
        self.storage.save(session_id, result)

        if not hasattr(self.engine.logger, '_turn_counter'):
            self.engine.logger._turn_counter = len(self.engine.logger.log_data.get("turns", []))
        self.engine.logger._turn_counter += 1
        
        self.engine.logger.save_turn(result, turn_number=self.engine.logger._turn_counter)
        
        if result.get("is_complete") and result.get("final_report"):
            final_report = result.get("final_report", {})
            if isinstance(final_report, dict):
                self.engine.logger.log_data["final_feedback"] = self.engine.logger._format_final_feedback_as_markdown(final_report)
            else:
                self.engine.logger.log_data["final_feedback"] = str(final_report)
            self.engine.logger._save_log()

        result_copy = copy.deepcopy(result)
        result["internal_thoughts"] = []
        self.storage.save(session_id, result)

        return result_copy

    def get_session(self, session_id: str) -> InterviewState | None:
        return self.storage.get(session_id)

    def delete_session(self, session_id: str) -> None:
        self.storage.delete(session_id)

    @staticmethod
    def _get_initial_state() -> InterviewState:
        return {
            "candidate_name": "",
            "candidate_grade": "",
            "candidate_experience": "",
            "candidate_profile": {
                "name": "",
                "position": "",
                "grade": "",
                "experience": "",
                "skills": [],
                "tech_stack": []
            },
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
            "metrics": {
                "total_tokens": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "latencies": [],
                "avg_latency": 0
            },
            "is_complete": False,
            "final_report": None
        }
