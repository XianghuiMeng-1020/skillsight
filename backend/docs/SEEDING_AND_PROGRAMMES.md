# Data Seeding and Programme Coverage (Gap 3)

## Adding a new programme

The system currently supports multiple programmes (e.g. BASc(SDS), BSc(IM)). To add another programme:

1. **Roles (job market data)**
   - Add or generate a roles JSON file (e.g. `roles_enriched_<programme_code>_linkedin.json`) in the repo root, with the same shape as existing `roles_enriched_basc_sds_linkedin.json` (role_id, role_title, skill requirements, etc.).
   - Run the roles import for that programme, or add the programme code to `scripts/load_all_seeds.py` and `scripts/refresh_roles_and_skills.py` in the "Import Roles" loop (e.g. add `"new_prog"` to the list).

2. **Courses**
   - Add course records to `backend/data/seeds/courses_hku.json` (or your programme-specific file) with `course_id`, `course_name`, and metadata.
   - Import via `POST /bff/admin/onboarding/course` or include in `load_all_seeds.py`.

3. **Course–skill map**
   - Add mappings to `backend/data/seeds/course_skill_map.json` with `course_id`, `skill_id`, and optional `relevance`.
   - Import via `POST /course-skill-map` or the same step in `load_all_seeds.py`.

4. **Optional: programme_id**
   - If the schema supports `programme_id` on roles or courses, set it when inserting so the UI can filter by programme.

## Refresh job data (Gap 2)

To refresh roles and skills from existing JSON without re-running the full seed pipeline:

```bash
python3 scripts/refresh_roles_and_skills.py
```

Can be run on a schedule (e.g. monthly) to update job-market data. Ensure `SKILLSIGHT_API` points at your backend.

## Placement and alumni data (Gap 9 – future)

Placement outcomes and alumni experience data are **not** in the current codebase. Implementing them would require HKU to provide data or a separate integration. The schema could support a future table such as:

- `placement_outcomes`: e.g. `programme_id`, `year`, `role_title`, `count` or anonymized list, for a "Where do graduates go?" view.
- Alumni experience could be stored in a similar structure and surfaced in the career dashboard.

No code changes are included for this in the current plan; it is documented as a follow-up feature.
