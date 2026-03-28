'use client';

import { useEffect, useState, useRef } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import Sidebar from '@/components/Sidebar';
import { useLanguage, getDateLocale } from '@/lib/contexts';
import { studentBff, getToken, BffError } from '@/lib/bffClient';

interface EvidenceItem {
  chunk_id: string;
  snippet: string;
  section_path?: string;
  page_start?: number;
  doc_id: string;
}

interface SkillEntry {
  skill_id: string;
  canonical_name: string;
  definition?: string;
  label: 'demonstrated' | 'mentioned' | 'not_enough_information' | 'not_assessed';
  rationale?: string;
  evidence_items: EvidenceItem[];
  refusal?: {
    code: string;
    message: string;
    next_step: string;
  };
}

interface ProfileData {
  subject_id: string;
  documents_count: number;
  documents: { doc_id: string; filename: string; status: string; scope: string }[];
  skills: SkillEntry[];
  generated_at: string;
}

const LABEL_KEYS: Record<string, string> = {
  demonstrated: 'skills.verified',
  mentioned: 'skills.mentioned',
  not_enough_information: 'skills.insufficient',
  not_assessed: 'skills.unassessed',
};

const LABEL_STYLE: Record<string, { color: string; bg: string; icon: string }> = {
  demonstrated:            { color: '#15803d', bg: '#dcfce7', icon: '✓' },
  mentioned:               { color: '#1d4ed8', bg: '#dbeafe', icon: '○' },
  not_enough_information:  { color: '#b45309', bg: '#fef3c7', icon: '⚠' },
  not_assessed:            { color: '#6b7280', bg: '#f3f4f6', icon: '—' },
};

export default function SkillsProfilePage() {
  const { t, language } = useLanguage();
  const locale = getDateLocale(language);
  const searchParams = useSearchParams();
  const highlightId = searchParams.get('highlight') ?? '';
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [filter, setFilter] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const highlightedRef = useRef<HTMLDivElement | null>(null);

  const fetchProfile = async () => {
    setLoading(true);
    setError(null);
    try {
      if (!getToken()) {
        setProfile(null);
        setError(t('skills.loginRequired') as string);
        setLoading(false);
        return;
      }
      const data = await studentBff.getProfile();
      setProfile(data as ProfileData);
    } catch (e) {
      if (e instanceof BffError && e.status === 401) {
        setError((t('skills.sessionExpired') as string) || 'Session expired. Please log in again.');
      } else {
        const msg = e instanceof Error ? e.message : 'Failed to load profile';
        const isNetworkError = typeof msg === 'string' && (msg === 'Failed to fetch' || msg.includes('fetch') || msg.includes('Network'));
        setError(isNetworkError ? (t('skills.networkErrorHint') as string) || msg : msg);
      }
      setProfile(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchProfile(); }, []);

  useEffect(() => {
    if (!highlightId || !profile?.skills?.length) return;
    setExpanded((prev) => new Set([...prev, highlightId]));
    const el = document.getElementById(`skill-${highlightId}`);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      (el as HTMLElement).style.setProperty('box-shadow', '0 0 0 3px var(--primary)');
      const t = setTimeout(() => {
        (el as HTMLElement).style.removeProperty('box-shadow');
      }, 2500);
      return () => clearTimeout(t);
    }
  }, [highlightId, profile?.skills?.length]);

  const toggleExpanded = (skillId: string) => {
    setExpanded(prev => {
      const next = new Set(prev);
      if (next.has(skillId)) next.delete(skillId);
      else next.add(skillId);
      return next;
    });
  };

  const skills = profile?.skills ?? [];
  const filtered = skills.filter(s => {
    const matchFilter = filter === 'all' || s.label === filter;
    const matchSearch = !searchQuery || s.canonical_name.toLowerCase().includes(searchQuery.toLowerCase());
    return matchFilter && matchSearch;
  });

  const counts = {
    all: skills.length,
    demonstrated: skills.filter(s => s.label === 'demonstrated').length,
    mentioned: skills.filter(s => s.label === 'mentioned').length,
    not_enough_information: skills.filter(s => s.label === 'not_enough_information').length,
    not_assessed: skills.filter(s => s.label === 'not_assessed').length,
  };

  return (
    <div className="app-container">
      <Sidebar />
      <main className="main-content">
        <div className="page-header">
          <div>
            <h1 className="page-title">{t('skills.profileTitle')}</h1>
            <p className="page-subtitle">
              {t('skills.claimHint')}
            </p>
          </div>
          <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
            <Link href="/export" className="btn btn-secondary btn-sm">
              📄 {t('skills.exportStatement')}
            </Link>
            <button className="btn btn-ghost btn-sm" onClick={fetchProfile}>
              ↻ {t('skills.refresh')}
            </button>
          </div>
        </div>

        <div className="page-content">
          {/* Documents summary */}
          {profile && (
            <div className="card" style={{ marginBottom: '1.5rem' }}>
              <div className="card-content" style={{
                display: 'flex', gap: '1.5rem', alignItems: 'center', flexWrap: 'wrap',
              }}>
                <div style={{ fontSize: '0.875rem', color: 'var(--gray-600)' }}>
                  <strong>{profile.documents_count}</strong> {t('skills.authorizedDocs')}
                </div>
                {profile.documents.slice(0, 3).map(d => (
                  <div key={d.doc_id} style={{
                    padding: '0.25rem 0.75rem', borderRadius: '20px',
                    background: 'var(--gray-100)', fontSize: '0.8rem', color: 'var(--gray-700)',
                  }}>
                    📄 {d.filename}
                  </div>
                ))}
                <div style={{ marginLeft: 'auto', fontSize: '0.8rem', color: 'var(--gray-400)' }}>
                  {t('skills.generatedAt')} {new Date(profile.generated_at).toLocaleString(locale)}
                </div>
              </div>
            </div>
          )}

          {/* Filter bar */}
          <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.25rem', flexWrap: 'wrap', alignItems: 'center' }}>
            {Object.entries(counts).map(([key, n]) => {
              const style = key === 'all' ? { color: 'var(--gray-700)', bg: 'var(--gray-100)' } : LABEL_STYLE[key];
              const badge = key === 'all' ? t('skills.all') : (LABEL_KEYS[key] ? t(LABEL_KEYS[key]) : key);
              return (
                <button
                  key={key}
                  onClick={() => setFilter(key)}
                  style={{
                    padding: '0.375rem 0.875rem',
                    borderRadius: '20px',
                    border: `1.5px solid ${filter === key ? (style?.color ?? '#333') : 'var(--gray-200)'}`,
                    background: filter === key ? (style?.bg ?? 'var(--gray-100)') : 'white',
                    color: filter === key ? (style?.color ?? '#333') : 'var(--gray-500)',
                    fontSize: '0.8rem',
                    fontWeight: filter === key ? 600 : 400,
                    cursor: 'pointer',
                  }}
                >
                  {badge} ({n})
                </button>
              );
            })}
            <input
              type="text"
              placeholder={t('skills.searchPlaceholder')}
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              style={{
                marginLeft: 'auto',
                padding: '0.375rem 0.75rem',
                border: '1.5px solid var(--gray-200)',
                borderRadius: '20px',
                fontSize: '0.875rem',
                outline: 'none',
                width: '180px',
              }}
            />
          </div>

          {/* Skills list */}
          {loading ? (
            <div className="loading" style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', alignItems: 'center' }}>
              <span><span className="spinner"></span> {t('skills.loading')}</span>
              <span style={{ fontSize: '0.8125rem', color: 'var(--gray-500)' }}>{t('skills.loadingSlowHint')}</span>
            </div>
          ) : error ? (
            <div className="alert alert-error">
              <span>⚠</span>
              <div style={{ flex: 1 }}>
                <strong>{t('skills.loadFailed')}</strong>
                <p style={{ marginTop: '0.25rem', fontSize: '0.875rem' }}>{error}</p>
                <p style={{ marginTop: '0.5rem', fontSize: '0.813rem' }}>
                  {t('skills.loadFailedMsg')}
                </p>
                <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.75rem' }}>
                  <button type="button" className="btn btn-secondary btn-sm" onClick={fetchProfile}>
                    {t('skills.retry')}
                  </button>
                  {!getToken() && (
                    <Link href="/login" className="btn btn-primary btn-sm">
                      {t('skills.goToLogin')}
                    </Link>
                  )}
                </div>
              </div>
            </div>
          ) : filtered.length === 0 ? (
            <div className="card">
              <div className="empty-state">
                <div className="empty-icon">🔍</div>
                <div className="empty-title">{t('skills.noMatch')}</div>
                <div className="empty-desc">
                  {t('skills.uploadFirst')}<Link href="/dashboard/upload" style={{ color: 'var(--primary)' }}>{t('skills.uploadDoc')}</Link>
                  {t('skills.andRunAssess')}
                </div>
              </div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              {filtered.map(skill => {
                const style = LABEL_STYLE[skill.label] ?? LABEL_STYLE.not_assessed;
                const badgeLabel = t(LABEL_KEYS[skill.label] ?? LABEL_KEYS.not_assessed);
                const isExpanded = expanded.has(skill.skill_id);
                const hasEvidence = skill.evidence_items.length > 0;

                return (
                  <div
                    id={`skill-${skill.skill_id}`}
                    key={skill.skill_id}
                    className="card"
                    ref={highlightId === skill.skill_id ? (r) => { highlightedRef.current = r; } : undefined}
                    style={{
                      border: `1.5px solid ${isExpanded ? 'var(--primary)' : 'var(--gray-100)'}`,
                      transition: 'border-color 0.2s, box-shadow 0.2s',
                    }}
                  >
                    {/* Skill header */}
                    <div
                      style={{
                        display: 'flex', alignItems: 'center', gap: '1rem',
                        padding: '1rem 1.25rem', cursor: 'pointer',
                      }}
                      onClick={() => toggleExpanded(skill.skill_id)}
                    >
                      {/* Status badge */}
                      <span style={{
                        padding: '0.25rem 0.625rem',
                        borderRadius: '12px',
                        background: style.bg,
                        color: style.color,
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        whiteSpace: 'nowrap',
                        minWidth: '72px',
                        textAlign: 'center',
                      }}>
                        {style.icon} {badgeLabel}
                      </span>

                      {/* Skill name */}
                      <div style={{ flex: 1 }}>
                        <div style={{ fontWeight: 600, color: 'var(--gray-900)', fontSize: '0.9375rem' }}>
                          {skill.canonical_name}
                        </div>
                        {skill.definition && (
                          <div style={{ fontSize: '0.8rem', color: 'var(--gray-500)', marginTop: '0.125rem' }}>
                            {skill.definition.slice(0, 80)}...
                          </div>
                        )}
                      </div>

                      {/* Evidence count */}
                      <div style={{ fontSize: '0.8rem', color: 'var(--gray-400)', whiteSpace: 'nowrap' }}>
                        {hasEvidence ? `${skill.evidence_items.length} ${t('skills.evidence')}` : t('skills.noEvidence')}
                      </div>

                      {/* Expand toggle */}
                      <span style={{
                        fontSize: '1rem', color: 'var(--gray-400)',
                        transform: isExpanded ? 'rotate(180deg)' : 'none',
                        transition: 'transform 0.2s',
                      }}>▼</span>
                    </div>

                    {/* Expanded: Why / Evidence */}
                    {isExpanded && (
                      <div style={{
                        borderTop: '1px solid var(--gray-100)',
                        padding: '1rem 1.25rem',
                        background: 'var(--gray-50)',
                      }}>
                        {/* Rationale */}
                        {skill.rationale && (
                          <div style={{ marginBottom: '1rem' }}>
                            <div style={{
                              fontSize: '0.75rem', fontWeight: 700, color: 'var(--gray-500)',
                              textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.375rem',
                            }}>
                              {t('skills.whyReason')}
                            </div>
                            <p style={{ fontSize: '0.875rem', color: 'var(--gray-700)', lineHeight: 1.6 }}>
                              {skill.rationale}
                            </p>
                          </div>
                        )}

                        {/* Evidence items */}
                        {hasEvidence ? (
                          <div>
                            <div style={{
                              fontSize: '0.75rem', fontWeight: 700, color: 'var(--gray-500)',
                              textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.625rem',
                            }}>
                              {t('skills.evidenceSnippet')}
                            </div>
                            {skill.evidence_items.map((ev, idx) => (
                              <div key={ev.chunk_id} style={{
                                marginBottom: '0.75rem',
                                padding: '0.75rem 1rem',
                                background: 'white',
                                borderRadius: '8px',
                                border: '1px solid var(--gray-200)',
                              }}>
                                <div style={{
                                  display: 'flex', justifyContent: 'space-between',
                                  alignItems: 'flex-start', marginBottom: '0.5rem',
                                }}>
                                  <span style={{
                                    fontSize: '0.7rem', color: 'var(--gray-400)',
                                    fontFamily: 'monospace',
                                  }}>
                                    #{idx + 1} · chunk {ev.chunk_id.slice(0, 8)}
                                    {ev.page_start != null && ` · p.${ev.page_start}`}
                                    {ev.section_path && ` · §${ev.section_path}`}
                                  </span>
                                  <Link
                                    href={`/documents/${ev.doc_id}?chunk_id=${ev.chunk_id}`}
                                    style={{
                                      fontSize: '0.75rem', color: 'var(--primary)',
                                      textDecoration: 'none', whiteSpace: 'nowrap',
                                    }}
                                  >
                                    {t('skills.viewSource')}
                                  </Link>
                                </div>
                                <p style={{
                                  fontSize: '0.875rem', color: 'var(--gray-700)',
                                  lineHeight: 1.6, margin: 0,
                                  borderLeft: '3px solid var(--primary)',
                                  paddingLeft: '0.75rem',
                                }}>
                                  {ev.snippet}
                                </p>
                              </div>
                            ))}
                          </div>
                        ) : (
                          /* Refusal UX */
                          <div style={{
                            padding: '0.875rem 1rem',
                            background: '#fff8e6',
                            borderRadius: '8px',
                            border: '1px solid #f5d66e',
                          }}>
                            <div style={{ fontWeight: 600, color: '#8a6d00', fontSize: '0.875rem', marginBottom: '0.25rem' }}>
                              ⚠️ {skill.refusal?.code === 'not_enough_information' ? t('skills.insufficient') : t('skills.needMoreInfo')}
                            </div>
                            <p style={{ fontSize: '0.813rem', color: '#5a4900', margin: '0 0 0.375rem' }}>
                              {skill.refusal?.message}
                            </p>
                            <p style={{ fontSize: '0.8rem', color: '#6b5700', fontWeight: 500, margin: 0 }}>
                              {t('skills.nextStep')}{skill.refusal?.next_step}
                            </p>
                            <Link
                              href="/dashboard/upload"
                              className="btn btn-sm"
                              style={{
                                marginTop: '0.625rem',
                                display: 'inline-block',
                                padding: '0.375rem 0.875rem',
                                background: 'var(--primary)',
                                color: 'white',
                                borderRadius: '8px',
                                fontSize: '0.8rem',
                                textDecoration: 'none',
                              }}
                            >
                              📤 {t('skills.uploadEvidence')}
                            </Link>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
