'use client';

import { useCallback, useEffect, useState } from 'react';
import dynamic from 'next/dynamic';
import Link from 'next/link';
import { useSearchParams, usePathname } from 'next/navigation';
import Sidebar from '@/components/Sidebar';
import { AchievementNotification } from '@/components/Achievements';
import { ShareButton } from '@/components/ShareCard';
import { AgentChat } from '@/components/AgentChat';
import SkillJobGraph from '@/components/SkillJobGraph';

const AchievementsModal = dynamic(() => import('@/components/Achievements').then(m => ({ default: m.AchievementsModal })), { ssr: false });
import { useAchievements } from '@/lib/hooks';
import { studentBff, getToken, type ProfileResponse } from '@/lib/bffClient';
import { useLanguage } from '@/lib/contexts';
import { fmt2, fmtInt } from '@/lib/formatNumber';
import { DEMO_DASHBOARD_DOCUMENTS, DEMO_DASHBOARD_JOB_MATCHES, DEMO_DASHBOARD_SKILLS } from '@/lib/demoDataset';
import { isDemoQuery, readDemoMode, writeDemoMode } from '@/lib/demoMode';
import { useAssessmentWidget, type AssessmentWidgetType } from '@/lib/AssessmentWidgetContext';

interface Document {
  doc_id: string;
  filename: string;
  created_at: string;
  doc_type?: string;
}

interface EvidenceSource {
  chunk_id: string;
  snippet: string;
  doc_id: string;
  filename: string;
}

interface Skill {
  skill_id: string;
  canonical_name: string;
  level: number;
  status: 'verified' | 'pending' | 'missing';
  frequency?: number;
  evidence_sources?: EvidenceSource[];
}

interface JobMatch {
  role_id: string;
  role_title: string;
  readiness: number;
  gaps: string[];
  gaps_all?: string[];
  critical_gaps?: string[];
  improvable_gaps?: string[];
  required_skills?: string[];
  required_skills_all?: string[];
  required_skills_must?: string[];
  required_skills_optional?: string[];
  skills_met: number;
  skills_total: number;
  skills_met_must?: number;
  skills_total_must?: number;
  skills_met_optional?: number;
  skills_total_optional?: number;
  match_ratio_must?: number;
  next_best_assessment?: { skill_id?: string; skill_name?: string; reason?: string } | null;
}

interface PotentialJobCandidate extends JobMatch {
  verifiedMatchCount: number;
  missingSkills: string[];
}

interface AgentAssessmentContext {
  assessmentType: AssessmentWidgetType;
  skillId: string;
  skillName: string;
}

const DEFAULT_AGENT_CONTEXT: AgentAssessmentContext = {
  assessmentType: 'communication',
  skillId: 'HKU.SKILL.COMMUNICATION.v1',
  skillName: 'Communication',
};

const SKILL_TO_AGENT_CONTEXT: Record<string, AgentAssessmentContext> = {
  communication: DEFAULT_AGENT_CONTEXT,
  presentation: { assessmentType: 'presentation', skillId: 'HKU.SKILL.PRESENTATION.v1', skillName: 'Presentation' },
  sql: { assessmentType: 'data_analysis', skillId: 'HKU.SKILL.SQL.v1', skillName: 'SQL' },
  python: { assessmentType: 'programming', skillId: 'HKU.SKILL.PYTHON.v1', skillName: 'Python' },
  'machine learning': { assessmentType: 'data_analysis', skillId: 'HKU.SKILL.ML.v1', skillName: 'Machine Learning' },
  statistics: { assessmentType: 'data_analysis', skillId: 'HKU.SKILL.STATISTICS.v1', skillName: 'Statistics' },
  'data analysis': { assessmentType: 'data_analysis', skillId: 'HKU.SKILL.DATA_ANALYSIS.v1', skillName: 'Data Analysis' },
  'data visualization': { assessmentType: 'data_analysis', skillId: 'HKU.SKILL.DATA_VIZ.v1', skillName: 'Data Visualization' },
  'deep learning': { assessmentType: 'data_analysis', skillId: 'HKU.SKILL.DEEP_LEARNING.v1', skillName: 'Deep Learning' },
};

function resolveAgentAssessmentContext(skillName?: string): AgentAssessmentContext {
  const normalized = (skillName || '').trim().toLowerCase();
  const mapped = SKILL_TO_AGENT_CONTEXT[normalized];
  if (mapped) {
    return {
      ...mapped,
      skillName: skillName || mapped.skillName,
    };
  }
  return {
    ...DEFAULT_AGENT_CONTEXT,
    skillName: skillName || DEFAULT_AGENT_CONTEXT.skillName,
  };
}

export default function StudentDashboard() {
  const { t } = useLanguage();
  const assessmentWidget = useAssessmentWidget();
  const INSIGHTS_PREF_KEY = 'skillsight-dashboard-insights-expanded-v1';
  const searchParams = useSearchParams();
  const [documents, setDocuments] = useState<Document[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(true);
  const [userName, setUserName] = useState('Student');
  const [showFirstTimeHint, setShowFirstTimeHint] = useState(false);
  const [showAchievements, setShowAchievements] = useState(false);
  const [jobsMatchedCount, setJobsMatchedCount] = useState(0);
  const [jobMatches, setJobMatches] = useState<JobMatch[]>([]);
  const [showResumeReviewAgent, setShowResumeReviewAgent] = useState(false);
  const [potentialJobs, setPotentialJobs] = useState<PotentialJobCandidate[]>([]);

  const [isDemoMode, setIsDemoMode] = useState(false);
  const [showMoreInsights, setShowMoreInsights] = useState(true);
  const [staleSkills, setStaleSkills] = useState<Array<{ skill_id: string; skill_name: string; last_updated_at?: string }>>([]);
  const [unreadNotifications, setUnreadNotifications] = useState(0);

  const pathname = usePathname();
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
      const stale = (((profile as Record<string, unknown> | null)?.stale_skills) as Array<{ skill_id: string; skill_name: string; last_updated_at?: string }> | undefined) || [];
      setStaleSkills(stale);
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
          frequency: s.frequency ?? (s.evidence_items?.length || 0),
          evidence_sources: (s.evidence_sources || []).map((es) => ({
            chunk_id: es.chunk_id,
            snippet: es.snippet,
            doc_id: es.doc_id,
            filename: es.filename || 'unknown',
          })),
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
      const demo = isDemoQuery(searchParams.get('demo')) || readDemoMode();
      if (demo) {
        writeDemoMode(true);
        setIsDemoMode(true);
        setUserName('Demo Student');
        setDocuments(DEMO_DASHBOARD_DOCUMENTS);
        setSkills(DEMO_DASHBOARD_SKILLS);
        setJobsMatchedCount(DEMO_DASHBOARD_JOB_MATCHES.length);
        setJobMatches(DEMO_DASHBOARD_JOB_MATCHES);
        setLoading(false);
        return;
      }
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

      const savedInsightsPref = localStorage.getItem(INSIGHTS_PREF_KEY);
      if (savedInsightsPref === '0') setShowMoreInsights(false);
      if (savedInsightsPref === '1') setShowMoreInsights(true);
    } catch (e) {
      console.warn('Failed to read user data from localStorage:', e);
    }

    fetchData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  useEffect(() => {
    const controller = new AbortController();
    studentBff.getNotifications(20, controller.signal)
      .then((r) => setUnreadNotifications(Number(r.unread_count || 0)))
      .catch(() => setUnreadNotifications(0));
    return () => controller.abort();
  }, [pathname]);

  const hasDocuments = documents.length > 0;
  const hasVerifiedOrScoredSkills = skills.some((s) => s.status === 'verified' || s.level > 0);
  const hasJobMatches = jobsMatchedCount > 0;
  const showNextStepCard = !loading && (!hasDocuments || !hasVerifiedOrScoredSkills || !hasJobMatches);

  const nextStep = !hasDocuments
    ? {
        hint: t('dashboard.emptyDocsHint'),
        href: '/dashboard/upload',
        label: t('dashboard.uploadEvidence'),
      }
    : !hasVerifiedOrScoredSkills
      ? {
          hint: t('dashboard.emptySkillsHint'),
          href: '/dashboard/assessments',
          label: t('dashboard.goToAssessments'),
        }
      : {
          hint: t('dashboard.emptyJobsHint'),
          href: '/dashboard/jobs',
          label: t('dashboard.goToJobs'),
        };

  const openAssessmentAgentForPotentialJob = useCallback((job: PotentialJobCandidate) => {
    const firstMissing = job.next_best_assessment?.skill_name || job.missingSkills?.[0] || '';
    const context = resolveAgentAssessmentContext(firstMissing || 'Communication');
    assessmentWidget?.setContext({
      assessmentType: context.assessmentType,
      skillId: context.skillId,
      skillName: context.skillName,
    });
    assessmentWidget?.openWidget();
  }, [assessmentWidget]);

  useEffect(() => {
    if (!assessmentWidget || potentialJobs.length === 0) return;
    const firstMissing = potentialJobs[0]?.missingSkills?.[0] || 'Communication';
    const context = resolveAgentAssessmentContext(firstMissing);
    assessmentWidget.setContext({
      assessmentType: context.assessmentType,
      skillId: context.skillId,
      skillName: context.skillName,
    });
  }, [assessmentWidget, potentialJobs]);

  return (
    <div className="app-container">
      <Sidebar />
      <main className="main-content">
        {/* ── Header (unchanged) ── */}
        <div className="page-header">
          <div>
            <h1 className="page-title">{t('dashboard.welcome')}, {userName}! 👋</h1>
            <p className="page-subtitle">{t('dashboard.subtitle')}</p>
          </div>
          <div className="page-actions" style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'nowrap' }}>
              {isDemoMode && <span className="badge badge-warning" style={{ whiteSpace: 'nowrap' }}>{t('jobs.demoModeOn')}</span>}
              <button
                onClick={() => setShowAchievements(true)}
                style={{
                  padding: '0.5rem 0.875rem',
                  borderRadius: '10px',
                  border: '2px solid #E7E5E4',
                  background: 'white',
                  color: '#44403C',
                  fontWeight: 500,
                  fontSize: '0.8125rem',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.375rem',
                  transition: 'all 0.2s ease',
                  whiteSpace: 'nowrap',
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
                🏆 {fmt2(totalPoints)} {t('achievements.points')}
              </button>
              <Link href="/dashboard/upload" className="btn btn-primary btn-sm" style={{ whiteSpace: 'nowrap' }}>
                📤 {t('dashboard.uploadEvidence')}
              </Link>
              {isDemoMode && (
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  style={{ whiteSpace: 'nowrap' }}
                  onClick={() => {
                    writeDemoMode(false);
                    window.location.href = '/dashboard';
                  }}
                >
                  {t('jobs.exitDemoMode')}
                </button>
              )}
              <Link href="/settings/notifications" className="btn btn-ghost btn-sm" style={{ whiteSpace: 'nowrap', position: 'relative', fontSize: '1rem', padding: '0.375rem 0.5rem' }}>
                🔔{unreadNotifications > 0 && <span style={{ position: 'absolute', top: 0, right: 0, background: 'var(--coral)', color: 'white', borderRadius: '50%', width: '1rem', height: '1rem', fontSize: '0.625rem', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700 }}>{unreadNotifications}</span>}
              </Link>
              <Link href="/settings" className="btn btn-ghost btn-sm" style={{ whiteSpace: 'nowrap', fontSize: '1rem', padding: '0.375rem 0.5rem' }} title={t('nav.settings') as string}>
                ⚙️
              </Link>
              <Link href="/settings/privacy" className="btn btn-ghost btn-sm" style={{ whiteSpace: 'nowrap', fontSize: '1rem', padding: '0.375rem 0.5rem' }} title={t('nav.privacy') as string}>
                🔒
              </Link>
              <ShareButton
                userName={userName}
                skills={skills.map(s => ({ name: s.canonical_name, level: s.level }))}
                overallScore={Math.round((skills.reduce((sum, s) => sum + s.level * 25, 0) / Math.max(skills.length, 1)) * 100) / 100}
                onShareSuccess={unlockShareAchievement}
              />
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

          {!loading && staleSkills.length > 0 && (
            <div className="alert" style={{ marginBottom: '1rem', border: '1px solid var(--warning, #f59e0b)', background: 'var(--warning-light, #fef3c7)' }}>
              <span className="alert-icon">⏳</span>
              <div className="alert-content">
                <div className="alert-title">{t('dashboard.skillsNeedRefresh')}</div>
                <p>
                  {staleSkills.slice(0, 4).map((s) => s.skill_name).join(', ')}
                  {staleSkills.length > 4 ? ` +${staleSkills.length - 4} ${t('dashboard.moreSuffix')}` : ''} {t('dashboard.staleSkillsHint')}
                </p>
              </div>
              <Link href="/dashboard/assessments" className="btn btn-secondary btn-sm">
                {t('dashboard.reassessNow')}
              </Link>
            </div>
          )}

          <div style={{ marginBottom: '0.75rem', display: 'flex', justifyContent: 'flex-end' }}>
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => {
                setShowMoreInsights((v) => {
                  const next = !v;
                  try {
                    localStorage.setItem(INSIGHTS_PREF_KEY, next ? '1' : '0');
                  } catch {
                    // noop
                  }
                  return next;
                });
              }}
            >
              {showMoreInsights ? t('dashboard.hideExtraDetails') : t('dashboard.learnMore')}
            </button>
          </div>

          {showNextStepCard && (
            <div className="card" style={{ marginBottom: '1rem', border: '1px solid var(--gray-200)' }}>
              <div className="card-content" style={{ padding: '0.875rem 1rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.75rem', flexWrap: 'wrap' }}>
                <div style={{ minWidth: '16rem' }}>
                  <div style={{ fontWeight: 600, marginBottom: '0.25rem' }}>🧭 {t('dashboard.emptyStateTitle')}</div>
                  <p style={{ margin: 0, fontSize: '0.8125rem', color: 'var(--gray-600)' }}>{nextStep.hint}</p>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                  <Link href={nextStep.href} className="btn btn-primary btn-sm">
                    {nextStep.label}
                  </Link>
                </div>
              </div>
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
                  <div className="stat-card fade-in" style={{ animationDelay: '0s' }} title={t('dashboard.statDocsTip')}>
                    <div className="stat-icon green">📄</div>
                    <div className="stat-content">
                      <div className="stat-value">{fmtInt(documents.length)}</div>
                      <div className="stat-label">{t('dashboard.docsUploaded')}</div>
                    </div>
                  </div>
                  <div className="stat-card fade-in" style={{ animationDelay: '0.07s' }} title={t('dashboard.statVerifiedTip')}>
                    <div className="stat-icon green">✓</div>
                    <div className="stat-content">
                      <div className="stat-value">{fmtInt(skills.filter(s => s.status === 'verified').length)}</div>
                      <div className="stat-label">{t('dashboard.skillsVerified')}</div>
                    </div>
                  </div>
                  <div className="stat-card fade-in" style={{ animationDelay: '0.14s' }} title={t('dashboard.statProgressTip')}>
                    <div className="stat-icon yellow">○</div>
                    <div className="stat-content">
                      <div className="stat-value">{fmtInt(skills.filter(s => s.status === 'pending').length)}</div>
                      <div className="stat-label">{t('dashboard.inProgress')}</div>
                    </div>
                  </div>
                  <div className="stat-card fade-in" style={{ animationDelay: '0.21s' }} title={t('dashboard.statJobsTip')}>
                    <div className="stat-icon purple">🎯</div>
                    <div className="stat-content">
                      <div className="stat-value">{fmtInt(jobsMatchedCount)}</div>
                      <div className="stat-label">{t('dashboard.jobsMatched')}</div>
                    </div>
                  </div>
                </>
              )}
            </div>

            {/* Right 2×2: Recommended Next Steps */}
            {showMoreInsights ? <div className="card" style={{ border: '1px solid var(--gray-200)', padding: 0 }}>
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
            </div> : null}
          </div>

          {/* ── Section 2: Skills ↔ Jobs connection diagram ── */}
          <div style={{ marginBottom: '1.5rem' }}>
            <SkillJobGraph
              skills={skills}
              jobMatches={jobMatches}
              onPotentialJobsChange={setPotentialJobs}
              onOpenAssessmentAssistant={openAssessmentAgentForPotentialJob}
            />
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
                    className="cedarsIcon"
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
