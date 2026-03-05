# Protocol 10: Change Log (v0.1)

## Purpose
Defines how skill assessment changes are tracked and explained to users. Ensures transparency when a student's skill profile changes over time.

## Scope
- **In scope:** Change detection, change explanations, notification triggers
- **Out of scope:** Notification delivery mechanisms

## Core Principle

**"Every change has a reason."**

When a student's skill assessment changes, they must be able to see:
1. What changed (before vs. after)
2. Why it changed (new evidence, updated rubric, human override, etc.)

## Change Types

| Change Type | Trigger | Explanation |
|-------------|---------|-------------|
| `new_document` | User uploaded new document | "New evidence from [document title]" |
| `reassessment` | Document was re-assessed | "Updated analysis of existing evidence" |
| `rubric_update` | Skill rubric was modified | "Skill criteria have been updated" |
| `human_override` | Staff manually changed assessment | "Reviewed and adjusted by [staff name]" |
| `role_update` | Role requirements changed | "Role skill requirements were updated" |

## Objects and Fields (v0.1)

### ChangeLog
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `change_id` | UUID | Yes | Unique change identifier |
| `object_type` | string | Yes | What changed (skill_assessment, role_readiness, etc.) |
| `doc_id` | string | No | Related document |
| `key_id` | string | Yes | Skill ID or Role ID that changed |
| `change_type` | string | Yes | See Change Types above |
| `before` | object | Yes | State before change |
| `after` | object | Yes | State after change |
| `diff` | object | Yes | Computed difference |
| `explanation` | string | Yes | Human-readable explanation |
| `created_at` | timestamp | Yes | When change occurred |

## Database Schema

```sql
CREATE TABLE change_logs (
    change_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    object_type TEXT NOT NULL,
    doc_id TEXT,
    key_id TEXT NOT NULL,
    change_type TEXT NOT NULL,
    before_state JSONB NOT NULL DEFAULT '{}',
    after_state JSONB NOT NULL DEFAULT '{}',
    diff JSONB NOT NULL DEFAULT '{}',
    explanation TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_change_logs_doc ON change_logs(doc_id);
CREATE INDEX idx_change_logs_key ON change_logs(key_id);
CREATE INDEX idx_change_logs_created ON change_logs(created_at DESC);
```

## Diff Calculation

### Skill Proficiency Change
```python
def diff_skill_proficiency(before: dict, after: dict) -> dict:
    """Calculate difference between proficiency states."""
    return {
        "level_change": after.get("level", 0) - before.get("level", 0),
        "label_before": before.get("label"),
        "label_after": after.get("label"),
        "direction": "improved" if after.get("level", 0) > before.get("level", 0) 
                     else "declined" if after.get("level", 0) < before.get("level", 0)
                     else "unchanged"
    }
```

### Role Readiness Change
```python
def diff_role_readiness(before: dict, after: dict) -> dict:
    """Calculate difference between readiness states."""
    before_summary = before.get("status_summary", {})
    after_summary = after.get("status_summary", {})
    
    return {
        "score_before": before.get("score", 0),
        "score_after": after.get("score", 0),
        "score_change": after.get("score", 0) - before.get("score", 0),
        "meet_change": after_summary.get("meet", 0) - before_summary.get("meet", 0),
        "missing_change": after_summary.get("missing_proof", 0) - before_summary.get("missing_proof", 0),
        "direction": "improved" if after.get("score", 0) > before.get("score", 0)
                     else "declined" if after.get("score", 0) < before.get("score", 0)
                     else "unchanged"
    }
```

## Implementation

```python
def log_change(
    db,
    object_type: str,
    doc_id: str | None,
    key_id: str,
    change_type: str,
    before: dict,
    after: dict,
    explanation: str
) -> str:
    """Record a change in the change log."""
    change_id = str(uuid.uuid4())
    
    # Calculate diff based on object type
    if object_type == "skill_proficiency":
        diff = diff_skill_proficiency(before, after)
    elif object_type == "role_readiness":
        diff = diff_role_readiness(before, after)
    else:
        diff = {"before": before, "after": after}
    
    db.execute(
        text("""
            INSERT INTO change_logs 
            (change_id, object_type, doc_id, key_id, change_type, 
             before_state, after_state, diff, explanation, created_at)
            VALUES (:change_id, :object_type, :doc_id, :key_id, :change_type,
                    CAST(:before AS JSONB), CAST(:after AS JSONB), 
                    CAST(:diff AS JSONB), :explanation, now())
        """),
        {
            "change_id": change_id,
            "object_type": object_type,
            "doc_id": doc_id,
            "key_id": key_id,
            "change_type": change_type,
            "before": json.dumps(before),
            "after": json.dumps(after),
            "diff": json.dumps(diff),
            "explanation": explanation,
        }
    )
    
    return change_id
```

## Rules (v0.1)

1. **Always Log:** Any change to skill_proficiency or role_readiness MUST be logged.
2. **Before Required:** The `before` state must be captured before the change.
3. **Explanation Required:** Every change must have a human-readable explanation.
4. **No Content:** Don't store document content in change logs.
5. **User Access:** Users can view changes to their own documents.

## Examples

### Skill Proficiency Improved
```json
{
  "change_id": "...",
  "object_type": "skill_proficiency",
  "doc_id": "doc-123",
  "key_id": "HKU.SKILL.PRIVACY.v1",
  "change_type": "new_document",
  "before_state": {
    "level": 1,
    "label": "developing"
  },
  "after_state": {
    "level": 2,
    "label": "proficient"
  },
  "diff": {
    "level_change": 1,
    "label_before": "developing",
    "label_after": "proficient",
    "direction": "improved"
  },
  "explanation": "New evidence from 'Week 9 Project Report' demonstrates concrete privacy practices.",
  "created_at": "2026-01-21T12:00:00Z"
}
```

### Role Readiness Updated
```json
{
  "change_id": "...",
  "object_type": "role_readiness",
  "doc_id": "doc-123",
  "key_id": "HKU.ROLE.ASSISTANT_PM.v1",
  "change_type": "reassessment",
  "before_state": {
    "score": 0.5,
    "status_summary": {"meet": 1, "missing_proof": 1, "needs_strengthening": 0}
  },
  "after_state": {
    "score": 0.75,
    "status_summary": {"meet": 2, "missing_proof": 0, "needs_strengthening": 0}
  },
  "diff": {
    "score_before": 0.5,
    "score_after": 0.75,
    "score_change": 0.25,
    "direction": "improved"
  },
  "explanation": "Privacy skill now demonstrated at required level.",
  "created_at": "2026-01-21T12:05:00Z"
}
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/change-logs?doc_id=X` | List changes for a document |
| GET | `/change-logs?key_id=X` | List changes for a skill/role |

## Open Questions
- [ ] Should we support email/push notifications for significant changes?
- [ ] How long to retain change logs?
