/**
 * Thin logger shim. In production, swap console calls for a real
 * error-tracking service (e.g. Sentry) by implementing the stubs below.
 *
 * Usage:
 *   import { logger } from '@/lib/logger';
 *   logger.error('Something failed', err);
 *   logger.warn('Degraded mode');
 */

const isProd = process.env.NODE_ENV === 'production';

function captureException(err: unknown, context?: string) {
  // TODO: replace with Sentry.captureException(err, { extra: { context } })
  // when a DSN is configured.
  void err;
  void context;
}

export const logger = {
  error(message: string, err?: unknown) {
    if (!isProd) {
      // eslint-disable-next-line no-console
      console.error(`[error] ${message}`, err);
    }
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
