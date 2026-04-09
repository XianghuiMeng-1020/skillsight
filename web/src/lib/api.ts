/**
 * Shared API base URL for legacy direct-fetch paths.
 *
 * NOTE:
 * All authenticated business requests should go through `bffClient.ts`.
 */
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';
