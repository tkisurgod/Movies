/*
 * TK Entertainment — frontend runtime config
 *
 * SETUP
 *   1. Copy this file to `config.js` (same folder as index.html).
 *   2. Fill in the two values below from:
 *        Supabase Dashboard → Project Settings → API
 *   3. Reload the page.
 *
 * `config.js` is gitignored. This example file is committed.
 *
 * NOTE ON THE ANON KEY
 *   The anon key is *designed* to be public — it ships in every Supabase web
 *   app and is visible in devtools no matter what you do. Security comes from
 *   Row Level Security policies on the tables, not from hiding this string.
 *   The migration in supabase/migrations/0001_init.sql enables RLS on every
 *   table; do not disable it.
 *
 *   The *service_role* key is the opposite — it bypasses RLS entirely.
 *   Never put that one in this file or anywhere else in the frontend.
 *
 * WHY NOT .env?
 *   index.html has no build step. A browser cannot read a .env file — that
 *   format only works for server processes or bundlers that inline the values
 *   at build time. This file is the browser-native equivalent.
 */

window.__APP_CONFIG__ = {
    SUPABASE_URL: 'https://YOUR-PROJECT-REF.supabase.co',
    SUPABASE_ANON_KEY: 'YOUR-ANON-KEY',
};
