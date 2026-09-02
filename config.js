/*
 * TK Entertainment — frontend runtime config
 *
 * THIS FILE IS COMMITTED AND PUBLIC. It is served to every visitor's browser.
 * Only keys that are safe to publish belong here. Before adding anything new,
 * read CREDENTIAL-PROTECTION.md.
 *
 * Never put here: Supabase `service_role`, GEMINI_API_KEY, DB connection
 * strings. Those live in backend/.env, which is gitignored.
 */

window.__APP_CONFIG__ = {
    // Supabase Dashboard → Project Settings → API
    // Public by design; protected by Row Level Security, not by secrecy.
    SUPABASE_URL: 'https://coxujorbjoqietphovov.supabase.co',
    SUPABASE_ANON_KEY: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNveHVqb3Jiam9xaWV0cGhvdm92Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODU0OTc4MDgsImV4cCI6MjEwMTA3MzgwOH0.CT-1ID8l7efo2YLQSqVUPKkpd63REu3CvYdPeSC_Zj0',

    // ┌─────────────────────────────────────────────────────────────────────┐
    // │ ⚠️  ROTATE BEFORE COMMITTING — these two are the LEAKED originals.  │
    // │ They sat in index.html in public git history. Regenerate at         │
    // │ https://www.themoviedb.org/settings/api and paste the new values    │
    // │ over these, then delete this box.                                   │
    // └─────────────────────────────────────────────────────────────────────┘
    TMDB_API_KEY: 'a61fccf34d3b7d0701fcdde5db6043ab',
    TMDB_READ_TOKEN: 'eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiJhNjFmY2NmMzRkM2I3ZDA3MDFmY2RkZTVkYjYwNDNhYiIsIm5iZiI6MTc2MzY0NjIxOS45MSwic3ViIjoiNjkxZjFiMGI0ZWEwMzMyNDQ1MDU4NmRhIiwic2NvcGVzIjpbImFwaV9yZWFkIl0sInZlcnNpb24iOjF9.C29__PfaNFBL2P2mSh8Yf3Rpzj78kz80rB2y5eGIHRM',
};
