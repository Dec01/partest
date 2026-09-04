"""Byte factories and a mutation corpus for upload endpoints.

Testing an upload has two separate loops and mixing them wastes days:

* the **gate** — the synchronous HTTP response: is the file accepted at all
  (extension, MIME, size, part name, parent id, authentication);
* the **pipeline** — whatever happens afterwards in a worker, an object store or a
  broker: was the content actually parsed and persisted.

A 201 from the gate is not "the file was imported", and a 400 on a `.txt` is not "the
parser rejected the columns". Everything here belongs to the first loop.

Files are generated, never committed: real workbooks tend to carry real data, and a
repository is the wrong place for it. Only the standard library is used.

Deliberately absent: zip bombs, exploit payloads, macros with a payload. A corpus that
can take a stand down is not a test corpus.
"""

from __future__ import annotations

import io
import zipfile
from typing import List, NamedTuple, Optional, Sequence

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
XLS_MIME = "application/vnd.ms-excel"

_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-'
    'officedocument.spreadsheetml.sheet.main+xml"/>'
    "</Types>"
)
_ROOT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
    'relationships/officeDocument" Target="xl/workbook.xml"/>'
    "</Relationships>"
)
_WORKBOOK = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
    '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/></sheets>'
    "</workbook>"
)


def minimal_xlsx_bytes() -> bytes:
    """A structurally valid, empty XLSX package.

    Enough for a gate that inspects the container. Not enough for a parser expecting a
    particular sheet layout — generate that in the project, where the layout is known.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _CONTENT_TYPES)
        zf.writestr("_rels/.rels", _ROOT_RELS)
        zf.writestr("xl/workbook.xml", _WORKBOOK)
    return buffer.getvalue()


def minimal_ole_xls_bytes() -> bytes:
    """OLE compound-document header — what a legacy ``.xls`` starts with."""
    header = bytes([0xD0, 0xCF, 0x11, 0xE0, 0xA1, 0xB1, 0x1A, 0xE1])
    return header + b"\x00" * 504


def png_bytes() -> bytes:
    """PNG magic plus a stub body, for content-versus-name mismatch."""
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def pdf_bytes() -> bytes:
    return b"%PDF-1.4\n" + b"\x00" * 64 + b"\n%%EOF\n"


def empty_zip_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w"):
        pass
    return buffer.getvalue()


def zip_without_content_types() -> bytes:
    """A zip that is not an OOXML package: the manifest part is missing."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("xl/workbook.xml", _WORKBOOK)
    return buffer.getvalue()


def truncated_zip_bytes(keep: int = 128) -> bytes:
    """A valid package cut short — the central directory never arrives."""
    return minimal_xlsx_bytes()[:keep]


def zip_with_extra_part() -> bytes:
    """A valid package carrying one part more than the format needs."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _CONTENT_TYPES)
        zf.writestr("_rels/.rels", _ROOT_RELS)
        zf.writestr("xl/workbook.xml", _WORKBOOK)
        zf.writestr("xl/vbaProject.bin", b"\x00" * 32)
    return buffer.getvalue()


class UploadCase(NamedTuple):
    """One file mutation.

    ``gate_expect`` is a hint, not an assertion:

    * ``accept`` — a gate that works should take this;
    * ``reject`` — a gate that works should refuse it;
    * ``fact`` — genuinely depends on the product. Record what the API does and put
      the answer in the suite; do not guess a status code, and do not file a bug
      merely because a gate checks the extension only.
    """

    id: str
    filename: str
    content: bytes
    content_type: Optional[str]
    gate_expect: str

    @property
    def files_kwarg(self) -> dict:
        """Shape for ``ApiClient.make_request(files=...)`` with a single part."""
        return {"file": (self.filename, self.content, self.content_type)}


def format_cases(stem: str = "report", *, allowed: Sequence[str] = (".xlsx", ".xls")) -> List[UploadCase]:
    """Extension handling: the allow-list, its neighbours, and disguises."""
    cases: List[UploadCase] = []
    for ext in allowed:
        content = minimal_ole_xls_bytes() if ext == ".xls" else minimal_xlsx_bytes()
        mime = XLS_MIME if ext == ".xls" else XLSX_MIME
        cases.append(UploadCase(f"allowed{ext}", f"{stem}{ext}", content, mime, "accept"))

    cases += [
        UploadCase("neighbour-csv", f"{stem}.csv", b"a,b\n1,2\n", "text/csv", "reject"),
        UploadCase("neighbour-ods", f"{stem}.ods", empty_zip_bytes(),
                   "application/vnd.oasis.opendocument.spreadsheet", "reject"),
        UploadCase("no-extension", stem, minimal_xlsx_bytes(), XLSX_MIME, "reject"),
        UploadCase("double-extension", f"{stem}.xlsx.exe", minimal_xlsx_bytes(),
                   "application/octet-stream", "reject"),
        UploadCase("uppercase-extension", f"{stem}.XLSX", minimal_xlsx_bytes(), XLSX_MIME, "fact"),
    ]
    return cases


def spoof_cases(stem: str = "report") -> List[UploadCase]:
    """Content that disagrees with the name.

    Every one of these is ``fact``: a gate checking only the extension accepts them all,
    and that is a legitimate design when a downstream parser does the real validation.
    Establish what your API does, write it down, and say in the report that this covers
    the gate rather than the parser.
    """
    return [
        UploadCase("png-named-xlsx", f"{stem}.xlsx", png_bytes(), XLSX_MIME, "fact"),
        UploadCase("pdf-named-xlsx", f"{stem}.xlsx", pdf_bytes(), XLSX_MIME, "fact"),
        UploadCase("xlsx-named-txt", f"{stem}.txt", minimal_xlsx_bytes(), "text/plain", "reject"),
        UploadCase("ole-named-xlsx", f"{stem}.xlsx", minimal_ole_xls_bytes(), XLSX_MIME, "fact"),
        UploadCase("zip-no-manifest", f"{stem}.xlsx", zip_without_content_types(), XLSX_MIME, "fact"),
        UploadCase("truncated-zip", f"{stem}.xlsx", truncated_zip_bytes(), XLSX_MIME, "fact"),
        UploadCase("empty-zip", f"{stem}.xlsx", empty_zip_bytes(), XLSX_MIME, "fact"),
        UploadCase("extra-zip-part", f"{stem}.xlsx", zip_with_extra_part(), XLSX_MIME, "fact"),
    ]


def filename_cases(stem: str = "report", *, long_length: int = 300) -> List[UploadCase]:
    """Names that try to escape, confuse or overflow.

    No NUL byte: that breaks the HTTP client before the server ever sees it, which
    tests nothing.
    """
    content, mime = minimal_xlsx_bytes(), XLSX_MIME
    return [
        UploadCase("traversal-unix", f"../../{stem}.xlsx", content, mime, "fact"),
        UploadCase("traversal-windows", f"..\\..\\{stem}.xlsx", content, mime, "fact"),
        UploadCase("embedded-dots", f"{stem}..name.xlsx", content, mime, "fact"),
        UploadCase("unicode", f"отчёт-{stem}.xlsx", content, mime, "accept"),
        UploadCase("very-long", f"{stem * (long_length // len(stem) + 1)}"[:long_length] + ".xlsx",
                   content, mime, "fact"),
    ]


def size_cases(stem: str = "report", *, modest_kb: int = 64) -> List[UploadCase]:
    """Empty and a modest payload.

    No over-limit case: send one only when a limit is actually documented. Hammering a
    stand with a huge body to discover a limit nobody wrote down produces a flaky test
    and an angry platform team — raise the question instead.
    """
    padded = minimal_xlsx_bytes() + b"\x00" * (modest_kb * 1024)
    return [
        UploadCase("empty-file", f"{stem}.xlsx", b"", XLSX_MIME, "reject"),
        UploadCase("modest-size", f"{stem}.xlsx", padded, XLSX_MIME, "accept"),
    ]


def mutation_cases(stem: str = "report", *, allowed: Sequence[str] = (".xlsx", ".xls")) -> List[UploadCase]:
    """The whole gate corpus: formats, spoofed content, names, sizes."""
    return format_cases(stem, allowed=allowed) + spoof_cases(stem) + filename_cases(stem) + size_cases(stem)


__all__ = [
    "XLSX_MIME",
    "XLS_MIME",
    "UploadCase",
    "empty_zip_bytes",
    "filename_cases",
    "format_cases",
    "minimal_ole_xls_bytes",
    "minimal_xlsx_bytes",
    "mutation_cases",
    "pdf_bytes",
    "png_bytes",
    "size_cases",
    "spoof_cases",
    "truncated_zip_bytes",
    "zip_with_extra_part",
    "zip_without_content_types",
]
