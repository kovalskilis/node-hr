import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from colorama import Fore, Style, init

init(autoreset=True)


class NodeHRLogger:
    def __init__(self, log_dir: str = "logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        self.log_file = self.log_dir / f"interview_log_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
        self.log_data = {
            "participant_name": "",
            "turns": [],
            "final_feedback": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": None,
            "events": [],
            "metrics": {
                "total_tokens": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "latency_ms": [],
                "sentiment_scores": []
            }
        }
        self._turn_counter = 0
        self._setup_logger()

    def _setup_logger(self):
        logger = logging.getLogger("nodehr")
        logger.setLevel(logging.INFO)
        if not logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter('%(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        self.logger = logger

    def _get_color(self, agent: str) -> str:
        colors = {
            "Orchestrator": Fore.CYAN,
            "PythonSpecialist": Fore.GREEN,
            "FactChecker": Fore.YELLOW,
            "HRAgent": Fore.MAGENTA,
            "Observer": Fore.BLUE,
            "Interviewer": Fore.CYAN,
            "Validator": Fore.RED,
            "System": Fore.WHITE
        }
        return colors.get(agent, Fore.WHITE)

    def log(self, agent: str, message: str, data: Dict[str, Any] | None = None):
        timestamp = datetime.now(timezone.utc)
        color = self._get_color(agent)

        log_entry = {
            "timestamp": timestamp.isoformat(),
            "agent": agent,
            "message": message,
            "data": data or {}
        }

        self.log_data["events"].append(log_entry)

        agent_prefix = {
            "Orchestrator": "[LOG :: ORCHESTRATOR]",
            "PythonSpecialist": "[LOG :: PYTHON_SPEC]",
            "FactChecker": "[LOG :: FACT_CHECK]",
            "HRAgent": "[LOG :: HR_AGENT]",
            "Observer": "[LOG :: MENTOR]",
            "Interviewer": "[LOG :: INTERVIEWER]",
            "Validator": "[LOG :: VALIDATOR]",
            "System": "[LOG :: SYSTEM]"
        }.get(agent, f"[LOG :: {agent}]")

        formatted_msg = f"{color}{agent_prefix}{Style.RESET_ALL} {message}"
        if data:
            formatted_msg += f" | Data: {json.dumps(data, ensure_ascii=False)}"

        self.logger.info(formatted_msg)
        self._save_log()

    def log_state_transition(self, from_state: str, to_state: str, reason: str = ""):
        self.log("System", f"State transition: {from_state} → {to_state}", {"reason": reason})

    def log_metric(self, metric_name: str, value: Any):
        if metric_name not in self.log_data["metrics"]:
            self.log_data["metrics"][metric_name] = []

        if isinstance(self.log_data["metrics"][metric_name], list):
            self.log_data["metrics"][metric_name].append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "value": value
            })
        else:
            self.log_data["metrics"][metric_name] = value

    def log_tokens(self, prompt_tokens: int, completion_tokens: int):
        self.log_data["metrics"]["prompt_tokens"] += prompt_tokens
        self.log_data["metrics"]["completion_tokens"] += completion_tokens
        self.log_data["metrics"]["total_tokens"] += (prompt_tokens + completion_tokens)
        self.log("System", f"[METRIC :: TOKENS] +{prompt_tokens} prompt, +{completion_tokens} completion")

    def log_latency(self, latency_ms: float):
        self.log_data["metrics"]["latency_ms"].append(latency_ms)
        self.log("System", f"[METRIC :: LATENCY] {latency_ms:.2f}ms")

    def log_sentiment(self, score: float):
        self.log_data["metrics"]["sentiment_scores"].append(score)
        self.log("System", f"Sentiment: {score:.2f}")

    def _save_log(self):
        try:
            with open(self.log_file, 'w', encoding='utf-8') as f:
                json.dump(self.log_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving log: {e}")

    def _format_final_feedback_as_markdown(self, report: Dict[str, Any]) -> str:
        if not isinstance(report, dict):
            return str(report)
        
        lines = []
        
        decision = report.get("decision", {})
        if decision:
            lines.append("# Решение (Decision)")
            lines.append("")
            lines.append(f"**Уровень (Grade):** {decision.get('grade', 'N/A')}")
            lines.append(f"**Рекомендация по найму:** {decision.get('hiring_recommendation', 'N/A')}")
            lines.append(f"**Уровень уверенности:** {decision.get('confidence_score', 'N/A')}/100")
            lines.append("")
            reason = decision.get('recommendation_reason', '')
            if reason:
                lines.append(f"**Обоснование:** {reason}")
                lines.append("")
        
        skills_matrix = report.get("skills_matrix", {})
        if skills_matrix:
            lines.append("## Матрица навыков (Skills Matrix)")
            lines.append("")
            lines.append(f"- **Технические навыки:** {skills_matrix.get('technical_skills', 'N/A')}/10")
            lines.append(f"- **Коммуникация:** {skills_matrix.get('communication', 'N/A')}/10")
            lines.append(f"- **Решение проблем:** {skills_matrix.get('problem_solving', 'N/A')}/10")
            lines.append(f"- **Опыт:** {skills_matrix.get('experience', 'N/A')}/10")
            lines.append(f"- **Культурное соответствие:** {skills_matrix.get('cultural_fit', 'N/A')}/10")
            lines.append("")
            
            confirmed_skills = skills_matrix.get('confirmed_skills', [])
            if confirmed_skills:
                lines.append("### Подтвержденные навыки (Confirmed Skills)")
                lines.append("")
                for skill in confirmed_skills:
                    lines.append(f"- {skill}")
                lines.append("")
        
        knowledge_gaps = report.get("knowledge_gaps", [])
        if knowledge_gaps:
            lines.append("## Пробелы в знаниях (Knowledge Gaps)")
            lines.append("")
            for i, gap in enumerate(knowledge_gaps, 1):
                gap_text = gap.get('gap', 'N/A')
                educational_content = gap.get('educational_content', '')
                
                lines.append(f"### {i}. {gap_text}")
                lines.append("")
                if educational_content:
                    lines.append("**Образовательный контент:**")
                    lines.append("")
                    lines.append(educational_content)
                    lines.append("")
        
        roadmap = report.get("roadmap", {})
        if roadmap:
            lines.append("## Дорожная карта развития (Roadmap)")
            lines.append("")
            
            immediate = roadmap.get('immediate', [])
            if immediate:
                lines.append("### Немедленные действия (Immediate)")
                lines.append("")
                for item in immediate:
                    lines.append(f"- {item}")
                lines.append("")
            
            short_term = roadmap.get('short_term', [])
            if short_term:
                lines.append("### Краткосрочные цели (Short-term)")
                lines.append("")
                for item in short_term:
                    lines.append(f"- {item}")
                lines.append("")
            
            long_term = roadmap.get('long_term', [])
            if long_term:
                lines.append("### Долгосрочные цели (Long-term)")
                lines.append("")
                for item in long_term:
                    lines.append(f"- {item}")
                lines.append("")
        
        summary = report.get("summary", "")
        if summary:
            lines.append("## Резюме (Summary)")
            lines.append("")
            lines.append(summary)
            lines.append("")
        
        return "\n".join(lines)

    def reset(self):
        self.log_file = self.log_dir / f"interview_log_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
        self.log_data = {
            "participant_name": "",
            "turns": [],
            "final_feedback": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": None,
            "events": [],
            "metrics": {
                "total_tokens": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "latency_ms": [],
                "sentiment_scores": []
            }
        }
        self._turn_counter = 0

    def get_log_data(self) -> Dict[str, Any]:
        return self.log_data.copy()

    def save_turn(self, state: Dict[str, Any], turn_number: int = None):
        participant_name = (
            state.get("candidate_name") or
            state.get("candidate_profile", {}).get("name", "") or
            "Unknown"
        )
        if participant_name and participant_name != "Unknown":
            self.log_data["participant_name"] = participant_name

        if turn_number is not None:
            turn_id = turn_number
            self._turn_counter = max(self._turn_counter, turn_number)
        elif hasattr(self, '_turn_counter') and self._turn_counter > 0:
            turn_id = self._turn_counter
        else:
            turn_id = len(self.log_data["turns"]) + 1
            self._turn_counter = turn_id

        conversation_history = state.get("conversation_history", [])
        user_message = ""

        for msg in reversed(conversation_history):
            if msg.get("role") == "user":
                user_message = msg.get("content", "")
                break

        agent_visible_message = ""
        for msg in reversed(conversation_history):
            if msg.get("role") == "assistant":
                agent_visible_message = msg.get("content", "")
                break

        if not agent_visible_message:
            agent_visible_message = state.get("interviewer_response", "")

        internal_thoughts_list = state.get("internal_thoughts", [])
        internal_thoughts_str = ""
        if internal_thoughts_list:
            thought_parts = []
            for thought in internal_thoughts_list:
                agent = thought.get("agent", "Unknown")
                thought_text = thought.get("thought", "")
                if thought_text:
                    thought_parts.append(f"[{agent}]: {thought_text}")
            internal_thoughts_str = "\n".join(thought_parts)
            if internal_thoughts_str and not internal_thoughts_str.endswith("\n"):
                internal_thoughts_str += "\n"

        turn_data = {
            "turn_id": turn_id,
            "agent_visible_message": agent_visible_message,
            "user_message": user_message,
            "internal_thoughts": internal_thoughts_str
        }

        self.log_data["turns"].append(turn_data)

        if state.get("is_complete") and state.get("final_report"):
            final_report = state.get("final_report", {})
            if isinstance(final_report, dict):
                self.log_data["final_feedback"] = self._format_final_feedback_as_markdown(final_report)
            else:
                self.log_data["final_feedback"] = str(final_report)

        self._save_log()
        
        state["internal_thoughts"] = []
