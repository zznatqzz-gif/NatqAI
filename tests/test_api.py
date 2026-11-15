import os
import tempfile
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from app import db
from app.main import app


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_path = db.DATABASE_PATH
        db.DATABASE_PATH = os.path.join(self.temp.name, "test.sqlite3")
        db.init_db()
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        db.DATABASE_PATH = self.old_path
        self.temp.cleanup()

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_registration_profile_and_owned_chat(self):
        response = self.client.post("/api/v1/auth/register", json={
            "name": "Test User", "email": "TEST@example.com", "password": "password123"
        })
        self.assertEqual(response.status_code, 201)
        token = response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        profile = self.client.get("/api/v1/users/me", headers=headers)
        self.assertEqual(profile.status_code, 200)
        self.assertEqual(profile.json()["email"], "test@example.com")
        chat = self.client.post("/api/v1/chats", headers=headers, json={})
        self.assertEqual(chat.status_code, 201)
        self.assertEqual(self.client.get(f"/api/v1/chats/{chat.json()['id']}/messages", headers=headers).json(), [])

    def test_duplicate_registration_is_conflict(self):
        payload = {"name": "Test User", "email": "test@example.com", "password": "password123"}
        self.assertEqual(self.client.post("/api/v1/auth/register", json=payload).status_code, 201)
        self.assertEqual(self.client.post("/api/v1/auth/register", json=payload).status_code, 409)

    def test_private_endpoint_requires_auth(self):
        self.assertEqual(self.client.get("/api/v1/users/me").status_code, 401)

    def test_project_files_can_be_saved_listed_and_read_by_owner(self):
        from app.workspace_tools import security as workspace_security
        workspace_security.WORKSPACE_ROOT = Path(self.temp.name) / "workspace"
        registration = self.client.post("/api/v1/auth/register", json={
            "name": "Workspace User", "email": "workspace@example.com", "password": "password123"
        })
        headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
        project = self.client.post("/api/v1/projects", headers=headers, json={"name": "Demo"}).json()
        project_id = project["id"]

        saved = self.client.put(
            f"/api/v1/projects/{project_id}/files/src/main.py", headers=headers,
            json={"content": "print('hello')"}
        )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["status"], "saved")

        listing = self.client.get(f"/api/v1/projects/{project_id}/files", headers=headers)
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()[0]["path"], "src/main.py")

        loaded = self.client.get(
            f"/api/v1/projects/{project_id}/files/src/main.py", headers=headers
        )
        self.assertEqual(loaded.status_code, 200)
        self.assertEqual(loaded.json()["content"], "print('hello')")

    def test_project_files_are_private_and_project_must_exist(self):
        from app.workspace_tools import security as workspace_security
        workspace_security.WORKSPACE_ROOT = Path(self.temp.name) / "workspace"
        registration = self.client.post("/api/v1/auth/register", json={
            "name": "Owner User", "email": "owner@example.com", "password": "password123"
        })
        owner_headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
        project = self.client.post("/api/v1/projects", headers=owner_headers, json={"name": "Private"}).json()
        other = self.client.post("/api/v1/auth/register", json={
            "name": "Other User", "email": "other-workspace@example.com", "password": "password123"
        })
        other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
        hidden = self.client.get(f"/api/v1/projects/{project['id']}/files", headers=other_headers)
        self.assertEqual(hidden.status_code, 404)

    def test_project_file_rejects_path_traversal(self):
        from app.workspace_tools import security as workspace_security
        workspace_security.WORKSPACE_ROOT = Path(self.temp.name) / "workspace"
        registration = self.client.post("/api/v1/auth/register", json={
            "name": "Safe User", "email": "safe@example.com", "password": "password123"
        })
        headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
        project = self.client.post("/api/v1/projects", headers=headers, json={"name": "Safe"}).json()
        response = self.client.put(
            f"/api/v1/projects/{project['id']}/files/..%2Fsecret.txt", headers=headers,
            json={"content": "no"}
        )
        self.assertEqual(response.status_code, 400)


    def _authenticated_chat(self):
        registration = self.client.post("/api/v1/auth/register", json={
            "name": "Usage User", "email": "usage@example.com", "password": "password123"
        })
        headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
        chat = self.client.post("/api/v1/chats", headers=headers, json={})
        return headers, chat.json()["id"]

    def test_usage_starts_at_zero(self):
        headers, _ = self._authenticated_chat()
        response = self.client.get("/api/v1/usage", headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["messages_used"], 0)
        self.assertGreaterEqual(response.json()["messages_remaining"], 0)

    def test_successful_ai_message_is_metered(self):
        headers, chat_id = self._authenticated_chat()
        fake_result = {"content": "Hello", "model": "mock-model", "usage": {
            "prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8
        }}
        with patch("app.main.OpenAICompatibleProvider.chat", new=AsyncMock(return_value=fake_result)):
            response = self.client.post(
                f"/api/v1/chats/{chat_id}/messages", headers=headers,
                json={"message": "Hi", "preferred_language": "en"}
            )
        self.assertEqual(response.status_code, 200)
        usage = self.client.get("/api/v1/usage", headers=headers).json()
        self.assertEqual(usage["messages_used"], 1)
        self.assertEqual(usage["tokens_used"], 8)

    def test_streaming_chat_sends_events_and_persists_completed_reply(self):
        headers, chat_id = self._authenticated_chat()
        async def fake_stream(self, messages):
            yield "Hello"
            yield " streamed"
        with patch("app.main.OpenAICompatibleProvider.stream_chat", new=fake_stream):
            response = self.client.post(
                f"/api/v1/chats/{chat_id}/stream", headers=headers,
                json={"message": "Hi", "preferred_language": "en"}
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn('"content": "Hello"', response.text)
        self.assertIn('"content": " streamed"', response.text)
        self.assertIn('"type": "done"', response.text)
        saved = self.client.get(f"/api/v1/chats/{chat_id}/messages", headers=headers).json()
        self.assertEqual([m["role"] for m in saved], ["user", "assistant"])
        self.assertEqual(saved[-1]["content"], "Hello streamed")

    def test_streaming_chat_requires_authentication(self):
        response = self.client.post("/api/v1/chats/1/stream", json={"message": "Hi"})
        self.assertEqual(response.status_code, 401)

    def test_media_image_job_completes_with_mock_provider(self):
        headers, _ = self._authenticated_chat()
        fake = AsyncMock(return_value={"output_url": "https://cdn.example.test/image.png", "provider_job_id": "mock-1"})
        with patch("app.main.MediaProvider.generate", new=fake):
            response = self.client.post("/api/v1/media/jobs", headers=headers, json={
                "media_type": "image", "prompt": "A calm mountain landscape"
            })
        self.assertEqual(response.status_code, 202)
        job_id = response.json()["id"]
        status = self.client.get(f"/api/v1/media/jobs/{job_id}", headers=headers)
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["status"], "succeeded")
        self.assertEqual(status.json()["output_url"], "https://cdn.example.test/image.png")

    def test_media_job_provider_configuration_error_is_recorded(self):
        from app.media import MediaProviderError
        headers, _ = self._authenticated_chat()
        fake = AsyncMock(side_effect=MediaProviderError("provider not configured"))
        with patch("app.main.MediaProvider.generate", new=fake):
            response = self.client.post("/api/v1/media/jobs", headers=headers, json={
                "media_type": "video", "prompt": "A short cinematic ocean scene"
            })
        self.assertEqual(response.status_code, 202)
        status = self.client.get(f"/api/v1/media/jobs/{response.json()['id']}", headers=headers)
        self.assertEqual(status.json()["status"], "queued")
        self.assertEqual(status.json()["attempt_count"], 1)
        self.assertIn("not configured", status.json()["error"])

    def test_media_job_retry_is_persisted_and_claimed_once(self):
        from app.main import process_due_media_jobs
        headers, _ = self._authenticated_chat()
        with patch("app.main.MediaProvider.generate", new=AsyncMock(side_effect=RuntimeError("temporary"))):
            response = self.client.post("/api/v1/media/jobs", headers=headers, json={
                "media_type": "image", "prompt": "Retryable task"
            })
        job_id = response.json()["id"]
        queued = self.client.get(f"/api/v1/media/jobs/{job_id}", headers=headers).json()
        self.assertEqual(queued["status"], "queued")
        self.assertEqual(queued["attempt_count"], 1)
        with db.connection() as conn:
            conn.execute("UPDATE media_jobs SET next_attempt_at=CURRENT_TIMESTAMP WHERE id=?", (job_id,))
        with patch("app.main.MediaProvider.generate", new=AsyncMock(return_value={"output_url": "https://cdn.example.test/retry.png"})):
            import asyncio
            self.assertEqual(asyncio.run(process_due_media_jobs(10)), 1)
        done = self.client.get(f"/api/v1/media/jobs/{job_id}", headers=headers).json()
        self.assertEqual(done["status"], "succeeded")
        self.assertEqual(done["attempt_count"], 2)

    def test_media_job_is_private_to_owner(self):
        headers, _ = self._authenticated_chat()
        with patch("app.main.MediaProvider.generate", new=AsyncMock(return_value={"output_url": "https://cdn.example.test/a.png"})):
            response = self.client.post("/api/v1/media/jobs", headers=headers, json={
                "media_type": "image", "prompt": "A blue geometric flower"
            })
        other = self.client.post("/api/v1/auth/register", json={
            "name": "Other User", "email": "other@example.com", "password": "password123"
        })
        other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
        hidden = self.client.get(f"/api/v1/media/jobs/{response.json()['id']}", headers=other_headers)
        self.assertEqual(hidden.status_code, 404)

    def test_railway_redeploy_is_scoped_and_requires_valid_membership(self):
        headers, _ = self._authenticated_chat()
        project_payload = {"project": {"id": "project-1", "services": {"edges": [{"node": {"id": "service-1"}}]},
                           "environments": {"edges": [{"node": {"id": "environment-1"}}]}}}
        completed = __import__("subprocess").CompletedProcess([], 0, "Redeploy queued", "")
        with patch("app.main._railway_data", new=AsyncMock(return_value=project_payload)), \
             patch("app.main.get_user_railway_token", return_value="test-token"), \
             patch("app.main.shutil.which", return_value="/usr/bin/railway"), \
             patch("app.main.subprocess.run", return_value=completed) as run:
            response = self.client.post("/api/v1/integrations/railway/service-action", headers=headers, json={
                "action": "redeploy", "project_id": "project-1", "service_id": "service-1", "environment_id": "environment-1"
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "REQUEST_ACCEPTED")
        self.assertIn("redeploy", run.call_args.args[0])
        self.assertIn("service-1", run.call_args.args[0])
        self.assertEqual(run.call_args.kwargs["env"]["RAILWAY_API_TOKEN"], "test-token")

    def test_railway_stop_requires_explicit_confirmation(self):
        headers, _ = self._authenticated_chat()
        response = self.client.post("/api/v1/integrations/railway/service-action", headers=headers, json={
            "action": "stop", "project_id": "project-1", "service_id": "service-1", "environment_id": "environment-1"
        })
        self.assertEqual(response.status_code, 400)

    def test_railway_service_action_rejects_service_outside_project(self):
        headers, _ = self._authenticated_chat()
        project_payload = {"project": {"id": "project-1", "services": {"edges": [{"node": {"id": "other-service"}}]},
                           "environments": {"edges": [{"node": {"id": "environment-1"}}]}}}
        with patch("app.main._railway_data", new=AsyncMock(return_value=project_payload)), \
             patch("app.main.subprocess.run") as run:
            response = self.client.post("/api/v1/integrations/railway/service-action", headers=headers, json={
                "action": "redeploy", "project_id": "project-1", "service_id": "service-1", "environment_id": "environment-1"
            })
        self.assertEqual(response.status_code, 400)
        run.assert_not_called()

    def test_daily_quota_blocks_excess_requests(self):
        headers, chat_id = self._authenticated_chat()
        fake_result = {"content": "Hello", "model": "mock-model", "usage": {}}
        with patch("app.main.DAILY_MESSAGE_LIMIT", 1), patch(
            "app.main.OpenAICompatibleProvider.chat", new=AsyncMock(return_value=fake_result)
        ) as provider:
            first = self.client.post(
                f"/api/v1/chats/{chat_id}/messages", headers=headers,
                json={"message": "First"}
            )
            second = self.client.post(
                f"/api/v1/chats/{chat_id}/messages", headers=headers,
                json={"message": "Second"}
            )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
        self.assertEqual(provider.await_count, 1)


if __name__ == "__main__":
    unittest.main()
