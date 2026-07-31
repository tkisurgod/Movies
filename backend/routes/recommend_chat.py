from typing import List, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.gemini_concierge import ChatResponse, HistoryMessage, concierge_chat
from services.session_store import create_session, delete_session, get_session

router = APIRouter()


class RecommendChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: Optional[str] = Field(
        default=None, description="User answer for the current profiling turn"
    )


class RecommendationPayload(BaseModel):
    title: str = ""
    movie_id: Optional[int] = None
    genres: str = ""
    overview: str = ""
    release_date: str = ""
    vote_average: float = 0.0
    runtime: Optional[int] = None
    match_score: float = 0.0
    match_source: str = "gemini"
    reason: str = ""


class RecommendChatResponse(BaseModel):
    session_id: str
    turn_count: int
    phase: Literal["profiling", "complete"]
    message: str
    questions_asked: int
    target_questions: int
    answers_received: int
    recommendation: Optional[RecommendationPayload] = None
    trigger_action: str = "CHAT"
    stream_url: str = ""


def _session_to_history(session) -> List[HistoryMessage]:
    history: List[HistoryMessage] = []
    for i, answer in enumerate(session.answers):
        if i < len(session.questions):
            history.append(HistoryMessage(role="assistant", content=session.questions[i]))
        history.append(HistoryMessage(role="user", content=answer))
    return history


def _chat_to_recommend_response(
    session_id: str,
    turn_count: int,
    answers_count: int,
    target: int,
    chat: ChatResponse,
) -> RecommendChatResponse:
    is_complete = chat.trigger_action == "AUTO_PLAY"
    recommendation = None
    if is_complete and chat.movie_id:
        movie_id = int(chat.movie_id)
        recommendation = RecommendationPayload(
            title=_title_from_message(chat.bot_message),
            movie_id=movie_id,
            reason=chat.bot_message,
        )

    return RecommendChatResponse(
        session_id=session_id,
        turn_count=turn_count,
        phase="complete" if is_complete else "profiling",
        message=chat.bot_message,
        questions_asked=answers_count,
        target_questions=target,
        answers_received=answers_count,
        recommendation=recommendation,
        trigger_action=chat.trigger_action,
        stream_url=chat.stream_url,
    )


def _title_from_message(message: str) -> str:
    marker = "pick: "
    lower = message.lower()
    if marker in lower:
        start = lower.index(marker) + len(marker)
        rest = message[start:]
        return rest.split(".")[0].strip()
    return ""


@router.post("/recommend-chat", response_model=RecommendChatResponse)
def recommend_chat(body: RecommendChatRequest) -> RecommendChatResponse:
    message = (body.message or "").strip()

    if not body.session_id:
        session = create_session(target_questions=5, questions=[])
        chat = concierge_chat("", [])
        if chat.trigger_action == "AUTO_PLAY":
            delete_session(session.session_id)
        return _chat_to_recommend_response(
            session.session_id, 0, 0, session.target_questions, chat
        )

    session = get_session(body.session_id)
    if session is None:
        raise HTTPException(
            status_code=404, detail="Session not found. Start a new chat."
        )

    if session.complete:
        raise HTTPException(
            status_code=400,
            detail="Session already completed. Start a new chat without session_id.",
        )

    if not message:
        raise HTTPException(
            status_code=400,
            detail="message is required when continuing a session.",
        )

    session.answers.append(message)
    session.turn_count += 1
    history = _session_to_history(session)
    chat = concierge_chat(message, history[:-1])

    if chat.trigger_action == "AUTO_PLAY":
        session.complete = True
        delete_session(session.session_id)

    return _chat_to_recommend_response(
        session.session_id,
        session.turn_count,
        len(session.answers),
        session.target_questions,
        chat,
    )
