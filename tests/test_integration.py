# backend/tests/test_integration.py
# ─────────────────────────────────────────────────────────
# Integration tests — exercise the real FastAPI app against
# real MongoDB. Requires MongoDB running locally.
# Does NOT require Ollama for most tests (tests the
# "vector store not ready" path, which is safe pre-embedding).
#
# NOT part of --offline CI — run manually before merges/demos:
#   python tests/run_all_tests.py
#
# Uses only the seeded default accounts (admin/admin123,
# user1/user123) and cleans up any data it creates.
# ─────────────────────────────────────────────────────────

import sys
import os
import unittest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from main import app


class NiyamsetuIntegrationTest(unittest.TestCase):
    """
    Base class — logs in as both admin and user1 once,
    shares tokens across all test methods in the suite.
    """

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

        # Log in as admin using seeded default credentials
        admin_login = cls.client.post("/api/auth/login", json={
            "username": "admin",
            "password": "admin123",
        })
        if admin_login.status_code != 200:
            raise unittest.SkipTest(
                "Could not log in as default admin. Is MongoDB running "
                "and seeded with default users? (see db/users.py seed_default_users)"
            )
        cls.admin_token = admin_login.json()["access_token"]
        cls.admin_headers = {"Authorization": f"Bearer {cls.admin_token}"}

        # Log in as regular user
        user_login = cls.client.post("/api/auth/login", json={
            "username": "user1",
            "password": "user123",
        })
        if user_login.status_code != 200:
            raise unittest.SkipTest("Could not log in as default user1.")
        cls.user_token = user_login.json()["access_token"]
        cls.user_headers = {"Authorization": f"Bearer {cls.user_token}"}


class TestAuthFlow(NiyamsetuIntegrationTest):

    def test_login_returns_valid_token_shape(self):
        res = self.client.post("/api/auth/login", json={
            "username": "admin", "password": "admin123",
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("access_token", data)
        self.assertEqual(data["username"], "admin")
        self.assertEqual(data["role"], "admin")

    def test_login_wrong_password_returns_401(self):
        res = self.client.post("/api/auth/login", json={
            "username": "admin", "password": "wrong-password-123",
        })
        self.assertEqual(res.status_code, 401)

    def test_me_endpoint_returns_current_user(self):
        res = self.client.get("/api/auth/me", headers=self.admin_headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["username"], "admin")

    def test_me_endpoint_rejects_missing_token(self):
        res = self.client.get("/api/auth/me")
        self.assertEqual(res.status_code, 401)

    def test_admin_only_route_rejects_regular_user(self):
        # /api/auth/users is admin-only — user1 should get 403
        res = self.client.get("/api/auth/users", headers=self.user_headers)
        self.assertEqual(res.status_code, 403)

    def test_admin_only_route_allows_admin(self):
        res = self.client.get("/api/auth/users", headers=self.admin_headers)
        self.assertEqual(res.status_code, 200)
        usernames = [u["username"] for u in res.json()]
        self.assertIn("admin", usernames)
        self.assertIn("user1", usernames)


class TestQueryHealthAndChat(NiyamsetuIntegrationTest):

    def test_health_endpoint_reachable(self):
        res = self.client.get("/api/query/health", headers=self.user_headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("vector_ready", data)
        self.assertIn("ollama_online", data)
        self.assertIn("llm_model", data)

    def test_chat_without_auth_rejected(self):
        res = self.client.post("/api/query/chat", json={"query": "test", "history": []})
        self.assertEqual(res.status_code, 401)

    def test_chat_with_empty_vector_store_returns_graceful_message(self):
        """
        This is the realistic current dev state (no GRs embedded yet).
        Confirms the app doesn't crash and returns the expected
        "not ready" message instead of a 500 error.
        """
        res = self.client.post(
            "/api/query/chat",
            json={"query": "What is this GR about?", "history": []},
            headers=self.user_headers,
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("answer", data)
        self.assertIn("elapsed_sec", data)
        # If vector store genuinely isn't ready, success should be False
        # and the answer should mention the vector store / embedding
        if not data["success"]:
            self.assertIn("Vector store", data["answer"])

    def test_chat_marathi_query_detected_correctly(self):
        res = self.client.post(
            "/api/query/chat",
            json={"query": "या शासन निर्णयाचा विषय काय आहे?", "history": []},
            headers=self.user_headers,
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["language"], "marathi")


class TestSessionLifecycle(NiyamsetuIntegrationTest):
    """
    Full CRUD cycle for a chat session — creates its own session
    and deletes it at the end, so no test data is left behind.
    """

    def test_full_session_lifecycle(self):
        # Create
        create_res = self.client.post(
            "/api/sessions/", json={"title": "Integration Test Session"},
            headers=self.user_headers,
        )
        self.assertEqual(create_res.status_code, 200)
        session = create_res.json()["session"]
        session_id = session["_id"]
        self.addCleanup(self._delete_session, session_id)

        # List — new session should appear
        list_res = self.client.get("/api/sessions/", headers=self.user_headers)
        self.assertEqual(list_res.status_code, 200)
        ids = [s["_id"] for s in list_res.json()["sessions"]]
        self.assertIn(session_id, ids)

        # Load full session
        load_res = self.client.get(f"/api/sessions/{session_id}", headers=self.user_headers)
        self.assertEqual(load_res.status_code, 200)
        self.assertEqual(load_res.json()["session"]["title"], "Integration Test Session")

        # Append a message pair
        append_res = self.client.post(
            f"/api/sessions/{session_id}/messages",
            json={
                "user_msg": {"role": "user", "content": "test question"},
                "assistant_msg": {"role": "assistant", "content": "test answer"},
            },
            headers=self.user_headers,
        )
        self.assertEqual(append_res.status_code, 200)
        self.assertTrue(append_res.json()["success"])

        # Rename
        rename_res = self.client.patch(
            f"/api/sessions/{session_id}",
            json={"title": "Renamed Session"},
            headers=self.user_headers,
        )
        self.assertEqual(rename_res.status_code, 200)

        # Pin
        pin_res = self.client.patch(
            f"/api/sessions/{session_id}/pin",
            json={"pinned": True},
            headers=self.user_headers,
        )
        self.assertEqual(pin_res.status_code, 200)
        self.assertTrue(pin_res.json()["pinned"])

    def test_cannot_load_another_users_session(self):
        # Admin creates a session
        create_res = self.client.post(
            "/api/sessions/", json={"title": "Admin Private Session"},
            headers=self.admin_headers,
        )
        session_id = create_res.json()["session"]["_id"]
        self.addCleanup(self._delete_session_as_admin, session_id)

        # user1 tries to load admin's session — should 404, not leak data
        load_res = self.client.get(f"/api/sessions/{session_id}", headers=self.user_headers)
        self.assertEqual(load_res.status_code, 404)

    def _delete_session(self, session_id):
        self.client.delete(f"/api/sessions/{session_id}", headers=self.user_headers)

    def _delete_session_as_admin(self, session_id):
        self.client.delete(f"/api/sessions/{session_id}", headers=self.admin_headers)


if __name__ == "__main__":
    from json_test_runner import run_module_to_json
    import sys as _sys
    success = run_module_to_json(
        module=_sys.modules[__name__],
        output_path="integration_test_results.json",
        suite_name="Integration Tests (auth, query, sessions)",
    )
    _sys.exit(0 if success else 1)