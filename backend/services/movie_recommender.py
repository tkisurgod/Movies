import csv
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DATABASE_DIR = Path(__file__).resolve().parent.parent / "database"
CHROMA_DIR = DATABASE_DIR / "chroma_db"
MOVIES_CSV = DATABASE_DIR / "movies.csv"
CREDITS_CSV = DATABASE_DIR / "credits.csv"

_movies_cache: Optional[List[Dict[str, Any]]] = None
_chroma_db = None


def _parse_genres(raw: Any) -> str:
    try:
        genres_data = json.loads(raw)
        return ", ".join(g["name"] for g in genres_data)
    except (TypeError, json.JSONDecodeError, KeyError):
        return ""


def _tokenize(text: str) -> List[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 2]


def _load_movies() -> List[Dict[str, Any]]:
    global _movies_cache
    if _movies_cache is not None:
        return _movies_cache

    credits_by_title: Dict[str, dict] = {}
    with CREDITS_CSV.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            credits_by_title[row["title"]] = row

    movies: List[Dict[str, Any]] = []
    with MOVIES_CSV.open(encoding="utf-8", newline="") as f:
        for i, row in enumerate(csv.DictReader(f)):
            if i >= 500:
                break
            if not row.get("overview"):
                continue
            credit = credits_by_title.get(row["title"], {})
            merged = {**row, "cast": credit.get("cast", "")}
            movies.append(merged)

    _movies_cache = movies
    return movies


def _get_chroma_db():
    global _chroma_db
    if _chroma_db is not None:
        return _chroma_db

    if not CHROMA_DIR.exists() or not os.getenv("OPENAI_API_KEY"):
        return None

    try:
        from dotenv import load_dotenv
        from langchain_community.vectorstores import Chroma
        from langchain_openai import OpenAIEmbeddings

        load_dotenv()
        embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        _chroma_db = Chroma(
            persist_directory=str(CHROMA_DIR),
            embedding_function=embeddings,
        )
        return _chroma_db
    except Exception:
        return None


def _find_movie_by_title(title: str) -> Optional[Dict[str, Any]]:
    for movie in _load_movies():
        if movie.get("title") == title:
            return movie
    return None


def _recommend_with_chroma(profile_text: str) -> Optional[Dict[str, Any]]:
    db = _get_chroma_db()
    if db is None:
        return None

    results = db.similarity_search_with_score(profile_text, k=1)
    if not results:
        return None

    doc, score = results[0]
    title = doc.metadata.get("title", "")
    movie = _find_movie_by_title(title)
    if movie is None:
        return None

    return _format_recommendation(
        movie,
        match_score=float(max(0.0, 1.0 - score)),
        source="chroma",
    )


def _recommend_with_csv(profile_answers: List[str]) -> Dict[str, Any]:
    movies = _load_movies()
    query_tokens = _tokenize(" ".join(profile_answers))
    if not query_tokens:
        query_tokens = ["action", "adventure"]

    best_movie = movies[0]
    best_score = -1.0

    for movie in movies:
        genres = _parse_genres(movie.get("genres"))
        haystack = " ".join(
            filter(
                None,
                [
                    movie.get("title", ""),
                    movie.get("overview", ""),
                    genres,
                    movie.get("tagline", ""),
                ],
            )
        ).lower()
        hay_tokens = set(_tokenize(haystack))
        overlap = sum(1 for token in query_tokens if token in hay_tokens)
        popularity = float(movie.get("popularity") or 0)
        rating = float(movie.get("vote_average") or 0)
        score = overlap * 3.0 + (popularity / 200.0) + (rating / 10.0)

        if score > best_score:
            best_score = score
            best_movie = movie

    normalized = min(0.99, max(0.55, best_score / (len(query_tokens) * 3.0 + 5.0)))
    return _format_recommendation(best_movie, match_score=normalized, source="csv")


def _format_recommendation(
    movie: Dict[str, Any], match_score: float, source: str
) -> Dict[str, Any]:
    genres = _parse_genres(movie.get("genres"))
    title = movie.get("title", "Unknown")
    movie_id_raw = movie.get("id")
    movie_id = int(movie_id_raw) if movie_id_raw else None
    runtime_raw = movie.get("runtime")
    runtime = int(runtime_raw) if runtime_raw else None

    return {
        "title": title,
        "movie_id": movie_id,
        "genres": genres,
        "overview": (movie.get("overview") or "")[:400],
        "release_date": movie.get("release_date") or "",
        "vote_average": float(movie.get("vote_average") or 0),
        "runtime": runtime,
        "match_score": round(match_score, 3),
        "match_source": source,
        "reason": f"Best match for your {genres.lower() or 'movie'} mood profile.",
    }


def recommend_movie(profile_answers: List[str]) -> Dict[str, Any]:
    profile_text = ". ".join(profile_answers)
    chroma_result = _recommend_with_chroma(profile_text)
    if chroma_result is not None:
        return chroma_result
    return _recommend_with_csv(profile_answers)
