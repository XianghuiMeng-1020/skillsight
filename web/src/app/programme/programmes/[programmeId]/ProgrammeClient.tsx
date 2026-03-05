'use client';

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import { programmeBff } from '@/lib/bffClient';

interface CoverageMatrix {
  programme_id: string;
  courses: Array<{ course_id: string; course_name: string }>;
  skills: Array<{ skill_id: string; canonical_name: string }>;
  matrix: Record<string, unknown>[];
  gap_analysis: {
    uncovered_skills: Array<{ skill_id: string; canonical_name: string }>;
    overlapping_skills: Array<{ skill_id: string; canonical_name: string; covered_by_n_courses: number }>;
  };
  generated_at: string;
}

interface TrendItem {
  period: string;
  skill_id: string;
  skill_name: string;
  assessment_label: string;
  count: number;
}

export default function ProgrammeDetailPage() {
  const { programmeId } = useParams<{ programmeId: string }>();
  const [matrix, setMatrix] = useState<CoverageMatrix | null>(null);
  const [trend, setTrend] = useState<TrendItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [activeTab, setActiveTab] = useState<'matrix' | 'trend' | 'gaps'>('matrix');

  useEffect(() => {
    const load = async () => {
      try {
        const [matrixData, trendData] = await Promise.all([
          programmeBff.getCoverageMatrix(programmeId),
          programmeBff.getTrend(programmeId),
        ]);
        setMatrix(matrixData as CoverageMatrix);
        setTrend(((trendData as { trend?: TrendItem[] }).trend) || []);
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : 'Failed to load programme data');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [programmeId]);

  const labelColor = (label: string) => {
    if (label === 'demonstrated') return '#34d399';
    if (label === 'mentioned') return '#60a5fa';
    return '#64748b';
  };

  return (
    <div style={{ minHeight: '100vh', background: '#0f172a', color: '#e2e8f0' }}>
      <nav style={{ background: '#1e293b', borderBottom: '1px solid #334155', padding: '16px 32px', display: 'flex', alignItems: 'center', gap: 16 }}>
        <button onClick={() => history.back()} style={{ background: 'none', border: 'none', color: '#a78bfa', cursor: 'pointer', fontSize: 14 }}>
          ← All Programmes
        </button>
        <span style={{ color: '#475569' }}>|</span>
        <span style={{ color: '#94a3b8' }}>{programmeId}</span>
      </nav>

      <div style={{ maxWidth: 1200, margin: '0 auto', padding: '32px 24px' }}>
        <h1 style={{ fontSize: 28, fontWeight: 700, marginBottom: 4 }}>{programmeId}</h1>
        <p style={{ color: '#64748b', fontSize: 14, marginBottom: 32 }}>
          Aggregate analytics – no individual student data displayed.
        </p>

        <div style={{ display: 'flex', gap: 4, marginBottom: 28, background: '#1e293b', borderRadius: 10, padding: 4, width: 'fit-content', border: '1px solid #334155' }}>
          {(['matrix', 'trend', 'gaps'] as const).map(tab => (
            <button key={tab} onClick={() => setActiveTab(tab)}
              style={{
                padding: '8px 20px', borderRadius: 8, border: 'none', cursor: 'pointer', fontWeight: 600, fontSize: 14,
                background: activeTab === tab ? '#7c3aed' : 'transparent',
                color: activeTab === tab ? '#fff' : '#64748b',
              }}>
              {tab === 'matrix' ? 'Coverage Matrix' : tab === 'trend' ? 'Skill Trend' : 'Gap Analysis'}
            </button>
          ))}
        </div>

        {loading && <p style={{ color: '#64748b' }}>Loading…</p>}
        {error && <p style={{ color: '#f87171' }}>{error}</p>}

        {/* Coverage Matrix tab */}
        {activeTab === 'matrix' && matrix && !loading && (
          <div>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ borderCollapse: 'collapse', minWidth: '100%' }}>
                <thead>
                  <tr>
                    <th style={{ padding: '12px 16px', textAlign: 'left', color: '#64748b', fontSize: 13, borderBottom: '1px solid #334155', background: '#1e293b' }}>
                      Course
                    </th>
                    {matrix.skills.map(skill => (
                      <th key={skill.skill_id} style={{ padding: '8px 12px', textAlign: 'center', color: '#a78bfa', fontSize: 11, borderBottom: '1px solid #334155', background: '#1e293b', maxWidth: 100, wordBreak: 'break-word' }}>
                        {skill.canonical_name}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {matrix.courses.map((course, i) => {
                    const matrixRow = matrix.matrix.find(r => (r as Record<string, unknown>).course_id === course.course_id) as Record<string, unknown> | undefined;
                    return (
                      <tr key={course.course_id} style={{ background: i % 2 === 0 ? '#1e293b' : '#162032' }}>
                        <td style={{ padding: '12px 16px', fontWeight: 600, fontSize: 14, borderBottom: '1px solid #1e293b' }}>
                          <div style={{ color: '#e2e8f0' }}>{course.course_name}</div>
                          <div style={{ fontSize: 11, color: '#64748b' }}>{course.course_id}</div>
                        </td>
                        {matrix.skills.map(skill => {
                          const val = matrixRow?.[skill.skill_id];
                          return (
                            <td key={skill.skill_id} style={{ padding: '12px 8px', textAlign: 'center', borderBottom: '1px solid #1e293b' }}>
                              {val != null ? (
                                <span style={{ display: 'inline-block', width: 24, height: 24, borderRadius: 6, background: '#34d39930', color: '#34d399', fontSize: 16, lineHeight: '24px', textAlign: 'center' }}>✓</span>
                              ) : (
                                <span style={{ display: 'inline-block', width: 24, height: 24, borderRadius: 6, background: '#334155', color: '#475569', fontSize: 14, lineHeight: '24px', textAlign: 'center' }}>–</span>
                              )}
                            </td>
                          );
                        })}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {matrix.courses.length === 0 && <p style={{ color: '#64748b', textAlign: 'center', padding: 48 }}>No courses in this programme.</p>}
          </div>
        )}

        {/* Trend tab */}
        {activeTab === 'trend' && !loading && (
          <div>
            {trend.length === 0 ? (
              <p style={{ color: '#64748b', textAlign: 'center', padding: 48 }}>No trend data available yet.</p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {trend.slice(0, 50).map((item, i) => (
                  <div key={i} style={{ background: '#1e293b', borderRadius: 10, padding: '16px 20px', border: '1px solid #334155', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <div style={{ fontSize: 12, color: '#64748b', marginBottom: 2 }}>{item.period}</div>
                      <div style={{ fontWeight: 600, color: '#e2e8f0' }}>{item.skill_name}</div>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <div style={{ fontSize: 20, fontWeight: 700, color: labelColor(item.assessment_label) }}>{item.count}</div>
                      <div style={{ fontSize: 12, color: labelColor(item.assessment_label) }}>{item.assessment_label}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Gaps tab */}
        {activeTab === 'gaps' && matrix && !loading && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
            <div style={{ background: '#1e293b', borderRadius: 12, border: '1px solid #334155', padding: 24 }}>
              <h3 style={{ margin: '0 0 16px', fontSize: 16, color: '#f87171' }}>
                Uncovered Skills ({matrix.gap_analysis.uncovered_skills.length})
              </h3>
              <p style={{ color: '#64748b', fontSize: 13, marginBottom: 16 }}>Skills in the registry not mapped to any course in this programme.</p>
              {matrix.gap_analysis.uncovered_skills.length === 0
                ? <p style={{ color: '#34d399' }}>✓ All skills are covered.</p>
                : matrix.gap_analysis.uncovered_skills.map(s => (
                    <div key={s.skill_id} style={{ padding: '8px 0', borderBottom: '1px solid #334155', color: '#94a3b8', fontSize: 14 }}>
                      {s.canonical_name}
                    </div>
                  ))
              }
            </div>
            <div style={{ background: '#1e293b', borderRadius: 12, border: '1px solid #334155', padding: 24 }}>
              <h3 style={{ margin: '0 0 16px', fontSize: 16, color: '#fbbf24' }}>
                Overlapping Skills ({matrix.gap_analysis.overlapping_skills.length})
              </h3>
              <p style={{ color: '#64748b', fontSize: 13, marginBottom: 16 }}>Skills covered by more than one course (potential redundancy).</p>
              {matrix.gap_analysis.overlapping_skills.length === 0
                ? <p style={{ color: '#94a3b8' }}>No overlapping skills.</p>
                : matrix.gap_analysis.overlapping_skills.map(s => (
                    <div key={s.skill_id} style={{ padding: '8px 0', borderBottom: '1px solid #334155', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ color: '#94a3b8', fontSize: 14 }}>{s.canonical_name}</span>
                      <span style={{ background: '#78350f30', color: '#fbbf24', padding: '2px 8px', borderRadius: 12, fontSize: 12, fontWeight: 600 }}>
                        {s.covered_by_n_courses} courses
                      </span>
                    </div>
                  ))
              }
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
