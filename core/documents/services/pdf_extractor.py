"""
PDF text extraction.

A small, focused service: open a PDF and return its text grouped by
page. Nothing here knows about chunking, embeddings, Celery, or the
Document model — it takes a file-like object in and returns plain
data out, so it can be called equally from a view, a shell, or (later)
a Celery task.
"""
import logging

import pymupdf
from django.core.files.base import File

logger = logging.getLogger(__name__)


class PDFExtractionError(Exception):
    """
    Raised when a PDF cannot be opened or read.

    Wraps whatever PyMuPDF (or the underlying file object) raised, so
    callers only ever need to handle one predictable exception type
    instead of depending on PyMuPDF's own exception hierarchy.
    """


def extract_text_by_page(file: File) -> list[dict]:
    """
    Extract text from a PDF, one entry per page.

    `file` is any Django File-like object — a Document's `.file`
    (FieldFile), an uploaded file, or a plain binary file object.
    Its bytes are read directly and handed to PyMuPDF as a stream, so
    this works regardless of storage backend and never touches a
    filesystem path.

    Returns a list of ``{"page_number": <1-based int>, "text": <str>}``,
    one entry per page, in page order. A page with no extractable
    text (e.g. a scanned image with no text layer) yields an empty
    string, not a missing entry — page numbering is never skipped.

    Raises ``PDFExtractionError`` if the file cannot be opened as a
    PDF at all.
    """
    file_bytes = _read_bytes(file)

    try:
        with pymupdf.open(stream=file_bytes, filetype="pdf") as document:
            return [
                {
                    "page_number": page_number,
                    "text": _clean_text(page.get_text("text", sort=True)),
                }
                for page_number, page in enumerate(document, start=1)
            ]
    except Exception as exc:
        logger.exception("Failed to extract text from PDF")
        raise PDFExtractionError("The file could not be read as a PDF.") from exc


def _read_bytes(file: File) -> bytes:
    """
    Reads the full content of a Django File-like object as bytes.

    Handles both already-open files (e.g. a freshly uploaded file
    still attached to the current request) and closed ones (e.g. a
    Document's FieldFile re-loaded outside a request, such as from a
    future Celery task) — opening and closing it ourselves only in
    the latter case, so we never leave a caller's file handle in a
    different state than we found it.
    """
    opened_here = False
    if hasattr(file, "closed") and file.closed:
        file.open("rb")
        opened_here = True

    try:
        if hasattr(file, "seek"):
            file.seek(0)
        return file.read()
    finally:
        if opened_here:
            file.close()


def _clean_text(text: str) -> str:
    """
    Minimal, non-destructive cleanup: trims trailing whitespace from
    each line and collapses runs of 2+ blank lines down to one. Does
    not reflow paragraphs, strip punctuation, or otherwise rewrite
    the extracted content.
    """
    if not text:
        return ""

    cleaned_lines = []
    previous_was_blank = False
    for line in text.splitlines():
        line = line.rstrip()
        if line == "":
            if previous_was_blank:
                continue
            previous_was_blank = True
        else:
            previous_was_blank = False
        cleaned_lines.append(line)

    return "\n".join(cleaned_lines).strip()