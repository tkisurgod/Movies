# Dataset

`movies.csv` (5.5 MB) and `credits.csv` (39 MB) are **not committed** — they're
public data and 44 MB is not worth carrying in git history. `.gitignore` excludes
`backend/database/*.csv`.

## Getting them

Both files come from the **TMDB 5000 Movie Dataset** on Kaggle:

<https://www.kaggle.com/datasets/tmdb/tmdb-movie-metadata>

Download and drop both files in this directory:

```
backend/database/movies.csv
backend/database/credits.csv
```

## Who reads them

| Consumer | What it needs |
|---|---|
| `services/movie_recommender.py` | Both, merged on `title`. Caps at the first 500 rows with a non-empty `overview`. |
| `services/catalog.py` | First 100 rows, formatted into the Gemini system prompt as `title \| id \| genres`. |
| `database/ingest_data.py` | Both, merged on `title`, first 500 rows → Chroma embeddings. |

Without these files the concierge still runs — `gemini_concierge.py` catches the
failure and falls back — but the catalog it grounds against will be empty, so
recommendations degrade badly. Fetch them before running the backend.

## chroma_db/

Also gitignored. Regenerate with:

```bash
cd backend
python database/ingest_data.py   # needs OPENAI_API_KEY
```

Note: this path is currently inactive. See **REVAMP.md §1.2** — the ingestion
has never been run, so every recommendation falls through to keyword matching,
and there's an ID-matching bug to fix first if you do enable it.
