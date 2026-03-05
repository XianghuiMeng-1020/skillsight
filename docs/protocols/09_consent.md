# Protocol 9: Consent (v0.1)

## Purpose
Defines the consent management lifecycle for student artifacts. Ensures students have control over their data and that revocation triggers complete data deletion.

## Scope
- **In scope:** Consent states, grant/revoke workflow, cascade deletion
- **Out of scope:** Authentication, authorization (handled separately)

## Core Principle

**"Revoke means delete."**

When a user revokes consent for a document, ALL related data MUST be permanently deleted, including:
- The document file itself
- All chunks derived from the document
- All vector embeddings
- All skill assessments
- All proficiency records
- All role readiness records

## Consent States

| State | Description |
|-------|-------------|
| `granted` | User has granted consent for processing |
| `revoked` | User has revoked consent; data has been deleted |

## Objects and Fields (v0.1)

### ConsentRecord
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `consent_id` | UUID | Yes | Unique consent record ID |
| `user_id` | string | Yes | User who owns the document |
| `doc_id` | string | Yes | Document this consent applies to |
| `status` | string | Yes | "granted" or "revoked" |
| `created_at` | timestamp | Yes | When consent was granted |
| `revoked_at` | timestamp | No | When consent was revoked |
| `revoke_reason` | string | No | Reason for revocation |

## Database Schema

```sql
CREATE TABLE consents (
    consent_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    doc_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'granted',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at TIMESTAMPTZ,
    revoke_reason TEXT
);

CREATE INDEX idx_consents_user ON consents(user_id);
CREATE INDEX idx_consents_doc ON consents(doc_id);
CREATE INDEX idx_consents_status ON consents(status);
```

## Consent Grant Workflow

```
1. User uploads document with consent checkbox checked
2. System creates consent record (status = 'granted')
3. Document is processed (chunked, embedded, assessed)
4. User can access their skill profile
```

## Consent Revoke Workflow (CASCADE DELETE)

```
1. User requests consent revocation
2. System verifies user owns the document
3. Cascade delete begins (in order due to FK constraints):
   a. role_readiness records
   b. skill_proficiency records
   c. skill_assessments records
   d. chunks table records
   e. Vector embeddings (Qdrant)
   f. Physical file (storage)
   g. documents table record
4. Update consent status to 'revoked'
5. Write audit log (action, counts, but NOT content)
6. Return confirmation with deletion counts
```

## Implementation

```python
def cascade_delete_document_data(db, doc_id: str) -> dict:
    """Delete all data related to a document."""
    deleted = {}
    
    # Order matters for FK constraints
    tables = [
        "role_readiness",
        "skill_proficiency",
        "skill_assessments",
        "chunks",
    ]
    
    for table in tables:
        try:
            result = db.execute(
                text(f"DELETE FROM {table} WHERE doc_id = :doc_id"),
                {"doc_id": doc_id}
            )
            deleted[table] = result.rowcount or 0
        except Exception:
            deleted[table] = 0
    
    # Delete vector embeddings
    try:
        from backend.app.vector_store import get_client, delete_by_doc_id
        client = get_client()
        delete_by_doc_id(client, doc_id)
        deleted["embeddings"] = 1
    except Exception:
        deleted["embeddings"] = 0
    
    # Delete physical file
    try:
        row = db.execute(
            text("SELECT stored_path FROM documents WHERE doc_id = :doc_id"),
            {"doc_id": doc_id}
        ).mappings().first()
        if row and row.get("stored_path"):
            import os
            if os.path.exists(row["stored_path"]):
                os.remove(row["stored_path"])
                deleted["files"] = 1
    except Exception:
        deleted["files"] = 0
    
    # Delete document record
    try:
        result = db.execute(
            text("DELETE FROM documents WHERE doc_id = :doc_id"),
            {"doc_id": doc_id}
        )
        deleted["documents"] = result.rowcount or 0
    except Exception:
        deleted["documents"] = 0
    
    return deleted
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/consents` | List user's consent records |
| GET | `/consents/{doc_id}` | Get consent status for document |
| POST | `/consent/grant` | Grant consent for document |
| POST | `/consent/revoke` | Revoke consent (cascade delete) |
| POST | `/consent/revoke/dry-run` | Preview what would be deleted |

## Rules (v0.1)

1. **One Consent Per Document:** Each document has exactly one consent record.
2. **User Ownership:** Only the owning user can revoke consent.
3. **Complete Deletion:** Revoke MUST delete all derived data, not just mark inactive.
4. **Audit Trail:** Revocation is logged but content is NOT preserved.
5. **Irreversible:** Revoked data cannot be recovered (by design).

## Examples

### Grant Request
```json
{
  "user_id": "student-12345",
  "doc_id": "doc-67890"
}
```

### Grant Response
```json
{
  "ok": true,
  "consent_id": "abc-123",
  "status": "granted"
}
```

### Revoke Request
```json
{
  "user_id": "student-12345",
  "doc_id": "doc-67890",
  "reason": "I no longer want my data processed"
}
```

### Revoke Response
```json
{
  "ok": true,
  "doc_id": "doc-67890",
  "deleted": {
    "role_readiness": 2,
    "skill_proficiency": 15,
    "skill_assessments": 15,
    "chunks": 42,
    "embeddings": 1,
    "files": 1,
    "documents": 1
  },
  "audit_id": "audit-xyz",
  "message": "All document data has been permanently deleted."
}
```

## Open Questions
- [ ] Should we support partial consent (some skills but not others)?
- [ ] How to handle shared documents (multiple users)?
