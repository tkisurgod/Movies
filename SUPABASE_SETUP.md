# Supabase Setup

Everything on the code side is done. These are the steps only you can do —
they need dashboard access.

**Until you finish step 3, the app runs in guest mode** (localStorage only,
exactly as it behaved before) and logs a warning to the console. Nothing breaks.

---

## 1. Create the project

1. <https://supabase.com/dashboard> → **New project**
2. Name it whatever you like, pick a region close to your users, set a strong
   database password (you won't need it for this app — it's for direct SQL access).
3. Wait for provisioning (~2 min).

## 2. Run the schema

1. Dashboard → **SQL Editor** → **New query**
2. Paste the entire contents of [`supabase/migrations/0001_init.sql`](supabase/migrations/0001_init.sql)
3. **Run**

It's idempotent — safe to re-run if you change something later.

This creates:

| Object | Purpose |
|---|---|
| `profiles` | One row per user, auto-created on signup by trigger |
| `watch_progress` | One row per (user, title, season, episode) |
| `continue_watching` | View — latest unfinished row per title |
| `concierge_sessions` | AI Concierge past picks |

Row Level Security is enabled on all three tables, with policies restricting
every row to `auth.uid()`. **Don't disable it** — it's the only thing standing
between the public anon key and everyone's data.

### Verify it worked

Dashboard → **Table Editor** — you should see the three tables.
Then in SQL Editor:

```sql
select tablename, rowsecurity
from pg_tables
where schemaname = 'public';
```

`rowsecurity` must be `true` for all three.

## 3. Wire up the keys

Dashboard → **Project Settings** → **API**. Copy:

- **Project URL** → `SUPABASE_URL`
- **Project API keys** → the `anon` `public` one → `SUPABASE_ANON_KEY`

Paste both into **`config.js`** in the repo root (already created, gitignored):

```js
window.__APP_CONFIG__ = {
    SUPABASE_URL: 'https://abcdefgh.supabase.co',
    SUPABASE_ANON_KEY: 'eyJhbGciOi...',
};
```

Reload. The console warning disappears and the **Sign In** button becomes live.

> ⚠️ **Never** paste the `service_role` key here. It bypasses RLS entirely and
> would hand every user's data to anyone who opens devtools.
>
> The `anon` key *is* meant to be public — it ships in every Supabase web app.
> `config.js` is gitignored for easy rotation, not because the key is a secret.

## 4. Configure auth

Dashboard → **Authentication** → **Sign In / Providers**

**Email** provider is on by default. Decide one thing:

- **Confirm email ON** (default, recommended for production) — new users get a
  confirmation link and can't sign in until they click it. The app handles this:
  it shows *"Almost there — check you@example.com for a confirmation link."*
- **Confirm email OFF** (faster for local testing) — signup logs you straight in.
  The app handles this too, via the `data.session` branch.

Then **Authentication → URL Configuration**:

- **Site URL** — where confirmation and password-reset links land.
  - Local dev: `http://localhost:5501` (your Live Server port from `.vscode/settings.json`)
  - Production: your deployed origin
- **Redirect URLs** — add every origin you'll use, one per line. Links from
  emails will be rejected if the origin isn't listed here.

### Adding Google sign-in later

Dashboard → **Authentication → Providers → Google**, supply a Google Cloud OAuth
client ID/secret, then uncomment the block marked
`--- Google OAuth hook ---` in `index.html` and add a button. The
`onAuthStateChange` handler already picks up the returning session — no other
wiring needed.

---

## What the app does now

| | Guest (not signed in) | Signed in |
|---|---|---|
| Watch history | `localStorage` | `watch_progress` table, synced across devices |
| Remove from Continue Watching | `localStorage` | `DELETE` on the table — **actually sticks now** |
| Concierge past picks | `localStorage` | `concierge_sessions` table |
| On first sign-in | — | Guest data is lifted into the account, then cleared locally |

**On first sign-in**, local guest data is merged into the account using
`ignoreDuplicates` — local rows never overwrite existing server progress.
localStorage entries carry no timestamp, so there's no way to tell which is
newer, and silently clobbering real progress is the worse failure.

**On logout**, in-memory history is cleared rather than written back to
localStorage. On a shared device, mirroring would leak one account's history to
the next guest. The data isn't lost — it's in the account, back on next sign-in.

---

## What this does *not* do yet

Continue Watching syncs **which episode** you were on, exactly. It does **not**
yet track *where in the episode* you stopped — `position_seconds` stays `0` and
`fidelity` stays `'none'` on every row.

The columns and the schema are ready for it. Capturing the actual playhead is
the next step, and it's constrained by something outside your control: the
player is a **cross-origin iframe**, so the browser will not let you read
`currentTime` from it. See **REVAMP.md §4.4** — it's tiered:

- **Tier 1 (`exact`)** — VidLink advertises a `postMessage` progress API. Needs a
  spike to confirm it behaves as documented before anything is built on it.
- **Tier 2 (`coarse`)** — wall-clock heartbeat for every other provider.
  Approximate by nature; the UI copy has to say "about 42 min in", not "42:17".

That's Epic S5–S7 (13 pts).

---

## Troubleshooting

**Console: `[auth] Supabase not configured`**
`config.js` still has placeholders, or the CDN script didn't load. Check the
Network tab for `supabase-js@2`.

**Signup succeeds but no email arrives**
Supabase's built-in SMTP is rate-limited and easy to miss. Check spam, then
Dashboard → **Authentication → Emails**. For production, configure your own SMTP.

**Confirmation link opens but doesn't sign me in**
The origin isn't in **Redirect URLs**. Add it, including the port.

**Console: `new row violates row-level security policy`**
You're writing a row where `user_id` isn't the signed-in user. `itemToRow()`
sets it from `currentUser.id` — this usually means the session expired mid-write.

**Continue Watching is empty right after signing in**
Expected if you had no guest data. Play something and it'll appear. If guest
data *should* have merged, check the console for `[merge]` warnings.
