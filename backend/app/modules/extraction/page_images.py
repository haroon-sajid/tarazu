"""Turn document bytes into page images for the vision model.

PyMuPDF renders PDFs with its own bundled MuPDF, so there is no poppler (or any
other system package) to install on the deploy box — which matters when the
deploy box is a fresh Alibaba Cloud ECS instance.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass

try:  # PyMuPDF >= 1.24 ships the `pymupdf` name; older builds only have `fitz`.
    import pymupdf
except ImportError:  # pragma: no cover - depends on the installed build
    import fitz as pymupdf

__all__ = [
    "PageImage",
    "image_bytes_to_page_image",
    "pdf_page_count",
    "pdf_to_page_images",
    "render_pdf_page",
]

#: PDF user space is 72 dpi, so this converts a target dpi into a render scale.
_PDF_BASE_DPI = 72.0

_MIME_BY_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"RIFF", "image/webp"),
)


@dataclass(frozen=True)
class PageImage:
    """One rendered page, ready to send to the vision model.

    `page` is 1-based, matching `Provenance.page` and what a human sees in a
    PDF viewer.
    """

    page: int
    content: bytes
    mime_type: str
    width: int
    height: int

    def as_data_url(self) -> str:
        """The `data:` URL form the OpenAI-compatible image content part wants."""
        encoded = base64.b64encode(self.content).decode("ascii")
        return f"data:{self.mime_type};base64,{encoded}"


def pdf_to_page_images(content: bytes, dpi: int = 200) -> list[PageImage]:
    """Render every page of a PDF to a PNG.

    Args:
        content: The raw PDF bytes.
        dpi: Render resolution. 200 is a good balance: high enough for the model
            to read a bank statement's small print, low enough that a 3-page
            statement stays well inside the request size limit.

    Returns:
        One `PageImage` per page, in document order, numbered from 1.

    Raises:
        ValueError: If the bytes are not a readable PDF, or it has no pages.
    """
    if dpi <= 0:
        raise ValueError("dpi must be positive")

    scale = dpi / _PDF_BASE_DPI
    matrix = pymupdf.Matrix(scale, scale)

    try:
        document = pymupdf.open(stream=content, filetype="pdf")
    except Exception as error:  # pymupdf raises several types for bad input
        raise ValueError(f"could not open the PDF: {error}") from error

    with document:
        if document.page_count == 0:
            raise ValueError("the PDF has no pages")
        pages: list[PageImage] = []
        for index in range(document.page_count):
            pixmap = document.load_page(index).get_pixmap(matrix=matrix, alpha=False)
            pages.append(
                PageImage(
                    page=index + 1,
                    content=pixmap.tobytes("png"),
                    mime_type="image/png",
                    width=pixmap.width,
                    height=pixmap.height,
                )
            )
    return pages


def pdf_page_count(content: bytes) -> int:
    """How many pages the PDF has. Raises `ValueError` if it is not one."""
    try:
        document = pymupdf.open(stream=content, filetype="pdf")
    except Exception as error:
        raise ValueError(f"could not open the PDF: {error}") from error
    with document:
        return document.page_count


def render_pdf_page(content: bytes, page: int, dpi: int = 110) -> PageImage:
    """Render one page of a PDF, for the evidence viewer.

    Renders only the page asked for — a viewer opening page 3 of a 40-page
    statement should not pay for the other 39. Lower dpi than the model gets by
    default, because a screen needs fewer pixels than a reader of small print.

    Raises:
        ValueError: Not a readable PDF, or `page` is outside 1..page_count.
    """
    if dpi <= 0:
        raise ValueError("dpi must be positive")
    try:
        document = pymupdf.open(stream=content, filetype="pdf")
    except Exception as error:
        raise ValueError(f"could not open the PDF: {error}") from error
    with document:
        if not 1 <= page <= document.page_count:
            raise ValueError(
                f"page {page} is out of range: the document has {document.page_count} page(s)"
            )
        scale = dpi / _PDF_BASE_DPI
        pixmap = document.load_page(page - 1).get_pixmap(
            matrix=pymupdf.Matrix(scale, scale), alpha=False
        )
        return PageImage(
            page=page,
            content=pixmap.tobytes("png"),
            mime_type="image/png",
            width=pixmap.width,
            height=pixmap.height,
        )


def image_bytes_to_page_image(content: bytes, page: int = 1) -> PageImage:
    """Wrap an already-image document (a photo of an invoice) as a `PageImage`.

    Raises:
        ValueError: If the bytes are not a supported image format.
    """
    for magic, mime_type in _MIME_BY_MAGIC:
        if content.startswith(magic):
            break
    else:
        raise ValueError("unsupported image format: expected PNG, JPEG, or WEBP")

    try:
        pixmap = pymupdf.Pixmap(content)
        width, height = pixmap.width, pixmap.height
    except Exception:  # pragma: no cover - dimensions are advisory only
        width = height = 0

    return PageImage(
        page=page, content=content, mime_type=mime_type, width=width, height=height
    )
