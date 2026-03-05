/**
 * API Configuration for SkillSight
 */

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';

export interface ApiError {
  detail: string;
  status?: number;
}

export class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl;
  }

  async request<T>(
    endpoint: string,
    options?: RequestInit
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    
    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ 
        detail: `Request failed with status ${response.status}` 
      }));
      throw new Error(error.detail || 'Request failed');
    }

    return response.json();
  }

  // Documents
  async uploadDocument(file: File, userId: string, consent: boolean) {
    const formData = new FormData();
    formData.append('file', file);
    
    return this.request<{ doc_id: string; filename: string; chunks_created: number }>(
      `/documents/upload?user_id=${userId}&consent=${consent}&doc_type=evidence`,
      {
        method: 'POST',
        body: formData,
        headers: {}, // Let browser set Content-Type for FormData
      }
    );
  }

  async getDocuments(limit = 50) {
    return this.request<{ items: Document[] }>(`/documents?limit=${limit}`);
  }

  async getDocument(docId: string) {
    return this.request<Document>(`/documents/${docId}`);
  }

  // Skills
  async getSkills(query?: string, limit = 50) {
    const params = new URLSearchParams({ limit: String(limit) });
    if (query) params.set('q', query);
    return this.request<{ items: Skill[] }>(`/skills?${params}`);
  }

  // Roles
  async getRoles() {
    return this.request<{ items: Role[] }>('/roles');
  }

  async getRole(roleId: string) {
    return this.request<Role>(`/roles/${roleId}`);
  }

  // Interactive Assessments
  async startCommunicationAssessment(userId: string, durationSeconds = 60) {
    return this.request<CommunicationSession>('/interactive/communication/start', {
      method: 'POST',
      body: JSON.stringify({ user_id: userId, duration_seconds: durationSeconds }),
    });
  }

  async submitCommunicationAssessment(sessionId: string, transcript: string, audioDuration: number) {
    return this.request<AssessmentResult>('/interactive/communication/submit', {
      method: 'POST',
      body: JSON.stringify({
        session_id: sessionId,
        transcript,
        audio_duration_seconds: audioDuration,
      }),
    });
  }

  async startProgrammingAssessment(userId: string, difficulty: 'easy' | 'medium' | 'hard') {
    return this.request<ProgrammingSession>('/interactive/programming/start', {
      method: 'POST',
      body: JSON.stringify({ user_id: userId, difficulty, language: 'python' }),
    });
  }

  async submitProgrammingAssessment(sessionId: string, code: string, language = 'python') {
    return this.request<AssessmentResult>('/interactive/programming/submit', {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId, code, language }),
    });
  }

  async startWritingAssessment(userId: string, timeLimitMinutes = 30) {
    return this.request<WritingSession>('/interactive/writing/start', {
      method: 'POST',
      body: JSON.stringify({
        user_id: userId,
        time_limit_minutes: timeLimitMinutes,
        min_words: 300,
        max_words: 500,
      }),
    });
  }

  async submitWritingAssessment(
    sessionId: string,
    content: string,
    antiCopyToken: string,
    keystrokeData?: { chars_per_minute: number; paste_count: number }
  ) {
    return this.request<AssessmentResult>('/interactive/writing/submit', {
      method: 'POST',
      body: JSON.stringify({
        session_id: sessionId,
        content,
        anti_copy_token: antiCopyToken,
        keystroke_data: keystrokeData || { chars_per_minute: 0, paste_count: 0 },
      }),
    });
  }

  // AI Assessment
  async assessDemonstration(skillId: string, docId: string) {
    return this.request<DemonstrationResult>('/ai/demonstration', {
      method: 'POST',
      body: JSON.stringify({ skill_id: skillId, doc_id: docId }),
    });
  }

  async assessProficiency(skillId: string, docId: string) {
    return this.request<ProficiencyResult>('/ai/proficiency', {
      method: 'POST',
      body: JSON.stringify({ skill_id: skillId, doc_id: docId }),
    });
  }

  // Role Readiness
  async getRoleReadiness(roleId: string, userId: string) {
    return this.request<RoleReadinessResult>('/assess/role_readiness', {
      method: 'POST',
      body: JSON.stringify({ role_id: roleId, user_id: userId }),
    });
  }

  // Health check
  async healthCheck() {
    return this.request<{ status: string; ok: boolean }>('/health');
  }
}

// Type definitions
export interface Document {
  doc_id: string;
  filename: string;
  user_id: string;
  doc_type: string;
  created_at: string;
  chunk_count?: number;
}

export interface Skill {
  skill_id: string;
  canonical_name: string;
  definition?: string;
  aliases?: string[];
}

export interface Role {
  role_id: string;
  role_title: string;
  description?: string;
  skills_required?: { skill_id: string; target_level: number; required: boolean }[];
}

export interface CommunicationSession {
  session_id: string;
  topic: string;
  duration_seconds: number;
}

export interface ProgrammingSession {
  session_id: string;
  problem: {
    title: string;
    description: string;
    function_signature?: string;
    examples?: string[];
  };
  time_limit_minutes: number;
}

export interface WritingSession {
  session_id: string;
  prompt: {
    title: string;
    prompt: string;
  };
  time_limit_minutes: number;
  anti_copy_token: string;
}

export interface AssessmentResult {
  session_id: string;
  evaluation: {
    score?: number;
    overall_score?: number;
    level?: number;
    level_label?: string;
    feedback?: string;
    details?: Record<string, unknown>;
  };
}

export interface DemonstrationResult {
  skill_id: string;
  doc_id: string;
  label: 'demonstrated' | 'mentioned' | 'not_enough_information';
  evidence_chunk_ids: string[];
  rationale: string;
}

export interface ProficiencyResult {
  skill_id: string;
  doc_id: string;
  level: number;
  label: string;
  evidence_chunk_ids: string[];
  rationale: string;
}

export interface RoleReadinessResult {
  role_id: string;
  user_id: string;
  readiness_score: number;
  skills_breakdown: {
    skill_id: string;
    status: 'meet' | 'missing_proof' | 'needs_strengthening';
    current_level?: number;
    target_level: number;
  }[];
}

// Default client instance
export const api = new ApiClient();
