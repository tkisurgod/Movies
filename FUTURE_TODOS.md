# Future implementations

Tracked improvements not yet built. Check items off as they ship.

---

## Concierge chat history (cloud sync)

- [ ] **MongoDB schema** — Add `conciergeSessions` array on `User` (mirror local shape: `id`, `movieTitle`, `movieId`, `streamUrl`, `endedAt`, `messages[]`).
- [ ] **`GET /api/user/concierge-sessions`** — Return sessions for the authenticated user (JWT / Bearer, same as watch history).
- [ ] **`POST /api/user/concierge-sessions`** — Append or upsert a session after `AUTO_PLAY` completes.
- [ ] **`DELETE /api/user/concierge-sessions/:id`** — Remove one session (optional: `DELETE` all for “clear history”).
- [ ] **Wire Express auth** — Connect `server.js` to MongoDB; mount routes under `/api/user/` (today only Python FastAPI + local `User.js` exist).
- [ ] **Frontend: save to API when logged in** — On `AUTO_PLAY`, call `POST` if `authToken` exists, else `localStorage` only.
- [ ] **Frontend: merge on login** — After successful login, fetch `GET /api/user/concierge-sessions`, merge with `conciergeChatSessions` in `localStorage` (dedupe by `id` or `movieId` + `endedAt`), write back local + optionally push local-only rows to server.
- [ ] **Frontend: load from API when logged in** — History panel reads merged list; prefer server as source of truth when online.
- [ ] **Offline / guest fallback** — Keep current `localStorage` behavior when not authenticated.

---

## Concierge UI polish

- [ ] **Delete single past pick** — Swipe or trash icon on a history row (local + API when synced).
- [ ] **Clear all past picks** — Button in history panel with confirm dialog.
- [ ] **New chat** — Explicit control to reset without closing the widget (clears in-progress thread, not saved history).
- [ ] **Align API port** — `CHAT_API_URL` in `index.html` vs uvicorn port (`8000` / `8001`) documented in README or env example.

---

## AI / recommendations backend

- [ ] **Run Chroma ingestion** — `python database/ingest_data.py` with `OPENAI_API_KEY`; verify `database/chroma_db` exists.
- [ ] **Ingestion metadata** — Ensure `movie_id` (and title) in vector metadata for all ingested docs (partially done in `ingest_data.py`).
- [ ] **Deploy FastAPI** — Host Python service (Render/Railway/Fly) so production frontend does not rely on `localhost`.
- [ ] **Proxy or single origin** — Optional: Express proxies `/api/chat` to Python to avoid CORS and split URLs.
- [ ] **Gemini env** — Document `GEMINI_API_KEY` in `.env.example` (no `set` prefix; no quotes unless required).

---

## Node / streaming backend

- [ ] **Auth routes on local Express** — `/api/auth/signup`, `verify`, `login` and user history if not only on Render.
- [ ] **Production `BACKEND_URL`** — Point frontend chat to deployed FastAPI or unified API gateway.

---

## Quality / ops

- [ ] **`.env.example`** — Template for `GEMINI_API_KEY`, `MONGODB_URI`, `JWT_SECRET`, `OPENAI_API_KEY`, `CORS_ORIGINS`.
- [ ] **Health check in CI** — Hit `/` and `/api/chat` smoke test on deploy.
- [ ] **Rate limiting** — On `/api/chat` to protect Gemini quota.
- [ ] **Session expiry** — Server-side in-memory sessions in `recommend_chat` (if still used) or document that only `/api/chat` + client history matter.

---

## Notes

| Storage | Scope | Status |
|---------|--------|--------|
| `localStorage.conciergeChatSessions` | Guest + offline | Done |
| MongoDB `conciergeSessions` | Logged-in, cross-device | Not started |
| `localStorage.watchHistory` | Guest watch list | Existing pattern to copy |

Reference implementation for merge-on-login: see `watchHistory` load/sync flow in `index.html` after login.
