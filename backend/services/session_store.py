import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ChatSession:
    session_id: str
    turn_count: int = 0
    target_questions: int = 3
    questions: List[str] = field(default_factory=list)
    answers: List[str] = field(default_factory=list)
    complete: bool = False

    @property
    def questions_asked(self) -> int:
        return len(self.answers)

    @property
    def profiling_done(self) -> bool:
        return self.questions_asked >= self.target_questions

    @property
    def can_recommend(self) -> bool:
        return self.questions_asked >= 3 and self.profiling_done


_sessions: Dict[str, ChatSession] = {}


def create_session(target_questions: int, questions: List[str]) -> ChatSession:
    session = ChatSession(
        session_id=str(uuid.uuid4()),
        target_questions=target_questions,
        questions=questions,
    )
    _sessions[session.session_id] = session
    return session


def get_session(session_id: str) -> Optional[ChatSession]:
    return _sessions.get(session_id)


def delete_session(session_id: str) -> None:
    _sessions.pop(session_id, None)
