# Resume Enhancement Center — Observability

Use this note with [DEPLOYMENT.md](DEPLOYMENT.md) to monitor upload → score → suggest → export.

## Structured log lines (backend)

| Log pattern | Meaning |
|-------------|---------|
| `bff.resume.score.timing_ms=` | Wall time for LLM scoring (`POST .../score`) |
| `bff.resume.suggest.timing_ms=` | Wall time for suggestion generation (`POST .../suggest`) |
| `apply-template: timing_ms=` | DOCX build time after text merge (`POST .../apply-template`) |
| `apply-template: PDF requested but LibreOffice not available` | User asked for PDF but `soffice`/`libreoffice` not on `PATH` — response is DOCX with `pdf_unavailable: true` |

## Suggested alerts

- **Error rate**: HTTP 5xx on `/bff/student/resume-review/*/apply-template` > 2% over 15 minutes.
- **Latency**: P95 `apply-template` > 8s (tune to your infra).
- **PDF**: spike in `pdf_unavailable` if you advertise PDF export — ensure LibreOffice is installed in production images.

## Audit actions

- `bff.resume.start`, `bff.resume.score`, `bff.resume.suggest`, `bff.resume.apply_template` — see audit store / `log_audit` metadata.

## New endpoints (reference)

- `GET /bff/student/resume-review/{id}/layout-check` — heuristic layout score + issues (no LLM).
- `GET /bff/student/resume-review/{id}/preview-html?template_id=` — HTML preview for the template palette.
- `GET /bff/student/resume-templates?review_id=` — templates ranked with `recommend_score` / `recommended` when the review has a target role.
