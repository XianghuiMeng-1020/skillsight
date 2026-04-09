import { BffError } from '@/lib/bffClient';

export function mapBffErrorToMessage(error: unknown, fallback: string): string {
  if (error instanceof BffError) {
    if (error.status === 401) return 'Session expired. Please log in again.';
    if (error.status === 403) return 'You do not have access to this operation.';
    if (error.status >= 500) return 'Server is temporarily unavailable. Please try again.';
    const detail = typeof error.detail === 'string' ? error.detail : '';
    return detail || fallback;
  }
  if (error instanceof Error) return error.message || fallback;
  return fallback;
}
