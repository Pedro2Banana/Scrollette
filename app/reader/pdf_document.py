import hashlib
from pathlib import Path

import fitz


class PdfDocument:
    """Small wrapper around PyMuPDF's document object."""

    def __init__(self):
        self.path: Path | None = None
        self._doc: fitz.Document | None = None
        self._file_hash: str | None = None

    def open(self, path):
        pdf_path = Path(path)
        if not pdf_path.is_file():
            raise FileNotFoundError(pdf_path)

        self.close()
        self._doc = fitz.open(str(pdf_path))
        self.path = pdf_path

    def close(self):
        if self._doc:
            self._doc.close()
        self._doc = None
        self.path = None
        self._file_hash = None

    @property
    def is_open(self):
        return self._doc is not None

    @property
    def page_count(self):
        return self._doc.page_count if self._doc else 0

    def page(self, index):
        if not self._doc:
            raise RuntimeError("No PDF is open.")
        return self._doc[index]

    def page_text(self, index):
        """Extract the plain text of a single page."""
        return self.page(index).get_text().strip()

    @property
    def file_hash(self):
        """Stable id for the open file (sha1 of its bytes); used as document_id.
        Cached after first access."""
        if not self.path:
            return None
        if self._file_hash is None:
            self._file_hash = hashlib.sha1(self.path.read_bytes()).hexdigest()
        return self._file_hash
