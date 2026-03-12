'use client';

import { useEffect } from 'react';
import Link from 'next/link';
import { useLanguage } from '@/lib/contexts';
import { logger } from '@/lib/logger';

/** B1: Dashboard 错误边界，避免白屏显示通用 "Application error" */
export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const { t } = useLanguage();
  useEffect(() => {
    logger.error('Dashboard error', error);
  }, [error]);

  return (
    <div
      className="app-container"
      style={{
        minHeight: '100vh',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '2rem',
        background: 'linear-gradient(180deg, rgba(249,206,156,0.06) 0%, rgba(201,221,227,0.06) 100%)',
      }}
    >
      <div style={{ maxWidth: '420px', textAlign: 'center' }}>
        <h1 style={{ fontSize: '1.5rem', marginBottom: '0.5rem' }}>
          {t('error.somethingWrong')}
        </h1>
        <p style={{ color: 'var(--gray-600)', marginBottom: '1.5rem' }}>
          {t('dashboard.errorFallback') || 'Dashboard failed to load. You can try again or go home.'}
        </p>
        <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'center', flexWrap: 'wrap' }}>
          <button type="button" onClick={reset} className="btn btn-primary">
            {t('error.tryAgain')}
          </button>
          <Link href="/" className="btn btn-secondary">
            {t('nav.home')}
          </Link>
          <Link href="/assess" className="btn btn-secondary">
            {t('nav.assess')}
          </Link>
        </div>
      </div>
    </div>
  );
}
