import { createClient } from '@supabase/supabase-js';
import type { Database } from './types';

const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL;
const SUPABASE_PUBLISHABLE_KEY = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY;

// Sign-in is optional: without Supabase settings the app runs with no login screen,
// which is how `docker compose up` serves it locally.
export const authEnabled = Boolean(SUPABASE_URL && SUPABASE_PUBLISHABLE_KEY);

export const supabase = authEnabled
  ? createClient<Database>(SUPABASE_URL as string, SUPABASE_PUBLISHABLE_KEY as string, {
      auth: {
        storage: localStorage,
        persistSession: true,
        autoRefreshToken: true,
      },
    })
  : null;
