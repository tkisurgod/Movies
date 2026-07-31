import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes.chat import router as chat_router
from routes.recommend_chat import router as recommend_chat_router

load_dotenv()

app = FastAPI(title="Movies Recommendation API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router, prefix="/api")
app.include_router(recommend_chat_router, prefix="/api")


@app.get("/")
def health():
    chroma_ready = (Path(__file__).parent / "database" / "chroma_db").exists()
    return {
        "status": "ok",
        "service": "movies-recommendation-api",
        "chroma_db_ready": chroma_ready,
        "openai_configured": bool(os.getenv("OPENAI_API_KEY")),
        "gemini_configured": bool(
            os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        ),
    }
