from __future__ import annotations

import importlib.util
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from lib.retrieval_adapters import Release


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts/create_retrieval_release.py"
SPEC = importlib.util.spec_from_file_location("create_retrieval_release", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RetrievalReleaseGitTests(unittest.TestCase):
    def test_release_exposes_declared_lexical_revision(self) -> None:
        release = Release(
            Path("/tmp/active-release.json"),
            {"artifacts": {"lexical_index": {"corpus_commit": "lexical123"}}},
        )

        self.assertEqual(release.lexical_revision, "lexical123")

    def test_git_revision_trusts_the_mounted_checkout_only(self) -> None:
        checkout = Path("/tmp/patra-darpan-test-checkout")
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="abc123\n", stderr=""
        )
        with patch.object(MODULE.subprocess, "run", return_value=completed) as run:
            revision = MODULE.git_revision(checkout)

        self.assertEqual(revision, "abc123")
        run.assert_called_once_with(
            [
                "git",
                "-c",
                f"safe.directory={checkout.resolve()}",
                "-C",
                str(checkout.resolve()),
                "rev-parse",
                "HEAD",
            ],
            check=True,
            text=True,
            capture_output=True,
        )


if __name__ == "__main__":
    unittest.main()
