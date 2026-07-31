from typing import List

from services.movie_recommender import _load_movies, _parse_genres


def get_catalog_snippet(limit: int = 100) -> str:
    lines: List[str] = []
    for movie in _load_movies()[:limit]:
        genres = _parse_genres(movie.get("genres"))
        lines.append(
            f"- {movie.get('title')} | id: {movie.get('id')} | genres: {genres}"
        )
    return "\n".join(lines)
