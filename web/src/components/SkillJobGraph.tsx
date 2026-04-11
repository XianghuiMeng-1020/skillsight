'use client';

import { useState, useRef, useCallback, useMemo, useEffect, type FocusEvent } from 'react';
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

export interface PotentialJobCandidate extends JobMatch {
  verifiedMatchCount: number;
  missingSkills: string[];
}

interface ScoredJob extends JobMatch {
  verifiedMatchCount: number;
  missingSkills: string[];
  matchedMustSkills: string[];
  mustMatchRatio: number;
}

export function buildRoleConnections(skills: Skill[], job: JobMatch): Array<{ skillId: string; isGap: boolean }> {
  const gapNamesLower = new Set((job.gaps_all || job.gaps || []).map(g => g.toLowerCase()));
  const requiredNamesLower = new Set((job.required_skills || []).map(s => s.toLowerCase()));
  const connected: Array<{ skillId: string; isGap: boolean }> = [];
  for (const skill of skills) {
    const nameLower = skill.canonical_name.toLowerCase();
    if (!requiredNamesLower.has(nameLower)) continue;
    if (gapNamesLower.has(nameLower)) {
      connected.push({ skillId: skill.skill_id, isGap: true });
    } else if (skill.level > 0) {
      connected.push({ skillId: skill.skill_id, isGap: false });
    }
  }
  return connected;
}

function readinessNum(r: number): number {
  return typeof r === 'number' && !Number.isNaN(r) ? r : 0;
}

function normalizedName(value: string): string {
  return value.trim().toLowerCase();
}

function countVerifiedMatches(skills: Skill[], job: JobMatch): number {
  const verifiedNames = new Set(skills.filter((s) => s.level > 0).map((s) => normalizedName(s.canonical_name)));
  const mustSkills = (job.required_skills_must && job.required_skills_must.length > 0)
    ? job.required_skills_must
    : (job.required_skills_all || job.required_skills || []);
  return mustSkills.filter((required) => verifiedNames.has(normalizedName(required))).length;
}

function collectMissingSkills(skills: Skill[], job: JobMatch): string[] {
  if (job.critical_gaps && job.critical_gaps.length > 0) {
    return [...job.critical_gaps, ...(job.improvable_gaps || [])];
  }
  const verifiedNames = new Set(skills.filter((s) => s.level > 0).map((s) => normalizedName(s.canonical_name)));
  const allRequired = (job.required_skills_all && job.required_skills_all.length > 0)
    ? job.required_skills_all
    : (job.required_skills || []);
  return allRequired.filter((required) => !verifiedNames.has(normalizedName(required)));
}

function collectMatchedMustSkills(skills: Skill[], job: JobMatch): string[] {
  const verifiedNames = new Set(skills.filter((s) => s.level > 0).map((s) => normalizedName(s.canonical_name)));
  const mustSkills = (job.required_skills_must && job.required_skills_must.length > 0)
    ? job.required_skills_must
    : (job.required_skills_all || job.required_skills || []);
  return mustSkills.filter((required) => verifiedNames.has(normalizedName(required)));
}

function computeMustMatchRatio(skills: Skill[], job: JobMatch): number {
  if (typeof job.match_ratio_must === 'number') {
    return job.match_ratio_must;
  }
  const mustSkills = (job.required_skills_must && job.required_skills_must.length > 0)
    ? job.required_skills_must
    : (job.required_skills_all || job.required_skills || []);
  if (mustSkills.length === 0) return 0;
  return collectMatchedMustSkills(skills, job).length / mustSkills.length;
}

interface SkillJobGraphProps {
  skills: Skill[];
  jobMatches: JobMatch[];
  onPotentialJobsChange?: (jobs: PotentialJobCandidate[]) => void;
  onOpenAssessmentAssistant?: (job: PotentialJobCandidate) => void;
}

const LEVEL_TO_PERCENT: Record<number, number> = { 0: 0, 1: 30, 2: 60, 3: 90 };

interface Line {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  isGap: boolean;
}

export default function SkillJobGraph({
  skills,
  jobMatches,
  onPotentialJobsChange,
  onOpenAssessmentAssistant,
}: SkillJobGraphProps) {
  const { t } = useLanguage();
  const containerRef = useRef<HTMLDivElement>(null);
  const skillRefs = useRef<Map<string, HTMLDivElement>>(new Map());
  const jobRefs = useRef<Map<string, HTMLDivElement>>(new Map());
  const [hoveredJob, setHoveredJob] = useState<string | null>(null);
  const [lines, setLines] = useState<Line[]>([]);
  const [connectedSkills, setConnectedSkills] = useState<Set<string>>(new Set());
  const [lineFilter, setLineFilter] = useState<'all' | 'gap' | 'met'>('all');
  const [isNarrow, setIsNarrow] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia('(max-width: 900px)');
    const sync = () => setIsNarrow(mq.matches);
    sync();
    mq.addEventListener('change', sync);
    return () => mq.removeEventListener('change', sync);
  }, []);

  const sortedSkills = useMemo(
    () => [...skills].sort((a, b) => b.level - a.level),
    [skills]
  );

  const { confirmedJobs, potentialJobs, visibleJobs } = useMemo(() => {
    const scored: ScoredJob[] = jobMatches.map((job) => ({
      ...job,
      verifiedMatchCount: countVerifiedMatches(skills, job),
      missingSkills: collectMissingSkills(skills, job),
      matchedMustSkills: collectMatchedMustSkills(skills, job),
      mustMatchRatio: computeMustMatchRatio(skills, job),
    }));

    const confirmed = scored
      .filter((job) => job.mustMatchRatio >= 0.7 && readinessNum(job.readiness) >= 65)
      .sort((a, b) => b.readiness - a.readiness)
      .slice(0, 5);

    const potential = scored
      .filter((job) => job.mustMatchRatio >= 0.35 && job.mustMatchRatio < 0.7 && readinessNum(job.readiness) >= 45)
      .sort((a, b) => b.readiness - a.readiness)
      .slice(0, 3);

    return {
      confirmedJobs: confirmed,
      potentialJobs: potential,
      visibleJobs: [...confirmed, ...potential],
    };
  }, [jobMatches, skills]);

  useEffect(() => {
    onPotentialJobsChange?.(potentialJobs);
  }, [onPotentialJobsChange, potentialJobs]);

  // Build a map: only connect skills explicitly required by each role.
  // Among required skills: dotted = gap, solid = met (level > 0).
  const jobSkillMap = useMemo(() => {
    const map = new Map<string, { skillId: string; isGap: boolean }[]>();
    for (const job of visibleJobs) {
      map.set(job.role_id, buildRoleConnections(skills, job));
    }
    return map;
  }, [visibleJobs, skills]);

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
    requestAnimationFrame(() => {
      setHoveredJob(roleId);
      calculateLines(roleId);
    });
  }, [calculateLines]);

  const handleJobLeave = useCallback(() => {
    setHoveredJob(null);
    setLines([]);
    setConnectedSkills(new Set());
    setLineFilter('all');
  }, []);

  const handleJobRowBlur = useCallback(
    (e: FocusEvent<HTMLDivElement>) => {
      const next = e.relatedTarget as Node | null;
      if (next && e.currentTarget.contains(next)) return;
      handleJobLeave();
    },
    [handleJobLeave],
  );

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

  const visibleLines = useMemo(
    () => lines.filter((line) => lineFilter === 'all' || (lineFilter === 'gap' ? line.isGap : !line.isGap)),
    [lines, lineFilter],
  );

  if (sortedSkills.length === 0 && visibleJobs.length === 0) {
    return (
      <div className="card" style={{ border: '1px solid var(--gray-200)' }}>
        <div className="card-content" style={{ textAlign: 'center', padding: '3rem 1rem' }}>
          <div style={{ fontSize: '2.5rem', marginBottom: '0.75rem' }}>🔗</div>
          <p style={{ color: 'var(--gray-500)' }}>{t('dashboard.noSkillsGraph')}</p>
          <Link href="/dashboard/upload" className="btn btn-primary btn-sm" style={{ marginTop: '0.75rem' }}>
            📤 {t('dashboard.uploadEvidence')}
          </Link>
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
          <button
            type="button"
            onClick={() => setLineFilter((prev) => (prev === 'gap' ? 'all' : 'gap'))}
            title={t('dashboard.graphLegendGap')}
            style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem', border: lineFilter === 'gap' ? '1px solid var(--peach, #F9CE9C)' : '1px solid transparent', borderRadius: 8, background: 'transparent', padding: '0.2rem 0.35rem', cursor: 'pointer', color: 'inherit' }}
          >
            <span style={{ width: 22, height: 0, borderTop: '2px dashed var(--peach, #F9CE9C)' }} aria-hidden />
            {t('dashboard.graphLegendGap')}
          </button>
          <button
            type="button"
            onClick={() => setLineFilter((prev) => (prev === 'met' ? 'all' : 'met'))}
            title={t('dashboard.graphLegendMet')}
            style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem', border: lineFilter === 'met' ? '1px solid var(--sage, #98B8A8)' : '1px solid transparent', borderRadius: 8, background: 'transparent', padding: '0.2rem 0.35rem', cursor: 'pointer', color: 'inherit' }}
          >
            <span style={{ width: 22, height: 0, borderTop: '2px solid var(--sage, #98B8A8)' }} aria-hidden />
            {t('dashboard.graphLegendMet')}
          </button>
        </div>
        <p style={{ margin: '0.5rem 0 0', fontSize: '0.75rem', lineHeight: 1.45, color: 'var(--gray-500)' }}>
          {t('dashboard.graphConnectionHelp')}
        </p>
      </div>
      <div className="card-content" style={{ padding: '1rem 1.5rem 1.5rem' }}>
        <div
          ref={containerRef}
          style={{ position: 'relative', display: 'grid', gridTemplateColumns: isNarrow ? '1fr' : '1fr 1fr', gap: isNarrow ? '1rem' : '3rem' }}
        >
          {/* SVG overlay */}
          <svg
            aria-hidden
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
            {visibleLines.map((line, i) => {
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
                    transition: 'all 0.25s ease',
                    filter: `drop-shadow(0 0 2px ${line.isGap ? 'rgba(249,206,156,0.3)' : 'rgba(152,184,168,0.3)'})`,
                    animation: 'fadeIn 220ms ease-out',
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
                  ref={(el) => {
                    if (el) skillRefs.current.set(skill.skill_id, el);
                    else skillRefs.current.delete(skill.skill_id);
                  }}
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
            {visibleJobs.length > 0 ? (
              <>
                {confirmedJobs.length > 0 && (
                  <div style={{ marginBottom: '0.25rem', fontSize: '0.75rem', color: 'var(--gray-500)', fontWeight: 600 }}>
                    {t('dashboard.confirmedMatches')}
                  </div>
                )}
                {confirmedJobs.map((job) => {
                  const isHovered = hoveredJob === job.role_id;
                  const rNum = readinessNum(job.readiness);
                  return (
                    <div
                      key={job.role_id}
                      ref={(el) => {
                        if (el) jobRefs.current.set(job.role_id, el);
                        else jobRefs.current.delete(job.role_id);
                      }}
                      tabIndex={0}
                      onMouseEnter={() => handleJobHover(job.role_id)}
                      onMouseLeave={handleJobLeave}
                      onFocus={() => handleJobHover(job.role_id)}
                      onBlur={handleJobRowBlur}
                      onClick={() => (hoveredJob === job.role_id ? handleJobLeave() : handleJobHover(job.role_id))}
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
                      <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontWeight: 500, fontSize: '0.875rem', color: 'var(--gray-900)' }}>
                        {job.role_title}
                      </div>
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
                })}

                {potentialJobs.length > 0 && (
                  <>
                    <div style={{ marginTop: '0.5rem', borderTop: '1px dashed var(--gray-300)', paddingTop: '0.65rem' }}>
                      <div style={{ marginBottom: '0.35rem', fontSize: '0.75rem', color: 'var(--gray-500)', fontWeight: 600 }}>
                        {t('dashboard.potentialMatches')}
                      </div>
                      <div style={{ marginBottom: '0.5rem', fontSize: '0.75rem', color: 'var(--gray-500)' }}>
                        {t('dashboard.youCouldQualify')}
                      </div>
                    </div>
                    {potentialJobs.map((job) => {
                      const isHovered = hoveredJob === job.role_id;
                      const rNum = readinessNum(job.readiness);
                      const matchedRequiredSkills = job.matchedMustSkills;
                      const matchedText = matchedRequiredSkills.slice(0, 3).join(', ');
                      const missingText = job.missingSkills.slice(0, 3).join(', ');
                      return (
                        <div
                          key={job.role_id}
                          ref={(el) => {
                            if (el) jobRefs.current.set(job.role_id, el);
                            else jobRefs.current.delete(job.role_id);
                          }}
                          tabIndex={0}
                          onMouseEnter={() => handleJobHover(job.role_id)}
                          onMouseLeave={handleJobLeave}
                          onFocus={() => handleJobHover(job.role_id)}
                          onBlur={handleJobRowBlur}
                          onClick={() => (hoveredJob === job.role_id ? handleJobLeave() : handleJobHover(job.role_id))}
                          style={{
                            padding: '0.625rem 0.75rem',
                            borderRadius: '10px',
                            background: isHovered ? 'rgba(152,184,168,0.12)' : 'var(--gray-50, #fafafa)',
                            border: `1.5px dashed ${isHovered ? 'var(--peach, #F9CE9C)' : 'var(--gray-300)'}`,
                            opacity: 0.72,
                            cursor: 'pointer',
                            transition: 'all 0.2s ease',
                          }}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.5rem' }}>
                            <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontWeight: 500, fontSize: '0.875rem', color: 'var(--gray-900)' }}>
                              {job.role_title}
                            </div>
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
                          <div style={{ marginTop: '0.3rem', fontSize: '0.72rem', color: 'var(--gray-500)' }}>
                            <strong>{t('dashboard.unlockByAssessment')}:</strong> {t('dashboard.takeAssessmentToUnlock')}
                          </div>
                          {matchedText && (
                            <div style={{ marginTop: '0.2rem', fontSize: '0.72rem', color: 'var(--gray-500)' }}>
                              <strong>{t('dashboard.matchedSkillsForRole')}:</strong> {matchedText}
                            </div>
                          )}
                          {missingText && (
                            <div style={{ marginTop: '0.2rem', fontSize: '0.72rem', color: 'var(--gray-500)' }}>
                              <strong>{t('dashboard.missingSkillsForRole')}:</strong> {missingText}
                            </div>
                          )}
                          <div style={{ marginTop: '0.45rem', display: 'flex', gap: '0.45rem', flexWrap: 'wrap' }}>
                            <Link href="/dashboard/assessments" className="btn btn-secondary btn-sm">
                              {t('dashboard.takeAssessment')}
                            </Link>
                            <button
                              type="button"
                              className="btn btn-ghost btn-sm"
                              onClick={(event) => {
                                event.stopPropagation();
                                onOpenAssessmentAssistant?.(job);
                              }}
                            >
                              {t('dashboard.askAgentToPlan')}
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </>
                )}
              </>
            ) : (
              <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--gray-400)', fontSize: '0.875rem' }}>
                {t('dashboard.noRolesAboveThreshold')}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
