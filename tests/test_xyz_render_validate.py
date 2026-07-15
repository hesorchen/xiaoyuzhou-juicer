import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


xyz_render = load("xyz_render")
xyz_validate = load("xyz_validate")
install_skill = load("install_skill")


META = {
    "title": "42: Test Episode",
    "podcast": "Test Pod",
    "url": "https://example.test/episode/abc",
    "duration_sec": 600,
    "duration_hms": "00:10:00",
    "pub_date": "2026-07-15T00:00:00Z",
    "stats": {"play_count": 100, "favorite_count": 5, "comment_count": 2, "podcast_subscriptions": 1000},
    "snapshot": {"age_hours": 4.0},
    "chapters": [{"ts": "00:30", "title": "Opening"}, {"ts": "05:00", "title": "Second"}],
}


class RenderValidateTest(unittest.TestCase):
    def test_full_scaffold_uses_exact_title_and_official_chapters(self):
        output = xyz_render.render_scaffold(META, "full")
        self.assertTrue(output.startswith("# 42: Test Episode\n"))
        self.assertIn("### 1. Opening（00:30–05:00）", output)
        self.assertIn("### 2. Second（05:00–00:10:00）", output)

    def test_quick_scaffold_is_short(self):
        output = xyz_render.render_scaffold(META, "quick")
        self.assertIn("## 推荐章节", output)
        self.assertNotIn("## 嘉宾背景卡", output)

    def test_detect_history_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "learning" / "podcasts"
            target.mkdir(parents=True)
            (target / "a-摘要.md").write_text("# a", encoding="utf-8")
            self.assertEqual(xyz_render.detect_history_dir(root), target)

    def test_validator_rejects_wrong_title_and_timestamp(self):
        text = xyz_render.render_scaffold(META, "full")
        text = text.replace("# 42: Test Episode", "# Wrong", 1).replace("[00:01]", "[11:00]")
        errors, _ = xyz_validate.validate(text, META, mode="full")
        self.assertTrue(any("H1" in error for error in errors))

    def test_validator_accepts_generated_full_scaffold_with_warning(self):
        text = xyz_render.render_scaffold(META, "full")
        errors, warnings = xyz_validate.validate(text, META, mode="full")
        self.assertEqual(errors, [])
        self.assertTrue(any("TODO" in warning for warning in warnings))

    def test_installer_syncs_runtime_without_touching_token(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            token = target / "config" / "token.txt"
            token.parent.mkdir(parents=True)
            token.write_text("secret", encoding="utf-8")
            install_skill.install(target)
            self.assertEqual(install_skill.drift(target), [])
            self.assertEqual(token.read_text(encoding="utf-8"), "secret")


if __name__ == "__main__":
    unittest.main()
