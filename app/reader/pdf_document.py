from pathlib import Path

import fitz


class PdfDocument:
    """Small wrapper around PyMuPDF's document object."""

    def __init__(self):
        self.path: Path | None = None
        self._doc: fitz.Document | None = None

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
