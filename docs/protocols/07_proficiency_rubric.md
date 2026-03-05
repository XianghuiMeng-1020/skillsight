# Protocol 7: Proficiency Rubric (v0.1)

## Purpose
Defines the proficiency level scale and rubric structure for skill assessment. Ensures proficiency judgments are grounded in observable criteria, not AI confidence scores.

## Scope
- **In scope:** Level definitions, rubric structure, assessment rules
- **Out of scope:** Specific rubrics for each skill (stored in skill registry)

## Proficiency Scale (v0.1)

| Level | Label | Description |
|-------|-------|-------------|
| 0 | Novice | No evidence or evidence too vague to assess |
| 1 | Developing | Skill mentioned or described at general level |
| 2 | Proficient | Concrete application demonstrated with specifics |
| 3 | Advanced | Multiple concrete examples, deep understanding, or complex application |

## Rubric Structure

Each skill defines a rubric with criteria for each level:

```json
{
  "levels": {
    "0": {
      "label": "novice",
      "criteria": [
        {"id": "XX0-1", "text": "No evidence of skill in artifact."},
        {"id": "XX0-2", "text": "Mentions too vague to locate or verify."}
      ]
    },
    "1": {
      "label": "developing",
      "criteria": [
        {"id": "XX1-1", "text": "Skill mentioned but not applied."},
        {"id": "XX1-2", "text": "General awareness without specifics."}
      ]
    },
    "2": {
      "label": "proficient",
      "criteria": [
        {"id": "XX2-1", "text": "Concrete example of skill application."},
        {"id": "XX2-2", "text": "Describes specific actions or decisions."}
      ]
    },
    "3": {
      "label": "advanced",
      "criteria": [
        {"id": "XX3-1", "text": "Multiple concrete examples across contexts."},
        {"id": "XX3-2", "text": "Evidence of reflection or optimization."},
        {"id": "XX3-3", "text": "Evidence spans multiple document sections."}
      ]
    }
  }
}
```

## Criterion ID Format
```
{SKILL_PREFIX}{LEVEL}-{NUMBER}
```
Examples:
- `AI0-1`: Academic Integrity, Level 0, Criterion 1
- `PR2-2`: Privacy, Level 2, Criterion 2

## Assessment Rules (v0.1)

1. **Rubric Required:** Every proficiency assessment MUST reference the skill's rubric.
2. **Evidence Required:** Level > 0 requires at least one valid evidence pointer.
3. **Criteria Matching:** Output must list which criteria IDs are matched.
4. **Highest Earned:** Assign the highest level where ALL criteria are met.
5. **Refusal to Level 0:** If insufficient evidence, assign level 0 (see Protocol 6).

## Assessment Output Format

```json
{
  "level": 2,
  "label": "proficient",
  "matched_criteria": ["PR2-1", "PR2-2"],
  "evidence_chunk_ids": ["chunk-123", "chunk-456"],
  "why": "The document describes anonymizing email addresses (PR2-1) and implementing access controls for student data (PR2-2)."
}
```

## Validation Logic

```python
def validate_proficiency_output(
    output: dict,
    valid_chunk_ids: list[str],
    valid_criteria: list[str]
) -> dict:
    """Validate and normalize proficiency output."""
    level = output.get("level", 0)
    if not isinstance(level, int) or level < 0 or level > 3:
        level = 0
    
    label_map = {0: "novice", 1: "developing", 2: "proficient", 3: "advanced"}
    label = label_map.get(level, "novice")
    
    # Filter evidence to valid IDs
    evidence_ids = output.get("evidence_chunk_ids", [])
    evidence_ids = [cid for cid in evidence_ids if cid in set(valid_chunk_ids)]
    
    # Filter criteria to valid IDs
    matched = output.get("matched_criteria", [])
    if valid_criteria:
        matched = [c for c in matched if c in set(valid_criteria)]
    
    # Enforce: no evidence → level 0
    if not evidence_ids and level > 0:
        level = 0
        label = "novice"
    
    return {
        "level": level,
        "label": label,
        "matched_criteria": matched,
        "evidence_chunk_ids": evidence_ids,
        "why": output.get("why", "")[:500]
    }
```

## Database Schema

```sql
CREATE TABLE skill_proficiency (
    prof_id UUID PRIMARY KEY,
    doc_id TEXT NOT NULL,
    skill_id TEXT NOT NULL REFERENCES skills(skill_id),
    level INTEGER NOT NULL DEFAULT 0,
    label TEXT NOT NULL DEFAULT 'novice',
    rationale TEXT,
    best_evidence JSONB,  -- Top evidence pointer
    signals JSONB,  -- Additional metadata
    meta JSONB,  -- Model version, run_id, etc.
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_prof_doc_skill ON skill_proficiency(doc_id, skill_id);
```

## Example Rubric: Academic Integrity

```json
{
  "skill_id": "HKU.SKILL.ACADEMIC_INTEGRITY.v1",
  "level_rubric": {
    "levels": {
      "0": {
        "label": "novice",
        "criteria": [
          {"id": "AI0-1", "text": "No evidence of academic integrity concepts."},
          {"id": "AI0-2", "text": "Mentions too vague to locate or verify."}
        ]
      },
      "1": {
        "label": "developing",
        "criteria": [
          {"id": "AI1-1", "text": "Mentions integrity/misconduct without application."},
          {"id": "AI1-2", "text": "General awareness without concrete actions."}
        ]
      },
      "2": {
        "label": "proficient",
        "criteria": [
          {"id": "AI2-1", "text": "Describes concrete integrity practice (citing, paraphrasing)."},
          {"id": "AI2-2", "text": "Identifies misconduct and appropriate response."}
        ]
      },
      "3": {
        "label": "advanced",
        "criteria": [
          {"id": "AI3-1", "text": "Multiple practices connected to policy reasoning."},
          {"id": "AI3-2", "text": "Describes risk case and corrective workflow."},
          {"id": "AI3-3", "text": "Evidence spans multiple document sections."}
        ]
      }
    }
  }
}
```

## Open Questions
- [ ] Should we support half-levels (e.g., 2.5)?
- [ ] How to handle skills without defined rubrics?
