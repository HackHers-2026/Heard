import { createClient } from "@supabase/supabase-js";

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const supabaseKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY;

// Fail loudly if the env vars are missing/misnamed, instead of silently
// passing `undefined` into createClient (which fails with a cryptic error
// only once you try to log in).
if (!supabaseUrl || !supabaseKey) {
  throw new Error(
    "Missing Supabase env vars. Set VITE_SUPABASE_URL and VITE_SUPABASE_PUBLISHABLE_KEY in web/.env.local"
  );
}

// Supabase JS persists the browser session in localStorage by default
// (key: sb-<project-ref>-auth-token) — exactly what the Chrome-extension
// bridge (extension/src/webapp-bridge.js) reads to authenticate recordings.
export const supabase = createClient(supabaseUrl, supabaseKey);
