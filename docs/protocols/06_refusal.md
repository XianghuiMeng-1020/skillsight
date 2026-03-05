# Protocol 6: Refusal (v0.1)

## Purpose
Defines when and how the system must refuse to make a skill assessment. Ensures the system never claims evidence when there is none, protecting against hallucination and false confidence.

## Scope
- **In scope:** Refusal conditions, refusal response format, guardrails
- **Out of scope:** How evidence is evaluated when present (Protocol 7)

## Core Principle

**"No pointer, no claim."**

If the system cannot point to specific evidence in the source document, it MUST refuse to make a positive claim about the skill.

## Refusal Conditions (v0.1)

The system MUST output `"not_enough_information"` when ANY of these conditions are true:

| Condition | Description |
|-----------|-------------|
| **No evidence chunks** | No chunks retrieved or all chunks scored below threshold |
| **Irrelevant evidence** | Retrieved chunks don't relate to the skill being assessed |
| **Generic mention** | Skill term appears but without concrete demonstration |
| **Empty pointer list** | LLM output contains no valid chunk_ids |
| **Parse failure** | LLM output cannot be parsed as valid JSON |
| **Invalid references** | chunk_ids in output don't exist in provided context |

## Response Format

### Refusal Response (Decision 2: Demonstration)
```json
{
  "label": "not_enough_information",
  "evidence_chunk_ids": [],
  "rationale": "",
  "refusal_reason": "Evidence insufficient or irrelevant to demonstrate this skill."
}
```

### Refusal Response (Decision 3: Proficiency)
```json
{
  "level": 0,
  "label": "novice",
  "matched_criteria": [],
  "evidence_chunk_ids": [],
  "why": "Insufficient evidence to assess proficiency level."
}
```

## Validation Logic

```python
def validate_demonstration_output(
    output: dict,
    valid_chunk_ids: list[str]
) -> dict:
    """
    Validate LLM output and enforce refusal rules.
    Returns normalized output.
    """
    label = output.get("label", "not_enough_information")
    evidence_ids = output.get("evidence_chunk_ids", [])
    
    # Rule 1: Filter to only valid chunk IDs
    valid_set = set(valid_chunk_ids)
    evidence_ids = [cid for cid in evidence_ids if cid in valid_set]
    
    # Rule 2: If claiming demonstrated/mentioned but no valid evidence → refuse
    if label in ("demonstrated", "mentioned") and not evidence_ids:
        return {
            "label": "not_enough_information",
            "evidence_chunk_ids": [],
            "rationale": output.get("rationale", ""),
            "refusal_reason": "No valid evidence chunk IDs provided."
        }
    
    # Rule 3: If refusing, ensure empty evidence list
    if label == "not_enough_information":
        return {
            "label": "not_enough_information",
            "evidence_chunk_ids": [],
            "rationale": "",
            "refusal_reason": output.get("refusal_reason") or "Evidence insufficient."
        }
    
    return {
        "label": label,
        "evidence_chunk_ids": evidence_ids,
        "rationale": output.get("rationale", ""),
        "refusal_reason": None
    }
```

## Prompt Engineering for Refusal

The LLM prompt MUST include explicit refusal instructions:

```
STRICT RULES
1) Do NOT invent evidence. Use only provided chunks.
2) If evidence is insufficient / irrelevant / too generic: label must be "not_enough_information".
3) If label is "demonstrated" or "mentioned": evidence_chunk_ids must include >= 1 chunk_id.
4) If label is "not_enough_information": evidence_chunk_ids must be [] and refusal_reason must be non-null.
```

## Guardrails

### Pre-LLM Guardrails
1. Check if any chunks were retrieved
2. Check if any chunks scored above minimum threshold
3. If both fail, return refusal without calling LLM

### Post-LLM Guardrails
1. Parse JSON output
2. Validate chunk_ids exist in provided context
3. Enforce pointer requirement for positive claims
4. Retry once if output invalid; fail to refusal if still invalid

## Test Cases

### Must Refuse
| Test Case | Input | Expected |
|-----------|-------|----------|
| Empty chunks | No chunks provided | `not_enough_information` |
| Irrelevant chunks | Chunks about unrelated topic | `not_enough_information` |
| Generic mention | "We value academic integrity" with no specifics | `not_enough_information` |
| Invalid chunk_ids | LLM outputs non-existent chunk_id | `not_enough_information` |
| Parse failure | LLM outputs malformed JSON | `not_enough_information` |

### Must Not Refuse
| Test Case | Input | Expected |
|-----------|-------|----------|
| Clear evidence | Chunks describe specific skill application | `demonstrated` with valid pointers |
| Mention with context | Skill mentioned with some context | `mentioned` with valid pointers |

## Examples

### Refusal Example
```json
{
  "skill_id": "HKU.SKILL.PRIVACY.v1",
  "doc_id": "abc123",
  "label": "not_enough_information",
  "evidence_chunk_ids": [],
  "rationale": "",
  "refusal_reason": "The document discusses project management but does not address privacy-sensitive data handling or protection measures.",
  "model": "llama3.2:3b"
}
```

### Valid Assessment Example
```json
{
  "skill_id": "HKU.SKILL.PRIVACY.v1",
  "doc_id": "abc123",
  "label": "demonstrated",
  "evidence_chunk_ids": ["chunk-456", "chunk-789"],
  "rationale": "The document describes anonymizing student emails before processing and implementing a data deletion workflow.",
  "refusal_reason": null
}
```

## Open Questions
- [ ] Should we track refusal rates per skill for quality monitoring?
- [ ] How to handle edge cases where evidence is borderline?
