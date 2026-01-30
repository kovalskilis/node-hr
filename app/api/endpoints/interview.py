import json
import logging
import uuid

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import Response

from app.api.deps import get_use_case

logger = logging.getLogger(__name__)
interview_router = APIRouter()


@interview_router.get("/test")
async def test_endpoint():
    logger.info("=== TEST ENDPOINT CALLED ===")
    return {"status": "ok", "message": "Router is working"}


@interview_router.get("/download-log")
async def download_interview_log(session_id: str = Query(..., description="Session ID")):
    try:
        logger.info(f"=== DOWNLOAD LOG ENDPOINT CALLED ===")
        logger.info(f"Download log requested for session: {session_id}")
        use_case = get_use_case()

        all_sessions = list(use_case.storage._sessions.keys())
        logger.info(f"Available sessions in storage: {all_sessions}")

        state = use_case.get_session(session_id)

        if not state:
            logger.warning(f"Session {session_id} not found. Available sessions: {all_sessions}")
            raise HTTPException(status_code=404, detail="Session not found")

        logger.info(f"Session {session_id} found, is_complete: {state.get('is_complete')}")

        logger_data = use_case.engine.logger.get_log_data()

        participant_name = (
            logger_data.get("participant_name") or
            state.get("candidate_name") or
            state.get("candidate_profile", {}).get("name", "Unknown")
        )

        turns = logger_data.get("turns", [])

        if not turns:
            conversation_history = state.get("conversation_history", [])
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

            user_messages = [msg for msg in conversation_history if msg.get("role") == "user"]
            assistant_messages = [msg for msg in conversation_history if msg.get("role") == "assistant"]

            for i, user_msg in enumerate(user_messages):
                turn = {
                    "turn_id": i + 1,
                    "user_message": user_msg.get("content", ""),
                    "agent_visible_message": assistant_messages[i].get("content", "") if i < len(assistant_messages) else "",
                    "internal_thoughts": internal_thoughts_str if i == len(user_messages) - 1 else ""
                }
                turns.append(turn)

        final_feedback = logger_data.get("final_feedback")
        if not final_feedback and state.get("is_complete"):
            final_report = state.get("final_report")
            if final_report:
                if isinstance(final_report, dict):
                    final_feedback = json.dumps(final_report, ensure_ascii=False, indent=2)
                else:
                    final_feedback = str(final_report)
            else:
                final_feedback = json.dumps({
                    "status": "completed",
                    "message": "Interview completed but final report not generated yet"
                }, ensure_ascii=False, indent=2)
        
        if not final_feedback:
            final_feedback = json.dumps({
                "status": "in_progress",
                "message": "Interview is still in progress"
            }, ensure_ascii=False, indent=2)

        interview_log = {
            "participant_name": participant_name,
            "turns": turns,
            "final_feedback": final_feedback
        }

        json_content = json.dumps(interview_log, ensure_ascii=False, indent=2)

        return Response(
            content=json_content,
            headers={
                "Content-Disposition": f'attachment; filename="interview_log_{session_id}.json"',
                "Content-Type": "application/json; charset=utf-8"
            },
            media_type="application/json"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in download_interview_log: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


async def websocket_interview(websocket: WebSocket):
    logger.info(f"WebSocket connection attempt from {websocket.client}")
    try:
        await websocket.accept()
        logger.info("WebSocket accepted successfully")
    except Exception as e:
        logger.error(f"WebSocket accept error: {e}")
        return

    session_id = None
    use_case = get_use_case()

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            action = message.get("action")

            if action == "start":
                session_id = message.get("session_id") or f"session_{uuid.uuid4().hex[:8]}"

                existing_state = use_case.get_session(session_id)
                if existing_state:
                    logger.info(f"Resuming existing session: {session_id}")
                    await websocket.send_text(json.dumps({
                        "type": "session_id",
                        "session_id": session_id
                    }, ensure_ascii=False))
                    await websocket.send_text(json.dumps({
                        "type": "session_resumed",
                        "session_id": session_id,
                        "state": existing_state
                    }, ensure_ascii=False))
                else:
                    logger.info(f"Starting new session: {session_id}")
                    await websocket.send_text(json.dumps({
                        "type": "session_id",
                        "session_id": session_id
                    }, ensure_ascii=False))

                    try:
                        initial_response = await use_case.start_interview(session_id)
                        metrics = initial_response.get("metrics", {})

                        await websocket.send_text(json.dumps({
                            "type": "interviewer",
                            "message": initial_response.get("interviewer_response", "Здравствуйте! Начнем интервью."),
                            "internal_thoughts": initial_response.get("internal_thoughts", []),
                            "metrics": {
                                "total_tokens": metrics.get("total_tokens", 0),
                                "avg_latency": round(metrics.get("avg_latency", 0), 0),
                                "validations": initial_response.get("validation_attempts", 0)
                            },
                            "state": initial_response
                        }, ensure_ascii=False))
                    except Exception as e:
                        await websocket.send_text(json.dumps({
                            "type": "error",
                            "message": f"Ошибка: {str(e)}"
                        }, ensure_ascii=False))

            elif action == "message":
                if not session_id:
                    session_id = message.get("session_id")
                    logger.info(f"Session ID from message: {session_id}")

                if not session_id:
                    logger.warning("No session_id provided in message")
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": "Сессия не найдена. Начните новое интервью."
                    }, ensure_ascii=False))
                    continue

                state_check = use_case.get_session(session_id)
                if not state_check:
                    logger.warning(f"Session {session_id} not found in storage")
                    all_sessions = list(use_case.storage._sessions.keys())
                    logger.warning(f"Available sessions: {all_sessions}")
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": "Сессия не найдена. Начните новое интервью."
                    }, ensure_ascii=False))
                    continue

                logger.info(f"Processing message for session: {session_id}")

                user_message = message.get("message", "")

                try:
                    await websocket.send_text(json.dumps({
                        "type": "status",
                        "status": "processing",
                        "message": "Анализирую ваш ответ..."
                    }, ensure_ascii=False))

                    await websocket.send_text(json.dumps({
                        "type": "status",
                        "status": "experts",
                        "message": "AI-HR отвечает..."
                    }, ensure_ascii=False))

                    new_state = await use_case.process_message(session_id, user_message)

                    await websocket.send_text(json.dumps({
                        "type": "status",
                        "status": "thinking",
                        "message": "Формулирую ответ..."
                    }, ensure_ascii=False))

                    if new_state.get("is_complete") or new_state.get("final_report"):
                        final_report = new_state.get("final_report", {})
                        logger.info(f"Final report generated: {type(final_report)}, keys: {final_report.keys() if isinstance(final_report, dict) else 'N/A'}")
                        metrics = new_state.get("metrics", {})
                        report_data = {
                            "type": "final_report",
                            "report": final_report,
                            "metrics": {
                                "total_tokens": metrics.get("total_tokens", 0),
                                "avg_latency": round(metrics.get("avg_latency", 0), 0),
                                "validations": new_state.get("validation_attempts", 0)
                            },
                            "state": new_state
                        }
                        logger.info(f"Sending final report, report keys: {final_report.keys() if isinstance(final_report, dict) else 'N/A'}")
                        await websocket.send_text(json.dumps(report_data, ensure_ascii=False))
                    else:
                        metrics = new_state.get("metrics", {})
                        await websocket.send_text(json.dumps({
                            "type": "interviewer",
                            "message": new_state.get("interviewer_response", ""),
                            "question": new_state.get("current_question", ""),
                            "internal_thoughts": new_state.get("internal_thoughts", []),
                            "expert_analysis": new_state.get("expert_analysis", {}),
                            "metrics": {
                                "total_tokens": metrics.get("total_tokens", 0),
                                "avg_latency": round(metrics.get("avg_latency", 0), 0),
                                "validations": new_state.get("validation_attempts", 0)
                            },
                            "state": new_state
                        }, ensure_ascii=False))
                except Exception as e:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": f"Ошибка обработки: {str(e)}"
                    }, ensure_ascii=False))

            elif action == "get_state":
                if session_id:
                    state = use_case.get_session(session_id)
                    if state:
                        await websocket.send_text(json.dumps({
                            "type": "state",
                            "state": state
                        }, ensure_ascii=False))

    except WebSocketDisconnect:
        if session_id:
            logger.info(f"WebSocket disconnected for session {session_id}, but session preserved")
