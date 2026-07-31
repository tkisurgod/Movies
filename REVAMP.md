# REVAMP.md

Audit + revamp plan for **TK Entertainment** (`Movies`).
Written 2026-07-31 against `main` @ `756e40f` plus uncommitted working-tree changes to `index.html`.

Everything below was verified by reading the code and probing the live Render service. Where a claim is inferred rather than confirmed, it says so.

> ## Progress
>
> - **✅ Phase 0 — download cleanup** (2026-07-31). All 6 local steps done.
>   "Error loading" fixed, `server.js` boots again, `DEVELOPMENT_LOG.md` archived
>   to `docs/archive/`. Step 7 (Render redeploy) still pending — `/api/download`
>   is live in production until you push.
> - **🔄 Phase 3 — Supabase** (2026-07-31). Code complete for S1–S4, S8, S9.
>   Schema in `supabase/migrations/0001_init.sql`, setup steps in
>   `SUPABASE_SETUP.md`. **Unverified against a live project** — no credentials
>   yet. S5–S7 (playhead capture) not started.
> - ⬜ Phase 1 — Epic A (remaining P0 bugs). B7 and B8 were fixed as part of
>   Phase 3; B2, B3, B4, B5, B13 still open.
> - ⬜ Phase 2 — recommendations decision.

---

## 0. Where the project actually is

| Layer | Location | State |
|---|---|---|
| Frontend | `index.html` (2542 lines, single file, no build) | Live, functional, **one null-deref bug on every player open** |
| Concierge / recommendations | `backend/` FastAPI (Python) | Works locally; **not deployed** |
| Vector search (Chroma) | `backend/database/chroma_db` | **Never generated** — path does not exist |
| Auth + watch history | `backend/server.js` (Express) | **Does not run** — crashes at require; deployed copy has no auth routes |
| Download / scraper | deleted in `08507e7` | **Remnants in 4 files + still live in production** |

### Live probe results (Render, `https://movies-4myh.onrender.com`)

```
GET  /                    → 200  "Movies Backend is running without a database!"
POST /api/auth/login      → 404  (Express HTML error page)
POST /api/chat            → 404
GET  /api/download?url=…  → hangs, times out at 30s
```

**Three consequences worth stating plainly:**

1. **Auth is completely non-functional today.** The deployed backend is the same `server.js` in this repo — a health route and a download route, nothing else. `POST /api/auth/login` returns an Express HTML 404 page. The frontend does `await res.json()` on it (`index.html:1272`), which throws `Unexpected token '<'`, which surfaces to the user via `alert(err.message)`. Nobody has ever successfully signed in. This makes the Supabase migration (§4) a *repair*, not a *replacement*.
2. **The AI Concierge is dead in production.** `CHAT_API_URL` falls back to `BACKEND_URL` off-localhost (`index.html:1124-1126`), and that host 404s `/api/chat`.
3. **The download endpoint is still running in production** even though the local code was deleted. It hangs for ≥30s per request, which on Render's free tier means a request slot burning CPU on Puppeteer. See §2.

---

# 1. Recommendation system — status of completion

**Overall: ~65% complete. The end-to-end Gemini path works locally. The vector-search path was designed but never activated, a second parallel API was built and abandoned, and none of it is deployed.**

## 1.1 What is built and working

### The path the frontend actually uses: `POST /api/chat`

`index.html` → `callConciergeChat()` (`:2299`) → `backend/routes/chat.py` → `services/gemini_concierge.py::concierge_chat()`

This is a complete, reasonably well-built pipeline:

- **Structured output.** `_call_gemini()` (`gemini_concierge.py:104`) uses `google-genai` with `response_mime_type="application/json"` and `response_schema=ChatResponse`, so the model returns typed `{bot_message, trigger_action, movie_id, movie_title, stream_url}`. Good choice — no regex-parsing of prose.
- **Catalog grounding.** `_build_system_instruction()` (`:48`) injects the top 100 movies as `title | id | genres` and instructs the model never to invent IDs.
- **Profiling guard.** `_enforce_profiling_guard()` (`:149`) refuses `AUTO_PLAY` before `MIN_PROFILING_ANSWERS = 3` and re-asks a canned question instead. Prevents the model recommending on turn one.
- **Post-hoc repair.** `_enrich_auto_play()` (`:168`) is the strongest piece: if the model returns `AUTO_PLAY` without a usable numeric ID, it (a) falls back to `recommend_movie()` on the collected answers, (b) failing that, scans the catalog for a title mentioned in the bot's own prose, (c) failing that, downgrades to `CHAT` with a recovery message. Three layers of graceful degradation.
- **Full offline fallback.** If no Gemini key or any exception, `_fallback_response()` (`:120`) drives the whole conversation from `PROFILING_QUESTIONS` + the CSV recommender. The feature degrades instead of erroring.
- **Frontend integration is done.** Auto-play on `AUTO_PLAY` (`index.html:2368-2384`), session persistence to `localStorage.conciergeChatSessions`, a past-picks history panel with replay (`:2234-2267`), session restore (`:2278`). This is the bulk of the uncommitted 481-line diff.

### The recommender itself

`services/movie_recommender.py::recommend_movie()` — two-tier:
1. `_recommend_with_chroma()` — semantic search over the vector store.
2. `_recommend_with_csv()` — token-overlap scoring: `overlap * 3.0 + popularity/200 + rating/10`.

## 1.2 What is incomplete or broken

### ❌ Chroma vector search has never run — tier 1 is dead code

`backend/database/chroma_db/` does not exist. Confirmed:

```
$ ls backend/database/
credits.csv  ingest_data.py  movies.csv
```

`_get_chroma_db()` (`movie_recommender.py:59`) returns `None` when the directory is missing **or** `OPENAI_API_KEY` is unset. Both are true — `backend/.env` contains only `GEMINI_API_KEY`. So `_recommend_with_chroma()` always returns `None` and **every recommendation falls through to naive keyword overlap.**

This means the semantic quality you built the ingestion pipeline for (`ingest_data.py` builds a nice `Title / Genres / Cast / Plot` context string, `:46`) is not in play at all. `requirements.txt` carries `langchain`, `chromadb`, `langchain-openai`, `pandas` for a code path that never executes.

**Latent bug for when you do run it:** `_recommend_with_chroma()` matches on `doc.metadata["title"]` and then looks the title up via `_find_movie_by_title()`, which searches `_load_movies()` — the first 500 rows of `movies.csv` *filtered to rows with an overview*. But `ingest_data.py` takes the first 500 rows of `movies_df.merge(credits_df, on='title')`. A merge reorders and can drop/duplicate rows, so the two 500-row windows are **not the same set of movies**. Expect silent `None` returns (→ fallback to CSV) on titles that were ingested but fall outside the CSV window. `ingest_data.py:52` already writes `movie_id` into metadata — match on that instead of title and the problem disappears.

### ❌ A second, parallel recommendation API exists and is orphaned

`backend/routes/recommend_chat.py` (141 lines) + `backend/services/session_store.py` (46 lines) implement a stateful, server-session variant at `POST /api/recommend-chat`. **Nothing calls it.** The frontend only ever hits `/api/chat`. It is mounted in `main.py:24` and adds surface area for free.

It also has real bugs, so do not simply "switch to it":

- **Conversation history is silently truncated.** `create_session(target_questions=5, questions=[])` (`:100`) passes an empty questions list, and it is never populated. `_session_to_history()` (`:45`) guards with `if i < len(session.questions)`, which is always false — so **every assistant turn is dropped** and Gemini only ever sees a bare list of user answers with no idea what it asked. The model loses the thread.
- **Dead heuristic.** `_title_from_message()` (`:85`) scans for the literal marker `"pick: "`. Nothing in the system prompt asks the model to emit that string, so `RecommendationPayload.title` is always `""`.
- **Payload is 90% empty.** `RecommendationPayload` declares `genres`, `overview`, `release_date`, `vote_average`, `runtime`, `match_score` — `_chat_to_recommend_response()` (`:54`) populates only `title`, `movie_id`, `reason`.
- **Sessions leak.** `_sessions` is a module-level dict with no TTL and no eviction; entries are only removed on completion. Abandoned sessions live until process restart. Also means it cannot run multi-worker.

### ❌ Not deployed

FastAPI runs on localhost only. Production frontend points at the Node service, which 404s. Tracked in `FUTURE_TODOS.md:34` but not done.

### ⚠️ Port mismatch, still unresolved

`CHAT_API_URL` uses `http://localhost:8001` (`index.html:1125`); the error message tells the user to *"Start the Python API on port 8000"* (`index.html:2326`). Also flagged at `FUTURE_TODOS.md:26`.

### ⚠️ Two unused profiling helpers

`profiling.py` exports `pick_target_question_count()` and `build_question_sequence()`. Neither is imported anywhere — only the `PROFILING_QUESTIONS` list is used. Leftover from a deterministic-questionnaire design that Gemini replaced.

### ⚠️ Recommendations are movies-only

`build_stream_url()` (`gemini_concierge.py:26`) takes a `media_type` param but every caller uses the default `"movie"`. The frontend hardcodes `openPlayer(playId, 'movie', false)` (`:2374`). The catalog is a TMDB movies CSV. TV and Anime — two of your three top-level tabs — get no recommendations at all.

### ⚠️ Catalog is 500 rows of a static CSV

The main grid pulls live TMDB data across tens of thousands of titles; the concierge can only recommend from ~500 rows of a snapshot CSV. A user can be recommended a film, and separately browse a catalogue 100× larger. The two halves of the product don't share a universe.

## 1.3 Completion checklist

| Item | Status |
|---|---|
| Gemini structured-output chat | ✅ Done |
| System prompt + catalog grounding | ✅ Done |
| Profiling guard (min 3 questions) | ✅ Done |
| AUTO_PLAY → resolve movie ID → play | ✅ Done |
| Offline / no-key fallback | ✅ Done |
| Frontend chat UI + local history | ✅ Done (uncommitted) |
| CSV keyword recommender | ✅ Done |
| Chroma ingestion script | ✅ Written, ❌ never run |
| Chroma semantic search wired in | ⚠️ Coded, permanently inactive |
| Chroma ID-based lookup (not title) | ❌ Bug |
| `/api/recommend-chat` endpoint | ⚠️ Built, orphaned, buggy |
| Server-side session TTL | ❌ Leaks |
| Cloud sync of concierge history | ❌ Not started (`FUTURE_TODOS.md:7-17`) |
| TV / Anime recommendations | ❌ Not started |
| Deployment | ❌ Not started |
| Rate limiting on Gemini | ❌ Not started |

## 1.4 Recommended next moves

1. **Delete `routes/recommend_chat.py` + `services/session_store.py`**, unmount from `main.py:24`. One chat API, not two. (If you want the stateful design later, rebuild it on Supabase rows rather than an in-process dict.)
2. **Decide on Chroma.** Either run the ingestion and fix the ID-matching, or delete `_recommend_with_chroma()` and drop `langchain*` / `chromadb` / `pandas` from `requirements.txt`. Right now you carry the dependency weight with none of the benefit.
   - If you keep it: consider Supabase `pgvector` instead (§4). You're already adopting Supabase; a second datastore for 500 embeddings is not worth it, and `pgvector` gets you RLS and one connection string.
3. **Deploy the FastAPI service** and repoint `CHAT_API_URL`. Until then the flagship feature only works on your laptop.
4. **Widen the catalog** — swap the CSV for live TMDB queries, or ingest a much larger slice, so recommendations and browsing share a universe.
5. Delete `pick_target_question_count()` / `build_question_sequence()`.

---

# 2. Hanging download code

The download feature was removed in `08507e7`, which deleted `backend/download.js` and `backend/.puppeteerrc.cjs` and stripped the `<button id="download-btn">` from the markup. **The JavaScript that drives that button was not removed**, and neither was the server wiring.

## 2.1 🔴 CRITICAL — the leftover JS throws on every single player open

`index.html:1845`
```js
const downloadBtn = document.getElementById('download-btn');   // → null, element deleted in 08507e7
```

`index.html:1894-1895`, inside the TMDB details `.then()`:
```js
// Show download button and attach logic
downloadBtn.style.display = 'block';   // 💥 TypeError: Cannot read properties of null
```

The `.catch()` at `index.html:1972-1974` swallows it:
```js
.catch(() => {
    document.getElementById('movie-title-header').innerText = 'Error loading';
});
```

**Failure scenario:** user clicks any movie, TV show, or anime card → `openPlayer()` → TMDB fetch resolves → the modal is correctly populated (title, overview, poster, rating, runtime) and `addToHistory()` fires → then line 1895 throws → the `.catch()` overwrites the title bar with **"Error loading"**.

Playback itself still works, because `buildSourceButtons()` is called outside this promise (`:2023` for movies, `:2013` via `loadEpisodes` for TV). So the symptom is: **every title in the player header reads "Error loading", on every open, for every user, in production right now.** It looks like a broken app while being functionally fine.

**This is the single highest-value one-line fix in the codebase.**

## 2.2 Full inventory of remnants

| # | File | Lines | What | Action |
|---|---|---|---|---|
| 1 | `index.html` | `1845` | `const downloadBtn = getElementById('download-btn')` → null | **Delete** |
| 2 | `index.html` | `1894-1970` | Entire `downloadBtn.style.display` + `.onclick` handler: `/api/download` fetch, yt-dlp clipboard copy, `#EXTVLCOPT` m3u blob generation, three `alert()`/`prompt()` walkthroughs | **Delete** (77 lines) |
| 3 | `backend/server.js` | `3` | `const downloadRoute = require('./download');` — **`download.js` no longer exists, so `node server.js` crashes at startup with `MODULE_NOT_FOUND`** | **Delete** |
| 4 | `backend/server.js` | `8-9` | `app.use('/api/download', downloadRoute);` | **Delete** |
| 5 | `backend/package.json` | `5` | `"puppeteer": "^22.0.0"` — declared but **not present in `node_modules`** (already uninstalled) | **Delete** |
| 6 | `DEVELOPMENT_LOG.md` | all 57 lines | Phases 1–5 are entirely the scraper/anti-bot/VLC-spoofing story. The doc's stated purpose is `download.js`. | **Archive or delete** |
| 7 | `FUTURE_TODOS.md` | `42` | `- [ ] **Restore download.js**` — an open TODO to bring it *back* | **Delete** |
| 8 | Render deployment | live | `/api/download` still served; hangs ≥30s per request | **Redeploy after cleanup** |

Note on #3: `server.js` is presently **unrunnable locally**. If you ever intend to use the Express service for anything, this is a blocker, not cosmetic.

## 2.3 Related orphans found nearby

Not download code, but leftovers of the same era, worth sweeping in the same pass:

- `index.html:2163-2164` — `closeCustomAlert()` / `closeCustomConfirm()` are called on `Escape`. **Neither function is defined anywhere in the file.** Guarded by `typeof === 'function'` so they're silent no-ops. Remnant of a custom-modal system that replaced native alerts — see §3, that system is still worth building.
- `backend/User.js` — a Mongoose `User` + `HistorySchema` model. **Nothing imports it.** Superseded by §4.
- `backend/node_modules/` contains `mongoose`, `bcryptjs`, `jsonwebtoken`, `nodemailer` — the full auth stack — but `backend/package.json` declares only `cors`, `express`, `puppeteer`. The dependency manifest and the installed tree disagree; the auth server code that used them was never committed.
- `backend/node_modules/` is **untracked and not gitignored** (`backend/.gitignore` contains only `.env`). Add `node_modules/`.

## 2.4 Cleanup order

```
1. index.html      — delete lines 1845 and 1894-1970          ← fixes "Error loading" immediately
2. backend/server.js  — delete lines 3, 8-9                    ← makes the Express service bootable
3. backend/package.json — drop puppeteer
4. backend/.gitignore   — add node_modules/
5. FUTURE_TODOS.md   — drop line 42
6. DEVELOPMENT_LOG.md — archive to docs/archive/ or delete
7. Redeploy Render so /api/download stops answering
```

---

# 3. UI — breaking points and revamp story points

The app looks good in screenshots. It breaks under three pressures: **wide viewports**, **narrow viewports**, and **time-on-page**. Below, "breaking point" means a confirmed defect, not a taste preference.

## 3.1 🔴 P0 — confirmed functional breaks

### B1. Player title bar always reads "Error loading"
`index.html:1895` → `:1972`. See §2.1. **1 line to fix.**

### B2. The auto-carousel scrolls the wrong element
`loadCarousel()` (`:1401`), `updateIndicatorsOnScroll()` (`:1429`) and `createIndicators()` (`:1452`) all do:
```js
const scrollContainer = document.querySelector('.card-scroll');
```
`.card-scroll` matches **two** elements, and `#continue-watching-scroll` (`:933`) appears in the DOM **before** `#latest-carousel` (`:943`). `querySelector` returns the first match — always Continue Watching, even while it's `display:none`.

**Failure scenario:** a returning user with watch history opens the site. The "NOW PLAYING · Auto Revolving" row never moves; the *Continue Watching* row auto-scrolls itself every 3.5s instead. The indicator dots under NOW PLAYING track the Continue Watching scroll offset. Clicking a dot scrolls Continue Watching. The headline feature of the homepage is inert. Fix: `getElementById('latest-carousel')`.

### B3. Carousel accelerates over time (listener + interval leak)
`startAutoCarousel()` (`:1410-1426`) attaches a **new** `mouseenter`/`mouseleave` pair to `#carousel-wrapper` on every call — and `mouseleave` calls `startAutoCarousel()` again:
```js
wrapper.addEventListener('mouseenter', () => clearInterval(autoCarouselInterval));
wrapper.addEventListener('mouseleave', () => startAutoCarousel(container));
```
After *n* hovers, `mouseleave` fires *n* handlers → *n* new `setInterval`s created, but only the last ID is stored in `autoCarouselInterval`, so `clearInterval` can only ever cancel one. Orphaned intervals accumulate geometrically.

**Failure scenario:** user hovers the carousel five times over a minute. Scrolling becomes visibly jittery, then runaway — multiple intervals each firing `scrollBy` every 3.5s. Fix: attach the listeners once, outside the function, or use `{ once: true }` semantics with a guard.

### B4. Pagination silently discards the search query
`prevBtn` / `nextBtn` (`:1637-1638`) unconditionally call `loadGridContent()`. `searchContent()` reads `currentPage` but is never re-invoked.

**Failure scenario:** user searches "Dune", gets page 1 of results, clicks `›` — the grid replaces the search results with generic popularity-sorted discover content while the search box still shows "Dune". Fix: route paging through a dispatcher that checks whether a query is active.

### B5. Chat widget overflows the viewport on mobile
`.chatbot-window` (`:690-704`) is `width: 350px; height: 500px; bottom: 90px; right: 20px` with **no override in the `@media (max-width: 600px)` block** (`:653-666`).

**Failure scenario:** on a 360px-wide phone, 350 + 20 = 370px > 360 → horizontal overflow, and 500 + 90 = 590px exceeds the visible area on short viewports so the input row is off-screen. The AI Concierge — the product's differentiator — is unusable on the majority device class. Fix: `width: min(350px, calc(100vw - 2rem)); height: min(500px, calc(100dvh - 120px));`

### B6. Auth surfaces a JSON parse error to users
Covered in §0. `res.json()` on an HTML 404 → `alert("Unexpected token '<' …")`. Resolved by §4.

### B7. Crash if `authToken` outlives `userEmail`
`updateAuthUI()` (`:1192`):
```js
authBtn.innerHTML = `… <span>${userEmail.split('@')[0]}</span>`;
```
No null guard. Both keys are written together in `finishLogin()`, but a partially-cleared `localStorage` (browser storage pressure, manual clearing, extension) leaves `authToken` set and `userEmail` null → `TypeError` at module init, **before the IIFE finishes** → the entire app fails to boot (blank page, no grid, no carousel).

### B8. History removal doesn't sync; history vanishes on logout
- `removeFromHistory()` (`:1780-1784`) writes `localStorage` only — **no `DELETE` to the backend**, even when `authToken` is set. Removed items return on next refresh/login.
- `addToHistory()` (`:1767-1776`) writes to the backend **or** `localStorage`, never both. Log out → `updateAuthUI()` reloads from `localStorage`, which has no server-side entries → Continue Watching empties.

Both dissolve under §4's single source of truth.

## 3.2 🟠 P1 — layout, performance, robustness

### B9. Sticky offsets are hardcoded to a variable-height header
`.filters { top: 70px }` (`:97`); mobile `.filters { top: 112px }` (`:657`). The header is `flex-wrap: wrap` with content-sized children (`:29-42`), and `#search-container` moves to `order: 3; flex-basis: 100%` below 600px (`:656`). Header height is therefore fluid — long titles, wrapped rows, and font-size differences all shift it. At any width where actual height ≠ 70/112px, the filter bar either overlaps the header or leaves a gap. Fix: `position: sticky` on a shared wrapper, or a `--header-h` custom property set from a `ResizeObserver`.

### B10. The gold shimmer costs a style recalc every frame, forever
`index.html:1100-1117` — an unconditional `requestAnimationFrame` loop writing **six** CSS custom properties on `document.documentElement` at ~60fps. Because they're `:root` variables consumed across the whole stylesheet, each write invalidates style for the entire document. It never stops, never pauses when the tab is hidden, and **ignores `prefers-reduced-motion`**. On a phone this is a measurable battery cost for an effect most users won't consciously notice. Fix: gate on `prefers-reduced-motion`, throttle to ~10fps, and pause on `visibilitychange`.

### B11. Fixed-pixel poster heights distort artwork
`.movie-poster { height: 200px }` (`:351`), `.slide-poster { height: 240px }` (`:230`), mobile `200px` (`:659`), with `object-fit: cover`. Grid columns are `minmax(150px, 1fr)` (`:333`) so card width is fluid while height is frozen → the crop ratio changes with viewport width and posters are cropped inconsistently. Fix: `aspect-ratio: 2 / 3; height: auto;`

### B12. The carousel is built for phones and breaks on desktop
`.slide-card { flex: 0 0 calc(94% - 1rem); max-width: 460px }` (`:215-216`). On a 1920px display each card is capped at 460px inside a full-width scroller — you see ~1.2 cards with acres of dead space, in a component whose entire purpose is to show a rotating selection. Fix: responsive `flex-basis` via `clamp()` or a `repeat(auto-fill, …)` grid.

### B13. `via.placeholder.com` is used for every missing image
Five call sites: `:1469, :1477, :1558, :1728, :1877`. That service is unreliable/defunct — missing posters render as broken-image icons plus a failed third-party request. Fix: an inline SVG data-URI placeholder. Zero network, always works, themeable.

### B14. z-index has no scale, and the chat window loses
| Layer | z-index | Line |
|---|---|---|
| header | 1000 | `:38` |
| filters | 999 | `:97` |
| genre dropdown menu | 1001 | `:314` |
| chatbot button | 999 | `:684` |
| chatbot window | 1000 | `:701` |
| movie modal | 2000 | `:407` |
| auth modal | 2001 | `:617` |

The chat window (1000) sits **below** the genre dropdown (1001) and **level with** the sticky header — an open dropdown overlaps the concierge. Fix: a named scale (`--z-base/sticky/dropdown/overlay/modal`).

### B15. Ad-blocker monkey-patches DOM prototypes globally
`index.html:2513-2525` replaces `Element.prototype.appendChild` and `Element.prototype.insertBefore` for the whole document. Combined with `blockedPatterns` (`:2416-2425`) using bare **substring** matching on tokens as short as `'ad'`, `'pop'`, `'click'`, `'pixel'`, `'delivery'`. `'ad'` is a substring of `download`, `upload`, `loading`, `thread`, `adventure`, `broadcast` — and of arbitrary hashes in generated URLs.

I did **not** confirm a specific current false-positive breakage (the MutationObserver only inspects directly-added nodes, so the YouTube trailer iframes nested inside carousel cards slip past it). But this is a loaded gun: any future code that appends a script or `position: fixed` iframe, or loads a URL whose random ID happens to contain `ad`, will be silently killed with only a `console.warn`. Prototype patching also breaks third-party libraries you may adopt later. Fix: word-boundary regexes at minimum; ideally drop the prototype patches and keep only the `window.open` guard and the MutationObserver.

### B16. Skip Intro / Skip Outro / Next Episode are pure guesswork
`setupSkipIntro()` (`:1695`) shows the button 3s after load; `setupSkipOutro()` (`:1707`) at exactly 120s. Neither has any connection to real playback position — they can't, because the player is a cross-origin iframe (see §4.4). Worse, the skip action does:
```js
player.src = currentSrc + '&start=90';   // :1701
```
which **reloads the entire iframe**, losing all state, and `start=` is not a parameter most of these providers honour. So the button visibly restarts the video rather than skipping. This is the same technical constraint as §4 and should be solved by the same mechanism.

### B17. `innerHTML` with unescaped TMDB strings
`createCard()` (`:1564`) interpolates `title` into both markup and `alt="${title}"`. A title containing `"` breaks the attribute; a title containing markup injects it. TMDB is a semi-trusted source and this is low-severity, but `renderConciergeHistoryList()` (`:2253-2254`) already does it correctly with `textContent` — the codebase is inconsistent with itself.

## 3.3 🟡 P2 — polish, accessibility, structure

- **Native `alert`/`confirm`/`prompt` ×8** — including the logout confirm (`:1206`) and every auth error (`:1280`). Blocking, unstyled, unbrandable, and on iOS shows the origin URL. The stub calls at `:2163-2164` show a custom system was planned.
- **`maximum-scale=1` in the viewport meta** (`:6`) blocks pinch-zoom — a WCAG 1.4.4 failure.
- **No focus-visible styling anywhere.** Keyboard users cannot see where they are. `.type-btn`, `.source-btn`, `.genre-option`, `.indicator-dot`, `.movie-card` are all click-only.
- **Icon-only buttons have no accessible name** — `#fullscreen-toggle` (`:897`), `#refresh-player` (`:974`), `#back-btn` (`:971`), `#chat-close` (`:1081`) are bare `<i>` glyphs. Add `aria-label`.
- **Modals aren't dialogs.** `#movie-modal` / `#auth-modal` are `<div>`s toggled via `style.display`. No `role="dialog"`, no `aria-modal`, no focus trap, no focus restore. `Escape` handles the movie and auth modals (`:2148-2166`) but **not the chat window**.
- **Interactive `<div>`s** — `.genre-dropdown-button` (`:908`), `.genre-option`, `.indicator-dot`, `#skip-intro-btn` (`:982`), `.history-remove-btn` (`:1738`), `.chatbot-btn` (`:1070`) are all divs. Not focusable, not Enter/Space activatable, not announced.
- **No loading skeletons** — a centred spinner replaces the whole grid (`:1488`), so the layout collapses and re-expands on every page change.
- **No empty/error design** — errors are raw red text (`:1514`, `:1536`).
- **Colour contrast** — `#888`/`#666` body text on `#0a0a0a`–`#111` backgrounds (`:772`, `:802`, `:1049`) falls below 4.5:1.
- **Branding is inconsistent post-rebrand** — `<title>` says "TK IS GOD · Futuristic Streaming" (`:5`), the header says "TK ENTERTAINMENT" (`:891`).
- **Logo click does `window.location.reload()`** (`:1597-1599`) — a full network round-trip to return home.
- **TMDB API key + read token hardcoded in client JS** (`:1119-1120`). Public-repo-visible. TMDB keys are low-severity by design, but they should still move behind your API.
- **Continue Watching shows no progress** — just a poster and `"Movie"` or `"S1 E3"` (`:1731-1735`). No bar, no percentage, no "23 min left".
- **Structural:** one 2542-line `index.html`. ~880 lines of CSS with no design tokens beyond the gold ramp; every value is a magic number. All JS in two IIFEs sharing module-scope mutable state (`currentModalId`, `currentSeason`, `chatBusy`, …). No build step, no components, no tests, no linting. **This is what makes every fix above cost more than it should**, and it's the main argument for the revamp.

## 3.4 Story points

Fibonacci. 1 pt ≈ half a day for one developer familiar with the code.

### Epic A — Stop the bleeding (P0) · **13 pts**
| Story | Pts |
|---|---|
| A1. Delete download remnants; fix "Error loading" (§2.1) | 1 |
| A2. Carousel targets `#latest-carousel`, not first `.card-scroll` (B2) | 1 |
| A3. Fix listener/interval leak in `startAutoCarousel` (B3) | 2 |
| A4. Pagination respects active search (B4) | 2 |
| A5. Responsive chat window (B5) | 2 |
| A6. Null-guard `updateAuthUI`; make history read/write symmetric (B7, B8) | 3 |
| A7. Inline-SVG placeholders replacing `via.placeholder.com` (B13) | 2 |

*Ship A on its own. It's ~2 days and removes every user-visible defect without touching architecture.*

### Epic B — Design system foundation · **21 pts**
| Story | Pts |
|---|---|
| B1. Token layer: colour/space/radius/type/z-index/motion scales; keep gold as one accent token | 5 |
| B2. Split `index.html` → `index.html` + `styles/` + `js/` ES modules (no framework, no build) | 8 |
| B3. Fluid header/filter sticky with `--header-h` (B9) | 3 |
| B4. `aspect-ratio` posters + responsive carousel sizing (B11, B12) | 3 |
| B5. Motion pass: gate shimmer on `prefers-reduced-motion`, throttle, pause when hidden (B10) | 2 |

### Epic C — Component & interaction layer · **21 pts**
| Story | Pts |
|---|---|
| C1. Toast + dialog primitives; replace all 8 native `alert`/`confirm`/`prompt`; wire the `closeCustomAlert` stubs | 5 |
| C2. Accessible modal shell: `role="dialog"`, focus trap, focus restore, Escape — applied to player, auth, chat | 5 |
| C3. Semantic buttons + `aria-label` + `:focus-visible` across all controls | 5 |
| C4. Skeleton loaders for grid, carousel, modal | 3 |
| C5. Designed empty + error states | 3 |

### Epic D — Continue Watching UI · **13 pts** *(depends on §4)*
| Story | Pts |
|---|---|
| D1. Progress bar overlay + "23 min left" / "S2 E4 · 12 min left" on cards | 3 |
| D2. Resume-vs-restart affordance in the player modal | 3 |
| D3. Cross-device sync states (syncing / offline / conflict) | 3 |
| D4. Playback-accurate Skip Intro/Outro/Next Episode replacing the timers (B16) | 4 |

### Epic E — Hardening · **13 pts**
| Story | Pts |
|---|---|
| E1. `textContent` / escaping audit; kill unsafe `innerHTML` (B17) | 3 |
| E2. Rewrite ad-blocker: word-boundary matching, drop prototype patches (B15) | 5 |
| E3. Move TMDB calls behind your API; remove client-side keys | 3 |
| E4. Contrast pass to WCAG AA; remove `maximum-scale=1` | 2 |

**Total: 81 points.** Epic A alone (13) fixes everything a user would report as a bug.

### Suggested sequence
```
A ──► B ──► C ──► E
       └──► §4 (Supabase) ──► D
```

---

# 4. Supabase: registration + frame-accurate Continue Watching

## 4.1 Why this is a repair, not a migration

There is nothing to migrate *from*. The deployed backend has no auth routes and no database ("*running without a database!*"). `User.js` is an uncommitted, unimported Mongoose model. **Zero users exist.** No migration, no dual-write, no cutover — you are implementing auth for the first time. That makes this materially cheaper than it looks.

Supabase gives you, in one service: Postgres, auth (email/password, magic link, OAuth, email verification, password reset — replacing the hand-rolled nodemailer 6-digit-code flow that was never finished), row-level security, auto-generated REST, realtime subscriptions (for cross-device progress sync), and `pgvector` (which can absorb §1's Chroma store).

## 4.2 Schema

```sql
-- ── profiles ──────────────────────────────────────────────
create table public.profiles (
  id           uuid primary key references auth.users on delete cascade,
  display_name text,
  avatar_url   text,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

alter table public.profiles enable row level security;
create policy "own profile: read"   on public.profiles for select using (auth.uid() = id);
create policy "own profile: write"  on public.profiles for update using (auth.uid() = id);

-- auto-create a profile row on signup
create function public.handle_new_user() returns trigger
  language plpgsql security definer set search_path = '' as $$
begin
  insert into public.profiles (id, display_name)
  values (new.id, split_part(new.email, '@', 1));
  return new;
end; $$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();


-- ── watch_progress ────────────────────────────────────────
create table public.watch_progress (
  user_id          uuid not null references auth.users on delete cascade,
  tmdb_id          integer not null,
  media_type       text    not null check (media_type in ('movie','tv')),
  season           integer not null default 0,   -- 0 for movies
  episode          integer not null default 0,   -- 0 for movies
  is_anime         boolean not null default false,

  position_seconds numeric not null default 0,
  duration_seconds numeric,
  progress_pct     numeric generated always as (
                     case when duration_seconds > 0
                       then least(100, round((position_seconds / duration_seconds) * 100, 2))
                       else 0 end
                   ) stored,
  completed        boolean not null default false,

  title            text,
  poster_path      text,
  source           text,          -- which provider reported this
  fidelity         text not null default 'coarse'
                     check (fidelity in ('exact','coarse','none')),

  updated_at       timestamptz not null default now(),

  primary key (user_id, tmdb_id, media_type, season, episode)
);

create index watch_progress_recent
  on public.watch_progress (user_id, updated_at desc);

alter table public.watch_progress enable row level security;
create policy "own progress" on public.watch_progress
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);


-- ── concierge_sessions (absorbs FUTURE_TODOS.md §1) ───────
create table public.concierge_sessions (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references auth.users on delete cascade,
  movie_id    integer,
  movie_title text,
  stream_url  text,
  messages    jsonb not null default '[]'::jsonb,
  ended_at    timestamptz not null default now()
);

alter table public.concierge_sessions enable row level security;
create policy "own sessions" on public.concierge_sessions
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
```

**Design notes**
- `season`/`episode` default to `0` rather than `NULL` so they participate in the primary key — Postgres treats `NULL`s as distinct, which would let duplicate movie rows accumulate.
- Per-episode rows (not per-show) so a user can be mid-way through S1E4 and S3E2 independently. "Continue Watching" is a `distinct on (tmdb_id)` over `updated_at desc`.
- `fidelity` records *how* the position was obtained — the UI must not promise "resume at 42:17" when the number is a wall-clock estimate. See §4.4.
- `progress_pct` is a generated column, so the UI never computes it.

## 4.3 Auth wiring

Replace `index.html:1236-1314` (the `authForm.onsubmit` + `finishLogin` + `loadBackendHistory` block) with the Supabase JS client.

```js
import { createClient } from '@supabase/supabase-js';
const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

// signup — Supabase sends the verification email; delete the 6-digit code UI
const { data, error } = await supabase.auth.signUp({
  email, password,
  options: { emailRedirectTo: `${location.origin}/index.html` }
});

// login
const { data, error } = await supabase.auth.signInWithPassword({ email, password });

// session restored automatically on load; replaces the localStorage token dance
supabase.auth.onAuthStateChange((event, session) => {
  currentUser = session?.user ?? null;
  updateAuthUI();
  syncWatchProgress();
});
```

Publishing the anon key in client JS is correct and intended — RLS is the security boundary, not key secrecy. Which means **the RLS policies above are load-bearing; don't skip them.**

Frontend changes:
- Delete `#code-group` (`:1058-1060`) and the `authMode = 'verify'` branch (`:1260-1268`) — Supabase handles verification via emailed link.
- Delete `authToken` / `userEmail` localStorage handling (`:1153-1154`, `:1207-1210`, `:1294-1295`); use `supabase.auth.getSession()`.
- Fix the fragile `switch-auth-mode` re-binding (`:1217-1234`) — it clobbers `#auth-switch-text` with `innerHTML` and then re-reads `.onclick` off the now-detached original node. It works by accident. Rebuild with `hidden` toggles.
- Add password reset and OAuth — both are ~5 lines each once the client is in.

## 4.4 Accurate Continue Watching — the honest constraint

**This is the part that determines whether the feature is real, so read it before estimating.**

Your player is a third-party cross-origin `<iframe>` (`buildSourceButtons`, `:1807-1814`: vidlink.pro, vidsrc.xyz, 2embed.cc, multiembed.mov, vidsrc.net, embed.su). The browser's same-origin policy means **you cannot read `currentTime` from it.** No amount of JS gets you the playhead. The only channel is a `postMessage` API that the provider chooses to expose.

Equally: even if you *know* the position, **seeking back to it requires the provider to accept a start-time parameter**. Most don't — which is exactly why the existing Skip Intro appends `&start=90` and just reloads the video (B16).

So "resume from exactly where they left off" is **provider-dependent, not implementable uniformly.** Three tiers:

### Tier 1 — `exact` · postMessage-capable providers
VidLink is the one source in your current list that advertises a `postMessage` progress API. **Verify the current event name and payload shape against VidLink's own docs before building on it** — third-party embed APIs change without notice and I have not run this against the live provider.

```js
window.addEventListener('message', (event) => {
  // MUST validate origin — this is an untrusted cross-origin channel
  if (event.origin !== 'https://vidlink.pro') return;

  const payload = event.data;
  if (!payload || payload.type !== 'MEDIA_DATA') return;

  // shape per provider docs; treat defensively
  const { currentTime, duration } = extractProgress(payload);
  if (!Number.isFinite(currentTime) || !Number.isFinite(duration)) return;

  queueProgressWrite({
    position_seconds: currentTime,
    duration_seconds: duration,
    source: 'vidlink',
    fidelity: 'exact',
  });
});
```

Resume: reopen with the provider's documented start parameter. If they don't have one, fall back to Tier 2's UX.

### Tier 2 — `coarse` · everything else (the realistic default)
No progress channel. Approximate with a wall-clock heartbeat: start a timer when the iframe loads, accumulate elapsed seconds, pause on `visibilitychange` and on window blur, write every ~15s and on `beforeunload`.

This is genuinely approximate — it counts time-with-tab-open, not time-played. It over-counts if the user pauses, under-counts nothing. **Do not present it as an exact timestamp.** Instead:
- Show a progress bar (approximate position is fine for a bar).
- For TV, restore the **exact season and episode** — that part is fully reliable and is most of the perceived value.
- Offer "Resume (about 42 min in)" rather than "Resume from 42:17", and always offer "Start over".

### Tier 3 — `none` · self-hosted player
Resolve the stream yourself and render it in your own `<video>` + HLS.js. Total control: exact position, real seeking, real Skip Intro, subtitle control, no ads.

**But this is precisely the scraping problem you just deleted** (`DEVELOPMENT_LOG.md` Phases 1–5 document five rounds of losing that fight — bot detection, nested iframes, IP-locking, popup focus-stealing). Recommend against reopening it.

### Recommended approach
Build **Tier 2 for all sources**, plus **Tier 1 for VidLink** (already the default source at index 0, `:1808`). Track which you got via `fidelity`, and let the UI's copy follow the column. That gives honest, useful resume across every provider today, and genuinely exact resume on the default one — with a clean upgrade path as more providers expose progress APIs.

### Write strategy
```js
// debounce to protect quota: at most 1 write / 15s / title, plus a flush
const flushProgress = debounce(upsertProgress, 15_000);

document.addEventListener('visibilitychange', () => {
  if (document.hidden) upsertProgress.flush();
});
window.addEventListener('pagehide', () => {
  navigator.sendBeacon(SUPABASE_REST_URL, buildBeaconPayload());  // survives tab close
});

async function upsertProgress(row) {
  await supabase.from('watch_progress').upsert(row, {
    onConflict: 'user_id,tmdb_id,media_type,season,episode'
  });
}
```

Use `sendBeacon` for the unload path — a normal `fetch` is cancelled when the tab closes, which is the single most common moment a user stops watching.

### Guest mode
Keep `localStorage` as the anonymous store, unchanged in shape. On sign-in, upsert local rows into Supabase (server row wins on `updated_at`), then clear local. Preserves the existing guest experience and fixes B8's asymmetry — the DB becomes the single source of truth when authenticated.

## 4.5 Story points — Supabase epic · **34 pts**

| Story | Pts |
|---|---|
| S1. Supabase project, schema, RLS policies, `handle_new_user` trigger | 3 |
| S2. Client integration + `onAuthStateChange` session handling | 3 |
| S3. Rebuild auth modal: signup / login / verify-by-link / password reset; delete the 6-digit code flow | 5 |
| S4. OAuth providers (Google at minimum) | 2 |
| S5. `watch_progress` read/write layer w/ debounce + `sendBeacon` | 5 |
| S6. Tier-1 VidLink `postMessage` listener w/ origin validation (**spike first — verify the API exists as documented**) | 5 |
| S7. Tier-2 wall-clock heartbeat w/ visibility + blur pausing | 3 |
| S8. Guest → account merge on first sign-in | 3 |
| S9. Migrate concierge history from `localStorage` to `concierge_sessions` (closes `FUTURE_TODOS.md:7-17`) | 3 |
| S10. Realtime cross-device progress sync | 2 |

**S6 is the risk.** Time-box a spike: open a VidLink embed, log every `message` event, confirm the payload shape. If it doesn't deliver, Tier 2 covers everything and you lose only exact-second resume — plan the UI copy so that outcome is not a regression.

## 4.6 What gets deleted

- `backend/User.js` — Mongoose model, unimported, superseded.
- `backend/server.js` — after the download routes go (§2), only a health check remains. Delete the Express service entirely; Supabase + FastAPI cover everything.
- `mongoose`, `bcryptjs`, `jsonwebtoken`, `nodemailer` from `backend/node_modules`.
- `FUTURE_TODOS.md:9-13, 43-44` — the MongoDB/Express auth plan, now obsolete.

---

# 5. Consolidated roadmap

| Phase | Contents | Points | Outcome |
|---|---|---|---|
| **0. Cleanup** | §2 download removal | 3 | "Error loading" gone; Express bootable; prod endpoint retired |
| **1. Stop the bleeding** | Epic A | 13 | Zero user-visible defects |
| **2. Recommendations decision** | §1.4 items 1, 2, 3, 5 | 8 | One chat API, Chroma resolved, service deployed |
| **3. Supabase** | Epic S | 34 | Working registration; accurate Continue Watching |
| **4. Design system** | Epics B + C | 42 | Maintainable, accessible, componentised UI |
| **5. Continue Watching UI** | Epic D | 13 | Progress bars, resume UX, real skip controls |
| **6. Hardening** | Epic E | 13 | XSS-safe, sane ad-blocker, keys off the client |

**Total ≈ 126 points.**

**If you only do one thing:** Phase 0 — three lines removed, and every title in your player stops saying "Error loading".

**If you only do one week:** Phases 0 + 1 + 2 (24 pts). Bug-free app, deployed concierge.

**Biggest unknown:** S6 (VidLink `postMessage`). Spike it before committing to "resume from exactly where they left off" in any user-facing copy.

---

## Appendix — file-by-file disposition

| File | Verdict |
|---|---|
| `index.html` | Keep; fix P0s, then split (Epic B2) |
| `backend/main.py` | Keep; unmount `recommend_chat` |
| `backend/routes/chat.py` | Keep |
| `backend/routes/recommend_chat.py` | **Delete** — orphaned, buggy |
| `backend/services/gemini_concierge.py` | Keep — strongest file in the repo |
| `backend/services/movie_recommender.py` | Keep; fix Chroma ID matching or drop tier 1 |
| `backend/services/catalog.py` | Keep |
| `backend/services/profiling.py` | Trim to `PROFILING_QUESTIONS` |
| `backend/services/session_store.py` | **Delete** — leaks, unused |
| `backend/database/ingest_data.py` | Keep if Chroma stays; port to `pgvector` otherwise |
| `backend/server.js` | **Delete** after §2 |
| `backend/User.js` | **Delete** — superseded by Supabase |
| `backend/package.json` | **Delete** with `server.js` |
| `backend/.gitignore` | Add `node_modules/` |
| `backend/requirements.txt` | Prune if Chroma goes |
| `DEVELOPMENT_LOG.md` | **Archive** — 100% scraper history |
| `FUTURE_TODOS.md` | Fold live items into this doc; delete |
