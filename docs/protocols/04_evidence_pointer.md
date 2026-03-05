# Protocol 4: Evidence Pointer (v0.1)

## Purpose
Defines the structure for referencing specific text spans in source documents. Ensures every skill assessment can be traced back to exact evidence in the original artifact.

## Scope
- **In scope:** Pointer structure, location fields, integrity verification
- **Out of scope:** How evidence is evaluated (Protocol 6, 7)

## Objects and Fields (v0.1)

### EvidencePointer
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `doc_id` | UUID | Yes | Reference to source document |
| `chunk_id` | UUID | Yes | Reference to specific chunk |
| `char_start` | integer | Yes | Character offset start (0-indexed) |
| `char_end` | integer | Yes | Character offset end (exclusive) |
| `page_start` | integer | No | PDF page number start (1-indexed) |
| `page_end` | integer | No | PDF page number end |
| `section_path` | string | No | Document structure path (e.g., "2.1 Methods") |
| `snippet` | string | Yes | Preview text (≤300 chars) |
| `quote_hash` | string | Yes | SHA-256 hash of original text for integrity |
| `storage_uri` | string | No | URI to original file in storage |
| `created_at` | timestamp | Yes | Creation timestamp |

## Rules (v0.1)

1. **Traceability:** Every skill assessment MUST include at least one EvidencePointer or explicitly refuse (Protocol 6).
2. **Immutability:** Once created, pointers are immutable. Changes require new assessment.
3. **Integrity:** `quote_hash` is computed from the original chunk text, not the snippet.
4. **Snippet Limit:** Snippet is max 300 characters for display; full text in chunk.
5. **Character Offsets:** `char_start` is inclusive, `char_end` is exclusive (Python slice semantics).

## Integrity Verification

```python
import hashlib

def verify_pointer_integrity(chunk_text: str, quote_hash: str) -> bool:
    """Verify that chunk text matches stored hash."""
    computed = hashlib.sha256(chunk_text.encode('utf-8')).hexdigest()
    return computed == quote_hash

def compute_quote_hash(text: str) -> str:
    """Compute hash for a text chunk."""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()
```

## Pointer Resolution

To display evidence to user:
1. Fetch document by `doc_id`
2. Fetch chunk by `chunk_id`
3. Verify `quote_hash` matches chunk text
4. Display `snippet` with link to full chunk
5. If PDF, navigate to `page_start`

## Database Schema

```sql
-- Chunks table stores the evidence content
CREATE TABLE chunks (
    chunk_id UUID PRIMARY KEY,
    doc_id UUID NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    idx INTEGER NOT NULL,
    char_start INTEGER NOT NULL,
    char_end INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    snippet TEXT NOT NULL,
    quote_hash TEXT NOT NULL,
    section_path TEXT,
    page_start INTEGER,
    page_end INTEGER,
    storage_uri TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Assessments reference chunks via evidence array
CREATE TABLE skill_assessments (
    assessment_id UUID PRIMARY KEY,
    doc_id TEXT NOT NULL,
    skill_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    evidence JSONB NOT NULL DEFAULT '[]',  -- Array of EvidencePointer objects
    decision_meta JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

## Examples

```json
{
  "doc_id": "550e8400-e29b-41d4-a716-446655440000",
  "chunk_id": "6fa459ea-ee8a-3ca4-894e-db77e160355e",
  "char_start": 1024,
  "char_end": 1356,
  "page_start": 3,
  "page_end": 3,
  "section_path": "2.1 Privacy Considerations",
  "snippet": "To protect student privacy, we anonymize all identifying information before processing. Names are replaced with random IDs, and email addresses are removed entirely...",
  "quote_hash": "a7ffc6f8bf1ed76651c14756a061d662f580ff4de43b49fa82d80a4b80f8434a"
}
```

## Validation Rules

```python
def validate_pointer(pointer: dict) -> list[str]:
    errors = []
    
    if not pointer.get("doc_id"):
        errors.append("doc_id is required")
    if not pointer.get("chunk_id"):
        errors.append("chunk_id is required")
    if pointer.get("char_start") is None:
        errors.append("char_start is required")
    if pointer.get("char_end") is None:
        errors.append("char_end is required")
    if pointer.get("char_start", 0) >= pointer.get("char_end", 0):
        errors.append("char_start must be < char_end")
    if not pointer.get("snippet"):
        errors.append("snippet is required")
    if len(pointer.get("snippet", "")) > 300:
        errors.append("snippet must be ≤ 300 characters")
    if not pointer.get("quote_hash"):
        errors.append("quote_hash is required")
    
    return errors
```

## Open Questions
- [ ] How to handle pointers when source document is updated?
- [ ] Should we support cross-document pointers?
