"""deterministic_zip / deterministic_xlsx: equal content, equal bytes.

The volatile parts are produced on purpose here — different entry times, a different
creating system, a different entry order, "now" in docProps/core.xml — instead of waiting
two seconds between two writes and hoping the clock ticked.
"""

from __future__ import annotations

import hashlib
import io
import zipfile

import pytest

from partest.files import (
    FIXED_CORE_TIMESTAMP,
    FIXED_ZIP_TIME,
    deterministic_xlsx,
    deterministic_zip,
    minimal_xlsx_bytes,
)

CORE = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
    'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
    'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
    "<dc:creator>generator</dc:creator>"
    '<dcterms:created xsi:type="dcterms:W3CDTF">{created}</dcterms:created>'
    '<dcterms:modified xsi:type="dcterms:W3CDTF">{modified}</dcterms:modified>'
    "<cp:lastPrinted>{created}</cp:lastPrinted>"
    "</cp:coreProperties>"
)


def package(entries, *, when=(2026, 10, 7, 12, 0, 0), system=0, comment=b""):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.comment = comment
        for name, data in entries:
            info = zipfile.ZipInfo(name, date_time=when)
            info.create_system = system
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, data)
    return buffer.getvalue()


def workbook(*, created, modified, reverse=False, when=(2026, 10, 7, 12, 0, 0), system=0):
    with zipfile.ZipFile(io.BytesIO(minimal_xlsx_bytes())) as zf:
        entries = [(i.filename, zf.read(i.filename)) for i in zf.infolist()]
    entries.append(("docProps/core.xml", CORE.format(created=created, modified=modified)))
    if reverse:
        entries.reverse()
    return package(entries, when=when, system=system)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_two_writes_of_the_same_workbook_get_one_checksum():
    first = workbook(created="2026-10-07T10:00:00Z", modified="2026-10-07T10:00:01Z")
    second = workbook(
        created="2026-10-08T23:59:59Z",
        modified="2026-10-09T00:00:00Z",
        reverse=True,
        when=(2030, 1, 2, 3, 4, 6),
        system=3,
    )
    assert sha(first) != sha(second)
    assert sha(deterministic_xlsx(first)) == sha(deterministic_xlsx(second))


def test_core_dates_are_fixed_and_nothing_else_in_the_part_changes():
    out = deterministic_xlsx(workbook(created="2026-10-07T10:00:00Z", modified="2026-10-07T11:00:00Z"))
    with zipfile.ZipFile(io.BytesIO(out)) as zf:
        core = zf.read("docProps/core.xml").decode("utf-8")
    assert core == CORE.format(created=FIXED_CORE_TIMESTAMP, modified=FIXED_CORE_TIMESTAMP)
    assert "<dc:creator>generator</dc:creator>" in core


def test_entries_are_sorted_with_the_manifest_first_and_times_fixed():
    out = deterministic_xlsx(workbook(created="x", modified="y", reverse=True))
    with zipfile.ZipFile(io.BytesIO(out)) as zf:
        infos = zf.infolist()
        assert zf.testzip() is None
    names = [i.filename for i in infos]
    assert names[0] == "[Content_Types].xml"
    assert names[1:] == sorted(names[1:])
    assert {i.date_time for i in infos} == {FIXED_ZIP_TIME}
    assert {i.create_system for i in infos} == {3}


def test_content_survives_the_repack():
    original = workbook(created="a", modified="b")
    with zipfile.ZipFile(io.BytesIO(original)) as zf:
        before = {i.filename: zf.read(i.filename) for i in zf.infolist() if i.filename != "docProps/core.xml"}
    with zipfile.ZipFile(io.BytesIO(deterministic_xlsx(original))) as zf:
        after = {i.filename: zf.read(i.filename) for i in zf.infolist() if i.filename != "docProps/core.xml"}
    assert before == after


def test_repacking_is_idempotent():
    once = deterministic_xlsx(workbook(created="a", modified="b"))
    assert deterministic_xlsx(once) == once


def test_deterministic_zip_leaves_entry_content_alone():
    raw = workbook(created="2026-10-07T10:00:00Z", modified="2026-10-07T10:00:00Z")
    with zipfile.ZipFile(io.BytesIO(deterministic_zip(raw))) as zf:
        assert b"2026-10-07T10:00:00Z" in zf.read("docProps/core.xml")


def test_stored_compression_for_a_checksum_across_zlib_builds():
    out = deterministic_zip(package([("b.txt", "bb"), ("a.txt", "aa")]), compression=zipfile.ZIP_STORED)
    with zipfile.ZipFile(io.BytesIO(out)) as zf:
        assert [i.filename for i in zf.infolist()] == ["a.txt", "b.txt"]
        assert {i.compress_type for i in zf.infolist()} == {zipfile.ZIP_STORED}
    # Stored entries put the content into the archive verbatim.
    assert b"aa" in out and b"bb" in out


def test_odf_mimetype_stays_first_and_uncompressed():
    raw = package([("content.xml", "<x/>"), ("mimetype", "application/vnd.oasis.opendocument.spreadsheet")])
    with zipfile.ZipFile(io.BytesIO(deterministic_zip(raw))) as zf:
        first = zf.infolist()[0]
    assert first.filename == "mimetype"
    assert first.compress_type == zipfile.ZIP_STORED


def test_comment_and_directories_are_normalised():
    a = package([("dir/", ""), ("dir/f.txt", "x")], comment=b"built on host A")
    b = package([("dir/", ""), ("dir/f.txt", "x")], comment=b"built on host B", system=3)
    assert deterministic_zip(a) == deterministic_zip(b)
    with zipfile.ZipFile(io.BytesIO(deterministic_zip(a))) as zf:
        assert zf.comment == b""
        assert zf.getinfo("dir/").is_dir()


def test_not_a_zip_is_an_error_not_a_silent_pass_through():
    with pytest.raises(zipfile.BadZipFile):
        deterministic_zip(b"not a zip at all")


def test_the_upload_corpus_is_untouched():
    """Additive: the existing byte factories still build their archives as before."""
    with zipfile.ZipFile(io.BytesIO(minimal_xlsx_bytes())) as zf:
        assert [i.filename for i in zf.infolist()] == [
            "[Content_Types].xml",
            "_rels/.rels",
            "xl/workbook.xml",
        ]


def test_a_real_openpyxl_workbook_saved_twice():
    """Optional: only where openpyxl is installed; partest does not depend on it."""
    openpyxl = pytest.importorskip("openpyxl")
    import datetime

    def save(moment):
        wb = openpyxl.Workbook()
        wb.active["A1"] = "value"
        wb.properties.created = moment
        wb.properties.modified = moment
        buffer = io.BytesIO()
        wb.save(buffer)
        return buffer.getvalue()

    first = save(datetime.datetime(2026, 10, 7, 10, 0, 0))
    second = save(datetime.datetime(2027, 1, 1, 0, 0, 0))
    assert first != second
    assert deterministic_xlsx(first) == deterministic_xlsx(second)


# --- review: defaults, limits, permissions ---------------------------------------


def test_entries_are_stored_by_default_so_the_checksum_needs_no_zlib():
    """zlib and zlib-ng deflate differently; stored bytes depend on the content alone."""
    out = deterministic_xlsx(workbook(created="a", modified="b"))
    with zipfile.ZipFile(io.BytesIO(out)) as zf:
        assert {i.compress_type for i in zf.infolist()} == {zipfile.ZIP_STORED}
    deflated = deterministic_xlsx(workbook(created="a", modified="b"), compression=zipfile.ZIP_DEFLATED)
    with zipfile.ZipFile(io.BytesIO(deflated)) as zf:
        assert {i.compress_type for i in zf.infolist()} == {zipfile.ZIP_DEFLATED}
    assert deterministic_xlsx(deflated) == out  # same content, same stored bytes


def test_source_permissions_never_reach_the_output():
    def archive(mode):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            info = zipfile.ZipInfo("a.txt", date_time=(2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = mode << 16
            zf.writestr(info, "x")
        return buffer.getvalue()

    executable, private = deterministic_zip(archive(0o100755)), deterministic_zip(archive(0o100600))
    assert executable == private
    with zipfile.ZipFile(io.BytesIO(executable)) as zf:
        assert zf.getinfo("a.txt").external_attr == 0o100644 << 16


def test_a_decompression_bomb_is_refused_without_inflating_it():
    bomb = io.BytesIO()
    with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("zeros.bin", b"\0" * (8 * 1024 * 1024))
    assert len(bomb.getvalue()) < 64 * 1024
    with pytest.raises(ValueError, match="inflates beyond"):
        deterministic_zip(bomb.getvalue(), max_entry_size=1024 * 1024)
    with pytest.raises(ValueError, match="inflates beyond"):
        deterministic_zip(bomb.getvalue(), max_total_size=1024 * 1024)


def test_too_many_entries_are_refused():
    many = package([(f"f{i}.txt", "x") for i in range(20)])
    with pytest.raises(ValueError, match="max_entries"):
        deterministic_zip(many, max_entries=10)


def test_a_pathological_core_part_is_handled_in_linear_time():
    import time

    hostile = (
        b"<cp:coreProperties>"
        + b"<dcterms:created " * 20000
        + b"x" * 200000
        + b"<dcterms:modified>" + b"y" * 100000
        + b"</cp:coreProperties>"
    )
    raw = package([("[Content_Types].xml", "<Types/>"), ("docProps/core.xml", hostile)])
    started = time.perf_counter()
    out = deterministic_xlsx(raw)
    assert time.perf_counter() - started < 2.0
    with zipfile.ZipFile(io.BytesIO(out)) as zf:
        assert zf.read("docProps/core.xml") == hostile  # nothing matched, nothing changed
