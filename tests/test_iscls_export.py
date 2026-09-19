from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from lib.iscls_export import export_documents


class IsclsExportTests(unittest.TestCase):
    def _fixture(self, root: Path) -> tuple[Path, Path, Path]:
        decoded = root / "decoded-corpus"
        sanchaya = root / "sanchaya"
        decoded.mkdir()
        sanchaya.mkdir()
        doc_dir = decoded / "by-doc" / "paper-1"
        (doc_dir / "media").mkdir(parents=True)
        (doc_dir / "document.md").write_text(
            "# Sūrya\n\n![Figure](media/figure.png)\n\nA passage.", encoding="utf-8"
        )
        (doc_dir / "media" / "figure.png").write_bytes(b"png")
        source = {
            "doc_id": "paper-1",
            "title": "A Jyotisha paper",
            "author_display": "A Researcher",
            "year": "2024",
            "journal_label": "IJHS-60-2024-Issue-1",
            "source_url": "https://insa.nic.in/paper.pdf",
            "gcs_key": "ijhs/paper-1.pdf",
        }
        (doc_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "doc_id": "paper-1",
                    "status": "ok",
                    "source": source,
                    "source_pdf_sha256": "pdf-hash",
                    "extractor": "test-extractor",
                    "run_id": "run-1",
                }
            ),
            encoding="utf-8",
        )
        (doc_dir / "quality.json").write_text(
            json.dumps({"status": "ok", "warnings": []}), encoding="utf-8"
        )
        (decoded / "manifest.jsonl").write_text(
            json.dumps({"doc_id": "paper-1", "status": "ok"}) + "\n", encoding="utf-8"
        )
        index_tsv = root / "index.tsv"
        index_tsv.write_text(
            "gcs_key\tsubject\tcategory\tju_url\n"
            "ijhs/paper-1.pdf\tAstronomy\tIndic\thttps://cahc.jainuniversity.ac.in/paper.pdf\n",
            encoding="utf-8",
        )
        return decoded, sanchaya, index_tsv

    def test_dry_run_does_not_write_sanchaya(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            decoded, sanchaya, index_tsv = self._fixture(Path(temp))
            result = export_documents(
                decoded_root=decoded,
                sanchaya_root=sanchaya,
                index_tsv=index_tsv,
            )
            self.assertTrue(result.ok)
            self.assertFalse(result.applied)
            self.assertFalse((sanchaya / "patra-darpan").exists())
            self.assertEqual(result.exported, ["paper-1"])

    def test_apply_writes_paper_media_and_typed_manifest_refs(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            decoded, sanchaya, index_tsv = self._fixture(Path(temp))
            result = export_documents(
                decoded_root=decoded,
                sanchaya_root=sanchaya,
                index_tsv=index_tsv,
                apply=True,
            )
            self.assertTrue(result.ok)
            paper = sanchaya / "patra-darpan" / "papers" / "paper-1"
            self.assertEqual((paper / "document.md").read_text(encoding="utf-8").splitlines()[0], "# Sūrya")
            self.assertEqual((paper / "media" / "figure.png").read_bytes(), b"png")
            rows = [
                json.loads(line)
                for line in (sanchaya / "patra-darpan" / "catalog" / "corpus-manifest.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            row = rows[0]
            self.assertEqual(row["document_id"], "pd:paper-1")
            self.assertEqual(row["primary_category"], "Astronomy")
            self.assertEqual({ref["kind"] for ref in row["source_refs"]}, {"insa-ijhs", "cahc", "gcs"})

    def test_second_identical_export_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            decoded, sanchaya, index_tsv = self._fixture(Path(temp))
            first = export_documents(
                decoded_root=decoded,
                sanchaya_root=sanchaya,
                index_tsv=index_tsv,
                apply=True,
            )
            manifest = sanchaya / "patra-darpan" / "catalog" / "corpus-manifest.jsonl"
            before = manifest.read_bytes()
            second = export_documents(
                decoded_root=decoded,
                sanchaya_root=sanchaya,
                index_tsv=index_tsv,
                apply=True,
            )
            self.assertTrue(first.ok and second.ok)
            self.assertEqual(second.skipped, ["paper-1"])
            self.assertEqual(manifest.read_bytes(), before)

    def test_missing_media_is_an_error_before_apply(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            decoded, sanchaya, index_tsv = self._fixture(Path(temp))
            md = decoded / "by-doc" / "paper-1" / "document.md"
            md.write_text("![Missing](media/missing.png)", encoding="utf-8")
            result = export_documents(
                decoded_root=decoded,
                sanchaya_root=sanchaya,
                index_tsv=index_tsv,
                apply=True,
            )
            self.assertFalse(result.ok)
            self.assertIn("missing local image", result.errors[0])
            self.assertFalse((sanchaya / "patra-darpan").exists())


if __name__ == "__main__":
    unittest.main()
