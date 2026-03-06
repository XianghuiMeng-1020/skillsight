'use client';

import { useEffect } from 'react';
import Link from 'next/link';
import { useLanguage } from '@/lib/contexts';

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const { t } = useLanguage();
  useEffect(() => {
    console.error('App error:', error);
  }, [error]);

  return (
    <div className="app-container" style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '2rem' }}>
      <div style={{ maxWidth: '420px', textAlign: 'center' }}>
        <h1 style={{ fontSize: '1.5rem', marginBottom: '0.5rem' }}>{t('error.somethingWrong')}</h1>
        <p style={{ color: 'var(--gray-600)', marginBottom: '1.5rem' }}>
          We encountered an error. You can try again or return to the dashboard.
        </p>
        <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'center', flexWrap: 'wrap' }}>
          <button
            type="button"
            onClick={reset}
            className="btn btn-primary"
          >
            {t('error.tryAgain')}
          </button>
          <Link href="/dashboard" className="btn btn-secondary">
            {t('error.backToDashboard')}
          </Link>
        </div>
      </div>
    </div>
  );
}
