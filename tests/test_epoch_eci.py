"""Include the Node prefetch contract tests in the repository's required test command."""
import pathlib
import subprocess
import unittest


class EpochEciPrefetchTests(unittest.TestCase):
    def test_node_prefetch_contract(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        result = subprocess.run(
            ['node', '--test', 'tests/epoch_eci.test.js'],
            cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout)


if __name__ == '__main__':
    unittest.main()
