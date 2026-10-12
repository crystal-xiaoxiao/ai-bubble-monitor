"""Exercise the actual HTML renderer in the repository's required test command."""
import pathlib
import subprocess
import unittest


class FrontendFreshnessTests(unittest.TestCase):
    def test_real_page_renderer(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        result = subprocess.run(
            ['node', 'tests/frontend_freshness.test.js'],
            cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout)


if __name__ == '__main__':
    unittest.main()
