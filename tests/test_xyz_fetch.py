import datetime as dt
import gzip
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("xyz_fetch", ROOT / "scripts" / "xyz_fetch.py")
xyz_fetch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(xyz_fetch)


class FetchHelpersTest(unittest.TestCase):
    def test_decode_gzip_by_magic_byte(self):
        payload = b'[{"text":"hello"}]'
        self.assertEqual(xyz_fetch.decode_http_body(gzip.compress(payload)), payload)

    def test_stale_gzip_header_does_not_double_decode(self):
        payload = b'[{"text":"already decoded"}]'
        self.assertEqual(xyz_fetch.decode_http_body(payload, "gzip"), payload)

    def test_extract_chapters_supports_split_lines(self):
        shownotes = "00:01 Intro\n00:02:03\nDeep dive\n"
        self.assertEqual(
            xyz_fetch.extract_chapters(shownotes),
            [("00:01", "Intro"), ("00:02:03", "Deep dive")],
        )

    def test_snapshot_metrics_are_age_normalized(self):
        now = dt.datetime(2026, 7, 15, 12, tzinfo=dt.timezone.utc)
        result = xyz_fetch.snapshot_metrics("2026-07-15T10:00:00Z", 1000, 20, now)
        self.assertEqual(result["age_hours"], 2.0)
        self.assertEqual(result["plays_per_hour"], 500.0)
        self.assertEqual(result["comments_per_1000_plays"], 20.0)

    def test_unknown_comment_association_is_not_called_host(self):
        tags = xyz_fetch._author_tags({"authorAssociation": "ORIGINAL"})
        self.assertEqual(tags, ["[关联:ORIGINAL]"])

    def test_atomic_write_replaces_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "token.txt"
            path.write_text("old", encoding="utf-8")
            xyz_fetch.atomic_write_text(str(path), "new\n")
            self.assertEqual(path.read_text(encoding="utf-8"), "new\n")


if __name__ == "__main__":
    unittest.main()
