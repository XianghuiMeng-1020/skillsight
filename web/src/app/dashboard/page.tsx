'use client';

import { useEffect, useState } from 'react';
import dynamic from 'next/dynamic';
import Link from 'next/link';
import Sidebar from '@/components/Sidebar';
import { AchievementNotification } from '@/components/Achievements';
import { ShareButton } from '@/components/ShareCard';
import { AgentChat } from '@/components/AgentChat';
import SkillJobGraph from '@/components/SkillJobGraph';

const AchievementsModal = dynamic(() => import('@/components/Achievements').then(m => ({ default: m.AchievementsModal })), { ssr: false });
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

interface JobMatch {
  role_id: string;
  role_title: string;
  readiness: number;
  gaps: string[];
  skills_met: number;
  skills_total: number;
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
  const [jobMatches, setJobMatches] = useState<JobMatch[]>([]);
  const [showResumeReviewAgent, setShowResumeReviewAgent] = useState(false);

  const { totalPoints, recentUnlock, dismissRecentUnlock, unlockShareAchievement, checkSkillAchievements, checkDocumentAchievements } = useAchievements();

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
        setJobMatches(res.items || []);
      }).catch(() => {
        setJobsMatchedCount(0);
        setJobMatches([]);
      });
      const profile = profileData as ProfileResponse | null;
      const profileSkills = profile?.skills ?? [];
      const skillsWithStatus: Skill[] = profileSkills.slice(0, 12).map((s) => {
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
      checkSkillAchievements(skillsWithStatus.filter(s => s.status === 'verified').length);
      checkDocumentAchievements((docsData.items || []).length);
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

  return (
    <div className="app-container">
      <Sidebar />
      <main className="main-content">
        {/* ── Header (unchanged) ── */}
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
          {/* ── First-time hint (unchanged) ── */}
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

          {/* ── Section 1: Two side-by-side 2×2 grids ── */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '1.5rem', marginBottom: '1.5rem' }}>
            {/* Left 2×2: Stats */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
              {loading ? (
                <>
                  {[1,2,3,4].map(i => (
                    <div key={i} className="stat-card" style={{ opacity: 0.5 }}>
                      <div className="stat-content">
                        <div className="skeleton" style={{ width: '2rem', height: '1.5rem', marginBottom: '0.25rem' }}></div>
                        <div className="skeleton" style={{ width: '5rem', height: '0.75rem' }}></div>
                      </div>
                    </div>
                  ))}
                </>
              ) : (
                <>
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
                </>
              )}
            </div>

            {/* Right 2×2: Recommended Next Steps */}
            <div className="card" style={{ border: '1px solid var(--gray-200)', padding: 0 }}>
              <div className="card-header" style={{ padding: '0.75rem 1rem' }}>
                <h3 className="card-title" style={{ fontSize: '0.9375rem' }}>💡 {t('dashboard.nextSteps')}</h3>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.625rem', padding: '0.625rem 1rem 1rem' }}>
                {documents.length === 0 ? (
                  <Link
                    href="/dashboard/upload"
                    style={{ textDecoration: 'none', padding: '0.875rem', background: 'linear-gradient(135deg, var(--sage-50, #f0f7f2), var(--sage-light, #d4e6da))', borderRadius: '12px', border: '1px solid var(--sage-light, #d4e6da)', display: 'block' }}
                  >
                    <div style={{ fontWeight: 600, fontSize: '0.8125rem', color: 'var(--gray-900)', marginBottom: '0.25rem', display: 'flex', alignItems: 'center', gap: '0.375rem' }}>
                      <span>📤</span> {t('dashboard.uploadEvidence')}
                    </div>
                    <p style={{ fontSize: '0.75rem', color: 'var(--gray-600)', margin: 0, lineHeight: 1.4 }}>
                      {t('dashboard.actionUploadTip')}
                    </p>
                  </Link>
                ) : skills.filter(s => s.status === 'pending' || s.status === 'missing').length > 0 ? (
                  <Link
                    href="/dashboard/upload"
                    style={{ textDecoration: 'none', padding: '0.875rem', background: 'linear-gradient(135deg, var(--sage-50, #f0f7f2), var(--sage-light, #d4e6da))', borderRadius: '12px', border: '1px solid var(--sage-light, #d4e6da)', display: 'block' }}
                  >
                    <div style={{ fontWeight: 600, fontSize: '0.8125rem', color: 'var(--gray-900)', marginBottom: '0.25rem', display: 'flex', alignItems: 'center', gap: '0.375rem' }}>
                      <span>📊</span> {t('dashboard.addDataProject')}
                    </div>
                    <p style={{ fontSize: '0.75rem', color: 'var(--gray-600)', margin: 0, lineHeight: 1.4 }}>
                      {t('dashboard.uploadDataProjectDesc')}
                    </p>
                  </Link>
                ) : (
                  <Link
                    href="/dashboard/learning"
                    style={{ textDecoration: 'none', padding: '0.875rem', background: 'linear-gradient(135deg, var(--sage-50, #f0f7f2), var(--sage-light, #d4e6da))', borderRadius: '12px', border: '1px solid var(--sage-light, #d4e6da)', display: 'block' }}
                  >
                    <div style={{ fontWeight: 600, fontSize: '0.8125rem', color: 'var(--gray-900)', marginBottom: '0.25rem', display: 'flex', alignItems: 'center', gap: '0.375rem' }}>
                      <span>📚</span> {t('learning.path')}
                    </div>
                    <p style={{ fontSize: '0.75rem', color: 'var(--gray-600)', margin: 0, lineHeight: 1.4 }}>
                      {t('dashboard.personalizedLearningPath')}
                    </p>
                  </Link>
                )}
                <Link
                  href="/dashboard/assessments"
                  style={{ textDecoration: 'none', padding: '0.875rem', background: 'linear-gradient(135deg, var(--coral-50, #fff5f5), var(--coral-light, #fecdd3))', borderRadius: '12px', border: '1px solid var(--coral-light, #fecdd3)', display: 'block' }}
                >
                  <div style={{ fontWeight: 600, fontSize: '0.8125rem', color: 'var(--gray-900)', marginBottom: '0.25rem', display: 'flex', alignItems: 'center', gap: '0.375rem' }}>
                    <span>📝</span> {t('dashboard.assessDesc')}
                  </div>
                  <p style={{ fontSize: '0.75rem', color: 'var(--gray-600)', margin: 0, lineHeight: 1.4 }}>
                    {t('dashboard.actionAssessTip')}
                  </p>
                </Link>
                <Link
                  href="/dashboard/jobs"
                  style={{ textDecoration: 'none', padding: '0.875rem', background: 'linear-gradient(135deg, var(--peach-50, #fff8f0), var(--peach-light, #fde8c8))', borderRadius: '12px', border: '1px solid var(--peach-light, #fde8c8)', display: 'block' }}
                >
                  <div style={{ fontWeight: 600, fontSize: '0.8125rem', color: 'var(--gray-900)', marginBottom: '0.25rem', display: 'flex', alignItems: 'center', gap: '0.375rem' }}>
                    <span>🎯</span> {t('dashboard.seeReadiness')}
                  </div>
                  <p style={{ fontSize: '0.75rem', color: 'var(--gray-600)', margin: 0, lineHeight: 1.4 }}>
                    {t('dashboard.actionJobsTip')}
                  </p>
                </Link>
                <button
                  type="button"
                  onClick={() => setShowResumeReviewAgent(true)}
                  style={{ textAlign: 'left', padding: '0.875rem', background: 'linear-gradient(135deg, #f5f0ff, #ede4ff)', borderRadius: '12px', border: '1px solid #e4d8fc', cursor: 'pointer' }}
                >
                  <div style={{ fontWeight: 600, fontSize: '0.8125rem', color: 'var(--gray-900)', marginBottom: '0.25rem', display: 'flex', alignItems: 'center', gap: '0.375rem' }}>
                    <span>📄</span> {t('dashboard.reviewResume')}
                  </div>
                  <p style={{ fontSize: '0.75rem', color: 'var(--gray-600)', margin: 0, lineHeight: 1.4 }}>
                    {t('dashboard.reviewResumeDesc')}
                  </p>
                </button>
              </div>
            </div>
          </div>

          {/* ── Section 2: AI Agent greeting card (unchanged) ── */}
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

          {/* ── Section 3: Skills ↔ Jobs connection diagram ── */}
          <div style={{ marginBottom: '1.5rem' }}>
            <SkillJobGraph skills={skills} jobMatches={jobMatches} />
          </div>

          {/* ── Section 4: HKU CEDARS contact bar ── */}
          <div
            className="card"
            style={{
              border: '1px solid var(--gray-200)',
              background: 'linear-gradient(135deg, rgba(152,184,168,0.06), rgba(201,221,227,0.04))',
            }}
          >
            <div className="card-content" style={{ padding: '1rem 1.5rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '1.5rem', flexWrap: 'wrap' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexShrink: 0 }}>
                  <div
                    style={{
                      width: 40,
                      height: 40,
                      borderRadius: '10px',
                      background: 'linear-gradient(135deg, var(--sage, #98B8A8), var(--sage-dark, #7a9a8a))',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: '1.25rem',
                      color: 'white',
                    }}
                  >
                    🎓
                  </div>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: '0.9375rem', color: 'var(--gray-900)' }}>
                      {t('dashboard.cedarsTitle')}
                    </div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>
                      {t('dashboard.cedarsSubtitle')}
                    </div>
                  </div>
                </div>

                <div style={{ flex: 1, display: 'flex', gap: '1.5rem', flexWrap: 'wrap', fontSize: '0.8125rem', color: 'var(--gray-600)' }}>
                  <div>
                    <span style={{ fontWeight: 500 }}>📍</span>{' '}
                    3/F, Meng Wah Complex
                  </div>
                  <div>
                    <span style={{ fontWeight: 500 }}>🕐</span>{' '}
                    Mon–Thu 9:00–5:45pm · Fri 9:00–6:00pm
                  </div>
                  <div>
                    <span style={{ fontWeight: 500 }}>📞</span>{' '}
                    3917 2317
                  </div>
                  <div>
                    <span style={{ fontWeight: 500 }}>✉️</span>{' '}
                    <a href="mailto:careers@hku.hk" style={{ color: 'var(--primary)', textDecoration: 'none' }}>
                      careers@hku.hk
                    </a>
                  </div>
                </div>

                <a
                  href="https://www.cedars.hku.hk/careers/home"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn btn-sm btn-secondary"
                  style={{ flexShrink: 0 }}
                >
                  {t('dashboard.cedarsVisit')} →
                </a>
              </div>
            </div>
          </div>

          {/* Achievements modal */}
          {showAchievements && (
            <AchievementsModal onClose={() => setShowAchievements(false)} />
          )}
        </div>
      </main>

      {/* Achievement notification */}
      <AchievementNotification
        achievement={recentUnlock}
        onDismiss={dismissRecentUnlock}
      />

      {/* Resume review AI agent modal */}
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
