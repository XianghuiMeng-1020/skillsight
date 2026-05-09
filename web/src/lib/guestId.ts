'use client';

/**
 * Per-browser persistent guest identity.
 *
 * Why this exists:
 * Previously the "Sign in with HKU portal" and "Try Demo" buttons hard-coded
 * `hku_demo_user` as the BFF subject_id, which meant every public visitor
 * shared the SAME backend account. That violated Protocol 9 (Consent) and
 * caused data cross-contamination on `/bff/student/profile`.
 *
 * This module generates and persists a unique guest id in localStorage so
 * each browser gets its own subject_id, while still allowing repeat visits
 * from the same browser to see their own uploaded documents.
 */

const GUEST_ID_KEY = 'skillsight-guest-id-v1';
const GUEST_ID_PREFIX = 'hku_guest_';

function generateRandomId(): string {
  try {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID().replace(/-/g, '');
    }
  } catch {
    // fall through
  }
  // Fallback: timestamp + random; 24+ chars of entropy is sufficient for our
  // collision domain (a single deployment's guests).
  const ts = Date.now().toString(36);
  const rnd = Math.random().toString(36).slice(2, 12) + Math.random().toString(36).slice(2, 12);
  return `${ts}${rnd}`.slice(0, 32);
}

/**
 * Returns a stable per-browser guest subject_id, e.g. "hku_guest_a1b2c3...".
 * Generates and persists one on first call. SSR-safe: returns a transient id
 * when window is unavailable (will be re-generated on the client).
 */
export function getOrCreateGuestSubjectId(): string {
  if (typeof window === 'undefined') {
    return `${GUEST_ID_PREFIX}ssr_${generateRandomId().slice(0, 8)}`;
  }
  try {
    const existing = localStorage.getItem(GUEST_ID_KEY);
    if (existing && /^[a-zA-Z0-9_-]{4,}$/.test(existing)) {
      return existing.startsWith(GUEST_ID_PREFIX) ? existing : `${GUEST_ID_PREFIX}${existing}`;
    }
    const fresh = `${GUEST_ID_PREFIX}${generateRandomId()}`;
    localStorage.setItem(GUEST_ID_KEY, fresh);
    return fresh;
  } catch {
    return `${GUEST_ID_PREFIX}${generateRandomId()}`;
  }
}

/** Clear the persisted guest id (used on explicit "reset" / sign-out flows). */
export function clearGuestSubjectId(): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.removeItem(GUEST_ID_KEY);
  } catch {
    // noop
  }
}
