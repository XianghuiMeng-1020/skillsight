'use client';

import { useEffect, useState } from 'react';
import Sidebar from '@/components/Sidebar';
import { studentBff, getToken } from '@/lib/bffClient';
import { useLanguage } from '@/lib/contexts';

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
}

export default function JobsPage() {
  const { t } = useLanguage();
  const [roles, setRoles] = useState<Role[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedRole, setSelectedRole] = useState<Role | null>(null);
  const [recommendedCourses, setRecommendedCourses] = useState<RecommendedCourse[]>([]);
  const [coursesLoading, setCoursesLoading] = useState(false);
  const [expandedGaps, setExpandedGaps] = useState<Set<string>>(new Set());

  useEffect(() => {
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
          };
        });

        rolesWithReadiness.sort((a, b) => b.readiness - a.readiness);
        setRoles(rolesWithReadiness);
      } catch {
        setRoles([]);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const handleSelectRole = async (role: Role) => {
    setSelectedRole(role);
    setRecommendedCourses([]);
    if (role.gapDetails.length > 0) {
      setCoursesLoading(true);
      try {
        const gapSkillIds = role.gapDetails.map((g) => g.skill_id);
        const res = await studentBff.getCourseRecommendations(role.role_id, gapSkillIds);
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

  return (
    <div className="app-container">
      <Sidebar />
      <main className="main-content">
        <div className="page-header">
          <div>
            <h1 className="page-title">{t('jobs.pageTitle')}</h1>
            <p className="page-subtitle">{t('jobs.pageSubtitle')}</p>
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
                </div>
              ) : (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem' }}>
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
                          {role.readiness}%
                        </span>
                        <span style={{ fontSize: '0.875rem', color: 'var(--gray-500)' }}>{t('jobs.ready')}</span>
                      </div>
                      <div className="progress" style={{ marginBottom: '0.5rem' }}>
                        <div 
                          className={`progress-bar ${getReadinessColor(role.readiness)}`}
                          style={{ width: `${role.readiness}%` }}
                        ></div>
                      </div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>
                        {role.skills_met}/{role.skills_total} {t('jobs.skillsMet')}
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
                <table className="table">
                  <thead>
                    <tr>
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
                        <td style={{ fontWeight: 500 }}>{role.role_title}</td>
                        <td>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                            <div className="progress" style={{ width: '100px' }}>
                              <div 
                                className={`progress-bar ${getReadinessColor(role.readiness)}`}
                                style={{ width: `${role.readiness}%` }}
                              ></div>
                            </div>
                            <span style={{ fontWeight: 600 }}>{role.readiness}%</span>
                          </div>
                        </td>
                        <td>{role.skills_met}/{role.skills_total}</td>
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
              )}
            </div>
          </div>

          {/* Role Detail Modal */}
          {selectedRole && (
            <div className="modal-overlay open" onClick={() => setSelectedRole(null)}>
              <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: '600px' }}>
                <div className="modal-header">
                  <h3>{selectedRole.role_title}</h3>
                  <button className="btn btn-icon btn-ghost" onClick={() => setSelectedRole(null)}>
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
                      {selectedRole.readiness}%
                    </div>
                    <div style={{ color: 'var(--gray-500)' }}>{t('jobs.readyForRole')}</div>
                    <div className="progress" style={{ marginTop: '1rem', height: '12px' }}>
                      <div 
                        className={`progress-bar ${getReadinessColor(selectedRole.readiness)}`}
                        style={{ width: `${selectedRole.readiness}%` }}
                      ></div>
                    </div>
                  </div>

                  <h4 style={{ marginBottom: '0.75rem' }}>{t('jobs.skillsBreakdown')}</h4>
                  <div style={{ marginBottom: '1.5rem' }}>
                    <div style={{ display: 'flex', gap: '1rem', marginBottom: '0.5rem' }}>
                      <div style={{ flex: 1, padding: '1rem', background: 'var(--success-light)', borderRadius: 'var(--radius)' }}>
                        <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--success)' }}>
                          {selectedRole.skills_met}
                        </div>
                        <div style={{ fontSize: '0.875rem', color: 'var(--gray-600)' }}>{t('jobs.skillsMetLabel')}</div>
                      </div>
                      <div style={{ flex: 1, padding: '1rem', background: 'var(--error-light)', borderRadius: 'var(--radius)' }}>
                        <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--error)' }}>
                          {selectedRole.skills_total - selectedRole.skills_met}
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
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginBottom: '1.5rem' }}>
                        {selectedRole.gapDetails.map((gap, i) => (
                          <div 
                            key={i}
                            style={{ 
                              padding: '1rem', 
                              background: gap.status === 'needs_strengthening' ? '#fefce8' : '#fef2f2', 
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
                                {gap.status === 'needs_strengthening' ? ' · needs strengthening' : ' · missing proof'}
                              </div>
                            </div>
                            <a href="/dashboard/upload" className="btn btn-sm btn-secondary">
                              {t('jobs.addEvidence')}
                            </a>
                          </div>
                        ))}
                      </div>

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
                  <button className="btn btn-secondary" onClick={() => setSelectedRole(null)}>
                    {t('jobs.close')}
                  </button>
                  <a href="/dashboard/skills" className="btn btn-primary">
                    {t('jobs.viewMySkills')}
                  </a>
                </div>
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
