# SkillSight Demo (Local)

## What this demo includes
- Upload .txt documents -> auto chunking (chunk_text + snippet + char offsets)
- Evidence search (BM25) + optional score breakdown (score_meta.breakdown)
- Skill registry (skills.json) + skill-based evidence search
- Decision 2: Demonstration assessment (rule-based) + persistence
- Decision 3: Proficiency level (rule-based) + persistence
- Decision 4: Role readiness + persistence
- Decision 5: Action cards (with why / based_on)
- Audit log (request + response_summary) + UI table
- Change log for role_readiness diffs + UI table

## Prerequisites
- Docker Desktop
- Python 3.11+
- Node.js

## One-command DB setup
```bash
./scripts/dev_up.sh
