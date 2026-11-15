import os
import tempfile
import unittest
import hashlib
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from app import db
from app.main import app
from app.workspace_tools import security as workspace_security


class ProjectFixTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_db = db.DATABASE_PATH
        self.old_workspace = workspace_security.WORKSPACE_ROOT
        db.DATABASE_PATH = os.path.join(self.temp.name, "test.sqlite3")
        workspace_security.WORKSPACE_ROOT = __import__("pathlib").Path(self.temp.name) / "workspace"
        db.init_db()
        self.client = TestClient(app)
        registered = self.client.post("/api/v1/auth/register", json={
            "name": "Fix User", "email": "fix@example.com", "password": "password123"
        })
        self.headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
        project = self.client.post("/api/v1/projects", headers=self.headers, json={"name": "Fix Demo"})
        self.project_id = project.json()["id"]
        self.path = f"/api/v1/projects/{self.project_id}/files/main.py"
        self.original = "print('before')\\n"
        self.client.put(self.path, headers=self.headers, json={"content": self.original})

    def tearDown(self):
        self.client.close()
        db.DATABASE_PATH = self.old_db
        workspace_security.WORKSPACE_ROOT = self.old_workspace
        self.temp.cleanup()

    def test_safe_project_check_reports_python_syntax_without_execution(self):
        self.client.put(
            f"/api/v1/projects/{self.project_id}/files/main.py",
            headers=self.headers, json={"content": "print('before')\n"}
        )
        self.client.put(
            f"/api/v1/projects/{self.project_id}/files/broken.py",
            headers=self.headers, json={"content": "def broken(:\n pass"}
        )
        response = self.client.post(
            f"/api/v1/projects/{self.project_id}/check", headers=self.headers
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["executed"])
        self.assertEqual(payload["counts"]["failed"], 1)
        failed = [item for item in payload["results"] if item["status"] == "failed"]
        self.assertEqual(failed[0]["path"], "broken.py")

    def test_preview_does_not_modify_and_apply_requires_matching_hash(self):
        proposed = "print('after')\\n"
        fake = {"content": __import__("json").dumps({
            "explanation": "Corrected the output.", "content": proposed
        }), "model": "mock-model", "usage": {}}
        with patch("app.main.OpenAICompatibleProvider.chat", new=AsyncMock(return_value=fake)):
            preview = self.client.post(
                f"/api/v1/projects/{self.project_id}/fix-preview",
                headers=self.headers,
                json={"path": "main.py", "issue": "Wrong output", "recommendation": "Correct the print statement"}
            )
        self.assertEqual(preview.status_code, 200)
        self.assertFalse(preview.json()["saved"])
        self.assertEqual(self.client.get(self.path, headers=self.headers).json()["content"], self.original)
        applied = self.client.put(
            f"/api/v1/projects/{self.project_id}/files/main.py/apply-fix",
            headers=self.headers,
            json={"expected_sha256": preview.json()["expected_sha256"], "content": proposed}
        )
        self.assertEqual(applied.status_code, 200)
        self.assertEqual(self.client.get(self.path, headers=self.headers).json()["content"], proposed)

    def test_apply_rejects_stale_preview(self):
        digest = hashlib.sha256(self.original.encode("utf-8")).hexdigest()
        self.client.put(self.path, headers=self.headers, json={"content": "print('changed')"})
        response = self.client.put(
            f"/api/v1/projects/{self.project_id}/files/main.py/apply-fix",
            headers=self.headers,
            json={"expected_sha256": digest, "content": "print('fixed')"}
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.client.get(self.path, headers=self.headers).json()["content"], "print('changed')")


if __name__ == "__main__":
    unittest.main()
