export const DEMO_DASHBOARD_DOCUMENTS = [
  { doc_id: 'demo-doc-1', filename: 'Demo_Resume.pdf', created_at: '2026-04-01T10:00:00Z', doc_type: 'resume' },
  { doc_id: 'demo-doc-2', filename: 'Demo_Data_Project.md', created_at: '2026-04-02T10:00:00Z', doc_type: 'project' },
];

export const DEMO_DASHBOARD_SKILLS = [
  { skill_id: 'HKU.SKILL.DATA_ANALYSIS.v1', canonical_name: 'Data Analysis', level: 2, status: 'verified' as const },
  { skill_id: 'HKU.SKILL.SQL.v1', canonical_name: 'SQL', level: 2, status: 'verified' as const },
  { skill_id: 'HKU.SKILL.DATA_VIZ.v1', canonical_name: 'Data Visualization', level: 1, status: 'pending' as const },
  { skill_id: 'HKU.SKILL.PRESENTATION.v1', canonical_name: 'Presentation', level: 1, status: 'pending' as const },
  { skill_id: 'HKU.SKILL.DEEP_LEARNING.v1', canonical_name: 'Deep Learning', level: 0, status: 'missing' as const },
];

export const DEMO_DASHBOARD_JOB_MATCHES = [
  {
    role_id: 'demo-role-1',
    role_title: 'Data Analyst (Demo)',
    readiness: 72,
    gaps: ['Data Visualization', 'Storytelling'],
    gaps_all: ['Data Visualization', 'Storytelling'],
    required_skills: ['Data Analysis', 'SQL', 'Data Visualization', 'Storytelling'],
    skills_met: 4,
    skills_total: 6,
  },
  {
    role_id: 'demo-role-2',
    role_title: 'Product Analyst (Demo)',
    readiness: 64,
    gaps: ['A/B Testing', 'Presentation'],
    gaps_all: ['A/B Testing', 'Presentation'],
    required_skills: ['Data Analysis', 'A/B Testing', 'Presentation'],
    skills_met: 3,
    skills_total: 6,
  },
];

export const DEMO_SKILLS_PROFILE = {
  subject_id: 'demo_student',
  documents_count: 2,
  documents: [
    { doc_id: 'demo-doc-1', filename: 'Demo_Resume.pdf', status: 'completed', scope: 'private' },
    { doc_id: 'demo-doc-2', filename: 'Demo_Data_Project.md', status: 'completed', scope: 'private' },
  ],
  generated_at: '2026-04-07T10:00:00Z',
  skills: [
    {
      skill_id: 'HKU.SKILL.DATA_ANALYSIS.v1',
      canonical_name: 'Data Analysis',
      label: 'demonstrated',
      rationale: 'Demonstrated via coursework and project report.',
      evidence_items: [{ chunk_id: 'demo-chunk-1', snippet: 'Performed exploratory analysis and interpreted trends.', doc_id: 'demo-doc-2' }],
    },
    {
      skill_id: 'HKU.SKILL.DATA_VIZ.v1',
      canonical_name: 'Data Visualization',
      label: 'mentioned',
      rationale: 'Mentioned in resume but lacks strong artifacts.',
      evidence_items: [{ chunk_id: 'demo-chunk-2', snippet: 'Built dashboard for internship weekly metrics.', doc_id: 'demo-doc-1' }],
    },
    {
      skill_id: 'HKU.SKILL.DEEP_LEARNING.v1',
      canonical_name: 'Deep Learning',
      label: 'not_enough_information',
      rationale: 'No concrete evidence found in uploaded documents.',
      evidence_items: [],
      refusal: {
        code: 'not_enough_information',
        message: 'More concrete project proof is needed.',
        next_step: 'Upload model training project or coursework artifacts.',
      },
    },
  ],
};

export const DEMO_RECENT_ASSESSMENT_UPDATES = [
  {
    session_id: 'demo-session-1',
    assessment_type: 'communication',
    skill_id: 'HKU.SKILL.COMMUNICATION.v1',
    score: 82,
    level: 2,
    submitted_at: '2026-04-05T08:00:00Z',
    skill_update: { level: 2, label: 'demonstrated', updated_at: '2026-04-05T08:01:00Z' },
  },
  {
    session_id: 'demo-session-2',
    assessment_type: 'programming',
    skill_id: 'HKU.SKILL.PYTHON.v1',
    score: 76,
    level: 2,
    submitted_at: '2026-04-06T08:00:00Z',
    skill_update: { level: 2, label: 'mentioned', updated_at: '2026-04-06T08:01:00Z' },
  },
];

export const DEMO_PEER_BENCHMARK = [
  { skill_id: 'Data Analysis', level: 2, percentile: 68 },
  { skill_id: 'SQL', level: 2, percentile: 72 },
  { skill_id: 'Python Programming', level: 1, percentile: 45 },
  { skill_id: 'Data Visualization', level: 1, percentile: 38 },
  { skill_id: 'Statistical Analysis', level: 2, percentile: 61 },
  { skill_id: 'Machine Learning', level: 0, percentile: 22 },
  { skill_id: 'Project Management', level: 1, percentile: 50 },
  { skill_id: 'Communication', level: 2, percentile: 75 },
];

export const DEMO_JOBS_LIVE = [
  { posting_id: 'demo-job-1', source_site: 'jobsdb_hk', title: 'Data Analyst', company: 'HSBC', location: 'Hong Kong', salary: 'HKD 28,000 – 38,000/month', source_url: 'https://hk.jobsdb.com/', match_score: 72, matched_skills: ['Data Analysis', 'SQL'] },
  { posting_id: 'demo-job-2', source_site: 'jobsdb_hk', title: 'Business Analyst', company: 'Deloitte HK', location: 'Hong Kong', salary: 'HKD 32,000 – 45,000/month', source_url: 'https://hk.jobsdb.com/', match_score: 65, matched_skills: ['Data Analysis'] },
  { posting_id: 'demo-job-3', source_site: 'ctgoodjobs_hk', title: 'Data Scientist', company: 'WeLab', location: 'Hong Kong', salary: 'HKD 40,000 – 60,000/month', source_url: 'https://www.ctgoodjobs.hk/', match_score: 55, matched_skills: ['Python Programming', 'Machine Learning'] },
  { posting_id: 'demo-job-4', source_site: 'ctgoodjobs_hk', title: 'BI Developer', company: 'HKEX', location: 'Hong Kong', salary: 'HKD 35,000 – 50,000/month', source_url: 'https://www.ctgoodjobs.hk/', match_score: 48, matched_skills: ['SQL', 'Data Visualization'] },
];
