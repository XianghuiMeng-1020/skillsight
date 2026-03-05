# Protocol 1: Skill ID (v0.1)

## Purpose
Defines the stable, versioned identifier format for skills in SkillSight. Ensures skills can be referenced consistently across documents, assessments, roles, and external systems.

## Scope
- **In scope:** Skill identifier format, versioning, aliases, canonical names
- **Out of scope:** Skill content/rubric definitions (see Protocol 7)

## Objects and Fields (v0.1)

### Skill
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `skill_id` | string | Yes | Stable identifier, format: `{NAMESPACE}.SKILL.{NAME}.{VERSION}` |
| `canonical_name` | string | Yes | Human-readable display name (e.g., "Academic Integrity") |
| `aliases` | string[] | No | Alternative names/synonyms for search |
| `definition` | string | Yes | 1-3 sentences describing observable behavior |
| `evidence_rules` | string | No | Guidance on what counts as evidence |
| `level_rubric_json` | object | No | Proficiency rubric (see Protocol 7) |
| `version` | string | Yes | Version tag (e.g., "v1", "v2") |
| `source` | string | No | Origin (e.g., "HKU", "O*NET", "Lightcast") |
| `created_at` | timestamp | Yes | Creation timestamp |
| `updated_at` | timestamp | No | Last modification timestamp |

### Skill ID Format
```
{NAMESPACE}.SKILL.{NAME}.{VERSION}
```
- **NAMESPACE:** Organization prefix (e.g., `HKU`, `ONET`)
- **NAME:** UPPERCASE_SNAKE_CASE identifier (e.g., `ACADEMIC_INTEGRITY`)
- **VERSION:** Version tag (e.g., `v1`, `v2`)

Examples:
- `HKU.SKILL.ACADEMIC_INTEGRITY.v1`
- `HKU.SKILL.PRIVACY.v1`
- `ONET.SKILL.CRITICAL_THINKING.v1`

## Rules (v0.1)

1. **Stability:** Once assigned, a `skill_id` MUST NOT change. To modify skill content, create a new version.
2. **Uniqueness:** `skill_id` is globally unique within the system.
3. **Versioning:** When skill definition changes materially, increment version (`v1` → `v2`).
4. **Aliases:** Aliases are searchable synonyms; they do NOT replace `canonical_name`.
5. **Crosswalk:** External skill IDs (O*NET, Lightcast) map via `skill_aliases` table with `source` field.

## Validation Rules

```python
import re

def validate_skill_id(skill_id: str) -> bool:
    pattern = r'^[A-Z0-9]+\.SKILL\.[A-Z0-9_]+\.v\d+$'
    return bool(re.match(pattern, skill_id))
```

## Database Tables

```sql
-- Primary skills table
CREATE TABLE skills (
    skill_id TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    definition TEXT NOT NULL,
    evidence_rules TEXT,
    level_rubric_json JSONB,
    version TEXT NOT NULL DEFAULT 'v1',
    source TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ
);

-- Aliases for search and crosswalk
CREATE TABLE skill_aliases (
    alias_id UUID PRIMARY KEY,
    skill_id TEXT NOT NULL REFERENCES skills(skill_id),
    alias TEXT NOT NULL,
    source TEXT,  -- e.g., "HKU", "ONET", "user_input"
    confidence NUMERIC,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_skill_alias ON skill_aliases(skill_id, alias);
```

## Examples

```json
{
  "skill_id": "HKU.SKILL.ACADEMIC_INTEGRITY.v1",
  "canonical_name": "Academic Integrity",
  "aliases": ["plagiarism", "cheating", "misconduct"],
  "definition": "Demonstrates understanding of academic integrity rules, identifies violations (e.g., cheating, plagiarism), and explains appropriate responses.",
  "evidence_rules": "Look for: citation practices, paraphrasing examples, discussion of misconduct policies.",
  "version": "v1",
  "source": "HKU"
}
```

## Open Questions
- [ ] Should we support hierarchical skills (parent/child)?
- [ ] How to handle deprecated skills that are still referenced?
