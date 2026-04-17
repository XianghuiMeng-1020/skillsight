'use client';

import { useState, useRef, useCallback, useMemo, useEffect, type FocusEvent } from 'react';
import Link from 'next/link';
import { useLanguage } from '@/lib/contexts';
import { fmt2 } from '@/lib/formatNumber';

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
  raw_readiness?: number;
  match_class?: 'confirmed' | 'potential' | 'below';
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
  adjacent_credits?: Array<{ required_skill: string; via_skill: string; transfer_weight: string }>;
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
  matchScore: number;
  mustTotal: number;
  mustMet: number;
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

interface Line {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  isGap: boolean;
}

function EvidencePopover({ sources, onClose }: { sources: EvidenceSource[]; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [onClose]);

  if (sources.length === 0) {
    return (
      <div
        ref={ref}
        style={{
          position: 'absolute',
          top: '100%',
          left: 0,
          zIndex: 100,
          background: 'white',
          border: '1px solid var(--gray-200)',
          borderRadius: '10px',
          boxShadow: '0 8px 24px rgba(0,0,0,0.12)',
          padding: '0.75rem 1rem',
          minWidth: '280px',
          maxWidth: '420px',
          marginTop: '4px',
          animation: 'fadeIn 150ms ease-out',
        }}
      >
        <p style={{ margin: 0, fontSize: '0.8125rem', color: 'var(--gray-500)' }}>
          No evidence found in uploaded materials.
        </p>
      </div>
    );
  }

  return (
    <div
      ref={ref}
      style={{
        position: 'absolute',
        top: '100%',
        left: 0,
        zIndex: 100,
        background: 'white',
        border: '1px solid var(--gray-200)',
        borderRadius: '10px',
        boxShadow: '0 8px 24px rgba(0,0,0,0.12)',
        padding: '0.75rem',
        minWidth: '300px',
        maxWidth: '460px',
        maxHeight: '320px',
        overflowY: 'auto',
        marginTop: '4px',
        animation: 'fadeIn 150ms ease-out',
      }}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
        {sources.map((src, i) => (
          <div
            key={src.chunk_id + i}
            style={{
              padding: '0.5rem 0.625rem',
              background: 'var(--gray-50, #fafafa)',
              borderRadius: '8px',
              border: '1px solid var(--gray-100, #f0f0f0)',
            }}
          >
            <p style={{
              margin: '0 0 0.35rem',
              fontSize: '0.8125rem',
              lineHeight: 1.5,
              color: 'var(--gray-700)',
            }}>
              &ldquo;...{src.snippet.trim()}...&rdquo;
            </p>
            <span style={{
              display: 'inline-block',
              fontSize: '0.6875rem',
              fontWeight: 500,
              color: 'var(--gray-500)',
              background: 'var(--gray-100, #f0f0f0)',
              padding: '0.15rem 0.45rem',
              borderRadius: '4px',
            }}>
              {src.filename}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
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
  const [selectedJob, setSelectedJob] = useState<string | null>(null);
  const [lines, setLines] = useState<Line[]>([]);
  const [connectedSkills, setConnectedSkills] = useState<Set<string>>(new Set());
  const [lineFilter, setLineFilter] = useState<'all' | 'gap' | 'met'>('all');
  const [isNarrow, setIsNarrow] = useState(false);
  const [evidencePopoverSkillId, setEvidencePopoverSkillId] = useState<string | null>(null);

  useEffect(() => {
    const mq = window.matchMedia('(max-width: 900px)');
    const sync = () => setIsNarrow(mq.matches);
    sync();
    mq.addEventListener('change', sync);
    return () => mq.removeEventListener('change', sync);
  }, []);

  const sortedSkills = useMemo(
    () => [...skills].sort((a, b) => (b.frequency ?? b.level) - (a.frequency ?? a.level)),
    [skills]
  );

  const { confirmedJobs, potentialJobs, potentialSet, visibleJobs } = useMemo(() => {
    const scored: ScoredJob[] = jobMatches.map((job) => {
      const ratio = computeMustMatchRatio(skills, job);
      const matchedMust = collectMatchedMustSkills(skills, job);
      const mustListLength = (job.required_skills_must && job.required_skills_must.length > 0)
        ? job.required_skills_must.length
        : ((job.required_skills_all && job.required_skills_all.length > 0)
            ? job.required_skills_all.length
            : (job.required_skills?.length ?? 0));
      const mustTotal = (typeof job.skills_total_must === 'number' && job.skills_total_must > 0)
        ? job.skills_total_must
        : mustListLength;
      const mustMet = (typeof job.skills_met_must === 'number')
        ? job.skills_met_must
        : matchedMust.length;
      return {
        ...job,
        verifiedMatchCount: countVerifiedMatches(skills, job),
        missingSkills: collectMissingSkills(skills, job),
        matchedMustSkills: matchedMust,
        mustMatchRatio: ratio,
        matchScore: Math.round(readinessNum(job.readiness) * (0.6 + 0.4 * ratio)),
        mustTotal,
        mustMet,
      };
    });

    // Prefer backend-emitted match_class (single source of truth from
    // backend.app.services.role_match_scoring); fall back to the legacy FE
    // heuristic only when the backend hasn't deployed yet or the field is
    // missing for any reason.
    const backendSaysAnything = scored.some((j) => typeof j.match_class === 'string');

    let confirmed: ScoredJob[];
    let potential: ScoredJob[];

    if (backendSaysAnything) {
      confirmed = scored
        .filter((j) => j.match_class === 'confirmed')
        .sort((a, b) => readinessNum(b.readiness) - readinessNum(a.readiness))
        .slice(0, 5);
      const confirmedIds = new Set(confirmed.map((j) => j.role_id));
      potential = scored
        .filter((j) => j.match_class === 'potential' && !confirmedIds.has(j.role_id))
        .sort((a, b) => readinessNum(b.readiness) - readinessNum(a.readiness))
        .slice(0, 3);
    } else {
      confirmed = scored
        .filter((job) => job.matchScore >= 65)
        .sort((a, b) => b.matchScore - a.matchScore)
        .slice(0, 5);
      const confirmedIds = new Set(confirmed.map((j) => j.role_id));
      potential = scored
        .filter((job) => {
          if (confirmedIds.has(job.role_id)) return false;
          if (job.matchScore < 35) return false;
          if (job.mustMatchRatio < 0.2) return false;
          return true;
        })
        .sort((a, b) => b.matchScore - a.matchScore)
        .slice(0, 3);
    }

    const potentialSet = new Set(potential.map(j => j.role_id));

    return {
      confirmedJobs: confirmed,
      potentialJobs: potential,
      potentialSet,
      visibleJobs: [...confirmed, ...potential].sort(
        (a, b) => readinessNum(b.readiness) - readinessNum(a.readiness),
      ),
    };
  }, [jobMatches, skills]);

  useEffect(() => {
    onPotentialJobsChange?.(potentialJobs);
  }, [onPotentialJobsChange, potentialJobs]);

  const jobSkillMap = useMemo(() => {
    const map = new Map<string, { skillId: string; isGap: boolean }[]>();
    for (const job of visibleJobs) {
      map.set(job.role_id, buildRoleConnections(skills, job));
    }
    return map;
  }, [visibleJobs, skills]);

  // activeJobId: for SVG lines (hover or click), selectedJobId: for skill list filtering (click only)
  const activeJobId = selectedJob || hoveredJob;

  const selectedJobData = useMemo(
    () => (selectedJob ? visibleJobs.find(j => j.role_id === selectedJob) ?? null : null),
    [visibleJobs, selectedJob]
  );

  const filteredSkillsForJob = useMemo(() => {
    if (!selectedJobData) return null;
    const allRequired = selectedJobData.required_skills_all || selectedJobData.required_skills || [];
    const gapNamesLower = new Set((selectedJobData.gaps_all || selectedJobData.gaps || []).map(g => g.toLowerCase()));
    const studentSkillMap = new Map(skills.map(s => [normalizedName(s.canonical_name), s]));

    return allRequired.map((reqName) => {
      const nameLower = normalizedName(reqName);
      const existing = studentSkillMap.get(nameLower);
      if (existing) {
        return { ...existing, isGap: gapNamesLower.has(nameLower) };
      }
      return {
        skill_id: `missing-${reqName}`,
        canonical_name: reqName,
        level: 0,
        status: 'missing' as const,
        frequency: 0,
        evidence_sources: [],
        isGap: true,
      };
    }).sort((a, b) => (b.frequency ?? b.level) - (a.frequency ?? a.level));
  }, [selectedJobData, skills]);

  const displaySkills = filteredSkillsForJob ?? sortedSkills;

  const calculateLines = useCallback((roleId: string) => {
    const container = containerRef.current;
    const jobEl = jobRefs.current.get(roleId);
    if (!container || !jobEl) return;

    const containerRect = container.getBoundingClientRect();
    const jobRect = jobEl.getBoundingClientRect();
    const newLines: Line[] = [];
    const matched = new Set<string>();

    if (selectedJob === roleId && filteredSkillsForJob) {
      // When a job is selected, draw lines from ALL display skills to the job
      for (const skill of filteredSkillsForJob) {
        const skillEl = skillRefs.current.get(skill.skill_id);
        if (!skillEl) continue;
        matched.add(skill.skill_id);
        const skillRect = skillEl.getBoundingClientRect();
        const isGap = 'isGap' in skill && !!(skill as { isGap?: boolean }).isGap;
        newLines.push({
          x1: skillRect.right - containerRect.left,
          y1: skillRect.top + skillRect.height / 2 - containerRect.top,
          x2: jobRect.left - containerRect.left,
          y2: jobRect.top + jobRect.height / 2 - containerRect.top,
          isGap,
        });
      }
    } else {
      const connections = jobSkillMap.get(roleId) || [];
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
    }

    setLines(newLines);
    setConnectedSkills(matched);
  }, [jobSkillMap, selectedJob, filteredSkillsForJob]);

  const handleJobHover = useCallback((roleId: string) => {
    requestAnimationFrame(() => {
      setHoveredJob(roleId);
      if (!selectedJob) {
        calculateLines(roleId);
      }
    });
  }, [calculateLines, selectedJob]);

  const handleJobLeave = useCallback(() => {
    setHoveredJob(null);
    if (!selectedJob) {
      setLines([]);
      setConnectedSkills(new Set());
      setLineFilter('all');
    }
  }, [selectedJob]);

  const handleJobClick = useCallback((roleId: string) => {
    if (selectedJob === roleId) {
      setSelectedJob(null);
      setLines([]);
      setConnectedSkills(new Set());
      setLineFilter('all');
    } else {
      setSelectedJob(roleId);
      setEvidencePopoverSkillId(null);
    }
  }, [selectedJob]);

  const handleJobRowBlur = useCallback(
    (e: FocusEvent<HTMLDivElement>) => {
      const next = e.relatedTarget as Node | null;
      if (next && e.currentTarget.contains(next)) return;
      handleJobLeave();
    },
    [handleJobLeave],
  );

  const getReadinessColor = (readiness: number) => {
    if (readiness >= 80) return 'var(--success, #16a34a)';
    if (readiness >= 60) return 'var(--sage, #98B8A8)';
    return 'var(--peach, #F9CE9C)';
  };

  const visibleLines = useMemo(
    () => lines.filter((line) => lineFilter === 'all' || (lineFilter === 'gap' ? line.isGap : !line.isGap)),
    [lines, lineFilter],
  );

  useEffect(() => {
    if (selectedJob) {
      requestAnimationFrame(() => calculateLines(selectedJob));
    }
  }, [selectedJob, calculateLines, displaySkills]);

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
        <p style={{ margin: '0.35rem 0 0', fontSize: '0.72rem', lineHeight: 1.45, color: 'var(--gray-500)' }}>
          <span style={{ fontSize: '0.625rem', padding: '0.05rem 0.3rem', borderRadius: '4px', background: 'rgba(249,206,156,0.2)', color: 'var(--peach-dark, #c4883c)', fontWeight: 600, marginRight: '0.35rem' }}>
            {t('dashboard.potentialTag') || 'Potential'}
          </span>
          {t('dashboard.classificationHelp') || 'A role is shown as Potential when key must-have skills are still missing — even if its overall readiness percentage looks high. Hover the badge or the “Must X/Y” chip to see the gap.'}
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

          {/* Left: Skills with frequency */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', position: 'relative', zIndex: 2 }}>
            {selectedJobData && (
              <div style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                marginBottom: '0.25rem',
                padding: '0.35rem 0.5rem',
                background: 'var(--sage-50, #f0f7f2)',
                borderRadius: '8px',
                fontSize: '0.75rem',
                color: 'var(--gray-600)',
              }}>
                <span>
                  {t('dashboard.skillsForRole') || 'Skills for'}: <strong>{selectedJobData.role_title}</strong>
                </span>
                <button
                  type="button"
                  onClick={() => { setSelectedJob(null); setLines([]); setConnectedSkills(new Set()); }}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '0.75rem', color: 'var(--gray-500)', padding: '0 0.25rem' }}
                >
                  ✕
                </button>
              </div>
            )}

            {/* Column header */}
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.75rem',
              padding: '0.25rem 0.75rem',
              fontSize: '0.6875rem',
              fontWeight: 600,
              color: 'var(--gray-400)',
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
            }}>
              <span style={{ flex: 1 }}>{t('dashboard.skillName') || 'Skills'}</span>
              <span style={{ minWidth: '90px', textAlign: 'right' }}>
                {t('dashboard.evidenceFrequency') || 'Occurrence in uploaded evidence'}
              </span>
            </div>

            {displaySkills.length > 0 ? displaySkills.map((skill) => {
              const freq = skill.frequency ?? 0;
              const isConnected = connectedSkills.has(skill.skill_id);
              const isGapSkill = 'isGap' in skill && (skill as { isGap?: boolean }).isGap;
              const hasEvidence = freq > 0;

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
                    background: isConnected
                      ? 'rgba(152,184,168,0.12)'
                      : isGapSkill
                        ? 'rgba(249,206,156,0.08)'
                        : 'var(--gray-50, #fafafa)',
                    border: isConnected
                      ? '1.5px solid var(--sage, #98B8A8)'
                      : isGapSkill
                        ? '1.5px dashed var(--peach, #F9CE9C)'
                        : '1px solid transparent',
                    transition: 'all 0.2s ease',
                    position: 'relative',
                  }}
                >
                  <Link
                    href={`/dashboard/skills?highlight=${encodeURIComponent(skill.skill_id)}`}
                    style={{
                      textDecoration: 'none',
                      color: isGapSkill && !hasEvidence ? 'var(--gray-400)' : 'var(--gray-900)',
                      fontWeight: 500,
                      fontSize: '0.875rem',
                      flex: 1,
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                    }}
                  >
                    {skill.canonical_name}
                  </Link>

                  {/* Frequency badge - clickable to show evidence */}
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      setEvidencePopoverSkillId(
                        evidencePopoverSkillId === skill.skill_id ? null : skill.skill_id
                      );
                    }}
                    style={{
                      minWidth: '44px',
                      textAlign: 'center',
                      padding: '0.2rem 0.5rem',
                      borderRadius: '6px',
                      border: 'none',
                      cursor: hasEvidence ? 'pointer' : 'default',
                      fontWeight: 600,
                      fontSize: '0.8125rem',
                      background: hasEvidence
                        ? freq >= 10
                          ? 'rgba(22,163,106,0.1)'
                          : freq >= 5
                            ? 'rgba(152,184,168,0.15)'
                            : 'rgba(249,206,156,0.15)'
                        : 'var(--gray-100, #f0f0f0)',
                      color: hasEvidence
                        ? freq >= 10
                          ? 'var(--success, #16a34a)'
                          : freq >= 5
                            ? 'var(--sage-dark, #6b8f7b)'
                            : 'var(--peach-dark, #c4883c)'
                        : 'var(--gray-400)',
                      transition: 'all 0.15s ease',
                      position: 'relative',
                    }}
                    title={hasEvidence ? (t('dashboard.clickToSeeEvidence') || 'Click to see evidence') : ''}
                  >
                    {freq}
                  </button>

                  {/* Evidence popover */}
                  {evidencePopoverSkillId === skill.skill_id && (
                    <EvidencePopover
                      sources={skill.evidence_sources || []}
                      onClose={() => setEvidencePopoverSkillId(null)}
                    />
                  )}
                </div>
              );
            }) : (
              <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--gray-400)', fontSize: '0.875rem' }}>
                {t('dashboard.noSkillsGraph')}
              </div>
            )}
          </div>

          {/* Right: Jobs — unified list sorted by readiness */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', position: 'relative', zIndex: 2 }}>
            {visibleJobs.length > 0 ? (
              <>
                {visibleJobs.map((job) => {
                  const isPotential = potentialSet.has(job.role_id);
                  const isActive = activeJobId === job.role_id;
                  const rNum = readinessNum(job.readiness);

                  if (isPotential) {
                    const matchedText = job.matchedMustSkills.slice(0, 3).join(', ');
                    const missingText = job.missingSkills.slice(0, 3).join(', ');
                    const mustGap = Math.max(job.mustTotal - job.mustMet, 0);
                    const potentialReason = (t('dashboard.potentialReason') || 'Overall readiness is {readiness}%, but {mustMet}/{mustTotal} must-have skills are met. Complete an assessment on the missing skills to unlock this role as a confirmed match.')
                      .replace('{readiness}', fmt2(rNum))
                      .replace('{mustMet}', String(job.mustMet))
                      .replace('{mustTotal}', String(job.mustTotal))
                      .replace('{mustGap}', String(mustGap));
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
                        onClick={() => handleJobClick(job.role_id)}
                        style={{
                          padding: '0.625rem 0.75rem',
                          borderRadius: '10px',
                          background: isActive ? 'rgba(152,184,168,0.12)' : 'var(--gray-50, #fafafa)',
                          border: `1.5px dashed ${isActive ? 'var(--peach, #F9CE9C)' : 'var(--gray-300)'}`,
                          cursor: 'pointer',
                          transition: 'all 0.2s ease',
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.5rem' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', overflow: 'hidden' }}>
                            <span
                              title={potentialReason}
                              style={{ fontSize: '0.625rem', padding: '0.1rem 0.35rem', borderRadius: '4px', background: 'rgba(249,206,156,0.2)', color: 'var(--peach-dark, #c4883c)', fontWeight: 600, flexShrink: 0, cursor: 'help', display: 'inline-flex', alignItems: 'center', gap: '0.2rem' }}
                            >
                              {t('dashboard.potentialTag') || 'Potential'}
                              <span style={{ fontSize: '0.65rem', opacity: 0.7 }}>ⓘ</span>
                            </span>
                            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontWeight: 500, fontSize: '0.875rem', color: 'var(--gray-900)' }}>
                              {job.role_title}
                            </span>
                          </div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', flexShrink: 0 }}>
                            {job.mustTotal > 0 && (
                              <span
                                title={(t('dashboard.mustHaveTooltip') || 'Required must-have skills met: {met} of {total}').replace('{met}', String(job.mustMet)).replace('{total}', String(job.mustTotal))}
                                style={{
                                  fontSize: '0.7rem',
                                  fontWeight: 600,
                                  color: 'var(--peach-dark, #c4883c)',
                                  background: 'rgba(249,206,156,0.18)',
                                  border: '1px dashed rgba(196,136,60,0.45)',
                                  padding: '0.15rem 0.4rem',
                                  borderRadius: '6px',
                                  cursor: 'help',
                                }}
                              >
                                {t('dashboard.mustShort') || 'Must'} {job.mustMet}/{job.mustTotal}
                              </span>
                            )}
                            <span
                              title={(t('dashboard.readinessTooltip') || 'Readiness: weighted match against this role’s skill requirements.')}
                              style={{
                                fontSize: '0.75rem',
                                fontWeight: 600,
                                color: getReadinessColor(rNum),
                                background: `${getReadinessColor(rNum)}18`,
                                padding: '0.2rem 0.5rem',
                                borderRadius: '6px',
                                cursor: 'help',
                              }}
                            >
                              {fmt2(rNum)}%
                            </span>
                          </div>
                        </div>
                        {matchedText && (
                          <div style={{ marginTop: '0.25rem', fontSize: '0.72rem', color: 'var(--gray-500)' }}>
                            ✓ {matchedText}
                          </div>
                        )}
                        {missingText && (
                          <div style={{ marginTop: '0.15rem', fontSize: '0.72rem', color: 'var(--peach-dark, #c4883c)' }}>
                            ✗ {missingText}
                          </div>
                        )}
                        {Array.isArray(job.adjacent_credits) && job.adjacent_credits.length > 0 && (
                          <div
                            title={t('dashboard.transferableHelp') || 'Partial credit was given because related skills you already have are transferable to this requirement.'}
                            style={{ marginTop: '0.2rem', fontSize: '0.7rem', color: 'var(--sage-dark, #6b8f7b)', cursor: 'help' }}
                          >
                            ↪ {t('dashboard.transferableShort') || 'Transferable'}: {job.adjacent_credits.slice(0, 2).map((c) => `${c.via_skill}→${c.required_skill}`).join(', ')}
                          </div>
                        )}
                        <div style={{ marginTop: '0.4rem', display: 'flex', gap: '0.45rem', flexWrap: 'wrap' }}>
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
                  }

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
                      onClick={() => handleJobClick(job.role_id)}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        gap: '0.5rem',
                        padding: '0.625rem 0.75rem',
                        borderRadius: '10px',
                        background: isActive ? 'rgba(152,184,168,0.12)' : 'var(--gray-50, #fafafa)',
                        border: isActive
                          ? '1.5px solid var(--sage, #98B8A8)'
                          : selectedJob === job.role_id
                            ? '1.5px solid var(--sage, #98B8A8)'
                            : '1px solid transparent',
                        cursor: 'pointer',
                        transition: 'all 0.2s ease',
                      }}
                    >
                      <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontWeight: 500, fontSize: '0.875rem', color: 'var(--gray-900)', flex: 1 }}>
                        {job.role_title}
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', flexShrink: 0 }}>
                        {job.mustTotal > 0 && (
                          <span
                            title={(t('dashboard.mustHaveTooltip') || 'Required must-have skills met: {met} of {total}').replace('{met}', String(job.mustMet)).replace('{total}', String(job.mustTotal))}
                            style={{
                              fontSize: '0.7rem',
                              fontWeight: 600,
                              color: 'var(--sage-dark, #6b8f7b)',
                              background: 'rgba(152,184,168,0.15)',
                              border: '1px solid rgba(107,143,123,0.35)',
                              padding: '0.15rem 0.4rem',
                              borderRadius: '6px',
                              cursor: 'help',
                            }}
                          >
                            {t('dashboard.mustShort') || 'Must'} {job.mustMet}/{job.mustTotal}
                          </span>
                        )}
                        <span
                          title={(t('dashboard.readinessTooltip') || 'Readiness: weighted match against this role’s skill requirements.')}
                          style={{
                            fontSize: '0.75rem',
                            fontWeight: 600,
                            color: getReadinessColor(rNum),
                            background: `${getReadinessColor(rNum)}18`,
                            padding: '0.2rem 0.5rem',
                            borderRadius: '6px',
                            cursor: 'help',
                          }}
                        >
                          {fmt2(rNum)}%
                        </span>
                      </div>
                    </div>
                  );
                })}
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
