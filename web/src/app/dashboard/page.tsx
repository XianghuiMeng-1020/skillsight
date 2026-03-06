'use client';

import { useEffect, useState, useMemo, memo } from 'react';
import dynamic from 'next/dynamic';
import Link from 'next/link';
import Sidebar from '@/components/Sidebar';
import { AchievementNotification } from '@/components/Achievements';
import { LearningPathCard } from '@/components/LearningPath';
import { ShareButton } from '@/components/ShareCard';

const AchievementsPanel = dynamic(() => import('@/components/Achievements').then(m => ({ default: m.AchievementsPanel })), { ssr: false });
import { useAchievements } from '@/lib/hooks';
import { studentBff, getToken } from '@/lib/bffClient';
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

export default function StudentDashboard() {
  const { t } = useLanguage();
  const [documents, setDocuments] = useState<Document[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(true);
  const [userName, setUserName] = useState('Student');
  const [showAchievements, setShowAchievements] = useState(false);

  const { achievements, totalPoints, recentUnlock, dismissRecentUnlock } = useAchievements();

  const fetchData = async () => {
    setLoading(true);
    try {
      const token = getToken();
      if (!token) {
        setDocuments([]);
        setSkills([]);
        return;
      }
      const [docsData, skillsData] = await Promise.all([
        studentBff.getDocuments(5).catch(() => ({ items: [] })),
        studentBff.getSkills(10).catch(() => ({ items: [] })),
      ]);
      setDocuments((docsData.items || []) as Document[]);
      // Transform skills data with deterministic status based on skill_id hash
      const skillsWithStatus: Skill[] = ((skillsData.items || []) as Array<Record<string, unknown>>).slice(0, 6).map((s) => {
        // Use a simple hash of skill_id to generate consistent level (0-3)
        const skillId = typeof s.skill_id === 'string' ? s.skill_id : '';
        const canonicalName = typeof s.canonical_name === 'string' ? s.canonical_name : 'Unknown Skill';
        const hash = skillId.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0);
        const level = (hash % 4);
        // Determine status based on level for consistency
        const status: Skill['status'] = level >= 2 ? 'verified' : level === 1 ? 'pending' : 'missing';
        return {
          skill_id: skillId,
          canonical_name: canonicalName,
          level,
          status
        };
      });
      setSkills(skillsWithStatus);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const userData = localStorage.getItem('user');
    if (userData) {
      const user = JSON.parse(userData);
      setUserName(user.name);
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
          </div>
          <div className="page-actions" style={{ display: 'flex', gap: '0.75rem' }}>
            <button
              onClick={() => setShowAchievements(!showAchievements)}
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
              }}
            >
              🏆 {totalPoints} {t('achievements.points')}
            </button>
            <ShareButton 
              userName={userName}
              skills={skills.map(s => ({ name: s.canonical_name, level: s.level }))}
              overallScore={Math.round(skills.reduce((sum, s) => sum + s.level * 25, 0) / Math.max(skills.length, 1))}
            />
            <Link href="/dashboard/upload" className="btn btn-primary">
              📤 {t('dashboard.uploadEvidence')}
            </Link>
          </div>
        </div>

        <div className="page-content">
          {/* Stats */}
          <div className="stats-grid">
            <div className="stat-card">
              <div className="stat-icon green">📄</div>
              <div className="stat-value">{documents.length}</div>
              <div className="stat-label">{t('dashboard.docsUploaded')}</div>
            </div>
            <div className="stat-card">
              <div className="stat-icon blue">✓</div>
              <div className="stat-value">{skills.filter(s => s.status === 'verified').length}</div>
              <div className="stat-label">{t('dashboard.skillsVerified')}</div>
            </div>
            <div className="stat-card">
              <div className="stat-icon yellow">○</div>
              <div className="stat-value">{skills.filter(s => s.status === 'pending').length}</div>
              <div className="stat-label">{t('dashboard.inProgress')}</div>
            </div>
            <div className="stat-card">
              <div className="stat-icon purple">🎯</div>
              <div className="stat-value">3</div>
              <div className="stat-label">{t('dashboard.jobsMatched')}</div>
            </div>
          </div>

          {/* Quick Actions */}
          <h2 style={{ marginBottom: '1rem' }}>{t('dashboard.quickActions')}</h2>
          <div className="action-grid" style={{ marginBottom: '2rem' }}>
            <Link href="/dashboard/upload" className="action-card">
              <div className="action-icon green">📤</div>
              <div className="action-title">{t('dashboard.uploadEvidence')}</div>
              <div className="action-desc">{t('dashboard.addDocumentsCode')}</div>
            </Link>
            <Link href="/dashboard/assessments" className="action-card">
              <div className="action-icon blue">📝</div>
              <div className="action-title">{t('dashboard.takeAssessment')}</div>
              <div className="action-desc">{t('dashboard.assessDesc')}</div>
            </Link>
            <Link href="/dashboard/jobs" className="action-card">
              <div className="action-icon purple">🎯</div>
              <div className="action-title">{t('dashboard.findJobs')}</div>
              <div className="action-desc">{t('dashboard.seeReadiness')}</div>
            </Link>
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
                  <Link href="/dashboard/documents" className="btn btn-ghost btn-sm">{t('dashboard.viewAll')}</Link>
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
                    <div key={skill.skill_id} className="skill-card" style={{ marginBottom: '0.5rem' }}>
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
                    </div>
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

          {/* 成就面板（可折叠） */}
          {showAchievements && (
            <div style={{ marginTop: '1.5rem' }}>
              <AchievementsPanel />
            </div>
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
    </div>
  );
}
