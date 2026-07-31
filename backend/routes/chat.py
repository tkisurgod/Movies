from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.gemini_concierge import ChatResponse, HistoryMessage, concierge_chat

router = APIRouter()


class ChatRequest(BaseModel):
    message: str = ""
    history: List[HistoryMessage] = Field(
        default_factory=list,
        description="Prior turns: role 'user' or 'assistant', content text",
    )


@router.post("/chat", response_model=ChatResponse)
def api_chat(data: ChatRequest) -> ChatResponse:
    try:
        return concierge_chat(data.message, data.history)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
