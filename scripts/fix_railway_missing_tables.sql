-- Bootstrap SkillSight core schema on Postgres without pgvector (Railway default).
-- Idempotent: safe to re-run. Does NOT create chunk_embeddings (requires vector type).

CREATE TABLE IF NOT EXISTS skills (
  skill_id TEXT PRIMARY KEY,
  canonical_name TEXT NOT NULL,
  definition TEXT NOT NULL DEFAULT '',
  evidence_rules TEXT NOT NULL DEFAULT '',
  level_rubric_json TEXT NOT NULL DEFAULT '{}',
  version TEXT NOT NULL DEFAULT 'v1',
  source TEXT NOT NULL DEFAULT 'manual',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_skills_canonical ON skills(canonical_name);

CREATE TABLE IF NOT EXISTS roles (
  role_id TEXT PRIMARY KEY,
  role_title TEXT NOT NULL,
  description TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS role_skill_requirements (
  req_id UUID PRIMARY KEY,
  role_id TEXT NOT NULL REFERENCES roles(role_id) ON DELETE CASCADE,
  skill_id TEXT NOT NULL,
  required BOOLEAN NOT NULL DEFAULT true,
  target_level INTEGER NOT NULL DEFAULT 0,
  weight NUMERIC NOT NULL DEFAULT 1.0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_role_req_role ON role_skill_requirements(role_id);
CREATE INDEX IF NOT EXISTS idx_role_req_skill ON role_skill_requirements(skill_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_role_skill ON role_skill_requirements(role_id, skill_id);

CREATE TABLE IF NOT EXISTS skill_aliases (
  alias_id UUID PRIMARY KEY,
  skill_id TEXT NOT NULL,
  alias TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'manual',
  confidence NUMERIC NOT NULL DEFAULT 1.0,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_skill_aliases_alias ON skill_aliases(alias);
CREATE INDEX IF NOT EXISTS idx_skill_aliases_skill ON skill_aliases(skill_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_skill_aliases_pair ON skill_aliases(skill_id, alias);

CREATE TABLE IF NOT EXISTS documents (
  doc_id UUID PRIMARY KEY,
  filename TEXT NOT NULL,
  stored_path TEXT NOT NULL,
  doc_type TEXT NOT NULL,
  title TEXT,
  source_type TEXT,
  storage_uri TEXT,
  metadata_json JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS chunks (
  chunk_id UUID PRIMARY KEY,
  doc_id UUID NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
  idx INTEGER NOT NULL,
  char_start INTEGER NOT NULL,
  char_end INTEGER NOT NULL,
  snippet TEXT NOT NULL,
  quote_hash TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  chunk_text TEXT NOT NULL,
  section_path TEXT,
  page_start INTEGER,
  page_end INTEGER,
  stored_path TEXT,
  storage_uri TEXT
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_chunks_doc_idx ON chunks(doc_id, idx);

CREATE TABLE IF NOT EXISTS skill_assessments (
  assessment_id UUID PRIMARY KEY,
  doc_id UUID NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
  skill_id TEXT NOT NULL,
  decision TEXT NOT NULL,
  evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
  decision_meta JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_skill_assess_doc ON skill_assessments(doc_id);
CREATE INDEX IF NOT EXISTS idx_skill_assess_skill ON skill_assessments(skill_id);

CREATE TABLE IF NOT EXISTS skill_proficiency (
  prof_id UUID PRIMARY KEY,
  doc_id UUID NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
  skill_id TEXT NOT NULL,
  level INTEGER NOT NULL,
  label TEXT NOT NULL,
  rationale TEXT NOT NULL,
  best_evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
  signals JSONB NOT NULL DEFAULT '{}'::jsonb,
  meta JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_skill_prof_doc ON skill_proficiency(doc_id);
CREATE INDEX IF NOT EXISTS idx_skill_prof_skill ON skill_proficiency(skill_id);

CREATE TABLE IF NOT EXISTS consents (
  consent_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id TEXT NOT NULL,
  doc_id TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'granted',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  revoked_at TIMESTAMPTZ,
  revoke_reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_consents_user ON consents(user_id);
CREATE INDEX IF NOT EXISTS idx_consents_doc ON consents(doc_id);
CREATE INDEX IF NOT EXISTS idx_consents_status ON consents(status);
