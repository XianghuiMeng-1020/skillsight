/**
 * Unified BFF Client
 * All frontend requests MUST go through this client.
 * Direct calls to non-/bff/* paths are prohibited.
 *
 * Role-based routing:
 *   student        -> /bff/student/*
 *   staff          -> /bff/staff/*
 *   programme_leader -> /bff/programme/*
 *   admin          -> /bff/admin/*
 */

const BFF_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';

export type BffRole = 'student' | 'staff' | 'programme_leader' | 'admin' | 'career_coach';

// ─── Token storage (client-side only) ─────────────────────────────────────────

const TOKEN_KEY = 'skillsight_token';
const ROLE_KEY = 'skillsight_role';

export function setToken(token: string, role: BffRole): void {
  if (typeof window !== 'undefined') {
    try {
      localStorage.setItem(TOKEN_KEY, token);
      localStorage.setItem(ROLE_KEY, role);
    } catch (e) {
      console.warn('Failed to save token to localStorage:', e);
    }
  }
}

export function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch (e) {
    console.warn('Failed to read token from localStorage:', e);
    return null;
  }
}

export function getRole(): BffRole | null {
  if (typeof window === 'undefined') return null;
  try {
    return localStorage.getItem(ROLE_KEY) as BffRole | null;
  } catch (e) {
    console.warn('Failed to read role from localStorage:', e);
    return null;
  }
}

export function clearToken(): void {
  if (typeof window !== 'undefined') {
    try {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(ROLE_KEY);
    } catch (e) {
      console.warn('Failed to clear token from localStorage:', e);
    }
  }
}

// ─── BFF prefix resolution ────────────────────────────────────────────────────

function bffPrefix(role?: BffRole | null): string {
  const r = role || getRole();
  switch (r) {
    case 'staff':      return '/bff/staff';
    case 'career_coach': return '/bff/staff';
    case 'programme_leader': return '/bff/programme';
    case 'admin':      return '/bff/admin';
    default:           return '/bff/student';
  }
}

// ─── Core request helper (retry on network failure for cold-start) ─────────────

const BFF_RETRY_ATTEMPTS = 3;
const BFF_RETRY_DELAYS_MS = [2000, 4000];

interface RequestOptions {
  method?: string;
  body?: unknown;
  role?: BffRole;
  purpose?: string;
  headers?: Record<string, string>;
}

async function bffRequest<T = unknown>(
  path: string,
  options: RequestOptions = {}
): Promise<T> {
  const token = getToken();
  const purpose = options.purpose || defaultPurpose(options.role);

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(purpose ? { 'X-Purpose': purpose } : {}),
    ...(options.headers || {}),
  };

  let lastError: unknown;
  for (let attempt = 0; attempt < BFF_RETRY_ATTEMPTS; attempt++) {
    try {
      const res = await fetch(`${BFF_BASE}${path}`, {
        method: options.method || 'GET',
        headers,
        ...(options.body !== undefined
          ? { body: JSON.stringify(options.body) }
          : {}),
      });

      if (!res.ok) {
        let detail: unknown;
        try { detail = await res.json(); } catch { detail = res.statusText; }
        throw new BffError(res.status, detail);
      }

      return res.json() as Promise<T>;
    } catch (e) {
      lastError = e;
      const isNetworkError =
        e instanceof TypeError && (e.message === 'Failed to fetch' || e.message?.includes('fetch'));
      if (!isNetworkError || attempt === BFF_RETRY_ATTEMPTS - 1) throw e;
      const delay = BFF_RETRY_DELAYS_MS[attempt] ?? 4000;
      await new Promise((r) => setTimeout(r, delay));
    }
  }
  throw lastError;
}

function defaultPurpose(role?: BffRole | null): string {
  const r = role || getRole();
  switch (r) {
    case 'staff':            return 'teaching_support';
    case 'career_coach':     return 'teaching_support';
    case 'programme_leader': return 'aggregate_programme_analysis';
    case 'admin':            return 'system_audit';
    default:                 return 'skill_assessment';
  }
}

export class BffError extends Error {
  constructor(public status: number, public detail: unknown) {
    super(`BFF request failed with status ${status}`);
    this.name = 'BffError';
  }
}

// ─── Student BFF response types (for type-safe usage in pages) ─────────────────

export interface ProfileSkillEntry {
  skill_id: string;
  canonical_name: string;
  label?: string;
  level?: number;
  rationale?: string;
  evidence_items?: Array<{ chunk_id: string; snippet: string; section_path?: string; page_start?: number; doc_id: string }>;
}

export interface ProfileResponse {
  subject_id: string;
  documents_count?: number;
  documents?: Array<{ doc_id: string; filename: string; status: string; scope?: string; created_at?: string }>;
  skills?: ProfileSkillEntry[];
  generated_at?: string;
  recent_assessment_events?: unknown[];
}

export interface LeaderboardResponse {
  my_rank: number | null;
  my_points: number;
  top: Array<{ rank: number; points: number }>;
}

export interface CareerSummaryResponse {
  summary: string;
  gap_skills: string[];
  top_actions: string[];
  export_statement_url?: string;
}

export interface ExportStatementResponse {
  subject_id: string;
  generated_at: string;
  verification_token?: string;
  statement: {
    total_skills_assessed: number;
    demonstrated_skills: number;
    total_evidence_items: number;
    documents: Array<{ doc_id: string; filename: string; status: string; scope?: string }>;
    skills: Array<{ skill_id: string; canonical_name: string; label: string; rationale?: string; evidence_items?: Array<{ chunk_id: string; snippet: string; doc_id: string; section_path?: string; page_start?: number }> }>;
  };
}

// ─── Auth (shared across roles) ───────────────────────────────────────────────

interface DevLoginParams {
  subject_id: string;
  role: BffRole;
  ttl_s?: number;
  faculty_id?: string;
  programme_id?: string;
  course_ids?: string[];
  term_id?: string;
}

export async function devLogin(params: DevLoginParams): Promise<{ token: string; role: string }> {
  const prefix = bffPrefix(params.role);
  const data = await bffRequest<{ token: string; role: string }>(
    `${prefix}/auth/dev_login`,
    { method: 'POST', body: params, role: params.role }
  );
  setToken(data.token, params.role as BffRole);
  return data;
}

// ─── Staff BFF client ─────────────────────────────────────────────────────────

export const staffBff = {
  getCourses: () =>
    bffRequest<{ courses: unknown[]; count: number }>('/bff/staff/courses'),

  getCourseSkillsSummary: (courseId: string) =>
    bffRequest<unknown>(`/bff/staff/courses/${courseId}/skills_summary`),

  getReviewQueue: (courseId: string, status?: string) =>
    bffRequest<{ tickets: unknown[]; count: number }>(
      `/bff/staff/courses/${courseId}/review_queue${status ? `?status=${status}` : ''}`
    ),

  resolveTicket: (ticketId: string, decision: string, comment?: string) =>
    bffRequest<unknown>(`/bff/staff/review/${ticketId}/resolve`, {
      method: 'POST',
      body: { decision, comment },
    }),

  getSkillDefinitions: (search?: string) =>
    bffRequest<{ skills: unknown[] }>(
      `/bff/staff/skills/definitions${search ? `?search=${encodeURIComponent(search)}` : ''}`
    ),

  getAuditSummary: (courseId?: string) =>
    bffRequest<unknown>(
      `/bff/staff/audit/summary${courseId ? `?course_id=${courseId}` : ''}`
    ),

  getHealth: () =>
    bffRequest<unknown>('/bff/staff/health'),
};

// ─── Programme BFF client ─────────────────────────────────────────────────────

export const programmeBff = {
  getProgrammes: () =>
    bffRequest<{ programmes: unknown[] }>('/bff/programme/programmes'),

  getCoverageMatrix: (programmeId: string, termId?: string) =>
    bffRequest<unknown>(
      `/bff/programme/programmes/${programmeId}/coverage_matrix${termId ? `?term_id=${termId}` : ''}`
    ),

  getTrend: (programmeId: string, skillId?: string) =>
    bffRequest<unknown>(
      `/bff/programme/programmes/${programmeId}/trend${skillId ? `?skill_id=${skillId}` : ''}`
    ),

  getAuditSummary: () =>
    bffRequest<unknown>('/bff/programme/audit/summary'),

  getHealth: () =>
    bffRequest<unknown>('/bff/programme/health'),
};

// ─── Admin BFF client ─────────────────────────────────────────────────────────

export const adminBff = {
  // Onboarding
  createFaculty: (data: { faculty_id: string; name: string }) =>
    bffRequest<unknown>('/bff/admin/onboarding/faculty', { method: 'POST', body: data }),

  createProgramme: (data: { programme_id: string; name: string; faculty_id: string }) =>
    bffRequest<unknown>('/bff/admin/onboarding/programme', { method: 'POST', body: data }),

  createCourse: (data: {
    course_id: string; course_name: string; description?: string;
    programme_id?: string; faculty_id?: string; term_id?: string
  }) => bffRequest<unknown>('/bff/admin/onboarding/course', { method: 'POST', body: data }),

  createTerm: (data: { term_id: string; label: string; start_date?: string; end_date?: string }) =>
    bffRequest<unknown>('/bff/admin/onboarding/term', { method: 'POST', body: data }),

  // User management
  assignRole: (data: { user_id: string; role: string }) =>
    bffRequest<unknown>('/bff/admin/users/assign_role', { method: 'POST', body: data }),

  assignContext: (data: {
    user_id: string; role: string; faculty_id?: string;
    programme_id?: string; course_id?: string; term_id?: string
  }) => bffRequest<unknown>('/bff/admin/users/assign_context', { method: 'POST', body: data }),

  addTeachingRelation: (data: { user_id: string; course_id: string; term_id?: string; role?: string }) =>
    bffRequest<unknown>('/bff/admin/users/teaching_relation', { method: 'POST', body: data }),

  // Skills & Roles
  getSkills: (limit?: number) =>
    bffRequest<{ skills: unknown[]; count: number }>(
      `/bff/admin/skills${limit ? `?limit=${limit}` : ''}`
    ),

  importSkills: (skills: unknown[]) =>
    bffRequest<unknown>('/bff/admin/skills/import', { method: 'POST', body: { skills } }),

  getRoles: (limit?: number) =>
    bffRequest<{ roles: unknown[]; count: number }>(
      `/bff/admin/roles${limit ? `?limit=${limit}` : ''}`
    ),

  importRoles: (roles: unknown[]) =>
    bffRequest<unknown>('/bff/admin/roles/import', { method: 'POST', body: { roles } }),

  // Audit
  searchAudit: (params?: {
    action?: string; status?: string; request_id?: string;
    subject_id_filter?: string; since?: string; until?: string; limit?: number
  }) => {
    const qs = new URLSearchParams();
    if (params?.action) qs.set('action', params.action);
    if (params?.status) qs.set('status', params.status);
    if (params?.request_id) qs.set('request_id', params.request_id);
    if (params?.subject_id_filter) qs.set('subject_id_filter', params.subject_id_filter);
    if (params?.since) qs.set('since', params.since);
    if (params?.until) qs.set('until', params.until);
    if (params?.limit) qs.set('limit', String(params.limit));
    const query = qs.toString();
    return bffRequest<{ items: unknown[]; count: number }>(
      `/bff/admin/audit/search${query ? `?${query}` : ''}`
    );
  },

  changeLogSearch: (params?: { subject_id?: string; event_type?: string; request_id?: string; since?: string; until?: string; limit?: number; cursor?: string }) => {
    const qs = new URLSearchParams();
    if (params?.subject_id) qs.set('subject_id', params.subject_id);
    if (params?.event_type) qs.set('event_type', params.event_type);
    if (params?.request_id) qs.set('request_id', params.request_id);
    if (params?.since) qs.set('since', params.since);
    if (params?.until) qs.set('until', params.until);
    if (params?.limit) qs.set('limit', String(params.limit));
    if (params?.cursor) qs.set('cursor', params.cursor);
    return bffRequest<{ items: unknown[]; next_cursor?: string }>(
      `/bff/admin/change_log/search${qs.toString() ? `?${qs.toString()}` : ''}`
    );
  },

  // Metrics
  getUsageMetrics: () =>
    bffRequest<unknown>('/bff/admin/metrics/usage'),

  getReliabilityMetrics: () =>
    bffRequest<unknown>('/bff/admin/metrics/reliability'),

  getHealth: () =>
    bffRequest<unknown>('/bff/admin/health'),
};

// ─── Student BFF types (explicit return types) ─────────────────────────────────

export interface ProfileSkillEntry {
  skill_id: string;
  canonical_name: string;
  label?: string;
  level?: number;
  rationale?: string;
  evidence_items?: Array<{ chunk_id: string; snippet: string; doc_id: string; section_path?: string; page_start?: number }>;
}

export interface ProfileResponse {
  subject_id: string;
  documents_count?: number;
  documents?: Array<{ doc_id: string; filename: string; status: string; scope?: string; created_at?: string }>;
  skills?: ProfileSkillEntry[];
  generated_at?: string;
}

export interface LeaderboardResponse {
  my_rank: number | null;
  my_points: number;
  top: Array<{ rank: number; points: number }>;
}

export interface CareerSummaryResponse {
  summary: string;
  gap_skills: string[];
  top_actions: string[];
  export_statement_url?: string;
}

export interface ExportStatementResponse {
  subject_id: string;
  generated_at: string;
  verification_token?: string;
  statement: {
    total_skills_assessed: number;
    demonstrated_skills: number;
    total_evidence_items: number;
    documents: Array<{ doc_id: string; filename: string; status: string; scope?: string }>;
    skills: Array<{ skill_id: string; canonical_name: string; label: string; rationale?: string; evidence_items?: Array<{ chunk_id: string; snippet: string; doc_id: string; section_path?: string; page_start?: number }> }>;
  };
}

/** POST /bff/student/documents/{doc_id}/auto-assess returns 202 Accepted. */
export interface AutoAssessResponse {
  status: 'accepted';
  doc_id: string;
  message: string;
}

// ─── Student BFF client (re-export pattern for consistency) ──────────────────

export const studentBff = {
  getDocuments: (limit?: number) =>
    bffRequest<{ items: unknown[]; count: number }>(
      `/bff/student/documents${limit ? `?limit=${limit}` : ''}`
    ),

  getSkills: (limit?: number) =>
    bffRequest<{ items: unknown[] }>(
      `/bff/student/skills${limit ? `?limit=${limit}` : ''}`
    ),

  getRoles: (limit?: number) =>
    bffRequest<{ items: unknown[] }>(
      `/bff/student/roles${limit ? `?limit=${limit}` : ''}`
    ),

  getRoleAlignmentBatch: (roleIds: string[], docId: string) =>
    bffRequest<{ items: Array<{ role_id: string; role_title: string; readiness: number; skills_met?: number; skills_total?: number; gaps?: string[] }>; count: number }>(
      '/bff/student/roles/alignment/batch',
      { method: 'POST', body: { role_ids: roleIds, doc_id: docId } }
    ),

  getRoleAlignment: async (roleId: string, docId?: string) => {
    type AlignResult = {
      role_id: string;
      role_title?: string;
      score?: number;
      status_summary?: { meet?: number; needs_strengthening?: number; missing_proof?: number };
      items?: Array<{ skill_id?: string; skill_name?: string; status?: string; achieved_level?: number; target_level?: number }>;
    };
    try {
      return await bffRequest<AlignResult>('/bff/student/roles/alignment', {
        method: 'POST',
        body: docId ? { role_id: roleId, doc_id: docId } : { role_id: roleId },
      });
    } catch {
      if (!docId) throw new Error('alignment failed');
      return bffRequest<AlignResult>('/assess/role_readiness', {
        method: 'POST',
        body: { role_id: roleId, doc_id: docId },
      });
    }
  },

  upload: async (file: File, purpose: string, scope: string, token: string) => {
    const form = new FormData();
    form.append('file', file);
    form.append('purpose', purpose);
    form.append('scope', scope);
    const res = await fetch(`${BFF_BASE}/bff/student/documents/upload`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: form,
    });
    if (!res.ok) throw new BffError(res.status, await res.json().catch(() => null));
    return res.json();
  },

  getProfile: (userId?: string) =>
    bffRequest<ProfileResponse>(
      `/bff/student/profile${userId ? `?user_id=${userId}` : ''}`
    ),

  getRecentAssessmentUpdates: (limit = 10) =>
    bffRequest<{
      user_id: string;
      count: number;
      items: Array<{
        session_id: string;
        assessment_type: string;
        skill_id: string;
        submitted_at?: string;
        completed_at?: string;
        score: number;
        level: number;
        skill_update?: {
          level?: number;
          label?: string;
          rationale?: string;
          doc_id?: string;
          updated_at?: string;
        } | null;
      }>;
    }>(`/bff/student/assessments/recent?limit=${Math.max(1, Math.min(limit, 50))}`),

  getConsents: () =>
    bffRequest<unknown>('/bff/student/consents'),

  getChangeLog: (limit = 50, cursor?: string) => {
    const params = new URLSearchParams();
    params.set('limit', String(limit));
    if (cursor) params.set('cursor', cursor);
    return bffRequest<{ items: unknown[]; next_cursor?: string; refusal?: { code: string; message: string; next_step: string } }>(
      `/bff/student/change_log?${params.toString()}`
    );
  },

  exportStatement: () =>
    bffRequest<ExportStatementResponse>('/bff/student/export/statement'),

  // Tutor dialogue (Live Agent + RAG) — evidence-insufficient follow-up
  tutorSessionStart: (skillId: string, docIds?: string[], mode?: 'assessment' | 'resume_review') =>
    bffRequest<{ session_id: string; skill_id: string; doc_ids: string[]; mode?: string }>('/bff/student/tutor-session/start', {
      method: 'POST',
      body: { skill_id: skillId, doc_ids: docIds ?? undefined, mode: mode ?? 'assessment' },
    }),

  tutorSessionGet: (sessionId: string) =>
    bffRequest<{
      session_id: string;
      skill_id: string;
      doc_ids: string[];
      status: string;
      created_at: string | null;
      turns: Array<{ role: string; content: string; created_at: string | null }>;
    }>(`/bff/student/tutor-session/${sessionId}`),

  tutorSessionMessage: (sessionId: string, content: string) =>
    bffRequest<{ reply: string; concluded: boolean; assessment?: { level: number; evidence_chunk_ids: string[]; why?: string } }>(
      `/bff/student/tutor-session/${sessionId}/message`,
      { method: 'POST', body: { content } }
    ),

  getCourseRecommendations: (roleId?: string, skillIds?: string[]) =>
    bffRequest<{
      items: Array<{
        course_id: string;
        course_name: string;
        credits: number;
        programme: string;
        category: string;
        skills: Array<{ skill_id: string; skill_name: string; intended_level: number }>;
      }>;
      count: number;
    }>('/bff/student/courses/for-gaps', {
      method: 'POST',
      body: { role_id: roleId, skill_ids: skillIds },
    }),

  /** Queue embed + skill assessment for this document (202 Accepted; runs in background). */
  autoAssessDocument: (docId: string) =>
    bffRequest<AutoAssessResponse>(
      `/bff/student/documents/${encodeURIComponent(docId)}/auto-assess`,
      { method: 'POST' }
    ),

  recommendActions: (docId: string, roleId?: string, skillId?: string) =>
    bffRequest<{ doc_id: string; role_id?: string; actions: Array<Record<string, unknown>>; timing_ms?: number }>(
      '/bff/student/actions/recommend',
      { method: 'POST', body: { doc_id: docId, role_id: roleId, skill_id: skillId } }
    ),

  getActionsProgress: (roleId?: string) =>
    bffRequest<{ items: Array<{ skill_id: string; gap_type: string; role_id?: string; status: string; completed_at?: string }>; count: number }>(
      `/bff/student/actions/progress${roleId ? `?role_id=${encodeURIComponent(roleId)}` : ''}`
    ),

  postActionProgress: (payload: { skill_id: string; gap_type: string; role_id?: string; doc_id?: string; status: 'pending' | 'completed' }) =>
    bffRequest<{ skill_id: string; gap_type: string; status: string; completed_at?: string }>(
      '/bff/student/actions/progress',
      { method: 'POST', body: payload }
    ),

  getAchievements: () =>
    bffRequest<{ achievements: unknown[]; totalPoints: number; recentUnlock: unknown }>('/bff/student/achievements'),

  postAchievementProgress: (achievementId: string, progress: number) =>
    bffRequest<{ achievement_id: string; progress: number; unlocked: boolean; unlocked_at?: string }>(
      '/bff/student/achievements/progress',
      { method: 'POST', body: { achievement_id: achievementId, progress } }
    ),

  getLeaderboard: (topN = 10) =>
    bffRequest<LeaderboardResponse>(
      `/bff/student/leaderboard?top_n=${Math.max(1, Math.min(topN, 50))}`
    ),

  getCareerSummary: () =>
    bffRequest<CareerSummaryResponse>('/bff/student/career-summary'),

  getJobMatches: async (): Promise<{ count: number; items: Array<{ role_id: string; role_title: string; readiness: number; gaps: string[]; skills_met: number; skills_total: number }> }> => {
    const [rolesData, docsData] = await Promise.all([
      bffRequest<{ items: unknown[] }>('/bff/student/roles?limit=20'),
      bffRequest<{ items: Array<{ doc_id?: string }> }>('/bff/student/documents?limit=1').catch(() => ({ items: [] })),
    ]);
    const latestDocId = (docsData.items || [])[0]?.doc_id;
    const roles = (rolesData.items || []) as Array<{ role_id?: string; role_title?: string }>;
    if (!latestDocId || !roles.length) return { count: 0, items: [] };

    const roleIds = roles.map(r => r.role_id ?? '').filter(Boolean);
    const batch = await bffRequest<{ items: Array<{ role_id: string; role_title: string; readiness: number; skills_met?: number; skills_total?: number; gaps?: string[] }> }>(
      '/bff/student/roles/alignment/batch',
      { method: 'POST', body: { role_ids: roleIds, doc_id: latestDocId } }
    );
    const byId = new Map(batch.items?.map(i => [i.role_id, i]) ?? []);
    const matched = roles
      .map(r => {
        const id = r.role_id ?? '';
        const b = byId.get(id);
        return b ? { role_id: id, role_title: b.role_title || (r.role_title ?? ''), readiness: b.readiness, gaps: b.gaps ?? [], skills_met: b.skills_met ?? 0, skills_total: b.skills_total ?? 0 } : null;
      })
      .filter((x): x is { role_id: string; role_title: string; readiness: number; gaps: string[]; skills_met: number; skills_total: number } => x !== null && x.readiness >= 60);
    return { count: matched.length, items: matched };
  },

  // Resume Enhancement Center
  resumeReviewStart: (docId: string, targetRoleId?: string) =>
    bffRequest<{ review_id: string; status: string }>('/bff/student/resume-review/start', {
      method: 'POST',
      body: { doc_id: docId, target_role_id: targetRoleId ?? undefined },
    }),

  resumeReviewScore: (reviewId: string) =>
    bffRequest<{
      initial_scores?: Record<string, { score: number; comment: string }>;
      total_initial?: number;
      total_final?: number | null;
      final_scores?: Record<string, { score: number; comment: string }> | null;
    }>(`/bff/student/resume-review/${encodeURIComponent(reviewId)}/score`, { method: 'POST' }),

  resumeReviewGetScore: (reviewId: string) =>
    bffRequest<{
      initial_scores: Record<string, { score: number; comment: string }> | null;
      final_scores: Record<string, { score: number; comment: string }> | null;
      total_initial: number | null;
      total_final: number | null;
    }>(`/bff/student/resume-review/${encodeURIComponent(reviewId)}/score`),

  resumeReviewState: (reviewId: string) =>
    bffRequest<{
      review_id: string;
      status: string;
      max_step: number;
      target_role_id?: string;
      has_initial_scores?: boolean;
      has_final_scores?: boolean;
    }>(`/bff/student/resume-review/${encodeURIComponent(reviewId)}/state`),

  resumeReviewSuggest: (reviewId: string) =>
    bffRequest<{
      suggestions: Array<{
        suggestion_id: string;
        dimension: string;
        section?: string;
        original_text?: string;
        suggested_text?: string;
        explanation?: string;
        priority: string;
        status: string;
      }>;
    }>(`/bff/student/resume-review/${encodeURIComponent(reviewId)}/suggest`, { method: 'POST' }),

  resumeReviewGetSuggestions: (reviewId: string, priority?: string) =>
    bffRequest<{
      suggestions: Array<{
        suggestion_id: string;
        dimension: string;
        section?: string;
        original_text?: string;
        suggested_text?: string;
        explanation?: string;
        priority: string;
        status: string;
        student_edit?: string;
      }>;
    }>(`/bff/student/resume-review/${encodeURIComponent(reviewId)}/suggestions${priority ? `?priority=${encodeURIComponent(priority)}` : ''}`),

  resumeReviewPatchSuggestion: (reviewId: string, suggestionId: string, status: string, studentEdit?: string) =>
    bffRequest<{ suggestion_id: string; status: string }>(
      `/bff/student/resume-review/${encodeURIComponent(reviewId)}/suggestion/${encodeURIComponent(suggestionId)}`,
      { method: 'PATCH', body: { status, student_edit: studentEdit } }
    ),

  resumeReviewRescore: (reviewId: string) =>
    bffRequest<{
      final_scores: Record<string, { score: number; comment: string }>;
      total_final: number;
      total_initial: number;
      improvements: Record<string, number>;
    }>(`/bff/student/resume-review/${encodeURIComponent(reviewId)}/rescore`, { method: 'POST' }),

  getResumeTemplates: (roleId?: string, industry?: string, reviewId?: string) => {
    const params = new URLSearchParams();
    if (roleId) params.set('role_id', roleId);
    if (industry) params.set('industry', industry);
    if (reviewId) params.set('review_id', reviewId);
    const q = params.toString();
    return bffRequest<{
      templates: Array<{
        template_id: string;
        name: string;
        description?: string;
        industry_tags?: string[];
        preview_url?: string;
        template_file?: string;
        recommend_score?: number;
        recommended?: boolean;
      }>;
    }>(`/bff/student/resume-templates${q ? `?${q}` : ''}`);
  },

  resumeReviewLayoutCheck: (reviewId: string) =>
    bffRequest<{
      score: number;
      issues: Array<{ level: string; code: string; message: string }>;
      locale_hint?: string;
    }>(`/bff/student/resume-review/${encodeURIComponent(reviewId)}/layout-check`),

  resumeReviewCompressionHints: (reviewId: string) =>
    bffRequest<{ review_id: string; estimated_pages: number; hints: string[] }>(
      `/bff/student/resume-review/${encodeURIComponent(reviewId)}/compression-hints`
    ),

  resumeReviewEditableResume: (reviewId: string) =>
    bffRequest<{ review_id: string; resume_text: string }>(
      `/bff/student/resume-review/${encodeURIComponent(reviewId)}/editable-resume`
    ),

  resumeReviewCloneVersion: (reviewId: string, opts?: { targetRoleId?: string; label?: string }) =>
    bffRequest<{ review_id: string; status: string; label?: string }>(
      `/bff/student/resume-review/${encodeURIComponent(reviewId)}/clone-version`,
      { method: 'POST', body: { target_role_id: opts?.targetRoleId, label: opts?.label } }
    ),

  resumeReviewDiffInsights: (
    reviewId: string,
    opts?: { compareReviewId?: string; resumeOverrideText?: string }
  ) =>
    bffRequest<{
      review_id: string;
      compare_review_id?: string;
      role_keywords: string[];
      summary: { added_lines: number; removed_lines: number; overlap_lines: number };
      metrics: {
        before: Record<string, number>;
        after: Record<string, number>;
      };
      dimension_impact: Record<string, { delta: number; signal: 'positive' | 'neutral' | 'negative' }>;
      highlights: string[];
      risks: Array<{ level: string; code: string; message: string }>;
      semantic_alignment: {
        avg_similarity: number;
        matched_sentences: number;
        added_sentences: number;
        removed_sentences: number;
        pairs: Array<{ before: string; after: string; similarity: number }>;
      };
      risk_validator: {
        risk_level: 'low' | 'medium' | 'high';
        issues: Array<{ level: string; code: string; message: string }>;
      };
      attribution: {
        total_delta?: number | null;
        by_dimension: Array<{
          dimension: string;
          score_before: number;
          score_after: number;
          score_delta: number;
          change_signal: 'positive' | 'neutral' | 'negative' | string;
          alignment: 'aligned' | 'mixed' | 'neutral' | string;
        }>;
      };
      next_actions: string[];
    }>(`/bff/student/resume-review/${encodeURIComponent(reviewId)}/diff-insights`, {
      method: 'POST',
      body: {
        compare_review_id: opts?.compareReviewId ?? undefined,
        resume_override_text: opts?.resumeOverrideText ?? undefined,
      },
    }),

  resumeReviewAttribution: (reviewId: string) =>
    bffRequest<{
      review_id: string;
      attribution: {
        total_delta?: number | null;
        by_dimension: Array<{
          dimension: string;
          score_before: number;
          score_after: number;
          score_delta: number;
          change_signal: 'positive' | 'neutral' | 'negative' | string;
          alignment: 'aligned' | 'mixed' | 'neutral' | string;
        }>;
      };
      verification_snapshot?: Record<string, unknown>;
      verification_version?: string;
      semantic_alignment?: {
        avg_similarity: number;
        matched_sentences: number;
        added_sentences: number;
        removed_sentences: number;
      };
    }>(`/bff/student/resume-review/${encodeURIComponent(reviewId)}/attribution`),

  resumeReviewExportAttributionReport: (
    reviewId: string,
    opts?: { exportFormat?: 'docx' | 'pdf'; compareReviewId?: string; resumeOverrideText?: string }
  ) =>
    bffRequest<{
      filename: string;
      content_base64: string;
      mime_type: string;
      format_used?: string;
      pdf_unavailable?: boolean;
      message?: string;
    }>(`/bff/student/resume-review/${encodeURIComponent(reviewId)}/export-attribution-report`, {
      method: 'POST',
      body: {
        export_format: opts?.exportFormat ?? 'docx',
        compare_review_id: opts?.compareReviewId ?? undefined,
        resume_override_text: opts?.resumeOverrideText ?? undefined,
      },
    }),

  resumeReviewPreviewHtml: async (
    reviewId: string,
    templateId: string,
    opts?: { resumeOverrideText?: string; templateOptions?: Record<string, unknown> }
  ): Promise<string> => {
    if (opts?.resumeOverrideText) {
      const token = getToken();
      const base = BFF_BASE.replace(/\/$/, '');
      const url = `${base}/bff/student/resume-review/${encodeURIComponent(reviewId)}/preview-html`;
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = `Bearer ${token}`;
      const r = await fetch(url, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          template_id: templateId,
          resume_override_text: opts.resumeOverrideText,
          template_options: opts?.templateOptions ?? undefined,
        }),
      });
      if (!r.ok) {
        const err = await r.text();
        throw new Error(err || `preview-html ${r.status}`);
      }
      return r.text();
    }
    const token = getToken();
    const base = BFF_BASE.replace(/\/$/, '');
    const url = `${base}/bff/student/resume-review/${encodeURIComponent(reviewId)}/preview-html?template_id=${encodeURIComponent(templateId)}`;
    const headers: Record<string, string> = {};
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const r = await fetch(url, { headers });
    if (!r.ok) {
      const err = await r.text();
      throw new Error(err || `preview-html ${r.status}`);
    }
    return r.text();
  },

  resumeReviewApplyTemplate: (
    reviewId: string,
    templateId: string,
    opts?: { exportFormat?: 'docx' | 'pdf'; resumeOverrideText?: string; templateOptions?: Record<string, unknown> }
  ) =>
    bffRequest<{
      filename: string;
      content_base64: string;
      mime_type: string;
      format_used?: string;
      pdf_unavailable?: boolean;
      message?: string;
    }>(`/bff/student/resume-review/${encodeURIComponent(reviewId)}/apply-template`, {
      method: 'POST',
      body: {
        template_id: templateId,
        export_format: opts?.exportFormat ?? 'docx',
        resume_override_text: opts?.resumeOverrideText ?? undefined,
        template_options: opts?.templateOptions ?? undefined,
      },
    }),

  getResumeReviews: (limit = 10, offset = 0) =>
    bffRequest<{
      reviews: Array<{
        review_id: string;
        doc_id: string;
        target_role_id?: string;
        status: string;
        total_initial?: number;
        total_final?: number;
        created_at?: string;
      }>;
      total: number;
    }>(`/bff/student/resume-reviews?limit=${limit}&offset=${offset}`),

  // Share bonus API (P3)
  recordShare: (data: { share_type: string; platform?: string }) =>
    bffRequest<{
      success: boolean;
      points_earned: number;
      new_achievement_unlocked?: string;
      message: string;
    }>('/actions/share', {
      method: 'POST',
      body: data,
    }),

  getShareStatus: () =>
    bffRequest<{
      has_shared: boolean;
      total_shares: number;
      last_share_at?: string;
    }>('/actions/share/status'),
};
