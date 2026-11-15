import unittest
from app.workspace_tools.project_checks import check_project_files


class ProjectChecksTests(unittest.TestCase):
    def test_valid_python_and_json_pass(self):
        result = check_project_files([
            {"path": "main.py", "content": "value = 1\n"},
            {"path": "config.json", "content": '{"ok": true}'}
        ])
        self.assertEqual(result["counts"]["passed"], 2)
        self.assertFalse(result["executed"])

    def test_invalid_python_and_json_are_reported(self):
        result = check_project_files([
            {"path": "broken.py", "content": "def broken(:\n pass"},
            {"path": "broken.json", "content": '{oops'}
        ])
        self.assertEqual(result["counts"]["failed"], 2)

    def test_javascript_is_not_claimed_as_checked_or_executed(self):
        result = check_project_files([{"path": "app.js", "content": "alert(1)"}])
        self.assertEqual(result["counts"]["not_checked"], 1)
        self.assertFalse(result["executed"])


if __name__ == "__main__":
    unittest.main()
