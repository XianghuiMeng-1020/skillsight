#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# SkillSight Protocol Patch (v0.1)
# - Creates/updates governance+protocol docs that reviewers will ask for:
#   1) Skill/Role versioning & freeze rules
#   2) Evidence integrity / immutability semantics
#   3) Consent semantics (revoke meaning, audit retention)
#   4) Assessment scope & responsibility boundary
#   5) Readiness philosophy (explicitly not a single match score)
#   6) Demo boundary definition (v0.1/v0.2)
# - Also scaffolds Week 1: 10 protocol drafts in docs/protocols/
#
# Run from repo root:
#   bash scripts/patch_protocols_v0_1.sh
# ============================================================

ROOT="$(pwd)"
DOCS_DIR="$ROOT/docs"
PROT_DIR="$DOCS_DIR/protocols"
MILE_DIR="$DOCS_DIR/milestones"
SCRIPTS_DIR="$ROOT/scripts"

mkdir -p "$PROT_DIR" "$MILE_DIR" "$SCRIPTS_DIR"

stamp() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }

write_file() {
  local path="$1"
  local tmp="${path}.tmp"
  cat > "$tmp"
  mkdir -p "$(dirname "$path")"
  if [[ -f "$path" ]]; then
    if cmp -s "$tmp" "$path"; then
      rm -f "$tmp"
      echo "[SKIP] Unchanged: ${path#$ROOT/}"
      return 0
    fi
    cp "$path" "${path}.bak.$(date -u +%Y%m%d%H%M%S)"
  fi
  mv "$tmp" "$path"
  echo "[WRITE] ${path#$ROOT/}"
}

ensure_readme_section() {
  local readme="$ROOT/README.md"
  if [[ ! -f "$readme" ]]; then
    cat > "$readme" <<'EOF'
# SkillSight

## Local Dev

## Docs
EOF
    echo "[WRITE] README.md"
  fi

  if ! grep -q "## Protocols" "$readme"; then
    cat >> "$readme" <<'EOF'

## Protocols
See `docs/protocols/` for data and governance protocols that define identifiers, evidence pointers, consent semantics, assessment scope, and change control.

Key entry points:
- `docs/protocols/skill_role_versioning.md`
- `docs/protocols/evidence_integrity.md`
- `docs/protocols/consent_semantics.md`
- `docs/protocols/assessment_scope.md`
- `docs/protocols/readiness_philosophy.md`
- `docs/milestones/demo_definition.md`
EOF
    echo "[PATCH] README.md (added Protocols section)"
  else
    echo "[SKIP] README.md already has Protocols section"
  fi
}

# --------------------------
# Gap protocol docs (6 files)
# --------------------------

write_file "$PROT_DIR/skill_role_versioning.md" <<EOF
# Skill/Role Versioning and Freeze Rules (v0.1)

**Status:** Draft (v0.1)  
**Last updated (UTC):** $(stamp)

This protocol defines how Skill Registry and Role Library definitions change over time without breaking trust, auditability, or stakeholder interpretation.

## 1. Objects in scope
- **Skill definition**: \`skill_id\`, \`canonical_name\`, \`aliases\`, \`definition\`, \`evidence_rules\`, \`level_rubric\`, \`source\`
- **Role definition**: \`role_id\`, \`role_title\`, \`skills_required[]\`, \`description\`
- **Assessment records**: generated outputs that reference \`skill_id\` (and optionally role_id)

## 2. Stable identifiers
- \`skill_id\` and \`role_id\` are **public identifiers** and must be stable.
- IDs must be **non-semantic** (no names embedded) and **versioned**.
  - Example: \`HKU.SSKILL.000123.v1\`

## 3. Version meaning
- **Major versions** (v1 -> v2) indicate a material change that may alter interpretation:
  - rubric thresholds/levels changed
  - evidence_rules changed (what counts as proof)
  - definition meaning changed
- **Minor revisions** (optional, e.g., v1.1) are non-material:
  - typo fixes
  - formatting improvements
  - adding examples that do not change criteria

If your system currently only supports \`v1, v2\`, treat those as major versions.

## 4. Freeze rule (what becomes “official”)
A Skill/Role version becomes **frozen** when:
1) it has a complete field set for the MVP schema, and  
2) it has been reviewed and approved by an authorized reviewer (e.g., faculty/admin role), and  
3) a \`change_log\` entry exists that explains the intent and scope of the version.

Frozen versions are **read-only** in the admin UI.

## 5. Backward compatibility and reassessment
- **Default rule:** historical assessments are **not recomputed automatically** when Skill/Role versions change.
- Each assessment record must store:
  - \`skill_id\` (including version)
  - \`role_id\` (including version, if used)
  - \`model_version\` and \`prompt_version\` (if AI is involved)
  - evidence pointer list
- Reassessment (recompute) is allowed only when explicitly requested and must produce a new assessment record with a new timestamp and an audit entry.

## 6. Role–Skill coupling rule
Roles reference Skills by \`skill_id\` **including version**.
- If a role is updated to reference \`HKU.SSKILL.000123.v2\`, that is a **role version bump** (role v1 -> v2).

## 7. Change control (minimum governance)
Every change to a frozen skill/role must:
- create a new version
- include a human-readable change summary
- include the reviewer identity (or reviewer role)
- be recorded in \`audit_logs\` and \`change_logs\`

## 8. Open questions (to resolve later)
- Whether minor versions (v1.1) are needed or \`v1/v2\` is sufficient
- Whether reassessment is allowed for entire cohorts vs only per-student request
EOF

write_file "$PROT_DIR/evidence_integrity.md" <<EOF
# Evidence Integrity and Pointer Stability (v0.1)

**Status:** Draft (v0.1)  
**Last updated (UTC):** $(stamp)

This protocol defines how an Evidence Pointer remains trustworthy over time, and how the system detects tampering or file replacement.

## 1. Evidence Pointer fields (MVP)
An Evidence Pointer must include:
- \`doc_id\`
- \`chunk_id\`
- \`page_start/page_end\` (if PDF)
- \`char_start/char_end\` (for plain text extraction)
- \`snippet\` (<= 300 chars)
- \`quote_hash\`
- \`storage_uri\`
- \`created_at\`

## 2. What \`quote_hash\` means
\`quote_hash\` is a cryptographic hash over a canonicalized text span:
- Canonicalization:
  - normalize line endings to \`\\n\`
  - trim trailing spaces
  - apply Unicode NFKC normalization
- Hash input:
  - \`doc_id + "::" + chunk_id + "::" + char_start + "::" + char_end + "::" + extracted_text_span\`
- Hash algorithm:
  - **SHA-256** (default)

This makes a pointer tamper-evident even if snippet display changes.

## 3. Storage immutability rule
A stored object referenced by \`storage_uri\` is treated as **logically immutable**:
- If content changes, the system must not overwrite the object under the same uri.
- Replace operation creates a new object and a new \`doc_id\` (or a new \`doc_version\` if you add versioning later).

## 4. Pointer verification API (recommended)
Implement (or plan) a verification step:
- Given \`doc_id\` + \`chunk_id\` + offsets, re-extract the span and recompute the hash.
- If mismatch:
  - mark pointer status as \`INVALID\`
  - block it from being used for assessment
  - write an audit log entry

## 5. “Stable jump-back” requirement
A pointer is considered stable if:
- the UI can open the original document and highlight the exact span, OR
- the UI can render the extracted span with enough context plus page/offset information to independently validate it.

If stable jump-back cannot be provided, evidence must be labeled as **non-auditable** and excluded from “trusted evidence” flows.

## 6. Known limitations
- Scanned PDFs without OCR: pointers can only reference page ranges and cannot guarantee char offsets.
- For those documents, \`char_start/end\` may be null, and \`quote_hash\` should be computed over OCR output or omitted with explicit \`pointer_type="PAGE_ONLY"\`.
EOF

write_file "$PROT_DIR/consent_semantics.md" <<EOF
# Consent Semantics and Revocation Handling (v0.1)

**Status:** Draft (v0.1)  
**Last updated (UTC):** $(stamp)

This protocol defines what consent means, what revocation means, what is deleted, and what minimal audit traces remain.

## 1. Consent states
- \`granted\`: system may store, process, and reference the document and derived artifacts.
- \`revoked\`: system must stop processing and remove stored content and derived artifacts.

## 2. Revocation meaning
Revocation means:
- the document and its derived artifacts are no longer available for retrieval, search, or assessment
- future assessments must not reference the revoked document

Revocation does **not** claim the document never existed. It means it is no longer authorized for use.

## 3. Deletion scope (minimum)
On revoke, delete:
- object storage file referenced by \`storage_uri\`
- \`documents\` row
- \`chunks\` rows
- \`embeddings\` rows
- any cached search indexes derived from those chunks

## 4. Audit retention (minimal safe trace)
The system may retain a minimal audit record that contains:
- consent action type (grant/revoke)
- actor (user/admin role)
- timestamp
- affected \`doc_id\`
- deletion outcome (success/failure)

The audit record must not retain recoverable content. If a hash is retained, it must not allow reconstruction of original content.

## 5. Visibility rules (recommended)
- Students: can view their own consent status and actions
- Admin/faculty: can view aggregated consent stats and audit trails only if policy allows
- External parties: no access to consent logs by default

## 6. Operational safeguards
- Revoke must be idempotent (safe to run twice)
- Failed deletions must produce an error record that is visible in admin tooling
- Backups must respect consent policy: if backups exist, document the retention period and deletion guarantees.

## 7. Open questions (to resolve later)
- Whether the system supports “temporary pause” vs only revoke
- Backup retention policy and enforcement mechanism
EOF

write_file "$PROT_DIR/assessment_scope.md" <<EOF
# Assessment Scope and Responsibility Boundary (v0.1)

**Status:** Draft (v0.1)  
**Last updated (UTC):** $(stamp)

This protocol prevents misinterpretation of SkillSight outputs as official certification and defines who is responsible for what.

## 1. What SkillSight produces
SkillSight produces **evidence-backed summaries** of:
- whether a document provides evidence related to a skill (demonstrated/mentioned/not enough information)
- an estimated proficiency level **based on the skill's rubric** and referenced evidence pointers

## 2. What SkillSight does NOT produce
SkillSight does not produce:
- official credentials or certifications by default
- a legal guarantee of a person's capability
- a standalone “AI confidence” score as proof

## 3. Roles and responsibility
- System: stores evidence pointers, runs retrieval and optional AI classification under documented rules
- AI component: proposes labels and rationales constrained by rubric and citations
- Human reviewer (faculty/admin): can approve, override, or mark as needs-review

## 4. Required provenance on every assessment record
Every assessment record must store:
- \`skill_id\` (including version)
- \`evidence_pointer_list\` (each with stable jump-back data)
- \`rubric_version\` (or \`skill_version\`)
- if AI used: \`model_id\`, \`prompt_version\`, \`run_timestamp\`

## 5. External use disclaimer (recommended text)
SkillSight outputs are intended to support interpretation and review of evidence within an institutional context. They should be treated as **decision support** and should not be interpreted as an official credential unless explicitly governed by institutional policy.

## 6. Refusal rule (hard requirement)
If evidence pointers do not meet the stability and integrity requirements, the system must output:
- \`not_enough_information\` and a refusal reason
and must not generate a proficiency claim.
EOF

write_file "$PROT_DIR/readiness_philosophy.md" <<EOF
# Readiness Philosophy (No Single Match Score) (v0.1)

**Status:** Draft (v0.1)  
**Last updated (UTC):** $(stamp)

This protocol explains why SkillSight does not produce a single match percentage and what it provides instead.

## 1. Why we do not provide a single match score
A single readiness or match score is often:
- hard to audit (weights become arbitrary)
- easy to misinterpret as ground truth
- unstable across job contexts and time
- prone to hiding evidence gaps

SkillSight prioritizes transparency: stakeholders should see *which skills* are supported by *which evidence*, and where gaps remain.

## 2. What we provide instead (minimum)
For a given role:
- a list of required/optional skills with target levels
- for each skill:
  - evidence status (demonstrated/mentioned/not enough information)
  - rubric-aligned level (if demonstrated)
  - evidence pointers enabling stable jump-back
- a role gap report:
  - missing required skills
  - below-target skills
  - evidence missing (cannot claim)

## 3. If stakeholders demand a summary number
If a numeric summary is necessary, it must be:
- clearly labeled as an internal aggregation for convenience
- accompanied by the skill-by-skill breakdown
- never used as the only basis for decisions

Default: do not show a number unless enabled by governance.
EOF

write_file "$MILE_DIR/demo_definition.md" <<EOF
# Demo Definition and Milestone Boundaries (v0.1)

**Status:** Draft (v0.1)  
**Last updated (UTC):** $(stamp)

This document defines what counts as a “demo” for SkillSight and what is explicitly out of scope at each demo stage.

## Demo v0.1 (target: end of Week 8)
A v0.1 demo is complete when:
1) Skills, Roles, Courses, Documents, Chunks are stored in Postgres with stable IDs and migrations.
2) A user can upload a TXT (and optionally DOCX/PDF later), create chunks, and see chunk snippets in the UI.
3) Evidence Pointers meet MVP fields and can jump back to source text (at least for TXT).
4) Consent grant/revoke works end-to-end and deletes stored content and derived artifacts.
5) Admin UI exists (even minimal) for editing Skill definitions and alias management.

Explicitly out of scope:
- any LLM-based classification
- any “match score” or ranking

## Demo v0.2 (target: end of Week 13)
A v0.2 demo is complete when:
1) Search: skill text -> Top-K evidence pointers via embeddings (with consent filters).
2) Decision outputs:
   - demonstrated/mentioned/not enough information
   - rubric-aligned proficiency levels with cited evidence
3) End-to-end: skill_id + doc_id -> stored assessment record with provenance.

Explicitly out of scope:
- production-scale monitoring
- institution-wide integrations (SSO, SIS/HRIS)
- formal credential issuance

## Acceptance principle
A demo is “real” only if stakeholders can:
- click from an assessment to the original evidence span
- understand what rule produced the claim
- see what the system refuses to claim
EOF

# --------------------------
# Week 1: 10 protocol drafts
# --------------------------

write_file "$PROT_DIR/00_index.md" <<EOF
# Protocol Index (v0.1)

**Last updated (UTC):** $(stamp)

This folder contains the protocols that make SkillSight auditable and institution-grade.

## Core protocols (reviewer-critical)
1. Skill/Role versioning: \`skill_role_versioning.md\`
2. Evidence integrity: \`evidence_integrity.md\`
3. Consent semantics: \`consent_semantics.md\`
4. Assessment scope: \`assessment_scope.md\`
5. Readiness philosophy: \`readiness_philosophy.md\`
6. Demo milestones: \`../milestones/demo_definition.md\`

## Week 1 drafts (scaffold)
- \`protocol_skill_id.md\`
- \`protocol_role_id.md\`
- \`protocol_course_id.md\`
- \`protocol_pointer_and_chunk.md\`
- \`protocol_chunking_rules.md\`
- \`protocol_refusal_rules.md\`
- \`protocol_proficiency_levels.md\`
- \`protocol_audit_and_change_logs.md\`
- \`protocol_consent_and_deletion.md\`
- \`protocol_release_and_compat.md\`
EOF

write_file "$PROT_DIR/protocol_skill_id.md" <<EOF
# Protocol: Skill ID (v0.1)

**Last updated (UTC):** $(stamp)

## Rule
- Skill IDs are stable, public, non-semantic, and versioned.
- Format (example): \`HKU.SSKILL.000123.v1\`

## Why
IDs must remain stable across renaming, alias changes, and rubric evolution.

## Required fields
- \`skill_id\`
- \`version\`
- \`source\`

## Open decisions
- Whether to support minor versions (v1.1) or major-only (v1, v2)
EOF

write_file "$PROT_DIR/protocol_role_id.md" <<EOF
# Protocol: Role ID (v0.1)

**Last updated (UTC):** $(stamp)

## Rule
- Role IDs are stable, public, non-semantic, and versioned.
- Roles reference skills by \`skill_id\` including version.

## Why
Role requirements must remain interpretable when skills evolve.
EOF

write_file "$PROT_DIR/protocol_course_id.md" <<EOF
# Protocol: Course ID and Course Metadata (v0.1)

**Last updated (UTC):** $(stamp)

## Rule
- Course IDs should be stable and map to the university’s official identifiers when available.

## Required metadata (minimum)
- \`course_id\`, \`code\`, \`title\`
- \`description\` (short)
- \`assessment_types\` (free text list is acceptable for v0.1)
EOF

write_file "$PROT_DIR/protocol_pointer_and_chunk.md" <<EOF
# Protocol: Evidence Pointer and Chunk (v0.1)

**Last updated (UTC):** $(stamp)

## Rule
- Every claim must cite one or more evidence pointers that can jump back to source.

## Chunk requirements
- stable \`chunk_id\`
- offsets (\`char_start/end\`) when possible
- page ranges for PDFs when possible
- stored \`quote_hash\` for integrity
EOF

write_file "$PROT_DIR/protocol_chunking_rules.md" <<EOF
# Protocol: Chunking Rules (v0.1)

**Last updated (UTC):** $(stamp)

## v0.1 chunking
- Chunk by paragraph (TXT/DOCX) with order preserved
- Carry a \`section_path\` when structure exists (DOCX headings)
- Keep chunk size under a configurable max length

## Non-goals
- OCR for scanned PDFs is not required in v0.1
EOF

write_file "$PROT_DIR/protocol_refusal_rules.md" <<EOF
# Protocol: Refusal Rules (v0.1)

**Last updated (UTC):** $(stamp)

## Hard refusal conditions
The system must refuse to make a skill/proficiency claim when:
- evidence pointers cannot be generated or verified
- evidence is missing or consent is revoked
- AI output lacks citations to pointers
EOF

write_file "$PROT_DIR/protocol_proficiency_levels.md" <<EOF
# Protocol: Proficiency Levels (v0.1)

**Last updated (UTC):** $(stamp)

## Rule
Proficiency is rubric-driven, not an "AI confidence score".

## Suggested scale (v0.1)
- Level 0: no evidence
- Level 1: basic / assisted
- Level 2: independent / competent
- Level 3: advanced / flexible transfer

Each skill may override or extend this with its own \`level_rubric\`.
EOF

write_file "$PROT_DIR/protocol_audit_and_change_logs.md" <<EOF
# Protocol: Audit Logs and Change Logs (v0.1)

**Last updated (UTC):** $(stamp)

## Audit log minimum
- actor (user/admin role)
- action
- object type + object id
- timestamp
- before/after summary (or change description)

## Change log minimum
- version bump reason
- reviewer identity/role
- effective date
EOF

write_file "$PROT_DIR/protocol_consent_and_deletion.md" <<EOF
# Protocol: Consent and Deletion (v0.1)

**Last updated (UTC):** $(stamp)

This file anchors the technical deletion chain to the consent semantics.

## Rule
Revoke triggers deletion of:
- object store content
- documents/chunks/embeddings rows
- derived indexes

Audit retains only minimal non-content traces.
EOF

write_file "$PROT_DIR/protocol_release_and_compat.md" <<EOF
# Protocol: Release and Compatibility (v0.1)

**Last updated (UTC):** $(stamp)

## Rule
- Protocol changes are versioned.
- Breaking changes require a major bump.
- Demos must state which protocol set they implement.

## Required
- \`docs/protocols/00_index.md\` is the entry point.
EOF

ensure_readme_section

echo ""
echo "✅ Protocol patch applied."
echo "Next steps:"
echo "  - Review docs/protocols/*.md"
echo "  - Commit: git add docs README.md && git commit -m \"Add governance protocols v0.1\""