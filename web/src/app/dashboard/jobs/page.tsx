'use client';

import { useEffect, useState } from 'react';
import Sidebar from '@/components/Sidebar';
import { studentBff, getToken } from '@/lib/bffClient';
import { useLanguage } from '@/lib/contexts';

interface Role {
  role_id: string;
  role_title: string;
  description?: string;
  readiness: number;
  skills_met: number;
  skills_total: number;
  gaps: string[];
}

export default function JobsPage() {
  const { t } = useLanguage();
  const [roles, setRoles] = useState<Role[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedRole, setSelectedRole] = useState<Role | null>(null);

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

        const rolesWithReadiness = await Promise.all(
          items.map(async (r): Promise<Role> => {
            const roleId = typeof r.role_id === 'string' ? r.role_id : '';
            const roleTitle = typeof r.role_title === 'string' ? r.role_title : '';
            const description = typeof r.description === 'string' ? r.description : undefined;

            try {
              const readinessRes = await studentBff.getRoleAlignment(roleId, latestDocId);
              const scored = typeof readinessRes.score === 'number' ? readinessRes.score : 0;
              const readiness = Math.round(Math.max(0, Math.min(1, scored)) * 100);
              const details = Array.isArray(readinessRes.items) ? readinessRes.items : [];
              const skills_total = details.length;
              const skills_met = details.filter((it) => it?.status === 'meet').length;
              const gaps = details
                .filter((it) => it?.status !== 'meet')
                .map((it) => String(it?.skill_id || ''))
                .filter(Boolean)
                .slice(0, 3);

              return {
                role_id: roleId,
                role_title: roleTitle,
                description,
                readiness,
                skills_met,
                skills_total,
                gaps,
              };
            } catch {
              return {
                role_id: roleId,
                role_title: roleTitle,
                description,
                readiness: 0,
                skills_met: 0,
                skills_total: 0,
                gaps: [],
              };
            }
          })
        );

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
                      onClick={() => setSelectedRole(role)}
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
                              {role.gaps.slice(0, 2).map((gap, i) => (
                                <span key={i} className="badge badge-neutral" style={{ fontSize: '0.7rem' }}>
                                  {gap}
                                </span>
                              ))}
                              {role.gaps.length > 2 && (
                                <span className="badge badge-neutral" style={{ fontSize: '0.7rem' }}>
                                  +{role.gaps.length - 2} {t('jobs.more')}
                                </span>
                              )}
                            </div>
                          ) : (
                            <span style={{ color: 'var(--success)' }}>{t('jobs.allMet')}</span>
                          )}
                        </td>
                        <td>
                          <button 
                            className="btn btn-sm btn-secondary"
                            onClick={() => setSelectedRole(role)}
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

                  {selectedRole.gaps.length > 0 && (
                    <>
                      <h4 style={{ marginBottom: '0.75rem' }}>{t('jobs.recommendedActions')}</h4>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                        {selectedRole.gaps.map((gap, i) => (
                          <div 
                            key={i}
                            style={{ 
                              padding: '1rem', 
                              background: 'var(--warning-light)', 
                              borderRadius: 'var(--radius)',
                              display: 'flex',
                              justifyContent: 'space-between',
                              alignItems: 'center'
                            }}
                          >
                            <div>
                              <div style={{ fontWeight: 500 }}>{gap}</div>
                              <div style={{ fontSize: '0.813rem', color: 'var(--gray-600)' }}>
                                {t('jobs.uploadOrAssess')}
                              </div>
                            </div>
                            <a href="/dashboard/upload" className="btn btn-sm btn-secondary">
                              {t('jobs.addEvidence')}
                            </a>
                          </div>
                        ))}
                      </div>
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
