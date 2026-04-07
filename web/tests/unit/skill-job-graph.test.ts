import { describe, it, expect } from 'vitest';
import { buildRoleConnections } from '@/components/SkillJobGraph';

describe('buildRoleConnections', () => {
  it('marks all missing required skills as gap lines (not limited to top3)', () => {
    const skills = [
      { skill_id: 's1', canonical_name: 'Data Visualization', level: 0, status: 'missing' as const },
      { skill_id: 's2', canonical_name: 'Deep Learning', level: 0, status: 'missing' as const },
      { skill_id: 's3', canonical_name: 'Python', level: 2, status: 'verified' as const },
      { skill_id: 's4', canonical_name: 'Statistics', level: 0, status: 'missing' as const },
    ];

    const job = {
      role_id: 'r1',
      role_title: 'Data Scientist Intern',
      readiness: 62,
      gaps: ['Data Visualization', 'Python', 'Deep Learning'],
      gaps_all: ['Data Visualization', 'Python', 'Deep Learning', 'Statistics'],
      required_skills: ['Data Visualization', 'Deep Learning', 'Python', 'Statistics'],
      skills_met: 1,
      skills_total: 4,
    };

    const connections = buildRoleConnections(skills, job);
    const byId = new Map(connections.map((c) => [c.skillId, c]));

    expect(connections).toHaveLength(4);
    expect(byId.get('s1')?.isGap).toBe(true);
    expect(byId.get('s2')?.isGap).toBe(true);
    expect(byId.get('s4')?.isGap).toBe(true);
    expect(byId.get('s3')?.isGap).toBe(true);
  });

  it('does not connect non-required skills', () => {
    const skills = [
      { skill_id: 'a', canonical_name: 'Communication', level: 2, status: 'verified' as const },
      { skill_id: 'b', canonical_name: 'Git', level: 2, status: 'verified' as const },
    ];
    const job = {
      role_id: 'r2',
      role_title: 'Analyst',
      readiness: 80,
      gaps: [],
      required_skills: ['Communication'],
      skills_met: 1,
      skills_total: 1,
    };

    const connections = buildRoleConnections(skills, job);
    expect(connections).toEqual([{ skillId: 'a', isGap: false }]);
  });
});
