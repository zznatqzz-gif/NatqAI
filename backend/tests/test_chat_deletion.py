import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from app import db
from app.main import app
from app.workspace_tools.attachments import ATTACHMENTS_ROOT


class ChatDeletionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_db = db.DATABASE_PATH
        db.DATABASE_PATH = os.path.join(self.temp.name, "test.sqlite3")
        db.init_db()
        self.old_attachments_root = __import__("app.main", fromlist=["ATTACHMENTS_ROOT"]).ATTACHMENTS_ROOT
        import app.main as main_module
        main_module.ATTACHMENTS_ROOT = Path(self.temp.name) / "attachments"
        self.attachments_root = main_module.ATTACHMENTS_ROOT
        self.client = TestClient(app)
        response = self.client.post("/api/v1/auth/register", json={
            "name": "Chat Owner", "email": "chat-owner@example.com", "password": "password123"
        })
        self.headers = {"Authorization": f"Bearer {response.json()['access_token']}"}

    def tearDown(self):
        import app.main as main_module
        main_module.ATTACHMENTS_ROOT = self.old_attachments_root
        self.client.close()
        db.DATABASE_PATH = self.old_db
        self.temp.cleanup()

    def test_delete_one_chat_removes_messages_and_attachment_files(self):
        chat = self.client.post("/api/v1/chats", headers=self.headers).json()
        with db.connection() as conn:
            conn.execute("INSERT INTO messages(chat_id,role,content) VALUES(?,?,?)",
                         (chat["id"], "user", "hello"))
        folder = self.attachments_root / "1" / str(chat["id"])
        folder.mkdir(parents=True)
        (folder / "sample.txt").write_text("test", encoding="utf-8")

        response = self.client.delete(f"/api/v1/chats/{chat['id']}", headers=self.headers)
        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.client.get("/api/v1/chats", headers=self.headers).json(), [])
        self.assertFalse(folder.exists())
        with db.connection() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM messages WHERE chat_id=?", (chat["id"],)).fetchone()[0], 0)

    def test_delete_all_chats_is_scoped_to_authenticated_user(self):
        first = self.client.post("/api/v1/chats", headers=self.headers).json()
        self.client.post("/api/v1/chats", headers=self.headers)
        other = self.client.post("/api/v1/auth/register", json={
            "name": "Other User", "email": "other-chat@example.com", "password": "password123"
        })
        other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
        other_chat = self.client.post("/api/v1/chats", headers=other_headers).json()

        response = self.client.delete("/api/v1/chats", headers=self.headers)
        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.client.get("/api/v1/chats", headers=self.headers).json(), [])
        self.assertEqual(len(self.client.get("/api/v1/chats", headers=other_headers).json()), 1)
        self.assertEqual(self.client.get(f"/api/v1/chats/{other_chat['id']}/messages", headers=other_headers).status_code, 200)
        self.assertEqual(self.client.delete(f"/api/v1/chats/{first['id']}", headers=other_headers).status_code, 404)

    def test_delete_requires_authentication(self):
        self.assertEqual(self.client.delete("/api/v1/chats").status_code, 401)
        self.assertEqual(self.client.delete("/api/v1/chats/1").status_code, 401)


if __name__ == "__main__":
    unittest.main()
