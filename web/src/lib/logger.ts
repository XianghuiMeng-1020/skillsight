/**
 * Thin logger shim. Errors are always surfaced (console.error) so they appear
 * in Cloudflare Pages / browser DevTools even in production. Warn/info are
 * suppressed in production to reduce noise.
 *
 * To add Sentry: set NEXT_PUBLIC_SENTRY_DSN and uncomment the Sentry call
 * inside captureException below.
 *
 * Usage:
 *   import { logger } from '@/lib/logger';
 *   logger.error('Something failed', err);
 *   logger.warn('Degraded mode');
 */

const isProd = process.env.NODE_ENV === 'production';

function captureException(err: unknown, context?: string) {
  // Uncomment when Sentry DSN is configured:
  // import * as Sentry from '@sentry/nextjs';
  // Sentry.captureException(err, { extra: { context } });
  void err;
  void context;
}

export const logger = {
  error(message: string, err?: unknown) {
    // Always emit errors — they show up in browser DevTools and Cloudflare logs.
    // eslint-disable-next-line no-console
    console.error(`[error] ${message}`, err);
    captureException(err, message);
  },

  warn(message: string, ...args: unknown[]) {
    if (!isProd) {
      // eslint-disable-next-line no-console
      console.warn(`[warn] ${message}`, ...args);
    }
  },

  info(message: string, ...args: unknown[]) {
    if (!isProd) {
      // eslint-disable-next-line no-console
      console.info(`[info] ${message}`, ...args);
    }
  },
};
