"""
Test suite for interactive assessment endpoints.
Covers: Communication, Programming, Writing assessments.
"""
import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy import text


class TestCommunicationAssessment:
    """Tests for Kira-style communication assessment."""
    
    def test_start_communication_session(self, client, db):
        """Test starting a communication assessment session."""
        response = client.post(
            "/interactive/communication/start",
            json={
                "user_id": "test_user",
                "duration_seconds": 60,
                "allow_retries": True
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert "topic" in data
        assert data["duration_seconds"] == 60
        assert data["max_attempts"] > 1
    
    def test_submit_communication_response(self, client, db):
        """Test submitting a communication response."""
        # First start a session
        start_response = client.post(
            "/interactive/communication/start",
            json={"user_id": "test_user", "duration_seconds": 60}
        )
        session_id = start_response.json()["session_id"]
        
        # Submit response
        response = client.post(
            "/interactive/communication/submit",
            json={
                "session_id": session_id,
                "transcript": "This is my response to the topic. I believe that communication skills are essential for professional success. In my experience working on team projects, clear and concise communication helped us achieve our goals.",
                "audio_duration_seconds": 45.5
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "evaluation" in data
        assert "overall_score" in data["evaluation"]
        assert "level" in data["evaluation"]
    
    def test_retry_allowed_when_enabled(self, client, db):
        """Test that retry is allowed when enabled."""
        # Start session with retries
        start_response = client.post(
            "/interactive/communication/start",
            json={"user_id": "test_user", "duration_seconds": 60, "allow_retries": True, "max_retries": 2}
        )
        session_id = start_response.json()["session_id"]
        
        # First attempt
        response1 = client.post(
            "/interactive/communication/submit",
            json={
                "session_id": session_id,
                "transcript": "First attempt response.",
                "audio_duration_seconds": 30
            }
        )
        
        assert response1.json()["can_retry"] == True
        assert response1.json()["remaining_attempts"] > 0
    
    def test_word_count_affects_score(self, client, db):
        """Test that word count affects evaluation score."""
        # Start session
        start_response = client.post(
            "/interactive/communication/start",
            json={"user_id": "test_user", "duration_seconds": 60}
        )
        session_id = start_response.json()["session_id"]
        
        # Short response
        response = client.post(
            "/interactive/communication/submit",
            json={
                "session_id": session_id,
                "transcript": "Very short.",
                "audio_duration_seconds": 5
            }
        )
        
        data = response.json()
        assert data["evaluation"]["metrics"]["word_count"] < 10
        # Score should be lower for very short responses
        assert data["evaluation"]["overall_score"] < 70


class TestProgrammingAssessment:
    """Tests for LeetCode-style programming assessment."""
    
    def test_start_programming_session(self, client, db):
        """Test starting a programming assessment session."""
        response = client.post(
            "/interactive/programming/start",
            json={
                "user_id": "test_user",
                "difficulty": "easy",
                "language": "python"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert "problem" in data
        assert "title" in data["problem"]
        assert "description" in data["problem"]
        assert "time_limit_seconds" in data
    
    def test_different_difficulties_available(self, client, db):
        """Test that different difficulty levels return different problems."""
        difficulties = ["easy", "medium", "hard"]
        time_limits = []
        
        for diff in difficulties:
            response = client.post(
                "/interactive/programming/start",
                json={"user_id": "test_user", "difficulty": diff}
            )
            time_limits.append(response.json()["time_limit_seconds"])
        
        # Harder problems should have longer time limits
        assert time_limits[0] <= time_limits[1] <= time_limits[2]
    
    def test_submit_programming_solution(self, client, db):
        """Test submitting a programming solution."""
        # Start session
        start_response = client.post(
            "/interactive/programming/start",
            json={"user_id": "test_user", "difficulty": "easy"}
        )
        session_id = start_response.json()["session_id"]
        
        # Submit code
        response = client.post(
            "/interactive/programming/submit",
            json={
                "session_id": session_id,
                "code": """def two_sum(nums, target):
    seen = {}
    for i, n in enumerate(nums):
        if target - n in seen:
            return [seen[target - n], i]
        seen[n] = i
    return []""",
                "language": "python"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "evaluation" in data
        assert "score" in data["evaluation"]


class TestWritingAssessment:
    """Tests for timed writing assessment."""
    
    def test_start_writing_session(self, client, db):
        """Test starting a writing assessment session."""
        response = client.post(
            "/interactive/writing/start",
            json={
                "user_id": "test_user",
                "time_limit_minutes": 30,
                "min_words": 300,
                "max_words": 500
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert "prompt" in data
        assert "anti_copy_token" in data
        assert data["time_limit_minutes"] == 30
    
    def test_submit_writing_with_valid_token(self, client, db):
        """Test submitting writing with valid anti-copy token."""
        # Start session
        start_response = client.post(
            "/interactive/writing/start",
            json={"user_id": "test_user", "time_limit_minutes": 30}
        )
        data = start_response.json()
        session_id = data["session_id"]
        token = data["anti_copy_token"]
        
        # Submit essay
        essay = "This is a sample essay about technology. " * 50  # ~350 words
        response = client.post(
            "/interactive/writing/submit",
            json={
                "session_id": session_id,
                "content": essay,
                "anti_copy_token": token,
                "keystroke_data": {
                    "chars_per_minute": 200,
                    "paste_count": 0
                }
            }
        )
        
        assert response.status_code == 200
        evaluation = response.json()["evaluation"]
        assert "overall_score" in evaluation
        assert "authenticity_score" in evaluation["metrics"]
    
    def test_submit_with_invalid_token_fails(self, client, db):
        """Test that invalid anti-copy token is rejected."""
        # Start session
        start_response = client.post(
            "/interactive/writing/start",
            json={"user_id": "test_user"}
        )
        session_id = start_response.json()["session_id"]
        
        # Submit with wrong token
        response = client.post(
            "/interactive/writing/submit",
            json={
                "session_id": session_id,
                "content": "Some essay content...",
                "anti_copy_token": "wrong_token",
            }
        )
        
        assert response.status_code == 400
        assert "token" in response.json()["detail"].lower()
    
    def test_paste_detection_lowers_score(self, client, db):
        """Test that paste events lower authenticity score."""
        # Start session
        start_response = client.post(
            "/interactive/writing/start",
            json={"user_id": "test_user"}
        )
        data = start_response.json()
        session_id = data["session_id"]
        token = data["anti_copy_token"]
        
        essay = "Sample essay content. " * 50
        
        # Submit with high paste count
        response = client.post(
            "/interactive/writing/submit",
            json={
                "session_id": session_id,
                "content": essay,
                "anti_copy_token": token,
                "keystroke_data": {
                    "chars_per_minute": 200,
                    "paste_count": 10  # Many pastes
                }
            }
        )
        
        evaluation = response.json()["evaluation"]
        assert evaluation["metrics"]["authenticity_score"] < 100
        assert len(evaluation["authenticity_flags"]) > 0


class TestSessionManagement:
    """Tests for session management functionality."""
    
    def test_get_session_details(self, client, db):
        """Test retrieving session details."""
        # Create a session
        start_response = client.post(
            "/interactive/communication/start",
            json={"user_id": "test_user"}
        )
        session_id = start_response.json()["session_id"]
        
        # Get session details
        response = client.get(f"/interactive/sessions/{session_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert "session" in data
        assert "attempts" in data
    
    def test_get_user_sessions(self, client, db):
        """Test listing all sessions for a user."""
        user_id = "test_user_sessions"
        
        # Create multiple sessions
        for _ in range(3):
            client.post(
                "/interactive/communication/start",
                json={"user_id": user_id}
            )
        
        # Get all sessions
        response = client.get(f"/interactive/sessions/user/{user_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["count"] >= 3
    
    def test_consistency_score_calculation(self, client, db):
        """Test consistency score across multiple attempts."""
        # Start session with retries
        start_response = client.post(
            "/interactive/communication/start",
            json={"user_id": "test_user", "max_retries": 3}
        )
        session_id = start_response.json()["session_id"]
        
        # Submit multiple attempts
        for i in range(2):
            client.post(
                "/interactive/communication/submit",
                json={
                    "session_id": session_id,
                    "transcript": f"Attempt {i+1}: This is my response with some content.",
                    "audio_duration_seconds": 30
                }
            )
        
        # Get consistency score
        response = client.get(f"/interactive/sessions/{session_id}/consistency")
        
        assert response.status_code == 200
        data = response.json()
        assert "consistency_score" in data
        assert "trend" in data


class TestInteractiveSkillSync:
    """Ensure interactive assessment updates student skill profile tables."""

    def test_programming_submit_persists_skill_records(self, client, db):
        start_response = client.post(
            "/interactive/programming/start",
            json={"user_id": "skill_sync_user", "difficulty": "easy", "language": "python"},
        )
        assert start_response.status_code == 200
        session_id = start_response.json()["session_id"]

        submit_response = client.post(
            "/interactive/programming/submit",
            json={
                "session_id": session_id,
                "code": "def two_sum(nums, target):\n    return [0, 1]",
                "language": "python",
            },
        )
        assert submit_response.status_code == 200

        row1 = db.execute(
            text("""
            SELECT decision, skill_id
            FROM skill_assessments
            WHERE skill_id = 'HKU.SKILL.CODING.v1'
            ORDER BY created_at DESC
            LIMIT 1
            """)
        ).mappings().first()
        assert row1 is not None
        assert row1["decision"] in ("demonstrated", "mentioned", "not_enough_information")

        row2 = db.execute(
            text("""
            SELECT level, label, skill_id
            FROM skill_proficiency
            WHERE skill_id = 'HKU.SKILL.CODING.v1'
            ORDER BY created_at DESC
            LIMIT 1
            """)
        ).mappings().first()
        assert row2 is not None
        assert isinstance(row2["level"], int)

    def test_profile_and_recent_updates_reflect_submission(self, client, db):
        start_response = client.post(
            "/interactive/writing/start",
            json={"user_id": "profile_sync_user", "time_limit_minutes": 30, "min_words": 100, "max_words": 500},
        )
        assert start_response.status_code == 200
        session = start_response.json()
        session_id = session["session_id"]
        anti_copy_token = session["anti_copy_token"]

        submit_response = client.post(
            "/interactive/writing/submit",
            json={
                "session_id": session_id,
                "content": ("this is integration writing content " * 40).strip(),
                "anti_copy_token": anti_copy_token,
                "keystroke_data": {"chars_per_minute": 160, "paste_count": 0},
            },
        )
        assert submit_response.status_code == 200
        submit_json = submit_response.json()
        assert submit_json.get("skill_update", {}).get("updated") is True

        # BFF profile should be able to read this user's updated skill signal.
        profile_resp = client.get(
            "/bff/student/profile",
            headers={"X-Subject-Id": "profile_sync_user", "X-Role": "student"},
        )
        assert profile_resp.status_code == 200
        profile = profile_resp.json()
        assert "skills" in profile
        assert isinstance(profile["skills"], list)

        # Dedicated recent updates endpoint should return latest assessment.
        recent_resp = client.get("/interactive/users/profile_sync_user/recent_updates?limit=5")
        assert recent_resp.status_code == 200
        recent = recent_resp.json()
        assert recent["count"] >= 1
        assert any(item.get("assessment_type") == "writing" for item in recent["items"])

    def test_submit_idempotency_key_avoids_duplicate_records(self, client, db):
        start_response = client.post(
            "/interactive/programming/start",
            json={"user_id": "idem_user", "difficulty": "easy", "language": "python"},
        )
        assert start_response.status_code == 200
        session_id = start_response.json()["session_id"]

        payload = {
            "session_id": session_id,
            "code": "def two_sum(nums, target):\n    return [0, 1]",
            "language": "python",
        }
        headers = {"Idempotency-Key": "idem-programming-1"}
        first = client.post("/interactive/programming/submit", json=payload, headers=headers)
        second = client.post("/interactive/programming/submit", json=payload, headers=headers)

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["attempt_id"] == second.json()["attempt_id"]

        attempts_count = db.execute(
            text("SELECT COUNT(*) AS n FROM assessment_attempts WHERE session_id = :sid"),
            {"sid": session_id},
        ).mappings().first()
        assert int((attempts_count or {}).get("n", 0)) == 1

        skill_count = db.execute(
            text("""
            SELECT COUNT(*) AS n
            FROM skill_assessments
            WHERE decision_meta ->> 'session_id' = :sid
            """),
            {"sid": session_id},
        ).mappings().first()
        assert int((skill_count or {}).get("n", 0)) == 1

    def test_replay_sync_endpoint_supports_noop_and_force(self, client, db):
        start_response = client.post(
            "/interactive/writing/start",
            json={"user_id": "replay_user", "time_limit_minutes": 30, "min_words": 100, "max_words": 500},
        )
        assert start_response.status_code == 200
        session = start_response.json()
        session_id = session["session_id"]

        submit_response = client.post(
            "/interactive/writing/submit",
            json={
                "session_id": session_id,
                "content": ("replay sync writing content " * 50).strip(),
                "anti_copy_token": session["anti_copy_token"],
                "keystroke_data": {"chars_per_minute": 180, "paste_count": 0},
            },
        )
        assert submit_response.status_code == 200

        noop = client.post(f"/interactive/sessions/{session_id}/replay_sync", json={"force": False})
        assert noop.status_code == 200
        assert noop.json().get("replayed") is False

        forced = client.post(f"/interactive/sessions/{session_id}/replay_sync", json={"force": True})
        assert forced.status_code == 200
        assert forced.json().get("replayed") is True
        assert forced.json().get("skill_update", {}).get("updated") is True

    def test_cross_user_profile_access_is_forbidden(self, client, db):
        response = client.get(
            "/bff/student/profile?user_id=other_user",
            headers={"X-Subject-Id": "owner_user", "X-Role": "student"},
        )
        assert response.status_code == 403

    def test_recent_updates_returns_unified_assessment_events_shape(self, client, db):
        start_response = client.post(
            "/interactive/programming/start",
            json={"user_id": "shape_user", "difficulty": "easy", "language": "python"},
        )
        assert start_response.status_code == 200
        session_id = start_response.json()["session_id"]
        submit_response = client.post(
            "/interactive/programming/submit",
            json={"session_id": session_id, "code": "def two_sum(nums, target):\n    return [0, 1]", "language": "python"},
        )
        assert submit_response.status_code == 200

        recent = client.get("/interactive/users/shape_user/recent_updates?limit=5")
        assert recent.status_code == 200
        body = recent.json()
        assert "items" in body and "assessment_events" in body
        assert isinstance(body["assessment_events"], list)
        if body["assessment_events"]:
            assert "event_id" in body["assessment_events"][0]
            assert "event_type" in body["assessment_events"][0]

    def test_submit_includes_version_fields_and_drift_summary_visible(self, client, db):
        start_response = client.post(
            "/interactive/programming/start",
            json={"user_id": "drift_user", "difficulty": "easy", "language": "python"},
        )
        assert start_response.status_code == 200
        session_id = start_response.json()["session_id"]

        submit_response = client.post(
            "/interactive/programming/submit",
            json={"session_id": session_id, "code": "def two_sum(nums, target):\n    return [0, 1]", "language": "python"},
            headers={"X-Model-Version": "model-test-v1", "X-Rubric-Version": "rubric-test-v1"},
        )
        assert submit_response.status_code == 200
        body = submit_response.json()
        assert body.get("model_version") == "model-test-v1"
        assert body.get("rubric_version") == "rubric-test-v1"
        assert body.get("idempotent_replay") is False

        drift = client.get("/interactive/drift/summary?window_hours=24")
        assert drift.status_code == 200
        drift_body = drift.json()
        assert "items" in drift_body
        assert any(item.get("assessment_type") == "programming" for item in drift_body.get("items", []))

    def test_repair_jobs_list_endpoint_returns_items(self, client, db):
        response = client.get("/interactive/repair_jobs?limit=5")
        assert response.status_code == 200
        body = response.json()
        assert "count" in body
        assert "items" in body
        assert isinstance(body["items"], list)
