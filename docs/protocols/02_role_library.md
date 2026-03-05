# Protocol 2: Role Library (v0.1)

## Purpose
Defines the structure for job roles and their skill requirements. Enables Decision 4 (Role Readiness) by mapping roles to required skills with target proficiency levels.

## Scope
- **In scope:** Role structure, skill requirements, target levels, weighting
- **Out of scope:** Skill definitions (Protocol 1), proficiency assessment (Protocol 7)

## Objects and Fields (v0.1)

### Role
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `role_id` | string | Yes | Stable identifier, format: `{NAMESPACE}.ROLE.{NAME}.{VERSION}` |
| `role_title` | string | Yes | Human-readable job title |
| `description` | string | No | Role description and context |
| `skills_required` | SkillRequirement[] | Yes | List of required/optional skills |
| `source` | string | No | Origin (e.g., "HKU", "Lightcast") |
| `created_at` | timestamp | Yes | Creation timestamp |
| `updated_at` | timestamp | No | Last modification timestamp |

### SkillRequirement
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `skill_id` | string | Yes | Reference to skills.skill_id |
| `target_level` | integer | Yes | Required proficiency level (0-3) |
| `required` | boolean | Yes | true = must have, false = nice to have |
| `weight` | float | No | Importance weight (default: 1.0) |

### Role ID Format
```
{NAMESPACE}.ROLE.{NAME}.{VERSION}
```
Examples:
- `HKU.ROLE.ASSISTANT_PM.v1`
- `HKU.ROLE.EDTECH_RESEARCH_ASSISTANT.v1`

## Rules (v0.1)

1. **Stability:** `role_id` is immutable once assigned.
2. **Skill References:** All `skill_id` values must exist in the skills table.
3. **Target Levels:** Must be 0-3 (matching Protocol 7 proficiency scale).
4. **Required Flag:** Used for readiness calculation; missing required skills = "missing_proof".
5. **Weights:** Higher weight = more important for role score calculation.

## Readiness Calculation

For each skill requirement:
- **meet:** demonstrated AND level >= target_level → 100%
- **needs_strengthening:** demonstrated but level < target_level → 50%
- **missing_proof:** not demonstrated → 0%

Overall score:
```
score = sum(skill_score × weight) / sum(weights)
```

## Database Tables

```sql
-- Roles table
CREATE TABLE roles (
    role_id TEXT PRIMARY KEY,
    role_title TEXT NOT NULL,
    description TEXT,
    source TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ
);

-- Role-skill requirements
CREATE TABLE role_skill_requirements (
    req_id UUID PRIMARY KEY,
    role_id TEXT NOT NULL REFERENCES roles(role_id) ON DELETE CASCADE,
    skill_id TEXT NOT NULL REFERENCES skills(skill_id) ON DELETE RESTRICT,
    target_level INTEGER NOT NULL DEFAULT 0,
    required BOOLEAN NOT NULL DEFAULT true,
    weight NUMERIC NOT NULL DEFAULT 1.0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_role_skill ON role_skill_requirements(role_id, skill_id);
```

## Examples

```json
{
  "role_id": "HKU.ROLE.ASSISTANT_PM.v1",
  "role_title": "Assistant Project Manager (Demo)",
  "skills_required": [
    {
      "skill_id": "HKU.SKILL.ACADEMIC_INTEGRITY.v1",
      "target_level": 2,
      "required": true,
      "weight": 1.0
    },
    {
      "skill_id": "HKU.SKILL.PRIVACY.v1",
      "target_level": 3,
      "required": true,
      "weight": 1.5
    }
  ]
}
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/roles` | List all roles |
| GET | `/roles/{role_id}` | Get role with requirements |
| POST | `/assess/role_readiness` | Calculate readiness for role |

## Open Questions
- [ ] Should we support role hierarchies (junior/senior)?
- [ ] How to handle roles with no skill requirements?
