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
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(ROLE_KEY, role);
  }
}

export function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function getRole(): BffRole | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(ROLE_KEY) as BffRole | null;
}

export function clearToken(): void {
  if (typeof window !== 'undefined') {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(ROLE_KEY);
  }
}

// ─── BFF prefix resolution ────────────────────────────────────────────────────

function bffPrefix(role?: BffRole | null): string {
  const r = role || getRole();
  switch (r) {
    case 'staff':      return '/bff/staff';
    case 'programme_leader': return '/bff/programme';
    case 'admin':      return '/bff/admin';
    default:           return '/bff/student';
  }
}

// ─── Core request helper ──────────────────────────────────────────────────────

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
}

function defaultPurpose(role?: BffRole | null): string {
  const r = role || getRole();
  switch (r) {
    case 'staff':            return 'teaching_support';
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

  getRoleAlignment: (roleId: string, docId?: string) =>
    bffRequest<{
      role_id: string;
      role_title?: string;
      score?: number;
      status_summary?: { meet?: number; needs_strengthening?: number; missing_proof?: number };
      items?: Array<{ skill_id?: string; status?: string }>;
    }>('/bff/student/roles/alignment', {
      method: 'POST',
      body: docId ? { role_id: roleId, doc_id: docId } : { role_id: roleId },
    }),

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
    bffRequest<unknown>(
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
    bffRequest<unknown>('/bff/student/export/statement'),

  getJobMatches: async (): Promise<{ count: number; items: Array<{ role_id: string; role_title: string; readiness: number }> }> => {
    const [rolesData, docsData] = await Promise.all([
      bffRequest<{ items: unknown[] }>('/bff/student/roles?limit=20'),
      bffRequest<{ items: Array<{ doc_id?: string }> }>('/bff/student/documents?limit=1').catch(() => ({ items: [] })),
    ]);
    const latestDocId = (docsData.items || [])[0]?.doc_id;
    if (!latestDocId || !rolesData.items?.length) return { count: 0, items: [] };

    const results = await Promise.allSettled(
      (rolesData.items as Array<{ role_id?: string; role_title?: string }>).map(async (r) => {
        const roleId = r.role_id ?? '';
        const res = await bffRequest<{ score?: number }>('/bff/student/roles/alignment', {
          method: 'POST',
          body: { role_id: roleId, doc_id: latestDocId },
        });
        const readiness = Math.round(Math.max(0, Math.min(1, res.score ?? 0)) * 100);
        return { role_id: roleId, role_title: r.role_title ?? '', readiness };
      })
    );
    const matched = results
      .filter((r): r is PromiseFulfilledResult<{ role_id: string; role_title: string; readiness: number }> => r.status === 'fulfilled')
      .map(r => r.value)
      .filter(r => r.readiness >= 60);
    return { count: matched.length, items: matched };
  },
};
