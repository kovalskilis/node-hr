import asyncio
import json
import re
import time
from typing import Any, Dict, List

from langgraph.graph import END, StateGraph
from mistralai import Mistral

from app.config.settings import settings
from app.core.models import InterviewState
from app.core.prompts import (
    FACT_CHECKER_PROMPT,
    FINAL_REPORT_PROMPT,
    HR_AGENT_PROMPT,
    INTERVIEWER_PROMPT,
    OBSERVER_PROMPT,
    ORCHESTRATOR_PROMPT,
    PYTHON_SPECIALIST_PROMPT,
    VALIDATOR_PROMPT,
)
from app.utils.logger import NodeHRLogger


class NodeHREngine:
    def __init__(self):
        self.client = Mistral(api_key=settings.MISTRAL_API_KEY)
        self.model = settings.MISTRAL_MODEL
        self.logger = NodeHRLogger()
        self.graph = self._build_graph()

    def _parse_json_response(self, content: str) -> Dict[str, Any]:
        json_str = None
        if "```json" in content:
            json_str = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            json_str = content.split("```")[1].split("```")[0].strip()
        else:
            json_str = content.strip()

        if not json_str or not json_str.startswith("{"):
            start_idx = content.find("{")
            if start_idx != -1:
                end_idx = content.rfind("}")
                if end_idx != -1 and end_idx > start_idx:
                    json_str = content[start_idx:end_idx+1]

        if json_str:
            json_str = json_str.strip()
            json_str = re.sub(r'^```json\s*', '', json_str, flags=re.MULTILINE)
            json_str = re.sub(r'^```\s*', '', json_str, flags=re.MULTILINE)
            json_str = re.sub(r'```\s*$', '', json_str, flags=re.MULTILINE)
            json_str = json_str.strip()
            return json_str
        return None

    def _extract_json(self, content: str) -> Dict[str, Any]:
        try:
            json_str = self._parse_json_response(content)
            if json_str:
                return json.loads(json_str)
            self.logger.log("System", f"Не удалось найти JSON в ответе. Content: {content[:500]}")
            return {"raw_response": content}
        except json.JSONDecodeError as e:
            self.logger.log("System", f"Ошибка парсинга JSON: {e}. Content: {content[:500]}")
            try:
                json_str = self._parse_json_response(content)
                if json_str:
                    cleaned = re.sub(r'//.*?$', '', json_str, flags=re.MULTILINE)
                    cleaned = re.sub(r',\s*}', '}', cleaned)
                    cleaned = re.sub(r',\s*]', ']', cleaned)
                    return json.loads(cleaned)
            except:
                pass
            return {"raw_response": content}
        except Exception as e:
            self.logger.log("System", f"Неожиданная ошибка парсинга: {e}. Content: {content[:500]}")
            return {"raw_response": content}

    def _update_metrics(self, state: InterviewState, tokens_used: Any, latency: float):
        if state is None:
            return
        if "metrics" not in state:
            state["metrics"] = {}
        state["metrics"]["total_tokens"] = state["metrics"].get("total_tokens", 0) + tokens_used.prompt_tokens + tokens_used.completion_tokens
        state["metrics"]["prompt_tokens"] = state["metrics"].get("prompt_tokens", 0) + tokens_used.prompt_tokens
        state["metrics"]["completion_tokens"] = state["metrics"].get("completion_tokens", 0) + tokens_used.completion_tokens
        if "latencies" not in state["metrics"]:
            state["metrics"]["latencies"] = []
        state["metrics"]["latencies"].append(latency)
        state["metrics"]["avg_latency"] = sum(state["metrics"]["latencies"]) / len(state["metrics"]["latencies"])

    def _call_llm(self, prompt: str, system_prompt: str | None = None, state: InterviewState | None = None) -> Dict[str, Any]:
        start_time = time.time()
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = self.client.chat.complete(model=self.model, messages=messages)
        latency = (time.time() - start_time) * 1000
        self.logger.log_latency(latency)

        content = response.choices[0].message.content
        tokens_used = response.usage
        self.logger.log_tokens(tokens_used.prompt_tokens, tokens_used.completion_tokens)
        self._update_metrics(state, tokens_used, latency)

        return self._extract_json(content)

    async def _call_llm_async(self, prompt: str, system_prompt: str | None = None, state: InterviewState | None = None) -> Dict[str, Any]:
        start_time = time.time()
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = await asyncio.to_thread(self.client.chat.complete, model=self.model, messages=messages)
        latency = (time.time() - start_time) * 1000
        self.logger.log_latency(latency)

        content = response.choices[0].message.content
        tokens_used = response.usage
        self.logger.log_tokens(tokens_used.prompt_tokens, tokens_used.completion_tokens)
        self._update_metrics(state, tokens_used, latency)

        return self._extract_json(content)

    def orchestrator_node(self, state: InterviewState) -> InterviewState:
        self.logger.log("Orchestrator", "Анализ контекста и извлечение информации")

        user_messages = [msg.get("content", "") for msg in state.get("conversation_history", []) if msg.get("role") == "user"]
        all_messages = state.get("conversation_history", [])

        if not user_messages:
            response_text = "Здравствуйте! Меня зовут AI-HR. Расскажите о себе: как вас зовут, на какую позицию вы претендуете и какой у вас уровень?"
            state["interviewer_response"] = response_text
            state["conversation_history"].append({"role": "assistant", "content": response_text})
            state["internal_thoughts"].append({
                "agent": "Orchestrator",
                "thought": "Начало интервью. Запрашиваю базовую информацию.",
                "timestamp": time.time()
            })
            return state

        profile = state.get("candidate_profile", {})
        if not profile:
            profile = {
                "name": state.get("candidate_name", ""),
                "position": "",
                "grade": state.get("candidate_grade", ""),
                "experience": state.get("candidate_experience", ""),
                "skills": [],
                "tech_stack": []
            }

        has_complete_profile = (profile.get("name") and profile.get("grade") and
                               (profile.get("position") or profile.get("experience")))

        if has_complete_profile:
            self.logger.log("Orchestrator", f"Профиль уже заполнен: {profile.get('name')} - {profile.get('position')} ({profile.get('grade')})")
            state["candidate_profile"] = profile
            return state

        recent_messages = all_messages[-4:] if len(all_messages) > 4 else all_messages
        conversation_text = "\n".join([f"{msg.get('role', 'unknown')}: {msg.get('content', '')}" for msg in recent_messages])

        extraction = self._call_llm(
            f"Извлеки информацию о кандидате из последних сообщений:\n\n{conversation_text}\n\n"
            f"Текущий профиль: {json.dumps(profile, ensure_ascii=False)}\n\n"
            f"Извлеки: имя, позицию, уровень (junior/middle/senior), опыт. Кратко, только факты.",
            ORCHESTRATOR_PROMPT,
            state
        )

        profile = state.get("candidate_profile", {})
        if not profile:
            profile = {"name": "", "position": "", "grade": "", "experience": "", "skills": [], "tech_stack": []}

        if extraction.get("name"):
            profile["name"] = extraction["name"]
            state["candidate_name"] = extraction["name"]
        if extraction.get("position"):
            profile["position"] = extraction["position"]
        if extraction.get("grade"):
            profile["grade"] = extraction["grade"].lower()
            state["candidate_grade"] = extraction["grade"].lower()
        if extraction.get("experience"):
            profile["experience"] = extraction["experience"]
            state["candidate_experience"] = extraction["experience"]
        if extraction.get("skills"):
            profile["skills"] = extraction["skills"]
        if extraction.get("tech_stack"):
            profile["tech_stack"] = extraction["tech_stack"]

        state["candidate_profile"] = profile
        missing_info = extraction.get("missing_info", [])
        ready_for_technical = extraction.get("ready_for_technical", False)
        reasoning = extraction.get("reasoning", "")

        state["internal_thoughts"].append({
            "agent": "Orchestrator",
            "thought": f"Извлечена информация: имя={profile.get('name', 'нет')}, позиция={profile.get('position', 'нет')}, уровень={profile.get('grade', 'нет')}. "
                      f"Готов к техническому интервью: {ready_for_technical}. "
                      f"Недостающая информация: {missing_info}. "
                      f"Обоснование: {reasoning}",
            "timestamp": time.time()
        })

        if ready_for_technical or (profile.get("name") and profile.get("grade") and (profile.get("position") or profile.get("experience"))):
            self.logger.log("Orchestrator", f"Вся информация собрана. Профиль: {profile.get('name')} - {profile.get('position')} ({profile.get('grade')})")
            response_text = "Отлично! Начинаем техническое интервью."
            state["interviewer_response"] = response_text
            state["conversation_history"].append({"role": "assistant", "content": response_text})
            return state

        if missing_info:
            question = missing_info[0] if isinstance(missing_info, list) and missing_info else "Расскажите больше о себе."
            response_text = question
            state["interviewer_response"] = response_text
            state["conversation_history"].append({"role": "assistant", "content": response_text})
            state["internal_thoughts"].append({
                "agent": "Orchestrator",
                "thought": f"Задаю вопрос о недостающей информации: {question}",
                "timestamp": time.time()
            })
            return state

        response_text = "Расскажите о себе: как вас зовут, на какую позицию вы претендуете и какой у вас уровень?"
        state["interviewer_response"] = response_text
        state["conversation_history"].append({"role": "assistant", "content": response_text})
        return state

    async def expert_pool_node(self, state: InterviewState) -> InterviewState:
        self.logger.log("ExpertPool", "Параллельный анализ экспертами")

        last_user_msg = ""
        for msg in reversed(state.get("conversation_history", [])):
            if msg.get("role") == "user":
                last_user_msg = msg.get("content", "")
                break

        if not last_user_msg:
            state["python_specialist_notes"] = "Нет ответов для анализа"
            state["fact_checker_notes"] = "Нет ответов для проверки"
            state["hr_agent_notes"] = "Нет данных для оценки"
            return state

        python_task = self._python_specialist_async(last_user_msg, state)
        fact_task = self._fact_checker_async(last_user_msg, state)
        hr_task = self._hr_agent_async(state.get("conversation_history", []), state)

        python_result, fact_result, hr_result = await asyncio.gather(python_task, fact_task, hr_task)

        state["python_specialist_notes"] = json.dumps(python_result, ensure_ascii=False)
        state["expert_analysis"]["python_specialist"] = python_result
        state["fact_checker_notes"] = json.dumps(fact_result, ensure_ascii=False)
        state["expert_analysis"]["fact_checker"] = fact_result
        state["hr_agent_notes"] = json.dumps(hr_result, ensure_ascii=False)
        state["expert_analysis"]["hr_agent"] = hr_result

        self.logger.log("ExpertPool", "Все эксперты завершили анализ")
        return state

    async def _python_specialist_async(self, user_msg: str, state: InterviewState) -> Dict[str, Any]:
        self.logger.log("PythonSpecialist", "Анализ технической точности")
        truncated_msg = user_msg[:500]
        analysis = await self._call_llm_async(f"Ответ: {truncated_msg}\nОцени техническую точность.", PYTHON_SPECIALIST_PROMPT, state)
        self.logger.log("PythonSpecialist", f"Анализ завершен: {analysis.get('technical_accuracy', 'N/A')}")
        return analysis

    async def _fact_checker_async(self, user_msg: str, state: InterviewState) -> Dict[str, Any]:
        self.logger.log("FactChecker", "Проверка на галлюцинации")
        truncated_msg = user_msg[:500]
        check = await self._call_llm_async(f"Ответ: {truncated_msg}\nПроверь на галлюцинации.", FACT_CHECKER_PROMPT, state)
        if check.get("has_hallucinations"):
            self.logger.log("FactChecker", f"Обнаружены галлюцинации: {check.get('detected_issues', [])}")
        return check

    async def _hr_agent_async(self, conversation_history: List[Dict], state: InterviewState) -> Dict[str, Any]:
        self.logger.log("HRAgent", "Оценка soft skills")
        recent_messages = conversation_history[-3:] if len(conversation_history) > 3 else conversation_history
        conversation_text = "\n".join([f"{msg['role']}: {msg['content'][:200]}" for msg in recent_messages])
        analysis = await self._call_llm_async(f"Сообщения:\n{conversation_text}\nОцени soft skills.", HR_AGENT_PROMPT, state)
        self.logger.log("HRAgent", f"Оценка завершена: Communication={analysis.get('communication_score', 'N/A')}")
        return analysis

    async def observer_node(self, state: InterviewState) -> InterviewState:
        self.logger.log("Observer", "Создание скрытых инструкций")

        expert_analysis = state.get("expert_analysis", {})
        python_data = expert_analysis.get("python_specialist", {})
        fact_checker_data = expert_analysis.get("fact_checker", {})
        hr_data = expert_analysis.get("hr_agent", {})

        python_score = python_data.get("technical_accuracy", 0)
        python_notes = python_data.get("notes", "")[:100]
        has_warning = fact_checker_data.get("warning", False)
        fact_issues = fact_checker_data.get("detected_issues", [])
        hr_score = hr_data.get("communication_score", 0)
        hr_observations = hr_data.get("observations", "")[:100]

        last_user_msg = ""
        for msg in reversed(state.get("conversation_history", [])):
            if msg.get("role") == "user":
                last_user_msg = msg.get("content", "")[:200]
                break

        difficulty_adjustment = "increase" if isinstance(python_score, (int, float)) and python_score >= 8 else "maintain"

        instructions = await self._call_llm_async(
            f"Анализ экспертов:\n"
            f"Python Specialist: оценка={python_score}, заметки={python_notes[:80]}\n"
            f"Fact Checker: warning={has_warning}, проблемы={fact_issues[:3]}\n"
            f"HR Agent: коммуникация={hr_score}, наблюдения={hr_observations[:80]}\n"
            f"Последний ответ кандидата: {last_user_msg[:150]}\n\n"
            f"Создай скрытые инструкции. Если оценка >=8 - увеличивай сложность. Если warning=true - укажи на это.",
            OBSERVER_PROMPT,
            state
        )

        instructions["difficulty_adjustment"] = difficulty_adjustment
        instructions["warning_present"] = has_warning
        state["observer_instructions"] = json.dumps(instructions, ensure_ascii=False)

        thought_text = f"[SENTIMENT: {instructions.get('sentiment', 'neutral')}] {instructions.get('hidden_instructions', '')} [GUIDANCE: {instructions.get('guidance', 'none')}]"
        if has_warning:
            thought_text += f" [WARNING: {', '.join(fact_issues[:2])}]"

        state["internal_thoughts"].append({
            "agent": "Observer",
            "thought": thought_text,
            "timestamp": time.time(),
            "sentiment": instructions.get("sentiment", "neutral"),
            "guidance": instructions.get("guidance", ""),
            "warning": has_warning
        })

        self.logger.log("Observer", f"Инструкции созданы. Sentiment: {instructions.get('sentiment')}, Warning: {has_warning}")
        return state

    async def interviewer_node(self, state: InterviewState) -> InterviewState:
        self.logger.log("Interviewer", "Формулировка ответа")

        instructions = json.loads(state.get("observer_instructions", "{}"))
        profile = state.get("candidate_profile", {})

        last_user_msg = ""
        for msg in reversed(state.get("conversation_history", [])):
            if msg.get("role") == "user":
                last_user_msg = msg.get("content", "")[:300]
                break

        profile_context = f"Кандидат: {profile.get('name', 'неизвестно')}, {profile.get('position', '')} ({profile.get('grade', '')})"
        warning_present = instructions.get("warning_present", False)
        guidance = instructions.get("guidance", "")
        difficulty = instructions.get("difficulty_adjustment", "maintain")
        sentiment = instructions.get("sentiment", "neutral")

        prompt_context = f"{profile_context}\n"
        prompt_context += f"Инструкции: {instructions.get('hidden_instructions', '')}\n"
        if warning_present:
            prompt_context += f"⚠️ WARNING: Fact Checker обнаружил технические неточности. Обрати на это внимание.\n"
        if guidance:
            prompt_context += f"Guidance: {guidance}\n"
        prompt_context += f"Sentiment: {sentiment}, Difficulty: {difficulty}\n"
        prompt_context += f"Ответ кандидата: {last_user_msg}\n"
        prompt_context += f"Сформулируй ответ. Если профиль заполнен - задай технический вопрос. Максимум 1 вопрос. Кратко."

        is_company_question = any(word in last_user_msg.lower() for word in ['компания', 'команда', 'вакансия', 'компании', 'команды', 'компанией'])

        response = await self._call_llm_async(prompt_context, INTERVIEWER_PROMPT, state)

        if is_company_question and not response.get("is_company_question", False):
            state["internal_thoughts"].append({
                "agent": "HR Agent",
                "thought": f"Кандидат задал вопрос о компании. Отвечаю как HR-специалист, затем вернусь к техническим вопросам.",
                "timestamp": time.time()
            })

        state["internal_thoughts"].append({
            "agent": "Interviewer",
            "thought": f"Сформирован ответ. Profile: {profile.get('name')} ({profile.get('grade')}). "
                      f"Sentiment: {sentiment}, Difficulty: {difficulty}. "
                      f"Warning handled: {warning_present}",
            "timestamp": time.time()
        })

        interviewer_response = response.get("response", "Продолжаем интервью.")
        question = response.get("question", "")

        if question:
            questions = [q.strip() for q in question.split('?') if q.strip()]
            if len(questions) > 1:
                question = questions[0] + "?"
                self.logger.log("Interviewer", f"Обнаружено несколько вопросов, оставлен только первый")

        if interviewer_response.count('?') > 1:
            parts = interviewer_response.split('?')
            if len(parts) > 1:
                interviewer_response = parts[0] + "?"
                self.logger.log("Interviewer", f"Обнаружено несколько вопросов в response, оставлен только первый")

        state["interviewer_response"] = interviewer_response
        state["current_question"] = question
        self.logger.log("Interviewer", "Ответ сформулирован")
        return state

    async def validator_node(self, state: InterviewState) -> InterviewState:
        self.logger.log("Validator", "Проверка качества ответа")

        validation = await self._call_llm_async(
            f"Ответ: {state.get('interviewer_response', '')}\n\n"
            f"Инструкции: {state.get('observer_instructions', '')}\n\n"
            f"Проверь: ответ не пустой и содержит вопрос или комментарий. Верни только approved: true/false.",
            "Ты валидатор. Проверь только базовое качество ответа. Будь мягче в оценке.",
            state
        )

        state["validator_approved"] = validation.get("approved", True)
        state["validation_attempts"] = state.get("validation_attempts", 0) + 1

        if state["validator_approved"]:
            self.logger.log("Validator", "Ответ одобрен")
        else:
            self.logger.log("Validator", f"Ответ отклонен (попытка {state['validation_attempts']})")

        return state

    async def finalizer_node(self, state: InterviewState) -> InterviewState:
        self.logger.log("System", "Генерация финального отчета")

        conversation_text = "\n".join([f"{msg['role']}: {msg['content']}" for msg in state.get("conversation_history", [])])
        expert_analysis = state.get("expert_analysis", {})
        expert_summary = {
            "python_specialist": expert_analysis.get("python_specialist", {}),
            "fact_checker": expert_analysis.get("fact_checker", {}),
            "hr_agent": expert_analysis.get("hr_agent", {}),
            "internal_thoughts": state.get("internal_thoughts", [])
        }

        report = await self._call_llm_async(
            f"История интервью:\n{conversation_text}\n\n"
            f"Анализ экспертов:\n{json.dumps(expert_summary, ensure_ascii=False)}\n\n"
            f"Внутренние мысли системы (internal_thoughts):\n{json.dumps(state.get('internal_thoughts', []), ensure_ascii=False)}\n\n"
            f"Создай финальный отчет с Decision объектом, Knowledge Gaps и Roadmap.",
            FINAL_REPORT_PROMPT,
            state
        )

        if not isinstance(report, dict) or "raw_response" in report:
            self.logger.log("System", f"Ошибка парсинга отчета, пытаемся исправить...")
            raw_content = report.get("raw_response", str(report)) if isinstance(report, dict) else str(report)

            try:
                start_idx = raw_content.find("{")
                end_idx = raw_content.rfind("}")
                if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                    json_str = raw_content[start_idx:end_idx+1]
                    json_str = re.sub(r'```json\s*', '', json_str)
                    json_str = re.sub(r'```\s*', '', json_str)
                    json_str = json_str.strip()
                    report = json.loads(json_str)
                    self.logger.log("System", "Отчет успешно распарсен после повторной попытки")
                else:
                    raise ValueError("JSON не найден в ответе")
            except Exception as e:
                self.logger.log("System", f"Не удалось распарсить отчет: {e}. Создаем fallback отчет")
                report = {
                    "decision": {
                        "grade": "Junior",
                        "hiring_recommendation": "no_hire",
                        "recommendation_reason": "Ошибка генерации отчета. Требуется ручная проверка.",
                        "confidence_score": 0
                    },
                    "skills_matrix": {
                        "technical_skills": 0,
                        "communication": 0,
                        "problem_solving": 0,
                        "experience": 0,
                        "cultural_fit": 0,
                        "confirmed_skills": []
                    },
                    "knowledge_gaps": [],
                    "roadmap": {"immediate": [], "short_term": [], "long_term": []},
                    "summary": "Произошла ошибка при генерации отчета. Пожалуйста, проверьте логи."
                }

        if "decision" not in report:
            report["decision"] = {}
        if "skills_matrix" not in report:
            report["skills_matrix"] = {}
        if "knowledge_gaps" not in report:
            report["knowledge_gaps"] = []
        if "roadmap" not in report:
            report["roadmap"] = {}

        state["final_report"] = report
        state["is_complete"] = True
        self.logger.log("System", f"Финальный отчет создан. Grade: {report.get('decision', {}).get('grade', 'N/A')}")
        return state

    def should_continue_orchestrator(self, state: InterviewState) -> str:
        profile = state.get("candidate_profile", {})
        has_name = state.get("candidate_name") or profile.get("name")
        has_grade = state.get("candidate_grade") or profile.get("grade")
        has_info = has_name and has_grade and (state.get("candidate_experience") or profile.get("experience") or profile.get("position"))

        if not has_info:
            last_assistant_msg = ""
            for msg in reversed(state.get("conversation_history", [])):
                if msg.get("role") == "assistant":
                    last_assistant_msg = msg.get("content", "")
                    break
            if last_assistant_msg:
                return "wait"
            return "orchestrator"
        return "expert_pool"

    def should_continue_validation(self, state: InterviewState) -> str:
        if state.get("is_complete"):
            return "finalizer"
        if state.get("validator_approved"):
            return "continue"
        if state.get("validation_attempts", 0) >= settings.MAX_VALIDATION_ATTEMPTS:
            self.logger.log("Validator", "Достигнут лимит попыток валидации, продолжаем")
            return "continue"
        return "interviewer"

    def _build_graph(self) -> StateGraph:
        workflow = StateGraph(InterviewState)
        workflow.add_node("orchestrator", self.orchestrator_node)
        workflow.add_node("expert_pool", self.expert_pool_node)
        workflow.add_node("observer", self.observer_node)
        workflow.add_node("interviewer", self.interviewer_node)
        workflow.add_node("validator", self.validator_node)
        workflow.add_node("finalizer", self.finalizer_node)
        workflow.set_entry_point("orchestrator")

        workflow.add_conditional_edges(
            "orchestrator",
            self.should_continue_orchestrator,
            {"orchestrator": "orchestrator", "wait": END, "expert_pool": "expert_pool"}
        )

        workflow.add_edge("expert_pool", "observer")
        workflow.add_edge("observer", "interviewer")
        workflow.add_edge("interviewer", "validator")

        workflow.add_conditional_edges(
            "validator",
            self.should_continue_validation,
            {"continue": END, "interviewer": "interviewer", "finalizer": "finalizer"}
        )

        workflow.add_edge("finalizer", END)
        return workflow.compile()
