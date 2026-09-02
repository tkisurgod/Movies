/*
 * TK Entertainment — frontend runtime config
 *
 * SETUP
 *   1. Copy this file to `config.js` (same folder as index.html).
 *   2. Fill in the values below — see each one's comment for where it lives.
 *   3. Reload the page.
 *
 * EVERY VALUE IN THIS FILE IS PUBLIC.
 *   config.js is committed and served to the browser, so treat it as a
 *   billboard, not a vault. Only keys that are safe to publish belong here.
 *   Read CREDENTIAL-PROTECTION.md before adding anything new.
 *
 *   Never put these here: the Supabase `service_role` key (bypasses RLS),
 *   the Gemini API key, or any database connection string. Those are
 *   server-side only and belong in backend/.env, which is gitignored.
 *
 * WHY NOT .env?
 *   index.html has no build step. A browser cannot read a .env file — that
 *   format only works for server processes or bundlers that inline the values
 *   at build time. This file is the browser-native equivalent.
 */

window.__APP_CONFIG__ = {
    // Supabase Dashboard → Project Settings → API
    //   The anon key is designed to be public — it ships in every Supabase web
    //   app. Security comes from Row Level Security policies on the tables, not
    //   from hiding this string. supabase/migrations/0001_init.sql enables RLS
    //   on every table; do not disable it.
    SUPABASE_URL: 'https://YOUR-PROJECT-REF.supabase.co',
    SUPABASE_ANON_KEY: 'YOUR-ANON-KEY',

    // TMDB → Settings → API (https://www.themoviedb.org/settings/api)
    //   Read-only and rate-limited per key. The browser calls TMDB directly, so
    //   this is visible in the Network tab regardless of where it's stored —
    //   see CREDENTIAL-PROTECTION.md § "Why the TMDB key is public".
    TMDB_API_KEY: 'YOUR-TMDB-API-KEY',
    TMDB_READ_TOKEN: 'YOUR-TMDB-READ-ACCESS-TOKEN',
};
