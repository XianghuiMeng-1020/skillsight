'use client';

import { useSearchParams } from 'next/navigation';
import { useEffect, useState, Suspense } from 'react';
import Link from 'next/link';
import { useLanguage } from '@/lib/contexts';

const API_URL = process.env.NEXT_PUBLIC_API_URL || '';

function VerifyContent() {
  const searchParams = useSearchParams();
  const { t } = useLanguage();
  const token = searchParams.get('token');
  const [status, setStatus] = useState<'loading' | 'valid' | 'invalid' | 'expired'>('loading');
  const [detail, setDetail] = useState<{ subject_id?: string; generated_at?: string; message?: string } | null>(null);

  useEffect(() => {
    if (!token) {
      setStatus('invalid');
      setDetail({ message: t('export.verifyNoToken') || 'No token provided.' });
      return;
    }
    const url = `${API_URL}/bff/student/export/verify?token=${encodeURIComponent(token)}`;
    fetch(url)
      .then(async (res) => {
        const data = await res.json().catch(() => ({}));
        if (res.ok && data.valid) {
          setStatus('valid');
          setDetail({
            subject_id: data.subject_id,
            generated_at: data.generated_at,
            message: data.message,
          });
        } else if (res.status === 400 && typeof data.detail === 'string' && data.detail.includes('expired')) {
          setStatus('expired');
          setDetail({ message: data.detail || (t('export.verifyExpired') || 'Statement expired, please regenerate.') });
        } else {
          setStatus('invalid');
          setDetail({ message: typeof data.detail === 'string' ? data.detail : (t('export.verifyInvalid') || 'Invalid or expired verification token.') });
        }
      })
      .catch(() => {
        setStatus('invalid');
        setDetail({ message: t('export.verifyError') || 'Verification request failed.' });
      });
  }, [token, t]);

  const maskSubject = (id: string) => {
    if (!id || id.length < 8) return '***';
    return id.slice(0, 4) + '…' + id.slice(-4);
  };

  return (
    <div style={{ maxWidth: '480px', margin: '4rem auto', padding: '2rem', fontFamily: 'system-ui, sans-serif' }}>
      <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
        <span style={{ fontSize: '2.5rem' }}>🔐</span>
        <h1 style={{ fontSize: '1.5rem', fontWeight: 700, marginTop: '0.5rem' }}>
          {t('export.verifyTitle') || 'Verify Statement'}
        </h1>
      </div>

      {status === 'loading' && (
        <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--gray-500)' }}>
          <div className="spinner" style={{ margin: '0 auto 1rem', width: 32, height: 32 }} />
          <p>{t('export.verifyChecking') || 'Checking…'}</p>
        </div>
      )}

      {status === 'valid' && detail && (
        <div style={{
          padding: '1.5rem',
          background: 'var(--success-light, #dcfce7)',
          borderRadius: '12px',
          border: '1px solid var(--success, #15803d)',
        }}>
          <p style={{ fontWeight: 600, color: 'var(--success, #15803d)', marginBottom: '0.75rem' }}>
            ✓ {t('export.verifyValid') || 'Valid statement'}
          </p>
          <p style={{ fontSize: '0.875rem', color: 'var(--gray-700)' }}>
            {t('export.verifyIssuedBy') || 'This statement was issued by SkillSight on'}{' '}
            <strong>{detail.generated_at || '—'}</strong>.
          </p>
          {detail.subject_id && (
            <p style={{ fontSize: '0.8125rem', color: 'var(--gray-600)', marginTop: '0.5rem' }}>
              {t('export.subjectId') || 'Subject ID'}: {maskSubject(detail.subject_id)}
            </p>
          )}
        </div>
      )}

      {(status === 'invalid' || status === 'expired') && detail && (
        <div style={{
          padding: '1.5rem',
          background: 'var(--error-light, #fef2f2)',
          borderRadius: '12px',
          border: '1px solid var(--error, #dc2626)',
        }}>
          <p style={{ fontWeight: 600, color: 'var(--error, #dc2626)', marginBottom: '0.5rem' }}>
            {status === 'expired' ? (t('export.verifyExpired') || 'Statement expired') : (t('export.verifyInvalid') || 'Invalid token')}
          </p>
          <p style={{ fontSize: '0.875rem', color: 'var(--gray-700)' }}>{detail.message}</p>
        </div>
      )}

      <p style={{ marginTop: '1.5rem', textAlign: 'center', fontSize: '0.875rem' }}>
        <Link href="/dashboard" style={{ color: 'var(--primary)', textDecoration: 'underline' }}>
          {t('export.backToDashboard') || 'Back to Dashboard'}
        </Link>
      </p>
    </div>
  );
}

export default function ExportVerifyPage() {
  return (
    <Suspense fallback={
      <div style={{ textAlign: 'center', padding: '4rem', color: 'var(--gray-500)' }}>
        {typeof window !== 'undefined' ? 'Loading…' : ''}
      </div>
    }>
      <VerifyContent />
    </Suspense>
  );
}
