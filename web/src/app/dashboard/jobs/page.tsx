'use client';

import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import Sidebar from '@/components/Sidebar';
import { ModalShell } from '@/components/ModalShell';
import DemoSafeHint from '@/components/DemoSafeHint';
import { studentBff, getToken } from '@/lib/bffClient';
import { useLanguage } from '@/lib/contexts';
import { fmt2 } from '@/lib/formatNumber';
import { isDemoQuery, readDemoMode, withDemoQuery, writeDemoMode } from '@/lib/demoMode';

/** Clamp readiness to [0,100] for progress bar width (API may return decimals). */
function rwPct(n: number): number {
  return Math.min(100, Math.max(0, n));
}

interface GapSkill {
  skill_id: string;
  skill_name: string;
  status: string;
  achieved_level: number;
  target_level: number;
}

interface RecommendedCourse {
  course_id: string;
  course_name: string;
  credits: number;
  programme: string;
  category: string;
  skills: Array<{ skill_id: string; skill_name: string }>;
}

interface SkillAlignment {
  skill_id: string;
  skill_name: string;
  required_level: number;
  current_level: number;
  status: string;
}

interface GapEvidence {
  skill_id: string;
  skill_name: string;
  documentEvidenceCount: number;
  documentIds: string[];
  sampleSnippet?: string;
  recentAssessmentAt?: string;
  actionStatus: 'completed' | 'pending' | 'none';
}

interface Role {
  role_id: string;
  role_title: string;
  description?: string;
  readiness: number;
  skills_met: number;
  skills_total: number;
  gaps: string[];
  gapDetails: GapSkill[];
  skillAlignment: SkillAlignment[];
  gapEvidence: GapEvidence[];
}

const DEMO_ROLES: Role[] = [
  {
    role_id: 'demo-role-1',
    role_title: 'Data Analyst (Demo)',
    description: 'Demo role for presentation. Analyze datasets, communicate insights, and support business decisions.',
    readiness: 72,
    skills_met: 4,
    skills_total: 6,
    gaps: ['Data Visualization', 'Storytelling'],
    gapDetails: [
      { skill_id: 'HKU.SKILL.DATA_VIZ.v1', skill_name: 'Data Visualization', status: 'needs_strengthening', achieved_level: 1, target_level: 3 },
      { skill_id: 'HKU.SKILL.COMMUNICATION.v1', skill_name: 'Storytelling', status: 'missing_proof', achieved_level: 0, target_level: 2 },
    ],
    skillAlignment: [
      { skill_id: 'HKU.SKILL.DATA_ANALYSIS.v1', skill_name: 'Data Analysis', required_level: 3, current_level: 3, status: 'meet' },
      { skill_id: 'HKU.SKILL.SQL.v1', skill_name: 'SQL', required_level: 2, current_level: 2, status: 'meet' },
      { skill_id: 'HKU.SKILL.DATA_VIZ.v1', skill_name: 'Data Visualization', required_level: 3, current_level: 1, status: 'needs_strengthening' },
      { skill_id: 'HKU.SKILL.COMMUNICATION.v1', skill_name: 'Storytelling', required_level: 2, current_level: 0, status: 'missing_proof' },
    ],
    gapEvidence: [],
  },
  {
    role_id: 'demo-role-2',
    role_title: 'Product Analyst (Demo)',
    description: 'Demo role for product metrics, experiment analysis, and roadmap support.',
    readiness: 64,
    skills_met: 3,
    skills_total: 6,
    gaps: ['A/B Testing', 'Presentation'],
    gapDetails: [
      { skill_id: 'HKU.SKILL.EXPERIMENT.v1', skill_name: 'A/B Testing', status: 'missing_proof', achieved_level: 0, target_level: 2 },
      { skill_id: 'HKU.SKILL.PRESENTATION.v1', skill_name: 'Presentation', status: 'needs_strengthening', achieved_level: 1, target_level: 3 },
    ],
    skillAlignment: [
      { skill_id: 'HKU.SKILL.DATA_ANALYSIS.v1', skill_name: 'Data Analysis', required_level: 3, current_level: 2, status: 'needs_strengthening' },
      { skill_id: 'HKU.SKILL.EXPERIMENT.v1', skill_name: 'A/B Testing', required_level: 2, current_level: 0, status: 'missing_proof' },
      { skill_id: 'HKU.SKILL.PRESENTATION.v1', skill_name: 'Presentation', required_level: 3, current_level: 1, status: 'needs_strengthening' },
    ],
    gapEvidence: [],
  },
  {
    role_id: 'demo-role-3',
    role_title: 'Business Intelligence Intern (Demo)',
    description: 'Demo role focusing on dashboards and operational reporting.',
    readiness: 81,
    skills_met: 5,
    skills_total: 6,
    gaps: ['Dashboard Automation'],
    gapDetails: [
      { skill_id: 'HKU.SKILL.DASHBOARD.v1', skill_name: 'Dashboard Automation', status: 'needs_strengthening', achieved_level: 1, target_level: 2 },
    ],
    skillAlignment: [
      { skill_id: 'HKU.SKILL.SQL.v1', skill_name: 'SQL', required_level: 2, current_level: 2, status: 'meet' },
      { skill_id: 'HKU.SKILL.DATA_ANALYSIS.v1', skill_name: 'Data Analysis', required_level: 3, current_level: 3, status: 'meet' },
      { skill_id: 'HKU.SKILL.DASHBOARD.v1', skill_name: 'Dashboard Automation', required_level: 2, current_level: 1, status: 'needs_strengthening' },
    ],
    gapEvidence: [],
  },
];

const DEMO_COURSES_BY_ROLE: Record<string, RecommendedCourse[]> = {
  'demo-role-1': [
    { course_id: 'STAT1010', course_name: 'Data Visualization Fundamentals', credits: 6, programme: 'BSc', category: 'Elective', skills: [{ skill_id: 'HKU.SKILL.DATA_VIZ.v1', skill_name: 'Data Visualization' }] },
    { course_id: 'CCHU9007', course_name: 'Storytelling with Data', credits: 6, programme: 'Common Core', category: 'Common Core', skills: [{ skill_id: 'HKU.SKILL.COMMUNICATION.v1', skill_name: 'Storytelling' }] },
  ],
  'demo-role-2': [
    { course_id: 'COMP2211', course_name: 'Experiment Design Basics', credits: 6, programme: 'BEng', category: 'Elective', skills: [{ skill_id: 'HKU.SKILL.EXPERIMENT.v1', skill_name: 'A/B Testing' }] },
  ],
};

export default function JobsPage() {
  const { t } = useLanguage();
  const searchParams = useSearchParams();
  const [roles, setRoles] = useState<Role[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedRole, setSelectedRole] = useState<Role | null>(null);
  const [recommendedCourses, setRecommendedCourses] = useState<RecommendedCourse[]>([]);
  const [coursesLoading, setCoursesLoading] = useState(false);
  const [expandedGaps, setExpandedGaps] = useState<Set<string>>(new Set());
  const [compareRoleIds, setCompareRoleIds] = useState<string[]>([]);
  const [isDemoMode, setIsDemoMode] = useState(false);

  const comparedRoles = useMemo(
    () => compareRoleIds.map((id) => roles.find((r) => r.role_id === id)).filter((r): r is Role => Boolean(r)),
    [compareRoleIds, roles],
  );

  const attachGapEvidence = async (baseRole: Role): Promise<Role> => {
    if (baseRole.gapDetails.length === 0) return { ...baseRole, gapEvidence: [] };
    try {
      const [profileRes, recentRes, progressRes] = await Promise.all([
        studentBff.getProfile().catch(() => null),
        studentBff.getRecentAssessmentUpdates(20).catch(() => null),
        studentBff.getActionsProgress(baseRole.role_id).catch(() => null),
      ]);

      const profileSkills = ((profileRes as { skills?: Array<{ skill_id?: string; evidence_items?: Array<{ doc_id?: string; snippet?: string }> }> } | null)?.skills || []);
      const recentItems = ((recentRes as { items?: Array<{ skill_id?: string; submitted_at?: string; completed_at?: string }> } | null)?.items || []);
      const actionItems = ((progressRes as { items?: Array<{ skill_id?: string; status?: string }> } | null)?.items || []);

      const evidenceBySkill = new Map<string, { count: number; docIds: string[]; snippet?: string }>();
      for (const s of profileSkills) {
        const sid = s.skill_id || '';
        if (!sid) continue;
        const evidenceItems = s.evidence_items || [];
        const docIds = Array.from(new Set(evidenceItems.map((e) => e.doc_id || '').filter(Boolean)));
        evidenceBySkill.set(sid, {
          count: evidenceItems.length,
          docIds,
          snippet: evidenceItems.find((e) => (e.snippet || '').trim().length > 0)?.snippet,
        });
      }

      const recentBySkill = new Map<string, string>();
      for (const item of recentItems) {
        const sid = item.skill_id || '';
        if (!sid || recentBySkill.has(sid)) continue;
        recentBySkill.set(sid, item.submitted_at || item.completed_at || '');
      }

      const actionBySkill = new Map<string, 'completed' | 'pending' | 'none'>();
      for (const item of actionItems) {
        const sid = item.skill_id || '';
        if (!sid) continue;
        if (item.status === 'completed') {
          actionBySkill.set(sid, 'completed');
        } else if (!actionBySkill.has(sid)) {
          actionBySkill.set(sid, 'pending');
        }
      }

      const gapEvidence: GapEvidence[] = baseRole.gapDetails.map((gap) => {
        const ev = evidenceBySkill.get(gap.skill_id);
        return {
          skill_id: gap.skill_id,
          skill_name: gap.skill_name,
          documentEvidenceCount: ev?.count ?? 0,
          documentIds: ev?.docIds ?? [],
          sampleSnippet: ev?.snippet,
          recentAssessmentAt: recentBySkill.get(gap.skill_id),
          actionStatus: actionBySkill.get(gap.skill_id) || 'none',
        };
      });

      return { ...baseRole, gapEvidence };
    } catch {
      return { ...baseRole, gapEvidence: [] };
    }
  };

  const buildDemoRoleWithEvidence = (role: Role): Role => ({
    ...role,
    gapEvidence: role.gapDetails.map((gap) => ({
      skill_id: gap.skill_id,
      skill_name: gap.skill_name,
      documentEvidenceCount: gap.status === 'missing_proof' ? 0 : 1,
      documentIds: gap.status === 'missing_proof' ? [] : ['demo_doc_001'],
      sampleSnippet: gap.status === 'missing_proof' ? undefined : 'Built dashboard for cohort-level trend analysis and presented insights.',
      recentAssessmentAt: gap.status === 'missing_proof' ? undefined : '2026-04-01',
      actionStatus: gap.status === 'missing_proof' ? 'pending' : 'completed',
    })),
  });

  const loadDemoDataset = () => {
    const seeded = DEMO_ROLES.map(buildDemoRoleWithEvidence);
    setRoles(seeded);
    setSelectedRole(null);
    setRecommendedCourses([]);
    setCompareRoleIds([]);
    setIsDemoMode(true);
    setLoading(false);
    writeDemoMode(true);
  };

  useEffect(() => {
    if (isDemoQuery(searchParams.get('demo'))) {
      loadDemoDataset();
      return;
    }
    if (readDemoMode()) {
      loadDemoDataset();
      return;
    }
    const token = getToken();
    if (!token) {
      setLoading(false);
      return;
    }
    const load = async () => {
      try {
        const [rolesData, docsData] = await Promise.all([
          studentBff.getRoles(20),
          studentBff.getDocuments(1).catch(() => ({ items: [] })),
        ]);
        const latestDocId = ((docsData as { items?: Array<{ doc_id?: string }> }).items || [])[0]?.doc_id;
        const items = (rolesData.items || []) as Array<Record<string, unknown>>;
        const roleIds = items.map(r => typeof r.role_id === 'string' ? r.role_id : '').filter(Boolean);

        // Fetch readiness via lightweight batch (single-pass SQL, fits in 30s timeout)
        type BatchItem = { role_id: string; role_title: string; readiness: number; skills_met?: number; skills_total?: number; gaps?: string[] };
        const batchMap = new Map<string, BatchItem>();
        if (latestDocId && roleIds.length > 0) {
          try {
            const batchRes = await studentBff.getRoleAlignmentBatch(roleIds, latestDocId);
            for (const b of (batchRes.items || [])) {
              batchMap.set(b.role_id, b);
            }
          } catch { /* batch failed */ }
        }

        const rolesWithReadiness = items.map((r): Role => {
          const roleId = typeof r.role_id === 'string' ? r.role_id : '';
          const roleTitle = typeof r.role_title === 'string' ? r.role_title : '';
          const description = typeof r.description === 'string' ? r.description : undefined;
          const b = batchMap.get(roleId);

          return {
            role_id: roleId,
            role_title: roleTitle,
            description,
            readiness: b?.readiness ?? 0,
            skills_met: b?.skills_met ?? 0,
            skills_total: b?.skills_total ?? 0,
            gaps: b?.gaps ?? [],
            gapDetails: [],
            skillAlignment: [],
            gapEvidence: [],
          };
        });

        rolesWithReadiness.sort((a, b) => b.readiness - a.readiness);
        setRoles(rolesWithReadiness);
        setIsDemoMode(false);
      } catch {
        setRoles([]);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [searchParams]);

  const handleSelectRole = async (role: Role) => {
    setSelectedRole(role);
    setRecommendedCourses([]);

    if (isDemoMode) {
      const roleWithEvidence = buildDemoRoleWithEvidence(role);
      setSelectedRole(roleWithEvidence);
      setRecommendedCourses(DEMO_COURSES_BY_ROLE[role.role_id] || []);
      return;
    }

    // Lazy-fetch real alignment data if not yet loaded
    if (role.skillAlignment.length === 0) {
      try {
        const docsData = await studentBff.getDocuments(1).catch(() => ({ items: [] as Array<{ doc_id?: string }> }));
        const latestDocId = ((docsData as { items?: Array<{ doc_id?: string }> }).items || [])[0]?.doc_id;
        const alignment = await studentBff.getRoleAlignment(role.role_id, latestDocId);
        const items = (alignment.items || []) as Array<{ skill_id?: string; skill_name?: string; status?: string; achieved_level?: number; target_level?: number }>;

        const gapDetails: GapSkill[] = items
          .filter(s => s.status !== 'meet')
          .map(s => ({
            skill_id: s.skill_id || '',
            skill_name: s.skill_name || s.skill_id || '',
            status: s.status || 'missing_proof',
            achieved_level: s.achieved_level ?? 0,
            target_level: s.target_level ?? 3,
          }));

        const skillAlignment: SkillAlignment[] = items.map(s => ({
          skill_id: s.skill_id || '',
          skill_name: s.skill_name || s.skill_id || '',
          required_level: s.target_level ?? 3,
          current_level: s.achieved_level ?? 0,
          status: s.status || 'missing_proof',
        }));

        let updatedRole: Role = { ...role, gapDetails, skillAlignment };
        updatedRole = await attachGapEvidence(updatedRole);
        setSelectedRole(updatedRole);
        setRoles(prev => prev.map(r => r.role_id === role.role_id ? updatedRole : r));

        if (gapDetails.length > 0) {
          setCoursesLoading(true);
          try {
            const gapSkillIds = gapDetails.map((g) => g.skill_id).filter(Boolean);
            const res = await studentBff.getCourseRecommendations(role.role_id, gapSkillIds);
            setRecommendedCourses((res.items || []) as RecommendedCourse[]);
          } catch {
            setRecommendedCourses([]);
          } finally {
            setCoursesLoading(false);
          }
        }
      } catch {
        // alignment fetch failed; modal still shows readiness summary
      }
    } else if (role.gapDetails.length > 0) {
      const roleWithEvidence = await attachGapEvidence(role);
      setSelectedRole(roleWithEvidence);
      setRoles(prev => prev.map(r => r.role_id === role.role_id ? roleWithEvidence : r));
      setCoursesLoading(true);
      try {
        const gapSkillIds = roleWithEvidence.gapDetails.map((g) => g.skill_id);
        const res = await studentBff.getCourseRecommendations(roleWithEvidence.role_id, gapSkillIds);
        setRecommendedCourses((res.items || []) as RecommendedCourse[]);
      } catch {
        setRecommendedCourses([]);
      } finally {
        setCoursesLoading(false);
      }
    }
  };

  const getReadinessColor = (readiness: number) => {
    if (readiness >= 80) return 'success';
    if (readiness >= 60) return 'warning';
    return 'error';
  };

  const getReadinessLabel = (readiness: number) => {
    if (readiness >= 80) return t('jobs.readyLabel');
    if (readiness >= 60) return t('jobs.almostReady');
    return t('jobs.inProgress');
  };

  const toggleCompareRole = (roleId: string) => {
    setCompareRoleIds((prev) => {
      if (prev.includes(roleId)) return prev.filter((id) => id !== roleId);
      if (prev.length >= 3) return prev;
      return [...prev, roleId];
    });
  };

  return (
    <div className="app-container">
      <Sidebar />
      <main className="main-content">
        <div className="page-header">
          <div>
            <h1 className="page-title">{t('jobs.pageTitle')}</h1>
            <p className="page-subtitle">{t('jobs.pageSubtitle')}</p>
          </div>
          <div className="page-actions" style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
            {isDemoMode && <span className="badge badge-warning">{t('jobs.demoModeOn')}</span>}
            <button type="button" className="btn btn-secondary btn-sm" onClick={loadDemoDataset}>
              {t('jobs.loadDemoDataset')}
            </button>
            {isDemoMode && <DemoSafeHint severity="warn" size="compact" />}
            {isDemoMode && (
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => {
                  setIsDemoMode(false);
                  writeDemoMode(false);
                  window.location.href = '/dashboard/jobs';
                }}
              >
                {t('jobs.exitDemoMode')}
              </button>
            )}
          </div>
        </div>

        <div className="page-content">
          {/* Top Matches */}
          <div className="card" style={{ marginBottom: '1.5rem' }}>
            <div className="card-header">
              <h3 className="card-title">{t('jobs.yourBestMatches')}</h3>
            </div>
            <div className="card-content">
              {loading ? (
                <div className="loading">
                  <span className="spinner"></span>
                  {t('jobs.analyzing')}
                </div>
              ) : roles.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--gray-500)' }}>
                  <div style={{ fontSize: '2.5rem', marginBottom: '0.75rem' }}>🎯</div>
                  <p style={{ fontWeight: 500, marginBottom: '0.5rem' }}>{t('jobs.noRolesYet')}</p>
                  <p style={{ fontSize: '0.875rem' }}>{t('jobs.uploadFirst')}</p>
                  <button type="button" className="btn btn-primary btn-sm" style={{ marginTop: '0.75rem' }} onClick={loadDemoDataset}>
                    {t('jobs.tryDemoNow')}
                  </button>
                  <p style={{ marginTop: '0.5rem' }}>
                    <DemoSafeHint severity="warn" display="block" style={{ margin: '0 auto' }} />
                  </p>
                </div>
              ) : (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: '1rem' }}>
                  {roles.slice(0, 3).sort((a, b) => b.readiness - a.readiness).map((role, i) => (
                    <div 
                      key={role.role_id}
                      style={{
                        padding: '1.5rem',
                        background: i === 0 ? 'var(--hku-green-50)' : 'var(--gray-50)',
                        borderRadius: 'var(--radius-lg)',
                        border: i === 0 ? '2px solid var(--hku-green)' : '1px solid var(--gray-200)',
                        cursor: 'pointer',
                        transition: 'all 0.2s ease'
                      }}
                      onClick={() => handleSelectRole(role)}
                    >
                      {i === 0 && (
                        <span className="badge badge-success" style={{ marginBottom: '0.75rem' }}>
                          {t('jobs.bestMatch')}
                        </span>
                      )}
                      <h4 style={{ marginBottom: '0.5rem' }}>{role.role_title}</h4>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
                        <span style={{ fontSize: '1.5rem', fontWeight: 700, color: `var(--${getReadinessColor(role.readiness)})` }}>
                          {fmt2(role.readiness)}%
                        </span>
                        <span style={{ fontSize: '0.875rem', color: 'var(--gray-500)' }}>{t('jobs.ready')}</span>
                      </div>
                      <div className="progress" style={{ marginBottom: '0.5rem' }}>
                        <div 
                          className={`progress-bar ${getReadinessColor(role.readiness)}`}
                          style={{ width: `${rwPct(role.readiness)}%` }}
                        ></div>
                      </div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>
                        {fmt2(role.skills_met)}/{fmt2(role.skills_total)} {t('jobs.skillsMet')}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* All Roles */}
          <div className="card">
            <div className="card-header">
              <h3 className="card-title">{t('jobs.allRoles')}</h3>
            </div>
            <div className="card-content" style={{ padding: 0 }}>
              {loading ? (
                <div className="loading">
                  <span className="spinner"></span>
                  {t('jobs.loadingRoles')}
                </div>
              ) : (
                <div style={{ overflowX: 'auto', WebkitOverflowScrolling: 'touch' }}>
                <table className="table">
                  <thead>
                    <tr>
                      <th>{t('jobs.compare')}</th>
                      <th>{t('jobs.role')}</th>
                      <th>{t('jobs.readiness')}</th>
                      <th>{t('jobs.skills')}</th>
                      <th>{t('jobs.status')}</th>
                      <th>{t('jobs.skillGaps')}</th>
                      <th>{t('jobs.action')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {roles.map((role) => (
                      <tr key={role.role_id}>
                        <td>
                          <input
                            type="checkbox"
                            checked={compareRoleIds.includes(role.role_id)}
                            disabled={!compareRoleIds.includes(role.role_id) && compareRoleIds.length >= 3}
                            onChange={() => toggleCompareRole(role.role_id)}
                            aria-label={`${t('jobs.compare')} ${role.role_title}`}
                          />
                        </td>
                        <td style={{ fontWeight: 500 }}>{role.role_title}</td>
                        <td>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                            <div className="progress" style={{ width: '100px' }}>
                              <div 
                                className={`progress-bar ${getReadinessColor(role.readiness)}`}
                                style={{ width: `${rwPct(role.readiness)}%` }}
                              ></div>
                            </div>
                            <span style={{ fontWeight: 600 }}>{fmt2(role.readiness)}%</span>
                          </div>
                        </td>
                        <td>{fmt2(role.skills_met)}/{fmt2(role.skills_total)}</td>
                        <td>
                          <span className={`badge badge-${getReadinessColor(role.readiness)}`}>
                            {getReadinessLabel(role.readiness)}
                          </span>
                        </td>
                        <td>
                          {role.gaps.length > 0 ? (
                            <div style={{ display: 'flex', gap: '0.25rem', flexWrap: 'wrap' }}>
                              {(expandedGaps.has(role.role_id) ? role.gaps : role.gaps.slice(0, 2)).map((gap, i) => (
                                <span key={i} className="badge badge-neutral" style={{ fontSize: '0.7rem' }}>
                                  {gap}
                                </span>
                              ))}
                              {role.gaps.length > 2 && !expandedGaps.has(role.role_id) && (
                                <button
                                  className="badge badge-neutral"
                                  style={{ fontSize: '0.7rem', cursor: 'pointer', border: 'none', background: 'var(--gray-200)' }}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setExpandedGaps(prev => new Set([...prev, role.role_id]));
                                  }}
                                  title={t('jobs.clickToExpand')}
                                >
                                  +{role.gaps.length - 2} {t('jobs.more')}
                                </button>
                              )}
                              {role.gaps.length > 2 && expandedGaps.has(role.role_id) && (
                                <button
                                  className="badge badge-neutral"
                                  style={{ fontSize: '0.7rem', cursor: 'pointer', border: 'none', background: 'var(--gray-200)' }}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setExpandedGaps(prev => {
                                      const next = new Set(prev);
                                      next.delete(role.role_id);
                                      return next;
                                    });
                                  }}
                                  title={t('jobs.clickToCollapse')}
                                >
                                  ▲
                                </button>
                              )}
                            </div>
                          ) : (
                            <span style={{ color: 'var(--success)' }}>{t('jobs.allMet')}</span>
                          )}
                        </td>
                        <td>
                          <button 
                            className="btn btn-sm btn-secondary"
                            onClick={() => handleSelectRole(role)}
                          >
                            {t('jobs.viewDetails')}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                </div>
              )}
            </div>
          </div>

          {comparedRoles.length >= 2 && (
            <div className="card" style={{ marginTop: '1rem' }}>
              <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
                <h3 className="card-title">⚖️ {t('jobs.compareTitle')}</h3>
                <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                  <span style={{ fontSize: '0.8125rem', color: 'var(--gray-500)' }}>
                    {t('jobs.compareHint')}
                  </span>
                  {isDemoMode && <DemoSafeHint severity="warn" size="compact" />}
                  <button type="button" className="btn btn-ghost btn-sm" onClick={() => setCompareRoleIds([])}>
                    {t('jobs.clearCompare')}
                  </button>
                </div>
              </div>
              <div className="card-content" style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '760px' }}>
                  <tbody>
                    <tr style={{ borderBottom: '1px solid var(--gray-200)' }}>
                      <th style={{ textAlign: 'left', padding: '0.625rem 0.5rem' }}>{t('jobs.role')}</th>
                      {comparedRoles.map((r) => (
                        <td key={r.role_id} style={{ padding: '0.625rem 0.5rem', fontWeight: 600 }}>{r.role_title}</td>
                      ))}
                    </tr>
                    <tr style={{ borderBottom: '1px solid var(--gray-100)' }}>
                      <th style={{ textAlign: 'left', padding: '0.625rem 0.5rem' }}>{t('jobs.readiness')}</th>
                      {comparedRoles.map((r) => (
                        <td key={r.role_id} style={{ padding: '0.625rem 0.5rem' }}>{fmt2(r.readiness)}%</td>
                      ))}
                    </tr>
                    <tr style={{ borderBottom: '1px solid var(--gray-100)' }}>
                      <th style={{ textAlign: 'left', padding: '0.625rem 0.5rem' }}>{t('jobs.skillsMet')}</th>
                      {comparedRoles.map((r) => (
                        <td key={r.role_id} style={{ padding: '0.625rem 0.5rem' }}>{fmt2(r.skills_met)}/{fmt2(r.skills_total)}</td>
                      ))}
                    </tr>
                    <tr style={{ borderBottom: '1px solid var(--gray-100)' }}>
                      <th style={{ textAlign: 'left', padding: '0.625rem 0.5rem' }}>{t('jobs.skillGaps')}</th>
                      {comparedRoles.map((r) => (
                        <td key={r.role_id} style={{ padding: '0.625rem 0.5rem' }}>
                          {r.gaps.length > 0 ? (
                            <div style={{ display: 'flex', gap: '0.25rem', flexWrap: 'wrap' }}>
                              {r.gaps.map((g, i) => (
                                <span key={`${r.role_id}-${i}`} className="badge badge-neutral" style={{ fontSize: '0.7rem' }}>
                                  {g}
                                </span>
                              ))}
                            </div>
                          ) : (
                            <span style={{ color: 'var(--success)' }}>{t('jobs.allMet')}</span>
                          )}
                        </td>
                      ))}
                    </tr>
                    <tr>
                      <th style={{ textAlign: 'left', padding: '0.625rem 0.5rem' }}>{t('jobs.learningPathDiff')}</th>
                      {comparedRoles.map((r) => (
                        <td key={r.role_id} style={{ padding: '0.625rem 0.5rem' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                            <span style={{ fontSize: '0.8125rem', color: 'var(--gray-600)' }}>
                              {r.gaps.length > 0 ? `${t('jobs.focusOn')}: ${r.gaps.slice(0, 2).join(', ')}` : t('jobs.keepCurrentPath')}
                            </span>
                            <button type="button" className="btn btn-secondary btn-sm" onClick={() => handleSelectRole(r)}>
                              {t('jobs.viewDetails')}
                            </button>
                          </div>
                        </td>
                      ))}
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Role Detail Modal */}
          <ModalShell
            open={!!selectedRole}
            onClose={() => setSelectedRole(null)}
            titleId="job-role-modal-title"
            modalStyle={{ maxWidth: '600px' }}
          >
            {selectedRole && (
              <>
                <div className="modal-header">
                  <h3 id="job-role-modal-title">{selectedRole.role_title}</h3>
                  <button
                    type="button"
                    className="btn btn-icon btn-ghost"
                    aria-label={t('jobs.close')}
                    onClick={() => setSelectedRole(null)}
                  >
                    ✕
                  </button>
                </div>
                <div className="modal-body">
                  {selectedRole.description && (
                    <div style={{ marginBottom: '1.25rem', fontSize: '0.875rem', lineHeight: 1.6 }}>
                      {(() => {
                        // Parse description into structured sections
                        const lines = selectedRole.description.split('\n').filter(l => l.trim());
                        const sections: { title?: string; items: string[] }[] = [];
                        let currentSection: { title?: string; items: string[] } = { items: [] };
                        
                        for (const line of lines) {
                          const trimmed = line.trim();
                          if (trimmed.match(/^(Employer|Location|About the Role|What You Will Do|What You Should Have|Overview|Our Mission|About|Role Responsibilities):/i)) {
                            if (currentSection.items.length > 0 || currentSection.title) {
                              sections.push(currentSection);
                            }
                            currentSection = { title: trimmed.replace(/:$/, ''), items: [] };
                          } else if (trimmed.startsWith('•') || trimmed.startsWith('-') || trimmed.startsWith('*')) {
                            currentSection.items.push(trimmed.replace(/^[•\-*]\s*/, ''));
                          } else if (trimmed) {
                            currentSection.items.push(trimmed);
                          }
                        }
                        if (currentSection.items.length > 0 || currentSection.title) {
                          sections.push(currentSection);
                        }
                        
                        return sections.map((section, idx) => (
                          <div key={idx} style={{ marginBottom: '0.75rem' }}>
                            {section.title && (
                              <div style={{ fontWeight: 600, color: 'var(--gray-700)', marginBottom: '0.25rem' }}>
                                {section.title}
                              </div>
                            )}
                            {section.items.length > 0 && (
                              <ul style={{ margin: 0, paddingLeft: '1.25rem', color: 'var(--gray-600)' }}>
                                {section.items.map((item, i) => (
                                  <li key={i} style={{ marginBottom: '0.15rem' }}>{item}</li>
                                ))}
                              </ul>
                            )}
                          </div>
                        ));
                      })()}
                    </div>
                  )}
                  <div style={{ textAlign: 'center', marginBottom: '1.5rem' }}>
                    <div style={{ fontSize: '3rem', fontWeight: 700, color: `var(--${getReadinessColor(selectedRole.readiness)})` }}>
                      {fmt2(selectedRole.readiness)}%
                    </div>
                    <div style={{ color: 'var(--gray-500)' }}>{t('jobs.readyForRole')}</div>
                    <div className="progress" style={{ marginTop: '1rem', height: '12px' }}>
                      <div 
                        className={`progress-bar ${getReadinessColor(selectedRole.readiness)}`}
                        style={{ width: `${rwPct(selectedRole.readiness)}%` }}
                      ></div>
                    </div>
                  </div>

                  <h4 style={{ marginBottom: '0.75rem' }}>{t('jobs.skillsBreakdown')}</h4>
                  <div style={{ marginBottom: '1.5rem' }}>
                    <div style={{ display: 'flex', gap: '1rem', marginBottom: '0.5rem' }}>
                      <div style={{ flex: 1, padding: '1rem', background: 'var(--success-light)', borderRadius: 'var(--radius)' }}>
                        <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--success)' }}>
                          {fmt2(selectedRole.skills_met)}
                        </div>
                        <div style={{ fontSize: '0.875rem', color: 'var(--gray-600)' }}>{t('jobs.skillsMetLabel')}</div>
                      </div>
                      <div style={{ flex: 1, padding: '1rem', background: 'var(--error-light)', borderRadius: 'var(--radius)' }}>
                        <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--error)' }}>
                          {fmt2(selectedRole.skills_total - selectedRole.skills_met)}
                        </div>
                        <div style={{ fontSize: '0.875rem', color: 'var(--gray-600)' }}>{t('jobs.skillsNeeded')}</div>
                      </div>
                    </div>
                  </div>

                  {selectedRole.skillAlignment.length > 0 && (
                    <>
                      <h4 style={{ marginBottom: '0.75rem' }}>{t('jobs.skillComparison')}</h4>
                      <div style={{ overflowX: 'auto', marginBottom: '1.5rem' }}>
                        <table style={{ width: '100%', fontSize: '0.875rem', borderCollapse: 'collapse' }}>
                          <thead>
                            <tr style={{ borderBottom: '1px solid var(--gray-200)', textAlign: 'left' }}>
                              <th style={{ padding: '0.5rem 0.5rem 0.5rem 0' }}>{t('jobs.skillName')}</th>
                              <th style={{ padding: '0.5rem' }}>{t('jobs.requiredLevel')}</th>
                              <th style={{ padding: '0.5rem' }}>{t('jobs.currentLevel')}</th>
                              <th style={{ padding: '0.5rem' }}>{t('jobs.status')}</th>
                            </tr>
                          </thead>
                          <tbody>
                            {selectedRole.skillAlignment.map((s, i) => (
                              <tr key={i} style={{ borderBottom: '1px solid var(--gray-100)' }}>
                                <td style={{ padding: '0.5rem 0.5rem 0.5rem 0' }}>{s.skill_name}</td>
                                <td style={{ padding: '0.5rem' }}>Lv.{s.required_level}</td>
                                <td style={{ padding: '0.5rem' }}>Lv.{s.current_level}</td>
                                <td style={{ padding: '0.5rem' }}>
                                  <span className={`badge badge-${s.status === 'meet' ? 'success' : s.status === 'needs_strengthening' ? 'warning' : 'neutral'}`}>
                                    {s.status === 'meet' ? t('jobs.meet') : s.status === 'needs_strengthening' ? t('jobs.needsStrengthening') : t('jobs.missingProof')}
                                  </span>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </>
                  )}

                  {selectedRole.gapDetails.length > 0 && (
                    <>
                      <h4 style={{ marginBottom: '0.75rem' }}>{t('jobs.recommendedActions')}</h4>
                      {isDemoMode && (
                        <p style={{ marginTop: '-0.25rem', marginBottom: '0.75rem' }}>
                          <DemoSafeHint severity="warn" size="compact" />
                        </p>
                      )}
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginBottom: '1.5rem' }}>
                        {selectedRole.gapDetails.map((gap, i) => (
                          <div 
                            key={i}
                            style={{ 
                              padding: '1rem', 
                              background: gap.status === 'needs_strengthening' ? 'var(--warning-light)' : 'var(--error-light)', 
                              borderRadius: 'var(--radius)',
                              display: 'flex',
                              justifyContent: 'space-between',
                              alignItems: 'center'
                            }}
                          >
                            <div>
                              <div style={{ fontWeight: 500 }}>{gap.skill_name}</div>
                              <div style={{ fontSize: '0.813rem', color: 'var(--gray-600)' }}>
                                Lv.{gap.achieved_level} → Lv.{gap.target_level}
                                {gap.status === 'needs_strengthening' ? t('jobs.gapNeedsStrengthening') : t('jobs.gapMissingProof')}
                              </div>
                            </div>
                            <a href={withDemoQuery('/dashboard/upload', isDemoMode)} className="btn btn-sm btn-secondary">
                              {t('jobs.addEvidence')}
                            </a>
                          </div>
                        ))}
                      </div>

                      {selectedRole.gapEvidence.length > 0 && (
                        <>
                          <h4 style={{ marginBottom: '0.75rem' }}>{t('jobs.gapEvidenceTrace')}</h4>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginBottom: '1.5rem' }}>
                            {selectedRole.gapEvidence.map((ev) => {
                              const matchedCourseCount = recommendedCourses.filter((c) => c.skills.some((s) => s.skill_id === ev.skill_id)).length;
                              return (
                                <div key={ev.skill_id} style={{ padding: '0.875rem', borderRadius: 'var(--radius)', background: 'var(--gray-50)', border: '1px solid var(--gray-200)' }}>
                                  <div style={{ fontWeight: 600, marginBottom: '0.5rem' }}>{ev.skill_name}</div>
                                  <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.5rem' }}>
                                    <span className="badge badge-neutral" style={{ fontSize: '0.72rem' }}>
                                      {t('jobs.evidenceDocs')}: {fmt2(ev.documentEvidenceCount)}
                                    </span>
                                    <span className="badge badge-neutral" style={{ fontSize: '0.72rem' }}>
                                      {t('jobs.evidenceAssessment')}: {ev.recentAssessmentAt ? ev.recentAssessmentAt.slice(0, 10) : t('jobs.noRecentAssessment')}
                                    </span>
                                    <span className={`badge badge-${ev.actionStatus === 'completed' ? 'success' : ev.actionStatus === 'pending' ? 'warning' : 'neutral'}`} style={{ fontSize: '0.72rem' }}>
                                      {t('jobs.evidenceActionProgress')}: {ev.actionStatus === 'completed' ? t('jobs.actionCompleted') : ev.actionStatus === 'pending' ? t('jobs.actionPending') : t('jobs.actionNotStarted')}
                                    </span>
                                    <span className="badge badge-neutral" style={{ fontSize: '0.72rem' }}>
                                      {t('jobs.evidenceCourses')}: {fmt2(matchedCourseCount)}
                                    </span>
                                  </div>
                                  {ev.documentIds.length > 0 && (
                                    <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)', marginBottom: '0.35rem' }}>
                                      {t('jobs.evidenceDocIds')}: {ev.documentIds.join(', ')}
                                    </div>
                                  )}
                                  {ev.sampleSnippet && (
                                    <div style={{ fontSize: '0.8125rem', color: 'var(--gray-700)', lineHeight: 1.5 }}>
                                      “{ev.sampleSnippet}”
                                    </div>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        </>
                      )}

                      <h4 style={{ marginBottom: '0.75rem' }}>{t('jobs.recommendedCourses')}</h4>
                      {coursesLoading ? (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '1rem', color: 'var(--gray-500)' }}>
                          <span className="spinner" style={{ width: 16, height: 16 }}></span>
                          {t('jobs.loadingCourses')}
                        </div>
                      ) : recommendedCourses.length === 0 ? (
                        <div style={{ padding: '1rem', color: 'var(--gray-500)', fontSize: '0.875rem' }}>
                          {t('jobs.noMatchingCourses')}
                        </div>
                      ) : (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                          {recommendedCourses.slice(0, 6).map((course) => (
                            <div
                              key={course.course_id}
                              style={{
                                padding: '1rem',
                                background: 'var(--hku-green-50, #f0fdf4)',
                                borderRadius: 'var(--radius)',
                                border: '1px solid var(--hku-green, #16a34a)',
                              }}
                            >
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                                <div>
                                  <div style={{ fontWeight: 600, marginBottom: '0.25rem' }}>
                                    {course.course_id} — {course.course_name}
                                  </div>
                                  <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)', marginBottom: '0.5rem' }}>
                                    {course.programme} · {course.category} · {course.credits} credits
                                  </div>
                                  <div style={{ display: 'flex', gap: '0.25rem', flexWrap: 'wrap' }}>
                                    {course.skills.map((s) => (
                                      <span
                                        key={s.skill_id}
                                        className="badge badge-success"
                                        style={{ fontSize: '0.7rem' }}
                                      >
                                        {s.skill_name}
                                      </span>
                                    ))}
                                  </div>
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </>
                  )}
                </div>
                <div className="modal-footer">
                  <button type="button" className="btn btn-secondary" onClick={() => setSelectedRole(null)}>
                    {t('jobs.close')}
                  </button>
                  <a href={withDemoQuery('/dashboard/skills', isDemoMode)} className="btn btn-primary">
                    {t('jobs.viewMySkills')}
                  </a>
                </div>
              </>
            )}
          </ModalShell>
        </div>
      </main>
    </div>
  );
}
