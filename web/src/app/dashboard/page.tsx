'use client';

import { useEffect, useState, useMemo, memo } from 'react';
import dynamic from 'next/dynamic';
import Link from 'next/link';
import Sidebar from '@/components/Sidebar';
import { AchievementNotification } from '@/components/Achievements';
import { LearningPathCard } from '@/components/LearningPath';
import { ShareButton } from '@/components/ShareCard';
import { AgentChat } from '@/components/AgentChat';

const AchievementsModal = dynamic(() => import('@/components/Achievements').then(m => ({ default: m.AchievementsModal })), { ssr: false });
import { useToast } from '@/components/Toast';
import { useAchievements } from '@/lib/hooks';
import { studentBff, getToken, type ProfileResponse } from '@/lib/bffClient';
import { useLanguage } from '@/lib/contexts';

interface Document {
  doc_id: string;
  filename: string;
  created_at: string;
  doc_type?: string;
}

interface Skill {
  skill_id: string;
  canonical_name: string;
  level: number;
  status: 'verified' | 'pending' | 'missing';
}

function PrepareSummaryButton() {
  const { t } = useLanguage();
  const { addToast } = useToast();
  const [loading, setLoading] = useState(false);
  const [summary, setSummary] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fetchSummary = async () => {
    setLoading(true);
    setError(null);
    setSummary(null);
    try {
      const data = await studentBff.getCareerSummary();
      const text = data.summary || '';
      setSummary(text);
      if (text) {
        navigator.clipboard.writeText(text);
        addToast('success', t('dashboard.summaryCopied'));
      }
    } catch {
      setError(t('common.error') || 'Failed to load');
    } finally {
      setLoading(false);
    }
  };
  const copyAndClose = () => {
    if (summary) {
      navigator.clipboard.writeText(summary);
    }
    setSummary(null);
  };
  const downloadTxt = () => {
    if (!summary) return;
    const blob = new Blob([summary], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'skillsight-advisor-summary.txt';
    a.click();
    URL.revokeObjectURL(url);
  };
  return (
    <>
      <button
        type="button"
        className="btn btn-secondary btn-sm"
        onClick={fetchSummary}
        disabled={loading}
      >
        {loading ? '...' : t('dashboard.prepareSummary')}
      </button>
      {summary && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 1000,
            background: 'rgba(0,0,0,0.4)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '1rem',
          }}
          onClick={copyAndClose}
        >
          <div
            style={{
              background: 'white',
              borderRadius: '12px',
              maxWidth: '520px',
              maxHeight: '80vh',
              overflow: 'auto',
              padding: '1.5rem',
              boxShadow: '0 8px 32px rgba(0,0,0,0.15)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <strong>{t('dashboard.summaryForAdvisor')}</strong>
              <button type="button" className="btn btn-ghost btn-sm" onClick={copyAndClose}>×</button>
            </div>
            <pre style={{ whiteSpace: 'pre-wrap', fontSize: '0.8125rem', color: 'var(--gray-700)' }}>{summary}</pre>
            <div style={{ marginTop: '1rem', display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
              <button type="button" className="btn btn-primary btn-sm" onClick={copyAndClose}>
                {t('dashboard.copyAndClose')}
              </button>
              <button type="button" className="btn btn-secondary btn-sm" onClick={downloadTxt}>
                {t('dashboard.downloadTxt')}
              </button>
            </div>
          </div>
        </div>
      )}
      {error && (
        <span style={{ fontSize: '0.75rem', color: 'var(--error)' }}>{error}</span>
      )}
    </>
  );
}

export default function StudentDashboard() {
  const { t } = useLanguage();
  const [documents, setDocuments] = useState<Document[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(true);
  const [userName, setUserName] = useState('Student');
  const [showFirstTimeHint, setShowFirstTimeHint] = useState(false);
  const [showAchievements, setShowAchievements] = useState(false);
  const [jobsMatchedCount, setJobsMatchedCount] = useState(0);
  const [showResumeReviewAgent, setShowResumeReviewAgent] = useState(false);
  const [leaderboard, setLeaderboard] = useState<{ my_rank: number | null; my_points: number; top: Array<{ rank: number; points: number }> } | null>(null);

  const { achievements, totalPoints, recentUnlock, dismissRecentUnlock, unlockShareAchievement } = useAchievements();

  const fetchData = async () => {
    setLoading(true);
    try {
      const token = getToken();
      if (!token) {
        setDocuments([]);
        setSkills([]);
        return;
      }
      const [docsData, profileData] = await Promise.all([
        studentBff.getDocuments(5).catch(() => ({ items: [] })),
        studentBff.getProfile().catch(() => null),
      ]);
      setDocuments((docsData.items || []) as Document[]);
      studentBff.getJobMatches().then((res) => {
        setJobsMatchedCount(res.count);
      }).catch(() => setJobsMatchedCount(0));
      studentBff.getLeaderboard(10).then(setLeaderboard).catch(() => setLeaderboard(null));
      // Build skills from real profile: map label to status and level
      const profile = profileData as ProfileResponse | null;
      const profileSkills = profile?.skills ?? [];
      const skillsWithStatus: Skill[] = profileSkills.slice(0, 6).map((s) => {
        const label = (s.label || 'not_assessed').toLowerCase();
        const status: Skill['status'] =
          label === 'demonstrated' || label === 'mentioned' ? 'verified'
            : label === 'not_enough_information' ? 'pending'
            : 'missing';
        const levelFromLabel = label === 'demonstrated' ? 2 : label === 'mentioned' ? 1 : 0;
        const level = typeof s.level === 'number' && s.level >= 0 && s.level <= 3 ? s.level : levelFromLabel;
        return {
          skill_id: s.skill_id,
          canonical_name: s.canonical_name || 'Unknown Skill',
          level,
          status,
        };
      });
      setSkills(skillsWithStatus);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    try {
      const userData = localStorage.getItem('user');
      if (userData) {
        const user = JSON.parse(userData);
        setUserName(user.name);
      }

      const hasSeenHint = localStorage.getItem('skillsight-first-route-seen');
      if (!hasSeenHint) {
        setShowFirstTimeHint(true);
        localStorage.setItem('skillsight-first-route-seen', 'true');
      }
    } catch (e) {
      console.warn('Failed to read user data from localStorage:', e);
    }

    fetchData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const formatTime = (dateStr: string) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const hours = Math.floor(diff / (1000 * 60 * 60));
    if (hours < 1) return t('dashboard.timeJustNow');
    if (hours < 24) return `${hours}${t('dashboard.hoursAgo')}`;
    const days = Math.floor(hours / 24);
    return `${days}${t('dashboard.daysAgo')}`;
  };

  const getDocIcon = (filename: string) => {
    const ext = filename?.split('.').pop()?.toLowerCase() || '';
    const icons: Record<string, string> = {
      pdf: '📕', docx: '📘', doc: '📘', txt: '📄', rtf: '📄', md: '📝',
      xlsx: '📊', xls: '📊', csv: '📊', pptx: '📽️', ppt: '📽️',
      jpg: '🖼️', jpeg: '🖼️', png: '🖼️', webp: '🖼️', gif: '🖼️', svg: '🖼️',
      mp4: '🎬', webm: '🎬', mov: '🎬', avi: '🎬',
      mp3: '🎵', wav: '🎵', m4a: '🎵',
      py: '🐍', ipynb: '📓', js: '💛', ts: '💙', java: '☕',
      cpp: '⚙️', c: '⚙️', go: '🔷', rs: '🦀', rb: '💎',
      json: '📋', yaml: '📋', yml: '📋', html: '🌐', css: '🎨',
    };
    return icons[ext] || '📄';
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'verified': return <span className="badge badge-success">✓ {t('dashboard.verifiedBadge')}</span>;
      case 'pending': return <span className="badge badge-warning">○ {t('dashboard.inProgressBadge')}</span>;
      case 'missing': return <span className="badge badge-error">⚠ {t('dashboard.needEvidence')}</span>;
      default: return null;
    }
  };

  return (
    <div className="app-container">
      <Sidebar />
      <main className="main-content">
        <div className="page-header">
          <div>
            <h1 className="page-title">{t('dashboard.welcome')}, {userName}! 👋</h1>
            <p className="page-subtitle">{t('dashboard.subtitle')}</p>
            <p style={{ marginTop: '0.25rem', fontSize: '0.8125rem', color: 'var(--gray-500)', maxWidth: '42rem' }}>
              {t('dashboard.visionPitch')}
            </p>
          </div>
          <div className="page-actions" style={{ display: 'flex', gap: '0.75rem' }}>
            <button
              onClick={() => setShowAchievements(true)}
              style={{
                padding: '0.625rem 1rem',
                borderRadius: '10px',
                border: '2px solid #E7E5E4',
                background: 'white',
                color: '#44403C',
                fontWeight: 500,
                fontSize: '0.875rem',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                transition: 'all 0.2s ease',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = 'var(--sage)';
                e.currentTarget.style.background = 'var(--sage-50)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = '#E7E5E4';
                e.currentTarget.style.background = 'white';
              }}
            >
              🏆 {totalPoints} {t('achievements.points')}
            </button>
            <ShareButton
              userName={userName}
              skills={skills.map(s => ({ name: s.canonical_name, level: s.level }))}
              overallScore={Math.round(skills.reduce((sum, s) => sum + s.level * 25, 0) / Math.max(skills.length, 1))}
              onShareSuccess={unlockShareAchievement}
            />
            <Link href="/dashboard/upload" className="btn btn-primary">
              📤 {t('dashboard.uploadEvidence')}
            </Link>
          </div>
        </div>

        <div className="page-content">
          {showFirstTimeHint && (
            <div className="alert" style={{ marginBottom: '1rem', border: '1px solid var(--gray-200)' }}>
              <span className="alert-icon">🧭</span>
              <div className="alert-content">
                <div className="alert-title">{t('tutorial.routeTitle')}</div>
                <p>{t('dashboard.firstTimeHint')}</p>
              </div>
              <button className="btn btn-ghost btn-sm" onClick={() => setShowFirstTimeHint(false)}>
                {t('common.close')}
              </button>
            </div>
          )}

          {/* Stats */}
          <div className="stats-grid">
            <div className="stat-card" title={t('dashboard.statDocsTip')}>
              <div className="stat-icon green">📄</div>
              <div className="stat-content">
                <div className="stat-value">{documents.length}</div>
                <div className="stat-label">{t('dashboard.docsUploaded')}</div>
              </div>
            </div>
            <div className="stat-card" title={t('dashboard.statVerifiedTip')}>
              <div className="stat-icon green">✓</div>
              <div className="stat-content">
                <div className="stat-value">{skills.filter(s => s.status === 'verified').length}</div>
                <div className="stat-label">{t('dashboard.skillsVerified')}</div>
              </div>
            </div>
            <div className="stat-card" title={t('dashboard.statProgressTip')}>
              <div className="stat-icon yellow">○</div>
              <div className="stat-content">
                <div className="stat-value">{skills.filter(s => s.status === 'pending').length}</div>
                <div className="stat-label">{t('dashboard.inProgress')}</div>
              </div>
            </div>
            <div className="stat-card" title={t('dashboard.statJobsTip')}>
              <div className="stat-icon purple">🎯</div>
              <div className="stat-content">
                <div className="stat-value">{jobsMatchedCount}</div>
                <div className="stat-label">{t('dashboard.jobsMatched')}</div>
              </div>
            </div>
          </div>

          {/* AI Agent greeting card */}
          <div
            className="card"
            style={{
              marginBottom: '1.5rem',
              background: 'linear-gradient(135deg, rgba(152,184,168,0.12), rgba(201,221,227,0.08))',
              border: '1px solid var(--sage-light, #98B8A8)',
            }}
          >
            <div className="card-content" style={{ display: 'flex', alignItems: 'center', gap: '1.25rem', flexWrap: 'wrap' }}>
              <div
                style={{
                  width: 56,
                  height: 56,
                  borderRadius: '50%',
                  background: 'linear-gradient(135deg, var(--sage), var(--sage-dark))',
                  color: 'white',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: '1.75rem',
                  flexShrink: 0,
                }}
              >
                🤖
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <p style={{ margin: 0, fontSize: '1rem', fontWeight: 500, color: 'var(--gray-900)' }}>
                  {t('dashboard.agentGreeting')}
                </p>
              </div>
              <div style={{ display: 'flex', gap: '0.75rem', flexShrink: 0 }}>
                <Link href="/dashboard/assessments" className="btn btn-primary btn-sm">
                  {t('dashboard.startAssessment')}
                </Link>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => setShowResumeReviewAgent(true)}
                >
                  {t('dashboard.reviewResume')}
                </button>
              </div>
            </div>
          </div>

          {/* Quick Actions */}
          <h2 style={{ marginBottom: '1rem' }}>{t('dashboard.quickActions')}</h2>
          <div className="action-grid" style={{ marginBottom: '2rem' }}>
            <Link href="/dashboard/upload" className="action-card" title={t('dashboard.actionUploadTip')}>
              <div className="action-icon green">📤</div>
              <div className="action-title">{t('dashboard.uploadEvidence')}</div>
              <div className="action-desc">{t('dashboard.addDocumentsCode')}</div>
            </Link>
            <Link href="/dashboard/assessments" className="action-card" title={t('dashboard.actionAssessTip')}>
              <div className="action-icon blue">📝</div>
              <div className="action-title">{t('dashboard.takeAssessment')}</div>
              <div className="action-desc">{t('dashboard.assessDesc')}</div>
            </Link>
            <Link href="/dashboard/jobs" className="action-card" title={t('dashboard.actionJobsTip')}>
              <div className="action-icon purple">🎯</div>
              <div className="action-title">{t('dashboard.findJobs')}</div>
              <div className="action-desc">{t('dashboard.seeReadiness')}</div>
            </Link>
          </div>

          {/* Leaderboard + Career Support */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem', marginBottom: '2rem' }}>
            <div className="card" style={{ border: '1px solid var(--gray-200)' }}>
              <div className="card-header">
                <h3 className="card-title">🏆 {t('dashboard.leaderboardTitle')}</h3>
              </div>
              <div className="card-content">
                <p style={{ fontSize: '0.875rem', color: 'var(--gray-600)', marginBottom: '1rem' }}>
                  {t('dashboard.leaderboardDesc')}
                </p>
                <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
                  <span style={{ fontWeight: 600, fontSize: '1.125rem' }}>
                    {t('dashboard.yourRank')}: <span style={{ color: 'var(--primary)' }}>{leaderboard?.my_rank ?? '—'}</span>
                    {leaderboard?.my_points != null && (
                      <span style={{ fontSize: '0.875rem', color: 'var(--gray-500)', marginLeft: '0.5rem' }}>({leaderboard.my_points} pts)</span>
                    )}
                  </span>
                  <span style={{ fontSize: '0.8125rem', color: 'var(--gray-500)' }}>{t('dashboard.topContributors')}:</span>
                </div>
                {leaderboard?.top && leaderboard.top.length > 0 ? (
                  <ul style={{ marginTop: '0.5rem', paddingLeft: '1.25rem', fontSize: '0.875rem', color: 'var(--gray-600)' }}>
                    {leaderboard.top.slice(0, 5).map((entry) => (
                      <li key={entry.rank}>No. {entry.rank}: {entry.points} pts</li>
                    ))}
                  </ul>
                ) : (
                  <>
                    <p style={{ marginTop: '0.75rem', fontSize: '0.75rem', color: 'var(--gray-400)' }}>
                      {t('dashboard.leaderboardPlaceholder')}
                    </p>
                    <p style={{ marginTop: '0.5rem', fontSize: '0.8125rem', color: 'var(--gray-500)' }}>
                      {t('dashboard.leaderboardCta')}{' '}
                      <Link href="/dashboard/assessments" style={{ color: 'var(--primary)', textDecoration: 'underline' }}>{t('dashboard.takeAssessment')}</Link>
                      {' · '}
                      <Link href="/dashboard/upload" style={{ color: 'var(--primary)', textDecoration: 'underline' }}>{t('dashboard.uploadEvidence')}</Link>
                    </p>
                  </>
                )}
              </div>
            </div>
            <div className="card" style={{ border: '1px solid var(--sage-light, #98B8A8)', background: 'rgba(152,184,168,0.04)' }}>
              <div className="card-header">
                <h3 className="card-title">👤 {t('dashboard.careerSupport')}</h3>
              </div>
              <div className="card-content">
                <p style={{ fontSize: '0.875rem', color: 'var(--gray-600)', marginBottom: '1rem' }}>
                  {t('dashboard.careerCentreDesc')}
                </p>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                  <a
                    href="https://www.careers.hku.hk/"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn btn-primary btn-sm"
                    style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem' }}
                  >
                    {t('dashboard.careerCentreCta')} →
                  </a>
                  <PrepareSummaryButton />
                </div>
              </div>
            </div>
          </div>

          {/* Two Column Layout */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
            {/* Recent Documents */}
            <div className="card">
              <div className="card-header">
                <h3 className="card-title">{t('dashboard.documents')}</h3>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <button 
                    onClick={(e) => { e.stopPropagation(); fetchData(); }}
                    className="btn btn-ghost btn-sm"
                    disabled={loading}
                    title={t('dashboard.refresh')}
                  >
                    {loading ? '⏳' : '🔄'}
                  </button>
                  <Link href="/dashboard/upload" className="btn btn-ghost btn-sm">{t('dashboard.viewAll')}</Link>
                </div>
              </div>
              <div className="card-content" style={{ padding: 0 }}>
                {loading ? (
                  <div className="loading">
                    <span className="spinner"></span>
                    {t('common.loading')}
                  </div>
                ) : documents.length > 0 ? (
                  <table className="table">
                    <tbody>
                      {documents.map((doc) => (
                        <tr 
                          key={doc.doc_id}
                          onClick={() => window.location.href = `/documents/${doc.doc_id}`}
                          style={{ cursor: 'pointer', transition: 'background 0.15s' }}
                          onMouseEnter={(e) => e.currentTarget.style.background = 'var(--gray-50)'}
                          onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
                        >
                          <td style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                            <span style={{ 
                              fontSize: '1.5rem',
                              width: '40px',
                              height: '40px',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              background: 'var(--gray-50)',
                              borderRadius: '10px'
                            }}>
                              {getDocIcon(doc.filename || doc.doc_type || '')}
                            </span>
                            <div>
                              <div style={{ fontWeight: 500, color: 'var(--gray-900)' }}>
                                {doc.filename?.length > 30 ? doc.filename.slice(0, 30) + '...' : doc.filename}
                              </div>
                              <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>
                                {formatTime(doc.created_at)}
                              </div>
                            </div>
                          </td>
                            <td style={{ textAlign: 'right', display: 'flex', alignItems: 'center', gap: '0.5rem', justifyContent: 'flex-end' }}>
                            <span className="badge badge-success">{t('dashboard.processed')}</span>
                            <span style={{ color: 'var(--gray-400)', fontSize: '0.875rem' }}>→</span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <div className="empty-state" style={{ padding: '2rem' }}>
                    <div className="empty-icon">📁</div>
                    <div className="empty-title">{t('dashboard.noDocumentsYet')}</div>
                    <div className="empty-desc">{t('dashboard.uploadFirstDocument')}</div>
                    <Link href="/dashboard/upload" className="btn btn-primary btn-sm">
                      📤 {t('dashboard.uploadNow')}
                    </Link>
                  </div>
                )}
              </div>
            </div>

            {/* Skills Overview */}
            <div className="card">
              <div className="card-header">
                <h3 className="card-title">{t('dashboard.skills')}</h3>
                <Link href="/dashboard/skills" className="btn btn-ghost btn-sm">{t('dashboard.viewAll')}</Link>
              </div>
              <div className="card-content" style={{ padding: '0.5rem 1rem' }}>
                {skills.length > 0 ? (
                  skills.slice(0, 4).map((skill) => (
                    <Link
                      key={skill.skill_id}
                      href={`/dashboard/skills?highlight=${encodeURIComponent(skill.skill_id)}`}
                      style={{ textDecoration: 'none', color: 'inherit', display: 'block' }}
                    >
                      <div className="skill-card" style={{ marginBottom: '0.5rem', cursor: 'pointer' }}>
                        <div className="skill-header">
                          <span className="skill-name">{skill.canonical_name}</span>
                          {getStatusBadge(skill.status)}
                        </div>
                        <div className="progress" style={{ marginTop: '0.5rem' }}>
                          <div 
                            className={`progress-bar ${skill.status === 'verified' ? 'success' : skill.status === 'pending' ? 'warning' : 'error'}`}
                            style={{ width: `${(skill.level / 3) * 100}%` }}
                          ></div>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '0.5rem', fontSize: '0.75rem', color: 'var(--gray-500)' }}>
                          <span>{t('dashboard.level')} {skill.level}/3</span>
                          <span>{skill.status === 'verified' ? `5 ${t('dashboard.evidenceItems')}` : skill.status === 'pending' ? `2 ${t('dashboard.itemsUnderReview')}` : t('dashboard.noEvidence')}</span>
                        </div>
                        <div style={{ marginTop: '0.375rem', fontSize: '0.7rem', color: 'var(--primary)' }}>
                          {t('dashboard.viewEvidence')}
                        </div>
                      </div>
                    </Link>
                  ))
                ) : (
                  <div className="empty-state" style={{ padding: '2rem' }}>
                    <div className="empty-icon">📊</div>
                    <div className="empty-title">{t('dashboard.noSkillsYet')}</div>
                    <div className="empty-desc">{t('dashboard.uploadEvidenceToStart')}</div>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* 成就弹窗 */}
          {showAchievements && (
            <AchievementsModal onClose={() => setShowAchievements(false)} />
          )}

          {/* 学习路径推荐 - 动态版 */}
          <div className="card" style={{ 
            marginTop: '1.5rem',
            border: '1px solid var(--gray-200)',
            background: 'linear-gradient(180deg, white, rgba(249,206,156,0.02))'
          }}>
            <div className="card-header" style={{ 
              background: 'linear-gradient(90deg, rgba(152,184,168,0.1), rgba(201,221,227,0.1))'
            }}>
              <h3 className="card-title" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span style={{
                  width: '28px',
                  height: '28px',
                  borderRadius: '8px',
                  background: 'linear-gradient(135deg, #98B8A8, #BBCFC3)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: '0.875rem'
                }}>🎯</span>
                {t('dashboard.personalizedLearningPath')}
              </h3>
              <Link href="/dashboard/learning" className="btn btn-ghost btn-sm">{t('dashboard.viewAll')}</Link>
            </div>
            <div className="card-content">
              <LearningPathCard 
                skills={skills.map(s => ({ name: s.canonical_name, level: s.level }))}
                maxItems={4}
              />
            </div>
          </div>

          {/* Action Recommendations - Enhanced */}
          <div className="card" style={{ 
            marginTop: '1.5rem',
            border: '1px solid var(--gray-200)',
            background: 'linear-gradient(180deg, white, rgba(249,206,156,0.02))'
          }}>
            <div className="card-header" style={{ 
              background: 'linear-gradient(90deg, rgba(249,206,156,0.05), rgba(201,221,227,0.05))'
            }}>
              <h3 className="card-title" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span style={{
                  width: '28px',
                  height: '28px',
                  borderRadius: '8px',
                  background: 'linear-gradient(135deg, var(--peach), var(--peach-dark))',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: '0.875rem'
                }}>💡</span>
                {t('dashboard.recommendations')}
              </h3>
            </div>
            <div className="card-content">
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem' }}>
                <div style={{ 
                  padding: '1.25rem', 
                  background: 'linear-gradient(135deg, var(--sage-50), var(--sage-light))', 
                  borderRadius: '16px',
                  border: '1px solid var(--sage-light)',
                  transition: 'all 0.2s ease'
                }}>
                  <div style={{ 
                    fontWeight: 600, 
                    marginBottom: '0.5rem',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.5rem'
                  }}>
                    <span>📚</span> {t('dashboard.takePythonCourse')}
                  </div>
                  <p style={{ fontSize: '0.875rem', color: 'var(--gray-600)', marginBottom: '0.75rem', lineHeight: 1.5 }}>
                    {t('dashboard.completeCOMP7404')}
                  </p>
                  <a href="#" className="btn btn-sm btn-hku" style={{ fontSize: '0.8125rem' }}>{t('dashboard.learnMore')}</a>
                </div>
                <div style={{ 
                  padding: '1.25rem', 
                  background: 'linear-gradient(135deg, var(--coral-50), var(--coral-light))', 
                  borderRadius: '16px',
                  border: '1px solid var(--coral-light)',
                  transition: 'all 0.2s ease'
                }}>
                  <div style={{ 
                    fontWeight: 600, 
                    marginBottom: '0.5rem',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.5rem'
                  }}>
                    <span>📝</span> {t('dashboard.communicationAssessment')}
                  </div>
                  <p style={{ fontSize: '0.875rem', color: 'var(--gray-600)', marginBottom: '0.75rem', lineHeight: 1.5 }}>
                    {t('dashboard.completeVideoAssessment')}
                  </p>
                  <Link href="/dashboard/assessments" className="btn btn-sm btn-primary" style={{ fontSize: '0.8125rem' }}>{t('dashboard.startNow')}</Link>
                </div>
                <div style={{ 
                  padding: '1.25rem', 
                  background: 'linear-gradient(135deg, var(--peach-50), var(--peach-light))', 
                  borderRadius: '16px',
                  border: '1px solid var(--peach-light)',
                  transition: 'all 0.2s ease'
                }}>
                  <div style={{ 
                    fontWeight: 600, 
                    marginBottom: '0.5rem',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.5rem'
                  }}>
                    <span>📊</span> {t('dashboard.addDataProject')}
                  </div>
                  <p style={{ fontSize: '0.875rem', color: 'var(--gray-600)', marginBottom: '0.75rem', lineHeight: 1.5 }}>
                    {t('dashboard.uploadDataProjectDesc')}
                  </p>
                  <Link href="/dashboard/upload" className="btn btn-sm btn-secondary" style={{ fontSize: '0.8125rem' }}>{t('dashboard.upload')}</Link>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>
      
      {/* 成就通知 */}
      <AchievementNotification 
        achievement={recentUnlock} 
        onDismiss={dismissRecentUnlock} 
      />

      {/* Resume review AI agent modal (pass doc_ids so RAG has evidence) */}
      {showResumeReviewAgent && (
        <AgentChat
          mode="resume_review"
          skillId="HKU.SKILL.COMMUNICATION.v1"
          docIds={documents.map((d) => d.doc_id)}
          onClose={() => setShowResumeReviewAgent(false)}
        />
      )}
    </div>
  );
}
