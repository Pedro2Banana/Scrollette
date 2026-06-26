import fitz
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter


class PdfRenderer:
    """Render PDF pages into Qt images."""

    @staticmethod
    def render_page(page, zoom):
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
        return image.copy()

    @staticmethod
    def combine(images, gap=12):
        if len(images) == 1:
            return images[0]

        height = max(image.height() for image in images)
        width = sum(image.width() for image in images) + gap * (len(images) - 1)
        canvas = QImage(width, height, QImage.Format_RGB888)
        canvas.fill(Qt.white)

        painter = QPainter(canvas)
        x = 0
        for image in images:
            painter.drawImage(x, 0, image)
            x += image.width() + gap
        painter.end()
        return canvas
