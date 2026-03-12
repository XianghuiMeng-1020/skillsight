'use client';

import Link from 'next/link';
import { useLanguage } from '@/lib/contexts';

export default function NotFound() {
  const { t } = useLanguage();
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
      }}
    >
      <div style={{ maxWidth: '420px', textAlign: 'center' }}>
        <h1 style={{ fontSize: '1.5rem', marginBottom: '0.5rem' }}>
          {t('error.notFound')}
        </h1>
        <p style={{ color: 'var(--gray-600)', marginBottom: '1.5rem' }}>
          {t('error.notFoundHint')}
        </p>
        <Link href="/dashboard" className="btn btn-primary">
          {t('error.backToDashboard')}
        </Link>
      </div>
    </div>
  );
}
