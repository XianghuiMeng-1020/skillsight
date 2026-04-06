'use client';

import { useState, useRef, useCallback, useMemo } from 'react';
import Link from 'next/link';
import { useLanguage } from '@/lib/contexts';
import { fmt2 } from '@/lib/formatNumber';

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

function readinessNum(r: number): number {
  return typeof r === 'number' && !Number.isNaN(r) ? r : 0;
}

interface SkillJobGraphProps {
  skills: Skill[];
  jobMatches: JobMatch[];
}

const LEVEL_TO_PERCENT: Record<number, number> = { 0: 0, 1: 30, 2: 60, 3: 90 };

interface Line {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  isGap: boolean;
}

export default function SkillJobGraph({ skills, jobMatches }: SkillJobGraphProps) {
  const { t } = useLanguage();
  const containerRef = useRef<HTMLDivElement>(null);
  const skillRefs = useRef<Map<string, HTMLDivElement>>(new Map());
  const jobRefs = useRef<Map<string, HTMLDivElement>>(new Map());
  const [hoveredJob, setHoveredJob] = useState<string | null>(null);
  const [lines, setLines] = useState<Line[]>([]);
  const [connectedSkills, setConnectedSkills] = useState<Set<string>>(new Set());

  const sortedSkills = useMemo(
    () => [...skills].sort((a, b) => b.level - a.level),
    [skills]
  );

  const sortedJobs = useMemo(
    () => [...jobMatches].sort((a, b) => b.readiness - a.readiness).slice(0, 8),
    [jobMatches]
  );

  // Build a map: for each job, which displayed skill_ids are relevant?
  // A skill is relevant if its canonical_name appears in the role's gaps (needed but unmet),
  // OR if the student has the skill (level > 0) and it's NOT a gap (implies it's met for that role).
  const jobSkillMap = useMemo(() => {
    const map = new Map<string, { skillId: string; isGap: boolean }[]>();
    for (const job of sortedJobs) {
      const gapNamesLower = new Set(job.gaps.map(g => g.toLowerCase()));
      const connected: { skillId: string; isGap: boolean }[] = [];
      for (const skill of skills) {
        const nameLower = skill.canonical_name.toLowerCase();
        if (gapNamesLower.has(nameLower)) {
          connected.push({ skillId: skill.skill_id, isGap: true });
        } else if (skill.level > 0) {
          connected.push({ skillId: skill.skill_id, isGap: false });
        }
      }
      map.set(job.role_id, connected);
    }
    return map;
  }, [sortedJobs, skills]);

  const calculateLines = useCallback((roleId: string) => {
    const container = containerRef.current;
    const jobEl = jobRefs.current.get(roleId);
    if (!container || !jobEl) return;

    const connections = jobSkillMap.get(roleId) || [];
    const containerRect = container.getBoundingClientRect();
    const jobRect = jobEl.getBoundingClientRect();

    const newLines: Line[] = [];
    const matched = new Set<string>();

    for (const conn of connections) {
      const skillEl = skillRefs.current.get(conn.skillId);
      if (!skillEl) continue;
      matched.add(conn.skillId);
      const skillRect = skillEl.getBoundingClientRect();
      newLines.push({
        x1: skillRect.right - containerRect.left,
        y1: skillRect.top + skillRect.height / 2 - containerRect.top,
        x2: jobRect.left - containerRect.left,
        y2: jobRect.top + jobRect.height / 2 - containerRect.top,
        isGap: conn.isGap,
      });
    }

    setLines(newLines);
    setConnectedSkills(matched);
  }, [jobSkillMap]);

  const handleJobHover = useCallback((roleId: string) => {
    setHoveredJob(roleId);
    calculateLines(roleId);
  }, [calculateLines]);

  const handleJobLeave = useCallback(() => {
    setHoveredJob(null);
    setLines([]);
    setConnectedSkills(new Set());
  }, []);

  const getBarColor = (level: number) => {
    if (level >= 3) return 'var(--success, #16a34a)';
    if (level >= 2) return 'var(--sage, #98B8A8)';
    if (level >= 1) return 'var(--peach, #F9CE9C)';
    return 'var(--gray-300, #d4d4d4)';
  };

  const getReadinessColor = (readiness: number) => {
    if (readiness >= 80) return 'var(--success, #16a34a)';
    if (readiness >= 60) return 'var(--sage, #98B8A8)';
    return 'var(--peach, #F9CE9C)';
  };

  if (sortedSkills.length === 0 && sortedJobs.length === 0) {
    return (
      <div className="card" style={{ border: '1px solid var(--gray-200)' }}>
        <div className="card-content" style={{ textAlign: 'center', padding: '3rem 1rem' }}>
          <div style={{ fontSize: '2.5rem', marginBottom: '0.75rem' }}>🔗</div>
          <p style={{ color: 'var(--gray-500)' }}>{t('dashboard.noSkillsGraph')}</p>
        </div>
      </div>
    );
  }

  return (
    <div
      className="card"
      style={{ border: '1px solid var(--gray-200)', overflow: 'visible' }}
    >
      <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', gap: '2rem' }}>
          <h3 className="card-title">{t('dashboard.skills')}</h3>
          <h3 className="card-title" style={{ color: 'var(--gray-400)' }}>⟷</h3>
          <h3 className="card-title">🎯 {t('dashboard.bestMatches')}</h3>
        </div>
        <span style={{ fontSize: '0.75rem', color: 'var(--gray-400)' }}>
          {t('dashboard.hoverToConnect')}
        </span>
      </div>
      <div style={{ padding: '0 1.5rem', marginTop: '-0.25rem', marginBottom: '0.5rem' }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'center', fontSize: '0.75rem', color: 'var(--gray-600)' }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem' }}>
            <span style={{ width: 22, height: 0, borderTop: '2px dashed var(--peach, #F9CE9C)' }} aria-hidden />
            {t('dashboard.graphLegendGap')}
          </span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem' }}>
            <span style={{ width: 22, height: 0, borderTop: '2px solid var(--sage, #98B8A8)' }} aria-hidden />
            {t('dashboard.graphLegendMet')}
          </span>
        </div>
        <p style={{ margin: '0.5rem 0 0', fontSize: '0.75rem', lineHeight: 1.45, color: 'var(--gray-500)' }}>
          {t('dashboard.graphConnectionHelp')}
        </p>
      </div>
      <div className="card-content" style={{ padding: '1rem 1.5rem 1.5rem' }}>
        <div
          ref={containerRef}
          style={{ position: 'relative', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '3rem' }}
        >
          {/* SVG overlay */}
          <svg
            style={{
              position: 'absolute',
              inset: 0,
              width: '100%',
              height: '100%',
              pointerEvents: 'none',
              zIndex: 1,
              overflow: 'visible',
            }}
          >
            {lines.map((line, i) => {
              const dx = line.x2 - line.x1;
              const cpx = dx * 0.4;
              return (
                <path
                  key={i}
                  d={`M ${line.x1} ${line.y1} C ${line.x1 + cpx} ${line.y1}, ${line.x2 - cpx} ${line.y2}, ${line.x2} ${line.y2}`}
                  fill="none"
                  stroke={line.isGap ? 'var(--peach, #F9CE9C)' : 'var(--sage, #98B8A8)'}
                  strokeWidth="2"
                  strokeOpacity="0.65"
                  strokeDasharray={line.isGap ? '6 4' : 'none'}
                  style={{
                    transition: 'all 0.2s ease',
                    filter: `drop-shadow(0 0 2px ${line.isGap ? 'rgba(249,206,156,0.3)' : 'rgba(152,184,168,0.3)'})`,
                  }}
                />
              );
            })}
          </svg>

          {/* Left: Skills */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', position: 'relative', zIndex: 2 }}>
            {sortedSkills.length > 0 ? sortedSkills.map((skill) => {
              const pct = LEVEL_TO_PERCENT[skill.level] ?? 0;
              const isConnected = connectedSkills.has(skill.skill_id);
              return (
                <div
                  key={skill.skill_id}
                  ref={(el) => { if (el) skillRefs.current.set(skill.skill_id, el); }}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.75rem',
                    padding: '0.625rem 0.75rem',
                    borderRadius: '10px',
                    background: isConnected ? 'rgba(152,184,168,0.12)' : 'var(--gray-50, #fafafa)',
                    border: isConnected ? '1.5px solid var(--sage, #98B8A8)' : '1px solid transparent',
                    transition: 'all 0.2s ease',
                  }}
                >
                  <Link
                    href={`/dashboard/skills?highlight=${encodeURIComponent(skill.skill_id)}`}
                    style={{
                      textDecoration: 'none',
                      color: 'var(--gray-900)',
                      fontWeight: 500,
                      fontSize: '0.875rem',
                      minWidth: '100px',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {skill.canonical_name}
                  </Link>
                  <div style={{ flex: 1, height: '6px', background: 'var(--gray-200)', borderRadius: '3px', overflow: 'hidden' }}>
                    <div
                      style={{
                        width: `${pct}%`,
                        height: '100%',
                        background: getBarColor(skill.level),
                        borderRadius: '3px',
                        transition: 'width 0.3s ease',
                      }}
                    />
                  </div>
                  <span style={{ fontSize: '0.75rem', color: 'var(--gray-500)', minWidth: '40px', textAlign: 'right' }}>
                    {fmt2(pct)}%
                  </span>
                </div>
              );
            }) : (
              <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--gray-400)', fontSize: '0.875rem' }}>
                {t('dashboard.noSkillsGraph')}
              </div>
            )}
          </div>

          {/* Right: Jobs */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', position: 'relative', zIndex: 2 }}>
            {sortedJobs.length > 0 ? sortedJobs.map((job) => {
              const isHovered = hoveredJob === job.role_id;
              const rNum = readinessNum(job.readiness);
              return (
                <div
                  key={job.role_id}
                  ref={(el) => { if (el) jobRefs.current.set(job.role_id, el); }}
                  onMouseEnter={() => handleJobHover(job.role_id)}
                  onMouseLeave={handleJobLeave}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '0.625rem 0.75rem',
                    borderRadius: '10px',
                    background: isHovered ? 'rgba(152,184,168,0.12)' : 'var(--gray-50, #fafafa)',
                    border: isHovered ? '1.5px solid var(--sage, #98B8A8)' : '1px solid transparent',
                    cursor: 'pointer',
                    transition: 'all 0.2s ease',
                  }}
                >
                  <Link
                    href="/dashboard/jobs"
                    style={{
                      textDecoration: 'none',
                      color: 'var(--gray-900)',
                      fontWeight: 500,
                      fontSize: '0.875rem',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {job.role_title}
                  </Link>
                  <span
                    style={{
                      fontSize: '0.75rem',
                      fontWeight: 600,
                      color: getReadinessColor(rNum),
                      background: `${getReadinessColor(rNum)}18`,
                      padding: '0.2rem 0.5rem',
                      borderRadius: '6px',
                      flexShrink: 0,
                    }}
                  >
                    {fmt2(rNum)}%
                  </span>
                </div>
              );
            }) : (
              <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--gray-400)', fontSize: '0.875rem' }}>
                {t('dashboard.noJobMatches')}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
