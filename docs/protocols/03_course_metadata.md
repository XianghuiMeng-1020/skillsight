# Protocol 3: Course Metadata (v0.1)

## Purpose
Defines the structure for course information and course-to-skill mappings. Enables tracking of which courses teach which skills at what intended level.

## Scope
- **In scope:** Course structure, course-skill mappings, intended levels
- **Out of scope:** Skill assessment from course artifacts (Protocol 4)

## Objects and Fields (v0.1)

### Course
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `course_id` | string | Yes | Course code (e.g., "COMP3278") |
| `course_title` | string | Yes | Full course name |
| `department` | string | No | Department code |
| `description` | string | No | Course description |
| `assessment_types` | string[] | No | Types of assessments (e.g., ["essay", "project", "exam"]) |
| `created_at` | timestamp | Yes | Creation timestamp |
| `updated_at` | timestamp | No | Last modification timestamp |

### CourseSkillMap
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `map_id` | UUID | Yes | Unique mapping ID |
| `course_id` | string | Yes | Reference to course |
| `skill_id` | string | Yes | Reference to skill |
| `intended_level` | integer | Yes | Course aims to develop skill to this level (0-3) |
| `evidence_type` | string | No | Expected evidence type (e.g., "project", "essay") |
| `status` | string | Yes | "pending", "approved", "rejected" |
| `approved_by` | string | No | Staff who approved the mapping |
| `notes` | string | No | Review notes |

## Rules (v0.1)

1. **Course ID:** Uses institution's official course code.
2. **Skill Mapping:** Each course can map to multiple skills.
3. **Intended Level:** The proficiency level the course aims to develop.
4. **Review Workflow:** Mappings start as "pending", require instructor approval.
5. **Uniqueness:** One mapping per (course_id, skill_id) pair.

## Database Tables

```sql
-- Courses table
CREATE TABLE courses (
    course_id TEXT PRIMARY KEY,
    course_title TEXT NOT NULL,
    department TEXT,
    description TEXT,
    assessment_types JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ
);

-- Course-skill mappings
CREATE TABLE course_skill_map (
    map_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    course_id TEXT NOT NULL REFERENCES courses(course_id),
    skill_id TEXT NOT NULL REFERENCES skills(skill_id),
    intended_level INTEGER NOT NULL DEFAULT 0,
    evidence_type TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    approved_by TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX uq_course_skill ON course_skill_map(course_id, skill_id);
```

## Review Workflow

```
1. Admin/System creates mapping → status = "pending"
2. Instructor reviews → status = "approved" or "rejected"
3. Approved mappings appear in course skill profile
4. Rejected mappings are logged but hidden from students
```

## Examples

```json
{
  "course_id": "COMP3278",
  "course_title": "Database Systems",
  "department": "CS",
  "assessment_types": ["project", "exam"],
  "skill_mappings": [
    {
      "skill_id": "HKU.SKILL.DATA_MODELING.v1",
      "intended_level": 2,
      "evidence_type": "project",
      "status": "approved"
    }
  ]
}
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/courses` | List all courses |
| GET | `/course-skill-map` | List all mappings |
| POST | `/course-skill-map` | Create mapping (pending) |
| PATCH | `/course-skill-map/{map_id}` | Approve/reject mapping |

## Open Questions
- [ ] How to handle course version changes (syllabi updates)?
- [ ] Should we support prerequisite relationships?
