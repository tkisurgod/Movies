import os
from typing import List, Optional

from pydantic import BaseModel, Field

from services.catalog import get_catalog_snippet
from services.movie_recommender import recommend_movie
from services.profiling import PROFILING_QUESTIONS

MIN_PROFILING_ANSWERS = 3


class HistoryMessage(BaseModel):
    role: str = Field(description="'user' or 'assistant'")
    content: str = ""


class ChatResponse(BaseModel):
    bot_message: str
    trigger_action: str = Field(description="'CHAT' or 'AUTO_PLAY'")
    movie_id: str = ""
    movie_title: str = ""
    stream_url: str = ""


def build_stream_url(movie_id: str, media_type: str = "movie") -> str:
    return f"https://vidlink.pro/{media_type}/{movie_id}?autoplay=1&mute=0"


def count_user_turns(history: List[HistoryMessage], message: str) -> int:
    turns = sum(1 for item in history if item.role.strip().lower() == "user")
    if message.strip():
        turns += 1
    return turns


def collect_user_answers(history: List[HistoryMessage], message: str) -> List[str]:
    answers = [
        item.content
        for item in history
        if item.role.strip().lower() == "user" and item.content.strip()
    ]
    if message.strip():
        answers.append(message.strip())
    return answers


def _build_system_instruction() -> str:
    catalog = get_catalog_snippet()
    return f"""You are an AI Movie Concierge for a streaming app.

Your job is to ask between 3 and 5 short profiling questions to learn the user's vibe
(mood, pacing, classic vs modern, who they are watching with, genres to avoid, etc.).

RULES:
1. While still profiling, set trigger_action to exactly "CHAT" and ask ONE question in bot_message.
2. Do NOT recommend a movie until you have asked at least {MIN_PROFILING_ANSWERS} profiling questions
   AND received meaningful answers in the conversation.
3. When ready to recommend, set trigger_action to exactly "AUTO_PLAY".
4. For AUTO_PLAY you MUST pick a movie from the catalog below and set movie_id to its numeric id string.
5. Set stream_url to: https://vidlink.pro/movie/<movie_id>?autoplay=1&mute=0
6. Never invent movie ids — only use ids listed in the catalog.
7. Keep bot_message warm and concise (1-3 sentences).

CATALOG (title | id | genres):
{catalog}
"""


def _build_gemini_contents(history: List[HistoryMessage], message: str):
    from google.genai import types

    contents = []
    for item in history:
        role = item.role.strip().lower()
        gemini_role = "user" if role == "user" else "model"
        if not item.content.strip():
            continue
        contents.append(
            types.Content(
                role=gemini_role,
                parts=[types.Part(text=item.content)],
            )
        )

    user_text = message.strip() or (
        "Start the concierge session. Greet the user briefly and ask your first profiling question."
    )
    contents.append(
        types.Content(role="user", parts=[types.Part(text=user_text)])
    )
    return contents


def _get_gemini_client():
    from google import genai

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if api_key:
        return genai.Client(api_key=api_key)
    return genai.Client()


def _call_gemini(history: List[HistoryMessage], message: str) -> ChatResponse:
    from google.genai import types

    client = _get_gemini_client()
    response = client.models.generate_content(
        model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        contents=_build_gemini_contents(history, message),
        config=types.GenerateContentConfig(
            system_instruction=_build_system_instruction(),
            response_mime_type="application/json",
            response_schema=ChatResponse,
        ),
    )
    return ChatResponse.model_validate_json(response.text)


def _fallback_response(
    history: List[HistoryMessage], message: str
) -> ChatResponse:
    answers = collect_user_answers(history, message)
    user_turns = len(answers)

    if user_turns < MIN_PROFILING_ANSWERS:
        question_index = min(user_turns, len(PROFILING_QUESTIONS) - 1)
        return ChatResponse(
            bot_message=PROFILING_QUESTIONS[question_index],
            trigger_action="CHAT",
        )

    movie = recommend_movie(answers)
    movie_id = str(movie["movie_id"]) if movie.get("movie_id") else ""
    stream_url = build_stream_url(movie_id) if movie_id else ""

    return ChatResponse(
        bot_message=(
            f"Based on your vibe, I found the perfect pick: {movie['title']}. "
            f"{movie['reason']} Starting playback now."
        ),
        trigger_action="AUTO_PLAY",
        movie_id=movie_id,
        movie_title=movie.get("title", ""),
        stream_url=stream_url,
    )


def _enforce_profiling_guard(
    parsed: ChatResponse,
    history: List[HistoryMessage],
    message: str,
) -> ChatResponse:
    user_turns = count_user_turns(history, message)

    if parsed.trigger_action == "AUTO_PLAY" and user_turns < MIN_PROFILING_ANSWERS:
        idx = min(user_turns, len(PROFILING_QUESTIONS) - 1)
        return ChatResponse(
            bot_message=(
                f"I need a bit more context before recommending. "
                f"{PROFILING_QUESTIONS[idx]}"
            ),
            trigger_action="CHAT",
        )
    return parsed


def _enrich_auto_play(
    parsed: ChatResponse,
    history: List[HistoryMessage],
    message: str,
) -> ChatResponse:
    if parsed.trigger_action != "AUTO_PLAY":
        return parsed

    movie_id = (parsed.movie_id or "").strip()
    if movie_id and movie_id.isdigit():
        parsed.stream_url = parsed.stream_url or build_stream_url(movie_id)
        parsed.movie_title = parsed.movie_title or _lookup_title(movie_id)
        return parsed

    answers = collect_user_answers(history, message)
    db_match = recommend_movie(answers) if answers else None

    if db_match and db_match.get("movie_id"):
        movie_id = str(db_match["movie_id"])
        parsed.movie_id = movie_id
        parsed.movie_title = db_match.get("title", "")
        parsed.stream_url = build_stream_url(movie_id)
        if not parsed.bot_message.strip():
            parsed.bot_message = (
                f"I found it: {db_match['title']}. Enjoy!"
            )
        return parsed

    for movie in _load_movies_from_recommender():
        title = movie.get("title", "")
        if title and title.lower() in parsed.bot_message.lower():
            movie_id = str(movie["id"])
            parsed.movie_id = movie_id
            parsed.movie_title = title
            parsed.stream_url = build_stream_url(movie_id)
            return parsed

    parsed.trigger_action = "CHAT"
    parsed.bot_message = (
        "I couldn't match that to our catalog. "
        "What mood or genre should we lean toward?"
    )
    return parsed


def _load_movies_from_recommender():
    from services.movie_recommender import _load_movies

    return _load_movies()


def _lookup_title(movie_id: str) -> str:
    for movie in _load_movies_from_recommender():
        if str(movie.get("id")) == str(movie_id):
            return str(movie.get("title", ""))
    return ""


def _attach_movie_title(parsed: ChatResponse) -> ChatResponse:
    if parsed.movie_id and not parsed.movie_title:
        parsed.movie_title = _lookup_title(parsed.movie_id)
    return parsed


def concierge_chat(message: str, history: Optional[List[HistoryMessage]] = None) -> ChatResponse:
    history = history or []
    use_gemini = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

    try:
        if use_gemini:
            parsed = _call_gemini(history, message)
        else:
            parsed = _fallback_response(history, message)
    except Exception:
        parsed = _fallback_response(history, message)

    parsed = _enforce_profiling_guard(parsed, history, message)
    parsed = _enrich_auto_play(parsed, history, message)
    parsed = _attach_movie_title(parsed)
    return parsed
