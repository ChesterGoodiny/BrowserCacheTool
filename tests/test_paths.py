import shutil
import tempfile
import unittest
from pathlib import Path

from paths import BrowserSpec, cache_targets, find_profiles


class PathTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="chrome-cache-tool-test-"))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_chromium_profiles_are_limited_to_expected_names(self):
        for name in ("Default", "Profile 1"):
            (self.root / name).mkdir()
        (self.root / "Other").mkdir()
        spec = BrowserSpec("test", "Test", self.root, "test.exe", "chromium", ("Cache",))

        self.assertEqual([item.name for item in find_profiles(spec)], ["Default", "Profile 1"])

    def test_firefox_cache_can_have_a_separate_root(self):
        profile = self.root / "abc.dev-edition-default-1"
        profile.mkdir()
        cache_root = self.root / "local-cache"
        spec = BrowserSpec(
            "test",
            "Test",
            self.root,
            "test.exe",
            "firefox",
            ("cache2",),
            cache_root,
        )

        self.assertEqual(find_profiles(spec), [profile])
        self.assertEqual(cache_targets(spec, profile), [cache_root / profile.name / "cache2"])


if __name__ == "__main__":
    unittest.main()
