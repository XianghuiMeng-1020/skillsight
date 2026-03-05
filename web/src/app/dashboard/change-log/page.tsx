'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import Sidebar from '@/components/Sidebar';
import { studentBff, getToken } from '@/lib/bffClient';
import { useLanguage, getDateLocale } from '@/lib/contexts';

interface ChangeLogItem {
  id: string;
  event_type: string;
  created_at: string;
  summary: string;
  before_state: Record<string, unknown>;
  after_state: Record<string, unknown>;
  diff: Record<string, unknown>;
  why: Record<string, unknown>;
  request_id?: string;
}

const EVENT_LABEL_KEYS: Record<string, string> = {
  skill_changed: 'changelog.skillChange',
  role_readiness_changed: 'changelog.roleChange',
  consent_withdrawn: 'changelog.consentRevoke',
  document_deleted: 'changelog.docDelete',
  actions_changed: 'changelog.actionUpdate',
};

export default function StudentChangeLogPage() {
  const { t, language } = useLanguage();
  const locale = getDateLocale(language);
  const [data, setData] = useState<{ items: ChangeLogItem[]; next_cursor?: string; refusal?: { code: string; message: string; next_step: string } } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [loadingMore, setLoadingMore] = useState(false);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const token = getToken();
      if (!token) {
        setError(t('changelog.loginToView'));
        setData(null);
        return;
      }
      const res = await studentBff.getChangeLog(50);
      setData(res as { items: ChangeLogItem[]; next_cursor?: string; refusal?: { code: string; message: string; next_step: string } });
    } catch (e) {
      setError(e instanceof Error ? e.message : t('changelog.loadFailedGeneric'));
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  const loadMore = async () => {
    if (!data?.next_cursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const res = await studentBff.getChangeLog(50, data.next_cursor) as {
        items: ChangeLogItem[];
        next_cursor?: string;
      };
      setData(prev => prev ? {
        ...prev,
        items: [...prev.items, ...res.items],
        next_cursor: res.next_cursor,
      } : prev);
    } catch (e) {
      setError(e instanceof Error ? e.message : t('changelog.loadFailedGeneric'));
    } finally {
      setLoadingMore(false);
    }
  };

  useEffect(() => { fetchData(); }, []);

  const toggleExpanded = (id: string) => {
    setExpanded(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div className="app-container">
      <Sidebar />
      <main className="main-content">
        <div className="page-header">
          <div>
            <h1 className="page-title">{t('changelog.pageTitle')}</h1>
            <p className="page-subtitle">
              {t('changelog.title')}
            </p>
          </div>
          <button className="btn btn-ghost btn-sm" onClick={fetchData}>{t('changelog.refresh')}</button>
        </div>

        <div className="page-content">
          {loading ? (
            <div className="loading"><span className="spinner"></span> {t('changelog.loading')}</div>
          ) : error ? (
            <div className="alert alert-error">
              <span>⚠</span>
              <div>
                <strong>{t('changelog.loadFailed')}</strong>
                <p style={{ marginTop: '0.25rem', fontSize: '0.875rem' }}>{error}</p>
                <p style={{ marginTop: '0.5rem', fontSize: '0.813rem' }}>
                  <Link href="/login" style={{ color: 'var(--primary)' }}>{t('common.login')}</Link> {t('common.retryAfterLogin')}
                </p>
              </div>
            </div>
          ) : data?.refusal && !data?.items?.length ? (
            <div className="card">
              <div className="empty-state">
                <div className="empty-icon">📜</div>
                <div className="empty-title">{data.refusal.message}</div>
                <div className="empty-desc">{data.refusal.next_step}</div>
                <div style={{ marginTop: '0.5rem', fontSize: '0.813rem', color: 'var(--gray-500)' }}>
                  {t('changelog.code')} {data.refusal.code}
                </div>
              </div>
            </div>
          ) : !data?.items?.length ? (
            <div className="card">
              <div className="empty-state">
                <div className="empty-icon">📜</div>
                <div className="empty-title">{t('changelog.noEvents')}</div>
                <div className="empty-desc">
                  {t('changelog.noEventsDesc')}
                </div>
              </div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              {(data.items as ChangeLogItem[]).map(item => {
                const isExpanded = expanded.has(item.id);
                const eventLabel = EVENT_LABEL_KEYS[item.event_type] ? t(EVENT_LABEL_KEYS[item.event_type]) : item.event_type;
                return (
                  <div key={item.id} className="card">
                    <div
                      className="card-content"
                      style={{ cursor: 'pointer' }}
                      onClick={() => toggleExpanded(item.id)}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
                        <span style={{ fontWeight: 600 }}>{item.summary}</span>
                        <span style={{ fontSize: '0.8rem', color: 'var(--gray-500)' }}>
                          {new Date(item.created_at).toLocaleString(locale)} · {eventLabel}
                        </span>
                      </div>
                      {isExpanded && (
                        <div style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid var(--gray-100)' }}>
                          <div style={{ fontSize: '0.875rem', marginBottom: '0.75rem' }}>
                            <strong>{t('changelog.before')}</strong>
                            <pre style={{ marginTop: '0.25rem', padding: '0.5rem', background: 'var(--gray-50)', borderRadius: '6px', overflow: 'auto', maxHeight: '120px' }}>
                              {JSON.stringify(item.before_state, null, 2)}
                            </pre>
                          </div>
                          <div style={{ fontSize: '0.875rem', marginBottom: '0.75rem' }}>
                            <strong>{t('changelog.after')}</strong>
                            <pre style={{ marginTop: '0.25rem', padding: '0.5rem', background: 'var(--gray-50)', borderRadius: '6px', overflow: 'auto', maxHeight: '120px' }}>
                              {JSON.stringify(item.after_state, null, 2)}
                            </pre>
                          </div>
                          {item.diff && Object.keys(item.diff).length > 0 && (
                            <div style={{ fontSize: '0.875rem', marginBottom: '0.75rem' }}>
                              <strong>Diff:</strong>
                              <pre style={{ marginTop: '0.25rem', padding: '0.5rem', background: 'var(--gray-50)', borderRadius: '6px', overflow: 'auto', maxHeight: '80px' }}>
                                {JSON.stringify(item.diff, null, 2)}
                              </pre>
                            </div>
                          )}
                          {item.why && Object.keys(item.why).length > 0 && (
                            <div style={{ fontSize: '0.875rem' }}>
                              <strong>{t('changelog.why')}</strong>
                              <pre style={{ marginTop: '0.25rem', padding: '0.5rem', background: 'var(--gray-50)', borderRadius: '6px', overflow: 'auto', maxHeight: '150px' }}>
                                {JSON.stringify(item.why, null, 2)}
                              </pre>
                            </div>
                          )}
                          {item.request_id && (
                            <div style={{ marginTop: '0.5rem', fontSize: '0.75rem', color: 'var(--gray-400)' }}>
                              request_id: {item.request_id}
                            </div>
                          )}
                        </div>
                      )}
                      <div style={{ marginTop: '0.5rem', fontSize: '0.75rem', color: 'var(--gray-400)' }}>
                        {isExpanded ? t('changelog.collapse') : t('changelog.expand')}
                      </div>
                    </div>
                  </div>
                );
              })}
              {data.next_cursor && (
                <button className="btn btn-ghost btn-sm" onClick={loadMore} disabled={loadingMore}>
                  {loadingMore ? t('common.loading') : t('changelog.loadMore')}
                </button>
              )}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
