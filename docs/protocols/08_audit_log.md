# Protocol 8: Audit Log (v0.1)

## Purpose
Defines the audit logging structure for tracking all significant actions in SkillSight. Ensures accountability, debugging capability, and compliance with data governance requirements.

## Scope
- **In scope:** Audit event structure, logged actions, retention policy
- **Out of scope:** Real-time monitoring, alerting

## Objects and Fields (v0.1)

### AuditLog
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `audit_id` | UUID | Yes | Unique audit entry identifier |
| `action` | string | Yes | Action type (see Action Types) |
| `subject_id` | string | Yes | Who performed the action (user_id or system_id) |
| `object_type` | string | Yes | Type of object affected (document, skill, role, etc.) |
| `object_id` | string | Yes | ID of the affected object |
| `detail` | object | No | Additional context (JSON) |
| `created_at` | timestamp | Yes | When the action occurred |

## Action Types (v0.1)

### Document Actions
| Action | Description |
|--------|-------------|
| `document.upload` | User uploaded a document |
| `document.delete` | Document was deleted |
| `document.view` | User viewed a document |

### Consent Actions
| Action | Description |
|--------|-------------|
| `consent.grant` | User granted consent for document processing |
| `consent.revoke` | User revoked consent (triggers cascade delete) |

### Assessment Actions
| Action | Description |
|--------|-------------|
| `assessment.run` | Skill assessment was executed |
| `assessment.override` | Staff overrode an AI assessment |
| `proficiency.calculate` | Proficiency level was calculated |
| `readiness.calculate` | Role readiness was calculated |

### Admin Actions
| Action | Description |
|--------|-------------|
| `skill.create` | New skill was added |
| `skill.update` | Skill definition was modified |
| `role.create` | New role was added |
| `role.update` | Role requirements were modified |
| `course_skill_map.approve` | Instructor approved course-skill mapping |
| `course_skill_map.reject` | Instructor rejected course-skill mapping |

### Auth Actions
| Action | Description |
|--------|-------------|
| `auth.login` | User logged in |
| `auth.logout` | User logged out |
| `auth.token_refresh` | Token was refreshed |

## Database Schema

```sql
CREATE TABLE audit_logs (
    audit_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    action TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    object_type TEXT NOT NULL,
    object_id TEXT NOT NULL,
    detail JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_audit_logs_subject ON audit_logs(subject_id);
CREATE INDEX idx_audit_logs_object ON audit_logs(object_type, object_id);
CREATE INDEX idx_audit_logs_action ON audit_logs(action);
CREATE INDEX idx_audit_logs_created ON audit_logs(created_at DESC);
```

## Logging Implementation

```python
import uuid
from datetime import datetime, timezone

def log_audit(
    db,
    action: str,
    subject_id: str,
    object_type: str,
    object_id: str,
    detail: dict = None
) -> str:
    """Write an audit log entry."""
    audit_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    
    db.execute(
        text("""
            INSERT INTO audit_logs 
            (audit_id, action, subject_id, object_type, object_id, detail, created_at)
            VALUES (:audit_id, :action, :subject_id, :object_type, :object_id, 
                    CAST(:detail AS JSONB), :created_at)
        """),
        {
            "audit_id": audit_id,
            "action": action,
            "subject_id": subject_id,
            "object_type": object_type,
            "object_id": object_id,
            "detail": json.dumps(detail or {}),
            "created_at": now,
        }
    )
    
    return audit_id
```

## Rules (v0.1)

1. **Completeness:** All actions in the action list MUST be logged.
2. **Immutability:** Audit logs are append-only; never update or delete.
3. **Subject Tracking:** Always identify who performed the action.
4. **Sensitive Data:** Detail field must NOT contain PII or document content.
5. **Retention:** Logs retained for minimum 7 years (configurable).

## Examples

### Consent Revoke Audit
```json
{
  "audit_id": "550e8400-e29b-41d4-a716-446655440000",
  "action": "consent.revoke",
  "subject_id": "user-12345",
  "object_type": "document",
  "object_id": "doc-67890",
  "detail": {
    "reason": "User requested data deletion",
    "deleted_counts": {
      "chunks": 15,
      "embeddings": 1,
      "assessments": 3
    }
  },
  "created_at": "2026-01-21T10:30:00Z"
}
```

### Assessment Run Audit
```json
{
  "audit_id": "...",
  "action": "assessment.run",
  "subject_id": "system",
  "object_type": "document",
  "object_id": "doc-67890",
  "detail": {
    "run_id": "run-abc123",
    "skills_evaluated": 25,
    "chunks_scanned": 42,
    "rule_version": "rule_v2_scored_keyword_match"
  },
  "created_at": "2026-01-21T10:31:00Z"
}
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/audit-logs` | List audit logs (admin only) |
| GET | `/audit-logs?object_id=X` | Filter by object |
| GET | `/audit-logs?subject_id=X` | Filter by user |

## Open Questions
- [ ] Should we support audit log export (CSV/JSON)?
- [ ] How to handle audit log search performance at scale?
