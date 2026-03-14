'use client';

import { useEffect, useState } from 'react';
import { useLanguage } from '@/lib/contexts';
import { useToast } from '@/components/Toast';
import { studentBff } from '@/lib/bffClient';
import styles from './resume.module.css';

interface Suggestion {
  suggestion_id: string;
  dimension: string;
  section?: string;
  original_text?: string;
  suggested_text?: string;
  explanation?: string;
  priority: string;
  status: string;
  student_edit?: string;
}

interface SuggestionPanelProps {
  reviewId: string;
  onContinue: () => void;
  onSuggestionsLoaded?: () => void;
}

export function SuggestionPanel({ reviewId, onContinue, onSuggestionsLoaded }: SuggestionPanelProps) {
  const { t } = useLanguage();
  const { addToast } = useToast();
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [filter, setFilter] = useState<string>('all');
  const [editId, setEditId] = useState<string | null>(null);
  const [editText, setEditText] = useState('');
  const [patching, setPatching] = useState<string | null>(null);

  const loadSuggestions = async () => {
    try {
      const res = await studentBff.resumeReviewGetSuggestions(reviewId);
      const list = res.suggestions || [];
      setSuggestions(list);
      if (list.length > 0) onSuggestionsLoaded?.();
    } catch {
      setSuggestions([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const run = async () => {
      setLoading(true);
      try {
        const res = await studentBff.resumeReviewGetSuggestions(reviewId);
        const list = res.suggestions || [];
        if (list.length === 0) {
          setGenerating(true);
          try {
            await studentBff.resumeReviewSuggest(reviewId);
            await loadSuggestions();
          } catch (e) {
            addToast('error', (e as Error).message || t('resume.generating'));
          } finally {
            setGenerating(false);
          }
        } else {
          setSuggestions(list);
          onSuggestionsLoaded?.();
        }
      } catch {
        setSuggestions([]);
      } finally {
        setLoading(false);
      }
    };
    run();
  }, [reviewId]);

  const handleStatus = async (suggestionId: string, status: string, studentEdit?: string) => {
    setPatching(suggestionId);
    try {
      await studentBff.resumeReviewPatchSuggestion(reviewId, suggestionId, status, studentEdit);
      await loadSuggestions();
      addToast('success', status === 'accepted' ? t('resume.accepted') : status === 'rejected' ? t('resume.rejected') : '');
    } catch (e) {
      addToast('error', (e as Error).message);
    } finally {
      setPatching(null);
      setEditId(null);
    }
  };

  const openEdit = (s: Suggestion) => {
    setEditId(s.suggestion_id);
    setEditText(s.student_edit || s.suggested_text || '');
  };

  const filtered = filter === 'all'
    ? suggestions
    : suggestions.filter((s) => s.priority === filter);
  const acceptedCount = suggestions.filter((s) => s.status === 'accepted' || s.status === 'edited').length;
  const rejectedCount = suggestions.filter((s) => s.status === 'rejected').length;
  const pendingCount = suggestions.filter((s) => s.status === 'pending').length;

  if (loading || generating) {
    return (
      <>
        <h2 style={{ fontSize: '1.25rem', marginBottom: '0.5rem' }}>{t('resume.step3Title')}</h2>
        <p style={{ color: 'var(--gray-600)' }}>{t('resume.generating')}</p>
      </>
    );
  }

  return (
    <>
      <h2 style={{ fontSize: '1.25rem', marginBottom: '0.5rem' }}>{t('resume.step3Title')}</h2>
      <p style={{ color: 'var(--gray-600)', marginBottom: '1rem' }}>{t('resume.step3Desc')}</p>

      <div className={styles.priorityTabs}>
        {['all', 'high', 'medium', 'low'].map((pri) => (
          <button
            key={pri}
            type="button"
            className={`${styles.priorityTab} ${filter === pri ? styles.priorityTabActive : ''}`}
            onClick={() => setFilter(pri)}
          >
            {pri === 'all' ? t('resume.allSuggestions') : t(`resume.${pri === 'high' ? 'high' : pri === 'medium' ? 'medium' : 'low'}Priority`)}
          </button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <p style={{ color: 'var(--gray-500)' }}>{t('resume.noSuggestions') || 'No suggestions.'}</p>
      ) : (
        <div style={{ marginBottom: '1rem' }}>
          {filtered.map((s) => (
            <div
              key={s.suggestion_id}
              className={styles.suggestionCard}
              style={{ opacity: s.status !== 'pending' ? 0.85 : 1 }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                <span style={{ fontSize: '0.75rem', background: 'var(--gray-200)', padding: '0.2rem 0.5rem', borderRadius: '999px' }}>
                  {s.dimension}
                </span>
                {s.section && <span style={{ fontSize: '0.8125rem', color: 'var(--gray-600)' }}>{s.section}</span>}
              </div>
              <p style={{ margin: 0, fontSize: '0.8125rem', fontWeight: 600 }}>{t('resume.before')}</p>
              <div className={styles.beforeBlock}>{s.original_text || '—'}</div>
              <p style={{ margin: 0, fontSize: '0.8125rem', fontWeight: 600 }}>{t('resume.after')}</p>
              <div className={styles.afterBlock}>
                {editId === s.suggestion_id ? (
                  <textarea
                    value={editText}
                    onChange={(e) => setEditText(e.target.value)}
                    rows={4}
                    style={{ width: '100%', padding: '0.5rem', border: '1px solid var(--gray-200)', borderRadius: 'var(--radius)' }}
                  />
                ) : (
                  s.student_edit || s.suggested_text || '—'
                )}
              </div>
              {s.explanation && (
                <p style={{ margin: '0.5rem 0 0', fontSize: '0.875rem', color: 'var(--gray-600)', fontStyle: 'italic' }}>
                  {t('resume.why')}: {s.explanation}
                </p>
              )}
              <div style={{ marginTop: '0.75rem', display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                {s.status === 'pending' && (
                  <>
                    <button
                      type="button"
                      className="btn btn-primary btn-sm"
                      onClick={() => handleStatus(s.suggestion_id, 'accepted')}
                      disabled={patching === s.suggestion_id}
                    >
                      {t('resume.accept')}
                    </button>
                    {editId === s.suggestion_id ? (
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => handleStatus(s.suggestion_id, 'edited', editText)}
                        disabled={patching === s.suggestion_id}
                      >
                        {t('resume.saveEdit')}
                      </button>
                    ) : (
                      <button type="button" className="btn btn-ghost btn-sm" onClick={() => openEdit(s)}>
                        {t('resume.edit')}
                      </button>
                    )}
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      style={{ color: 'var(--error)' }}
                      onClick={() => handleStatus(s.suggestion_id, 'rejected')}
                      disabled={patching === s.suggestion_id}
                    >
                      {t('resume.reject')}
                    </button>
                  </>
                )}
                {(s.status === 'accepted' || s.status === 'edited') && (
                  <span style={{ color: 'var(--success)', fontSize: '0.875rem' }}>✓ {t('resume.accepted')}</span>
                )}
                {s.status === 'rejected' && (
                  <span style={{ color: 'var(--gray-500)', fontSize: '0.875rem' }}>✗ {t('resume.rejected')}</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <div style={{ paddingTop: '1rem', borderTop: '1px solid var(--gray-200)' }}>
        <p style={{ marginBottom: '0.5rem' }}>
          {t('resume.statsAccepted')?.replace('{n}', String(acceptedCount))?.replace('{m}', String(suggestions.length)) ?? `Accepted ${acceptedCount}/${suggestions.length}`}
          {' · '}
          {t('resume.rejected')}: {rejectedCount}
          {' · '}
          {t('resume.pending')}: {pendingCount}
        </p>
        <button
          type="button"
          className="btn btn-primary"
          onClick={onContinue}
          disabled={acceptedCount === 0}
        >
          {t('resume.continueToComparison')}
        </button>
      </div>

      {editId && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 50 }}>
          <div style={{ background: 'var(--white)', padding: '1.5rem', borderRadius: 'var(--radius-lg)', maxWidth: '90%', maxHeight: '80%', overflow: 'auto' }}>
            <h3>{t('resume.editSuggestion')}</h3>
            <textarea
              value={editText}
              onChange={(e) => setEditText(e.target.value)}
              rows={6}
              style={{ width: '100%', marginTop: '0.5rem', padding: '0.5rem' }}
            />
            <div style={{ marginTop: '1rem', display: 'flex', gap: '0.5rem' }}>
              <button type="button" className="btn btn-primary" onClick={() => editId && handleStatus(editId, 'edited', editText)}>
                {t('resume.saveEdit')}
              </button>
              <button type="button" className="btn btn-ghost" onClick={() => setEditId(null)}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
