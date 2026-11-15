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


    def test_uploaded_zip_can_be_queued_to_railway_cli_without_local_execution(self):
        import io
        import zipfile
        from unittest.mock import AsyncMock, patch
        from app import main as api
        api.DEPLOYMENT_SOURCES_ROOT = Path(self.temp.name) / "deployment_sources"
        registration = self.client.post("/api/v1/auth/register", json={
            "name": "Deploy User", "email": "deploy-user@example.com", "password": "password123"
        })
        headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
        project = self.client.post("/api/v1/projects", headers=headers, json={"name": "Deploy target"}).json()
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("index.html", "<h1>Deploy remotely</h1>")
        uploaded = self.client.post(
            f"/api/v1/projects/{project['id']}/deployment-source", headers=headers,
            files={"file": ("site.zip", archive.getvalue(), "application/zip")}
        )
        self.assertEqual(uploaded.status_code, 201)
        remote = {"project": {
            "id": "rp", "services": {"edges": [{"node": {"id": "rs"}}]},
            "environments": {"edges": [{"node": {"id": "re"}}]},
        }}
        upload_process = type("Result", (), {"returncode": 0, "stdout": "queued", "stderr": ""})()
        status_process = type("Result", (), {"returncode": 0, "stdout": '{"deployments":[{"id":"dep-123","status":"SUCCESS","url":"https://example.up.railway.app"}]}', "stderr": ""})()
        with patch("app.main.get_user_railway_token", return_value="test-token"), \
             patch("app.main._railway_data", new=AsyncMock(return_value=remote)), \
             patch("app.main.shutil.which", return_value="/usr/bin/railway"), \
             patch("app.main.subprocess.run", side_effect=[upload_process, status_process]) as run:
            response = self.client.post(
                f"/api/v1/projects/{project['id']}/deployment-source/deploy", headers=headers,
                json={"railway_project_id": "rp", "railway_service_id": "rs", "railway_environment_id": "re"}
            )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["status"], "QUEUED")
        self.assertTrue(run.called)
        upload_command = run.call_args_list[0].args[0]
        monitor_command = run.call_args_list[1].args[0]
        self.assertIn("--project", upload_command)
        self.assertIn("--environment", upload_command)
        self.assertIn("--service", upload_command)
        self.assertIn("--project", monitor_command)
        self.assertIn("--environment", monitor_command)
        self.assertIn("--service", monitor_command)
        self.assertEqual(run.call_args_list[0].kwargs["env"]["RAILWAY_API_TOKEN"], "test-token")
        status = self.client.get(
            f"/api/v1/projects/{project['id']}/deployment-source/runs/{response.json()['run_id']}",
            headers=headers,
        )
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["status"], "triggered")
        self.assertEqual(status.json()["remote_status"], "SUCCESS")
        self.assertEqual(status.json()["deployment_id"], "dep-123")
        self.assertEqual(status.json()["deployment_url"], "https://example.up.railway.app")

    def test_uploaded_zip_deploy_rejects_missing_railway_cli(self):
        import io
        import zipfile
        from unittest.mock import patch
        from app import main as api
        api.DEPLOYMENT_SOURCES_ROOT = Path(self.temp.name) / "deployment_sources"
        registration = self.client.post("/api/v1/auth/register", json={
            "name": "No CLI User", "email": "no-cli@example.com", "password": "password123"
        })
        headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
        project = self.client.post("/api/v1/projects", headers=headers, json={"name": "No CLI"}).json()
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("index.html", "hello")
        self.client.post(f"/api/v1/projects/{project['id']}/deployment-source", headers=headers,
                         files={"file": ("site.zip", archive.getvalue(), "application/zip")})
        with patch("app.main.get_user_railway_token", return_value="test-token"), \
             patch("app.main.shutil.which", return_value=None):
            response = self.client.post(
                f"/api/v1/projects/{project['id']}/deployment-source/deploy", headers=headers,
                json={"railway_project_id": "rp", "railway_service_id": "rs", "railway_environment_id": "re"}
            )
        self.assertEqual(response.status_code, 503)

    def test_railway_deployment_json_normalizer(self):
        from app.main import _find_railway_deployment
        self.assertEqual(_find_railway_deployment({"deployments": [{"id": "d1", "status": "BUILDING"}]}),
                         {"id": "d1", "status": "BUILDING"})
        self.assertEqual(_find_railway_deployment({"deployments": {"edges": [{"node": {"id": "d2"}}]}}),
                         {"id": "d2"})
        self.assertIsNone(_find_railway_deployment({"deployments": []}))

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

    def test_project_download_returns_zip_for_owner(self):
        import io
        import zipfile
        from app.workspace_tools import security as workspace_security
        workspace_security.WORKSPACE_ROOT = Path(self.temp.name) / "workspace"
        registration = self.client.post("/api/v1/auth/register", json={
            "name": "Download User", "email": "download@example.com", "password": "password123"
        })
        headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
        project = self.client.post("/api/v1/projects", headers=headers, json={"name": "Downloadable"}).json()
        self.client.put(
            f"/api/v1/projects/{project['id']}/files/README.md", headers=headers,
            json={"content": "download me"}
        )
        response = self.client.get(f"/api/v1/projects/{project['id']}/download", headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/zip")
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            self.assertEqual(archive.read("README.md").decode(), "download me")

    def test_project_download_is_private(self):
        from app.workspace_tools import security as workspace_security
        workspace_security.WORKSPACE_ROOT = Path(self.temp.name) / "workspace"
        owner = self.client.post("/api/v1/auth/register", json={
            "name": "Download Owner", "email": "download-owner@example.com", "password": "password123"
        })
        owner_headers = {"Authorization": f"Bearer {owner.json()['access_token']}"}
        project = self.client.post("/api/v1/projects", headers=owner_headers, json={"name": "Private Download"}).json()
        other = self.client.post("/api/v1/auth/register", json={
            "name": "Other User", "email": "download-other@example.com", "password": "password123"
        })
        other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
        response = self.client.get(f"/api/v1/projects/{project['id']}/download", headers=other_headers)
        self.assertEqual(response.status_code, 404)

    def test_ai_project_generation_creates_files_for_owner(self):
        from app.workspace_tools import security as workspace_security
        workspace_security.WORKSPACE_ROOT = Path(self.temp.name) / "workspace"
        registration = self.client.post("/api/v1/auth/register", json={
            "name": "Generator User", "email": "generator@example.com", "password": "password123"
        })
        headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
        project = self.client.post("/api/v1/projects", headers=headers, json={"name": "Generated App"}).json()
        generated = {"summary": "A tiny starter project", "files": [
            {"path": "index.html", "content": "<h1>Hello</h1>"},
            {"path": "README.md", "content": "Run with a local web server."},
        ]}
        fake = {"content": __import__("json").dumps(generated), "model": "mock-model", "usage": {}}
        with patch("app.main.OpenAICompatibleProvider.chat", new=AsyncMock(return_value=fake)):
            response = self.client.post(
                f"/api/v1/projects/{project['id']}/generate", headers=headers,
                json={"prompt": "Create a small static website about books."}
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "created")
        self.assertEqual(len(response.json()["files"]), 2)
        loaded = self.client.get(
            f"/api/v1/projects/{project['id']}/files/index.html", headers=headers
        )
        self.assertEqual(loaded.json()["content"], "<h1>Hello</h1>")

    def test_ai_project_generation_rejects_unsafe_paths_without_writing(self):
        from app.workspace_tools import security as workspace_security
        workspace_security.WORKSPACE_ROOT = Path(self.temp.name) / "workspace"
        registration = self.client.post("/api/v1/auth/register", json={
            "name": "Generator User", "email": "generator-safe@example.com", "password": "password123"
        })
        headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
        project = self.client.post("/api/v1/projects", headers=headers, json={"name": "Safe App"}).json()
        generated = {"summary": "bad", "files": [{"path": "../outside.txt", "content": "bad"}]}
        fake = {"content": __import__("json").dumps(generated), "model": "mock-model", "usage": {}}
        with patch("app.main.OpenAICompatibleProvider.chat", new=AsyncMock(return_value=fake)):
            response = self.client.post(
                f"/api/v1/projects/{project['id']}/generate", headers=headers,
                json={"prompt": "Create a starter application with files."}
            )
        self.assertEqual(response.status_code, 502)
        self.assertEqual(self.client.get(
            f"/api/v1/projects/{project['id']}/files", headers=headers
        ).json(), [])

    def test_ai_project_generation_does_not_overwrite_existing_files(self):
        from app.workspace_tools import security as workspace_security
        workspace_security.WORKSPACE_ROOT = Path(self.temp.name) / "workspace"
        registration = self.client.post("/api/v1/auth/register", json={
            "name": "Generator User", "email": "generator-existing@example.com", "password": "password123"
        })
        headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
        project = self.client.post("/api/v1/projects", headers=headers, json={"name": "Existing App"}).json()
        self.client.put(f"/api/v1/projects/{project['id']}/files/keep.txt", headers=headers, json={"content": "keep"})
        with patch("app.main.OpenAICompatibleProvider.chat", new=AsyncMock()) as fake:
            response = self.client.post(
                f"/api/v1/projects/{project['id']}/generate", headers=headers,
                json={"prompt": "Create a starter application with files."}
            )
        self.assertEqual(response.status_code, 409)
        fake.assert_not_awaited()

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



    def test_ai_project_review_returns_report_without_modifying_files(self):
        from app.workspace_tools import security as workspace_security
        workspace_security.WORKSPACE_ROOT = Path(self.temp.name) / "workspace"
        registration = self.client.post("/api/v1/auth/register", json={
            "name": "Review User", "email": "review@example.com", "password": "password123"
        })
        headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
        project = self.client.post("/api/v1/projects", headers=headers, json={"name": "Review App"}).json()
        self.client.put(
            f"/api/v1/projects/{project['id']}/files/main.py", headers=headers,
            json={"content": "print('hello')"}
        )
        report = {"summary": "Looks good", "findings": [{
            "severity": "info", "file": "main.py", "issue": "No obvious issue",
            "recommendation": "Add tests"
        }]}
        fake = {"content": __import__("json").dumps(report), "model": "mock-model", "usage": {}}
        with patch("app.main.OpenAICompatibleProvider.chat", new=AsyncMock(return_value=fake)):
            response = self.client.post(
                f"/api/v1/projects/{project['id']}/review", headers=headers,
                json={"preferred_language": "en"}
            )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["executed"])
        self.assertFalse(response.json()["modified"])
        self.assertEqual(response.json()["findings"][0]["file"], "main.py")
        saved = self.client.get(
            f"/api/v1/projects/{project['id']}/files/main.py", headers=headers
        )
        self.assertEqual(saved.json()["content"], "print('hello')")

    def test_ai_project_review_is_private(self):
        from app.workspace_tools import security as workspace_security
        workspace_security.WORKSPACE_ROOT = Path(self.temp.name) / "workspace"
        owner = self.client.post("/api/v1/auth/register", json={
            "name": "Review Owner", "email": "review-owner@example.com", "password": "password123"
        })
        owner_headers = {"Authorization": f"Bearer {owner.json()['access_token']}"}
        project = self.client.post("/api/v1/projects", headers=owner_headers, json={"name": "Private Review"}).json()
        other = self.client.post("/api/v1/auth/register", json={
            "name": "Review Other", "email": "review-other@example.com", "password": "password123"
        })
        other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
        with patch("app.main.OpenAICompatibleProvider.chat", new=AsyncMock()) as fake:
            response = self.client.post(
                f"/api/v1/projects/{project['id']}/review", headers=other_headers, json={}
            )
        self.assertEqual(response.status_code, 404)
        fake.assert_not_awaited()

    def test_railway_connection_validates_and_stores_token_encrypted(self):
        from unittest.mock import Mock
        registration = self.client.post("/api/v1/auth/register", json={
            "name": "Railway User", "email": "railway@example.com", "password": "password123"
        })
        headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
        fake_response = Mock(status_code=200)
        fake_response.json.return_value = {"data": {"me": {"id": "acct-123", "name": "NatqAI Test"}}}
        with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=fake_response)) as remote:
            response = self.client.post("/api/v1/integrations/railway/connect", headers=headers,
                                        json={"token": "railway-secret-token"})
        self.assertEqual(response.status_code, 200, response.text)
        remote.assert_awaited_once()
        self.assertTrue(response.json()["connected"])
        status = self.client.get("/api/v1/integrations/railway", headers=headers).json()
        self.assertTrue(status["connected"])
        self.assertEqual(status["account_id"], "acct-123")
        self.assertNotIn("token", str(status).lower())
        with db.connection() as conn:
            row = conn.execute("SELECT encrypted_secret FROM user_integrations WHERE provider='railway'").fetchone()
        self.assertNotIn("railway-secret-token", row["encrypted_secret"])
        self.assertNotEqual(row["encrypted_secret"], "railway-secret-token")

    def test_railway_connection_rejects_invalid_token_without_saving(self):
        from unittest.mock import Mock
        registration = self.client.post("/api/v1/auth/register", json={
            "name": "Railway User", "email": "railway-invalid@example.com", "password": "password123"
        })
        headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
        fake_response = Mock(status_code=200)
        fake_response.json.return_value = {"errors": [{"message": "Unauthorized"}]}
        with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=fake_response)):
            response = self.client.post("/api/v1/integrations/railway/connect", headers=headers,
                                        json={"token": "invalid-token"})
        self.assertEqual(response.status_code, 400)
        status = self.client.get("/api/v1/integrations/railway", headers=headers).json()
        self.assertFalse(status["connected"])

    def test_railway_disconnect_removes_saved_credential(self):
        from unittest.mock import Mock
        registration = self.client.post("/api/v1/auth/register", json={
            "name": "Railway User", "email": "railway-disconnect@example.com", "password": "password123"
        })
        headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
        fake_response = Mock(status_code=200)
        fake_response.json.return_value = {"data": {"me": {"id": "acct-456", "name": "Test"}}}
        with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=fake_response)):
            self.client.post("/api/v1/integrations/railway/connect", headers=headers, json={"token": "secret"})
        removed = self.client.delete("/api/v1/integrations/railway", headers=headers)
        self.assertEqual(removed.status_code, 204)
        self.assertFalse(self.client.get("/api/v1/integrations/railway", headers=headers).json()["connected"])

    def test_railway_project_discovery_and_service_deployment_are_scoped(self):
        registration = self.client.post("/api/v1/auth/register", json={
            "name": "Railway User", "email": "railway-deploy@example.com", "password": "password123"
        })
        headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
        project_payload = {
            "project": {
                "id": "project-1", "name": "Demo",
                "services": {"edges": [{"node": {"id": "service-1", "name": "web"}}]},
                "environments": {"edges": [{"node": {"id": "environment-1", "name": "production"}}]},
            }
        }
        async def fake_railway(user_id, query, variables=None):
            if "projects {" in query:
                return {"projects": {"edges": [{"node": {"id": "project-1", "name": "Demo", "description": ""}}]}}
            if "serviceInstanceDeployV2" in query:
                return {"serviceInstanceDeployV2": "deployment-queued-1"}
            return project_payload
        with patch("app.main._railway_data", new=AsyncMock(side_effect=fake_railway)) as mocked:
            projects = self.client.get("/api/v1/integrations/railway/projects", headers=headers)
            self.assertEqual(projects.status_code, 200)
            self.assertEqual(projects.json()[0]["id"], "project-1")
            details = self.client.get("/api/v1/integrations/railway/projects/project-1", headers=headers)
            self.assertEqual(details.status_code, 200)
            self.assertEqual(details.json()["services"][0]["id"], "service-1")
            rejected = self.client.post("/api/v1/integrations/railway/deploy", headers=headers, json={
                "project_id": "project-1", "service_id": "other-service", "environment_id": "environment-1"
            })
            self.assertEqual(rejected.status_code, 400)
            self.assertEqual(mocked.await_count, 3)
            deployed = self.client.post("/api/v1/integrations/railway/deploy", headers=headers, json={
                "project_id": "project-1", "service_id": "service-1", "environment_id": "environment-1"
            })
            self.assertEqual(deployed.status_code, 200)
            self.assertEqual(deployed.json()["status"], "QUEUED")
            self.assertEqual(deployed.json()["deployment_id"], "deployment-queued-1")

    def test_railway_domain_management_is_scoped_and_confirmation_protected(self):
        registration = self.client.post("/api/v1/auth/register", json={
            "name": "Domain User", "email": "domain-user@example.com", "password": "password123"
        })
        headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
        remote = {"project": {
            "id": "p1", "services": {"edges": [{"node": {"id": "s1"}}]},
            "environments": {"edges": [{"node": {"id": "e1"}}]},
        }}
        cli_results = [
            type("Result", (), {"returncode": 0, "stdout": '[{"domain":"app.example.com"}]', "stderr": ""})(),
            type("Result", (), {"returncode": 0, "stdout": '{"dnsRecords":[{"type":"CNAME","value":"target.railway.app"}]}', "stderr": ""})(),
            type("Result", (), {"returncode": 0, "stdout": '{"status":"READY","certificate":"ISSUED"}', "stderr": ""})(),
            type("Result", (), {"returncode": 0, "stdout": '{"deleted":true}', "stderr": ""})(),
        ]
        with patch("app.main.get_user_railway_token", return_value="domain-secret"), \
             patch("app.main._railway_data", new=AsyncMock(return_value=remote)), \
             patch("app.main.shutil.which", return_value="/usr/bin/railway"), \
             patch("app.main.subprocess.run", side_effect=cli_results) as run:
            listing = self.client.get("/api/v1/integrations/railway/domains?project_id=p1&service_id=s1&environment_id=e1", headers=headers)
            self.assertEqual(listing.status_code, 200)
            self.assertEqual(listing.json()["domains"][0]["domain"], "app.example.com")
            added = self.client.post("/api/v1/integrations/railway/domains", headers=headers, json={
                "project_id": "p1", "service_id": "s1", "environment_id": "e1", "domain": "www.example.com", "port": 8080
            })
            self.assertEqual(added.status_code, 200)
            self.assertEqual(added.json()["status"], "REQUEST_ACCEPTED")
            status = self.client.get("/api/v1/integrations/railway/domains/status?domain=app.example.com&project_id=p1&service_id=s1&environment_id=e1", headers=headers)
            self.assertEqual(status.status_code, 200)
            self.assertEqual(status.json()["status"]["status"], "READY")
            no_confirm = self.client.request("DELETE", "/api/v1/integrations/railway/domains", headers=headers, json={
                "project_id": "p1", "service_id": "s1", "environment_id": "e1", "domain": "app.example.com"
            })
            self.assertEqual(no_confirm.status_code, 400)
            deleted = self.client.request("DELETE", "/api/v1/integrations/railway/domains", headers=headers, json={
                "project_id": "p1", "service_id": "s1", "environment_id": "e1", "domain": "app.example.com", "confirm_delete": True
            })
            self.assertEqual(deleted.status_code, 200)
            self.assertEqual(run.call_count, 4)
            self.assertIn("--project", run.call_args_list[1].args[0])
            self.assertIn("--environment", run.call_args_list[1].args[0])
            self.assertIn("--service", run.call_args_list[1].args[0])
            self.assertEqual(run.call_args_list[1].kwargs["env"]["RAILWAY_API_TOKEN"], "domain-secret")

    def test_railway_domain_rejects_invalid_host_and_foreign_service(self):
        registration = self.client.post("/api/v1/auth/register", json={
            "name": "Domain Guard", "email": "domain-guard@example.com", "password": "password123"
        })
        headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
        invalid = self.client.post("/api/v1/integrations/railway/domains", headers=headers, json={
            "project_id": "p1", "service_id": "s1", "environment_id": "e1", "domain": "https://bad.example.com/path"
        })
        self.assertEqual(invalid.status_code, 422)
        foreign = {"project": {"id": "p1", "services": {"edges": []}, "environments": {"edges": [{"node": {"id": "e1"}}]}}}
        with patch("app.main._railway_data", new=AsyncMock(return_value=foreign)), patch("app.main.get_user_railway_token", return_value="secret"):
            rejected = self.client.get("/api/v1/integrations/railway/domains?project_id=p1&service_id=not-owned&environment_id=e1", headers=headers)
        self.assertEqual(rejected.status_code, 400)

    def test_railway_deployment_routes_require_authentication(self):
        self.assertEqual(self.client.get("/api/v1/integrations/railway/projects").status_code, 401)
        self.assertEqual(self.client.post("/api/v1/integrations/railway/deploy", json={}).status_code, 401)
        self.assertEqual(self.client.get("/api/v1/integrations/railway/domains?project_id=p&service_id=s&environment_id=e").status_code, 401)
        self.assertEqual(self.client.post("/api/v1/integrations/railway/domains", json={}).status_code, 401)

    def test_railway_latest_deployment_reports_success_only_for_success_state(self):
        registration = self.client.post("/api/v1/auth/register", json={
            "name": "Railway Status", "email": "railway-status@example.com", "password": "password123"
        })
        headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
        async def fake_railway(user_id, query, variables=None):
            self.assertEqual(variables["first"], 1)
            return {"deployments": {"edges": [{"node": {
                "id": "dep-1", "status": "BUILDING", "createdAt": "2026-11-15T10:00:00Z",
                "url": None, "staticUrl": None
            }}]}}
        with patch("app.main._railway_data", new=AsyncMock(side_effect=fake_railway)):
            response = self.client.get(
                "/api/v1/integrations/railway/deployments/latest?project_id=p&service_id=s&environment_id=e",
                headers=headers,
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "BUILDING")
        self.assertFalse(response.json()["is_success"])

    def test_railway_latest_deployment_handles_empty_history(self):
        registration = self.client.post("/api/v1/auth/register", json={
            "name": "Railway Empty", "email": "railway-empty@example.com", "password": "password123"
        })
        headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
        with patch("app.main._railway_data", new=AsyncMock(return_value={"deployments": {"edges": []}})):
            response = self.client.get(
                "/api/v1/integrations/railway/deployments/latest?project_id=p&service_id=s&environment_id=e",
                headers=headers,
            )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["found"])
        self.assertEqual(response.json()["status"], "NO_DEPLOYMENTS")


    def test_deployment_source_zip_upload_and_readback(self):
        import io
        import zipfile
        from app import main as main_module
        main_module.DEPLOYMENT_SOURCES_ROOT = Path(self.temp.name) / "private_sources"
        registration = self.client.post("/api/v1/auth/register", json={
            "name": "Deploy User", "email": "deploy-source@example.com", "password": "password123"
        })
        headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
        project = self.client.post("/api/v1/projects", headers=headers, json={"name": "Deployable"}).json()
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("index.html", "hello")
            archive.writestr("package.json", '{"scripts":{"start":"node server.js"}}')
        response = self.client.post(
            f"/api/v1/projects/{project['id']}/deployment-source", headers=headers,
            files={"file": ("source.zip", stream.getvalue(), "application/zip")}
        )
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["status"], "STORED_AND_VALIDATED")
        self.assertEqual(response.json()["deployment_status"], "NOT_DEPLOYED")
        readback = self.client.get(f"/api/v1/projects/{project['id']}/deployment-source", headers=headers)
        self.assertTrue(readback.json()["found"])
        self.assertEqual(readback.json()["source"]["file_count"], 2)
        self.assertEqual(len(list(main_module.DEPLOYMENT_SOURCES_ROOT.iterdir())), 1)

    def test_deployment_source_rejects_zip_path_traversal(self):
        import io
        import zipfile
        from app import main as main_module
        main_module.DEPLOYMENT_SOURCES_ROOT = Path(self.temp.name) / "private_sources"
        registration = self.client.post("/api/v1/auth/register", json={
            "name": "Deploy User", "email": "deploy-traversal@example.com", "password": "password123"
        })
        headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
        project = self.client.post("/api/v1/projects", headers=headers, json={"name": "Unsafe"}).json()
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("../escape.txt", "bad")
        response = self.client.post(
            f"/api/v1/projects/{project['id']}/deployment-source", headers=headers,
            files={"file": ("unsafe.zip", stream.getvalue(), "application/zip")}
        )
        self.assertEqual(response.status_code, 422)

    def test_deployment_source_is_private_to_project_owner(self):
        registration = self.client.post("/api/v1/auth/register", json={
            "name": "Owner", "email": "source-owner@example.com", "password": "password123"
        })
        owner_headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
        project = self.client.post("/api/v1/projects", headers=owner_headers, json={"name": "Private"}).json()
        other = self.client.post("/api/v1/auth/register", json={
            "name": "Other", "email": "source-other@example.com", "password": "password123"
        })
        other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
        self.assertEqual(self.client.get(
            f"/api/v1/projects/{project['id']}/deployment-source", headers=other_headers
        ).status_code, 404)


    def test_deployment_logs_are_bounded_and_owner_scoped(self):
        from unittest.mock import patch
        from app import main as api
        registration = self.client.post("/api/v1/auth/register", json={
            "name": "Logs Owner", "email": "logs-owner@example.com", "password": "password123"
        })
        headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
        project = self.client.post("/api/v1/projects", headers=headers, json={"name": "Logs project"}).json()
        with db.connection() as conn:
            source = conn.execute(
                "INSERT INTO deployment_sources(user_id,project_id,stored_name,original_name,sha256,size_bytes,file_count) VALUES(?,?,?,?,?,?,?)",
                (registration.json()["user"]["id"], project["id"], "logs.zip", "logs.zip", "a" * 64, 10, 1),
            ).lastrowid
            run_id = conn.execute(
                "INSERT INTO deployment_runs(user_id,project_id,source_id,railway_project_id,railway_service_id,railway_environment_id,status) VALUES(?,?,?,?,?,?,?)",
                (registration.json()["user"]["id"], project["id"], source, "rp", "rs", "re", "triggered"),
            ).lastrowid
        fake = type("Result", (), {"returncode": 0, "stdout": '[{"message":"build ok"},{"message":"started"}]', "stderr": ""})()
        with patch("app.main.get_user_railway_token", return_value="secret-token"), \
             patch("app.main.shutil.which", return_value="/usr/bin/railway"), \
             patch("app.main.subprocess.run", return_value=fake) as run:
            response = self.client.get(
                f"/api/v1/projects/{project['id']}/deployment-source/runs/{run_id}/logs?kind=build", headers=headers
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["lines"]), 2)
        command = run.call_args.args[0]
        self.assertIn("--build", command)
        self.assertIn("150", command)
        self.assertEqual(run.call_args.kwargs["env"]["RAILWAY_API_TOKEN"], "secret-token")
        invalid = self.client.get(
            f"/api/v1/projects/{project['id']}/deployment-source/runs/{run_id}/logs?kind=other", headers=headers
        )
        self.assertEqual(invalid.status_code, 422)
        outsider = self.client.post("/api/v1/auth/register", json={
            "name": "Other User", "email": "logs-other@example.com", "password": "password123"
        })
        outsider_headers = {"Authorization": f"Bearer {outsider.json()['access_token']}"}
        denied = self.client.get(
            f"/api/v1/projects/{project['id']}/deployment-source/runs/{run_id}/logs", headers=outsider_headers
        )
        self.assertEqual(denied.status_code, 404)


    def test_android_package_exports_android_studio_source_and_excludes_secrets(self):
        import io
        import zipfile
        from app.workspace_tools import security as workspace_security
        workspace_security.WORKSPACE_ROOT = Path(self.temp.name) / "workspace"
        registration = self.client.post("/api/v1/auth/register", json={
            "name": "Android User", "email": "android-user@example.com", "password": "password123"
        })
        headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
        project = self.client.post("/api/v1/projects", headers=headers, json={"name": "Android demo"}).json()
        pid = project["id"]
        self.client.put(f"/api/v1/projects/{pid}/files/index.html", headers=headers,
                        json={"content": "<html><body>Demo</body></html>"})
        self.client.put(f"/api/v1/projects/{pid}/files/.env", headers=headers,
                        json={"content": "SECRET=do-not-export"})
        self.client.put(f"/api/v1/projects/{pid}/files/.env.development", headers=headers,
                        json={"content": "SECRET=also-do-not-export"})
        self.client.put(f"/api/v1/projects/{pid}/files/credentials.json", headers=headers,
                        json={"content": "{\"private\":true}"})
        response = self.client.get(f"/api/v1/projects/{pid}/android-package", headers=headers)
        self.assertEqual(response.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(response.content)) as bundle:
            names = bundle.namelist()
            self.assertIn("NatqAIAndroid/app/build.gradle", names)
            self.assertIn("NatqAIAndroid/app/src/main/java/com/natqai/generated/MainActivity.java", names)
            self.assertIn("NatqAIAndroid/app/src/main/assets/www/index.html", names)
            self.assertIn("NatqAIAndroid/app/src/main/assets/www/natqai-config.js", names)
            self.assertFalse(any(name.endswith("/.env") or "/.env." in name for name in names))
            self.assertFalse(any(name.endswith("/credentials.json") for name in names))
            self.assertNotIn(b"do-not-export", b"".join(bundle.read(name) for name in names if not name.endswith("/README_AR.md")))

    def test_android_package_requires_index_html(self):
        from app.workspace_tools import security as workspace_security
        workspace_security.WORKSPACE_ROOT = Path(self.temp.name) / "workspace"
        registration = self.client.post("/api/v1/auth/register", json={
            "name": "No HTML", "email": "no-html@example.com", "password": "password123"
        })
        headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
        project = self.client.post("/api/v1/projects", headers=headers, json={"name": "No HTML"}).json()
        self.client.put(f"/api/v1/projects/{project['id']}/files/main.js", headers=headers,
                        json={"content": "console.log('hi')"})
        response = self.client.get(f"/api/v1/projects/{project['id']}/android-package", headers=headers)
        self.assertEqual(response.status_code, 422)

    def test_android_apk_validator_rejects_non_apk_zip(self):
        import io
        import zipfile
        from app.main import _valid_android_apk
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as archive:
            archive.writestr("readme.txt", "not an APK")
        self.assertFalse(_valid_android_apk(data.getvalue()))
        self.assertFalse(_valid_android_apk(b"PK\x03\x04" + b"x" * 2048))

    def test_android_builder_url_allows_tls_and_private_endpoints_only(self):
        from app.main import _valid_android_builder_url
        self.assertTrue(_valid_android_builder_url("https://builder.example.com"))
        self.assertTrue(_valid_android_builder_url("http://natqai-android-builder.railway.internal:8080"))
        self.assertTrue(_valid_android_builder_url("http://127.0.0.1:8080"))
        self.assertTrue(_valid_android_builder_url("http://10.0.0.12:8080"))
        self.assertFalse(_valid_android_builder_url("http://builder.example.com"))
        self.assertFalse(_valid_android_builder_url("http://169.254.169.254"))
        self.assertFalse(_valid_android_builder_url("https://user:pass@builder.example.com"))
        self.assertFalse(_valid_android_builder_url("https://builder.example.com/private/path"))
        self.assertFalse(_valid_android_builder_url("https://builder.example.com/?token=secret"))

    def test_android_builder_status_rejects_insecure_public_http_url(self):
        registration = self.client.post("/api/v1/auth/register", json={
            "name": "Unsafe Builder", "email": "unsafe-builder@example.com", "password": "password123"
        })
        headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
        project = self.client.post("/api/v1/projects", headers=headers, json={"name": "Unsafe builder"}).json()
        with patch.dict(os.environ, {"ANDROID_BUILDER_URL": "http://public.example.com", "ANDROID_BUILDER_TOKEN": "secret-token"}), \
             patch("httpx.AsyncClient") as client:
            response = self.client.get(f"/api/v1/projects/{project['id']}/android-builder-status", headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["ready"])
        self.assertEqual(response.json()["status"], "not_configured")
        client.assert_not_called()
        self.assertNotIn("secret-token", response.text)

    def test_android_builder_status_reports_unconfigured_without_leaking_settings(self):
        registration = self.client.post("/api/v1/auth/register", json={
            "name": "Builder Status", "email": "builder-status@example.com", "password": "password123"
        })
        headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
        project = self.client.post("/api/v1/projects", headers=headers, json={"name": "Builder status"}).json()
        with patch.dict(os.environ, {"ANDROID_BUILDER_URL": "", "ANDROID_BUILDER_TOKEN": ""}):
            response = self.client.get(f"/api/v1/projects/{project['id']}/android-builder-status", headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "not_configured")
        self.assertFalse(response.json()["ready"])
        self.assertNotIn("token", response.text.lower())

    def test_android_builder_status_checks_private_worker_readiness(self):
        from types import SimpleNamespace
        registration = self.client.post("/api/v1/auth/register", json={
            "name": "Builder Ready", "email": "builder-ready@example.com", "password": "password123"
        })
        headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
        project = self.client.post("/api/v1/projects", headers=headers, json={"name": "Builder ready"}).json()
        class FakeClient:
            def __init__(self, *args, **kwargs): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return False
            async def get(self, url, headers=None):
                self.url = url
                self.headers = headers or {}
                FakeClient.last_headers = self.headers
                return SimpleNamespace(status_code=200)
        with patch.dict(os.environ, {"ANDROID_BUILDER_URL": "https://private-worker.invalid", "ANDROID_BUILDER_TOKEN": "secret-test-token"}), patch("httpx.AsyncClient", FakeClient):
            response = self.client.get(f"/api/v1/projects/{project['id']}/android-builder-status", headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ready"])
        self.assertEqual(response.json()["status"], "ready")
        self.assertEqual(FakeClient.last_headers, {"Authorization": "Bearer secret-test-token"})
        self.assertNotIn("private-worker.invalid", response.text)
        self.assertNotIn("secret-test-token", response.text)

    def test_android_apk_build_requires_configured_isolated_worker(self):
        from unittest.mock import patch
        registration = self.client.post("/api/v1/auth/register", json={
            "name": "APK User", "email": "apk-user@example.com", "password": "password123"
        })
        headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
        project = self.client.post("/api/v1/projects", headers=headers, json={"name": "APK demo"}).json()
        with patch.dict(os.environ, {"ANDROID_BUILDER_URL": "", "ANDROID_BUILDER_TOKEN": ""}):
            response = self.client.post(f"/api/v1/projects/{project['id']}/android-apk", headers=headers)
        self.assertEqual(response.status_code, 503)
        self.assertIn("خدمة بناء APK", response.json()["detail"])

    def test_android_apk_build_enforces_project_ownership(self):
        response = self.client.post("/api/v1/projects/999/android-apk")
        self.assertEqual(response.status_code, 401)

    def test_android_package_requires_project_ownership(self):
        response = self.client.get("/api/v1/projects/999/android-package")
        self.assertEqual(response.status_code, 401)

    def test_android_package_is_private_to_project_owner(self):
        from app.workspace_tools import security as workspace_security
        workspace_security.WORKSPACE_ROOT = Path(self.temp.name) / "workspace"
        owner = self.client.post("/api/v1/auth/register", json={
            "name": "Package Owner", "email": "package-owner@example.com", "password": "password123"
        })
        owner_headers = {"Authorization": f"Bearer {owner.json()['access_token']}"}
        project = self.client.post("/api/v1/projects", headers=owner_headers, json={"name": "Private app"}).json()
        self.client.put(f"/api/v1/projects/{project['id']}/files/index.html", headers=owner_headers,
                        json={"content": "<h1>Private</h1>"})
        other = self.client.post("/api/v1/auth/register", json={
            "name": "Package Guest", "email": "package-guest@example.com", "password": "password123"
        })
        guest_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
        response = self.client.get(f"/api/v1/projects/{project['id']}/android-package", headers=guest_headers)
        self.assertEqual(response.status_code, 404)



if __name__ == "__main__":
    unittest.main()

    def test_user_can_delete_owned_chat_and_related_rows(self):
        registration = self.client.post("/api/v1/auth/register", json={
            "name": "Delete User", "email": "delete-user@example.com", "password": "password123"
        })
        headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}
        chat = self.client.post("/api/v1/chats", headers=headers).json()
        with db.connection() as conn:
            conn.execute("INSERT INTO messages(chat_id,role,content) VALUES(?,?,?)", (chat["id"], "user", "hello"))
        response = self.client.delete(f"/api/v1/chats/{chat['id']}", headers=headers)
        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.client.get("/api/v1/chats", headers=headers).json(), [])
        self.assertEqual(self.client.get(f"/api/v1/chats/{chat['id']}/messages", headers=headers).status_code, 404)

    def test_user_can_delete_all_chats_without_affecting_other_users(self):
        first = self.client.post("/api/v1/auth/register", json={"name":"A User","email":"a-user@example.com","password":"password123"})
        second = self.client.post("/api/v1/auth/register", json={"name":"B User","email":"b-user@example.com","password":"password123"})
        h1 = {"Authorization": f"Bearer {first.json()['access_token']}"}
        h2 = {"Authorization": f"Bearer {second.json()['access_token']}"}
        self.client.post("/api/v1/chats", headers=h1)
        self.client.post("/api/v1/chats", headers=h1)
        other = self.client.post("/api/v1/chats", headers=h2).json()
        response = self.client.delete("/api/v1/chats", headers=h1)
        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.client.get("/api/v1/chats", headers=h1).json(), [])
        self.assertEqual(len(self.client.get("/api/v1/chats", headers=h2).json()), 1)
        self.assertEqual(self.client.get(f"/api/v1/chats/{other['id']}/messages", headers=h2).status_code, 200)
