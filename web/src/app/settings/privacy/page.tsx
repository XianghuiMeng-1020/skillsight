'use client';

import { useEffect, useState } from 'react';
import Sidebar from '@/components/Sidebar';
import { useLanguage, getDateLocale } from '@/lib/contexts';
import { studentBff, getToken } from '@/lib/bffClient';
import { API_BASE_URL } from '@/lib/api';

interface ConsentItem {
  consent_id: string;
  doc_id: string;
  filename: string;
  doc_type?: string;
  purpose: string;
  scope: string;
  status: 'granted' | 'revoked' | string;
  created_at: string | null;
  revoked_at: string | null;
  revoke_reason?: string;
}

export default function PrivacyPage() {
  const { t, language } = useLanguage();
  const locale = getDateLocale(language);
  const [consents, setConsents] = useState<ConsentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [withdrawing, setWithdrawing] = useState<string | null>(null);
  const [showConfirm, setShowConfirm] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; msg: string } | null>(null);

  const fetchConsents = () => {
    setLoading(true);
    if (!getToken()) {
      setConsents([]);
      setLoading(false);
      return;
    }
    studentBff.getConsents()
      .then((data: unknown) => setConsents((data as { items?: ConsentItem[] })?.items ?? []))
      .catch(() => setConsents([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchConsents(); }, []);

  const handleWithdraw = async (docId: string) => {
    setWithdrawing(docId);
    setFeedback(null);
    try {
      const token = getToken();
      const response = await fetch(`${API_BASE_URL}/bff/student/consents/withdraw`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ doc_id: docId, reason: 'Student withdrew consent from Privacy page' }),
      });

      if (response.ok) {
        const result = await response.json();
        setConsents(prev => prev.map(c =>
          c.doc_id === docId ? { ...c, status: 'revoked', revoked_at: new Date().toISOString() } : c
        ));
        setFeedback({
          type: 'success',
          msg: `${t('privacy.revokedSuccess')}${result.audit_id}`,
        });
      } else {
        const err = await response.json();
        setFeedback({ type: 'error', msg: err.detail?.message || err.detail || t('privacy.revokeFailed') });
      }
    } catch {
      setFeedback({ type: 'error', msg: t('common.networkError') });
    } finally {
      setWithdrawing(null);
      setShowConfirm(null);
    }
  };

  const handleWithdrawAll = async () => {
    if (!confirm(t('privacy.revokeConfirm'))) return;
    setLoading(true);
    const granted = consents.filter(c => c.status === 'granted');
    for (const c of granted) {
      await handleWithdraw(c.doc_id);
    }
    setLoading(false);
  };

  const activeConsents = consents.filter(c => c.status === 'granted');
  const revokedConsents = consents.filter(c => c.status !== 'granted');

  return (
    <div className="app-container">
      <Sidebar />
      <main className="main-content">
        <div className="page-header">
          <div>
            <h1 className="page-title">{t('nav.privacy')}</h1>
            <p className="page-subtitle">{t('privacy.pageSubtitle')}</p>
          </div>
        </div>

        <div className="page-content">
          {/* Privacy Overview */}
          <div className="card" style={{ marginBottom: '1.5rem' }}>
            <div className="card-header">
              <h3 className="card-title">🔒 {t('privacy.rightsTitle')}</h3>
            </div>
            <div className="card-content">
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1.5rem' }}>
                <div>
                  <h4 style={{ marginBottom: '0.5rem' }}>📋 {t('privacy.dataCollectionTitle')}</h4>
                  <p style={{ fontSize: '0.875rem', color: 'var(--gray-600)' }}>
                    {t('privacy.dataCollectionDesc')}
                  </p>
                </div>
                <div>
                  <h4 style={{ marginBottom: '0.5rem' }}>🛡️ {t('privacy.securityTitle')}</h4>
                  <p style={{ fontSize: '0.875rem', color: 'var(--gray-600)' }}>
                    {t('privacy.securityDesc')}
                  </p>
                </div>
                <div>
                  <h4 style={{ marginBottom: '0.5rem' }}>🗑️ {t('privacy.deletionTitle')}</h4>
                  <p style={{ fontSize: '0.875rem', color: 'var(--gray-600)' }}>
                    {t('privacy.deletionDesc')}
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Feedback */}
          {feedback && (
            <div style={{
              marginBottom: '1.25rem',
              padding: '0.875rem 1.25rem',
              borderRadius: '10px',
              background: feedback.type === 'success' ? '#dcfce7' : '#ffecec',
              border: `1px solid ${feedback.type === 'success' ? '#86efac' : '#f5c2c2'}`,
              color: feedback.type === 'success' ? '#15803d' : '#b42318',
              fontSize: '0.875rem',
            }}>
              {feedback.type === 'success' ? '✓ ' : '⚠ '}{feedback.msg}
            </div>
          )}

          {/* Data Summary */}
          <div className="card" style={{ marginBottom: '1.5rem' }}>
            <div className="card-header">
              <h3 className="card-title">{t('privacy.dataOverview')}</h3>
            </div>
            <div className="card-content">
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem' }}>
                <div style={{ textAlign: 'center', padding: '1rem' }}>
                  <div style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--primary)' }}>
                    {activeConsents.length}
                  </div>
                  <div style={{ fontSize: '0.875rem', color: 'var(--gray-500)' }}>{t('privacy.activeConsents')}</div>
                </div>
                <div style={{ textAlign: 'center', padding: '1rem' }}>
                  <div style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--gray-400)' }}>
                    {revokedConsents.length}
                  </div>
                  <div style={{ fontSize: '0.875rem', color: 'var(--gray-500)' }}>{t('privacy.revoked')}</div>
                </div>
                <div style={{ textAlign: 'center', padding: '1rem' }}>
                  <div style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--primary)' }}>
                    {consents.length}
                  </div>
                  <div style={{ fontSize: '0.875rem', color: 'var(--gray-500)' }}>{t('privacy.allRecords')}</div>
                </div>
              </div>
            </div>
          </div>

          <div className="card" style={{ marginBottom: '1.5rem' }}>
            <div className="card-header">
              <h3 className="card-title">{t('privacy.authorizedDocs')}</h3>
              <button
                className="btn btn-danger btn-sm"
                onClick={handleWithdrawAll}
                disabled={activeConsents.length === 0 || loading}
              >
                {t('privacy.revokeAll')}
              </button>
            </div>
            <div className="card-content" style={{ padding: 0 }}>
              {loading ? (
                <div className="loading"><span className="spinner"></span>{t('privacy.loading')}</div>
              ) : activeConsents.length > 0 ? (
                <table className="table">
                  <thead>
                    <tr>
                      <th>{t('privacy.filename')}</th>
                      <th>{t('privacy.purpose')}</th>
                      <th>{t('privacy.scope')}</th>
                      <th>{t('privacy.uploadTime')}</th>
                      <th>{t('privacy.actions')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {activeConsents.map((c) => (
                      <tr key={c.consent_id}>
                        <td style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                          <span style={{ fontSize: '1.25rem' }}>📄</span>
                          <span style={{ fontWeight: 500 }}>{c.filename}</span>
                        </td>
                        <td>
                          <span style={{
                            padding: '0.125rem 0.5rem', borderRadius: '12px',
                            background: '#dbeafe', color: '#1d4ed8',
                            fontSize: '0.75rem', fontWeight: 500,
                          }}>
                            {c.purpose || '—'}
                          </span>
                        </td>
                        <td>
                          <span style={{ fontSize: '0.8rem', color: 'var(--gray-600)' }}>
                            {c.scope || '—'}
                          </span>
                        </td>
                        <td style={{ fontSize: '0.8rem', color: 'var(--gray-500)' }}>
                          {c.created_at ? new Date(c.created_at).toLocaleDateString(locale) : '—'}
                        </td>
                        <td>
                          {showConfirm === c.doc_id ? (
                            <div style={{ display: 'flex', gap: '0.5rem' }}>
                              <button
                                className="btn btn-danger btn-sm"
                                onClick={() => handleWithdraw(c.doc_id)}
                                disabled={withdrawing === c.doc_id}
                              >
                                {withdrawing === c.doc_id ? t('common.deleting') : t('common.confirmDelete')}
                              </button>
                              <button
                                className="btn btn-ghost btn-sm"
                                onClick={() => setShowConfirm(null)}
                              >
                                {t('common.cancel')}
                              </button>
                            </div>
                          ) : (
                            <button
                              className="btn btn-secondary btn-sm"
                              onClick={() => setShowConfirm(c.doc_id)}
                            >
                              {t('privacy.revokeDelete')}
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div className="empty-state">
                  <div className="empty-icon">📁</div>
                  <div className="empty-title">{t('privacy.noActive')}</div>
                  <div className="empty-desc">{t('privacy.noActiveDesc')}</div>
                </div>
              )}
            </div>
          </div>

          {/* Revoked Consents (audit trail) */}
          {revokedConsents.length > 0 && (
            <div className="card" style={{ marginBottom: '1.5rem' }}>
              <div className="card-header">
                <h3 className="card-title">{t('privacy.revokedRecords')}</h3>
              </div>
              <div className="card-content" style={{ padding: 0 }}>
                <table className="table">
                  <thead>
                    <tr>
                      <th>{t('privacy.filename')}</th>
                      <th>{t('privacy.revokedAt')}</th>
                      <th>{t('privacy.reason')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {revokedConsents.map(c => (
                      <tr key={c.consent_id} style={{ opacity: 0.65 }}>
                        <td>{c.filename}</td>
                        <td style={{ fontSize: '0.8rem', color: 'var(--gray-500)' }}>
                          {c.revoked_at ? new Date(c.revoked_at).toLocaleString(locale) : '—'}
                        </td>
                        <td style={{ fontSize: '0.8rem', color: 'var(--gray-500)' }}>
                          {c.revoke_reason || '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Info Box */}
          <div className="alert alert-info" style={{ marginTop: '1.5rem' }}>
            <span className="alert-icon">ℹ️</span>
            <div className="alert-content">
              <div className="alert-title">{t('privacy.aboutDeletionTitle')}</div>
              <p>{t('privacy.aboutDeletionIntro')}</p>
              <ul style={{ marginTop: '0.5rem', marginLeft: '1.25rem', fontSize: '0.875rem' }}>
                <li>{t('privacy.aboutDeletionItem1')}</li>
                <li>{t('privacy.aboutDeletionItem2')}</li>
                <li>{t('privacy.aboutDeletionItem3')}</li>
                <li>{t('privacy.aboutDeletionItem4')}</li>
              </ul>
              <p style={{ marginTop: '0.5rem' }}>{t('privacy.aboutDeletionEnd')}</p>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
