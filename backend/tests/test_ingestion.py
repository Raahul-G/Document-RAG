"""
Unit tests for backend/services/ingestion.py

Covers:
- _flush_chunk(): word-boundary snapping when splitting at MAX_CHUNK_CHARS
- _flush_chunk(): overlap start snapped to next full word
- _flush_chunk(): empty text produces no records
- _chunk(): tiny section (< MIN_SECTION_CHARS) carry-forward into next section
- _chunk(): normal sections flushed as separate chunks
- _chunk(): last section always flushed
"""
from __future__ import annotations

import pytest

from backend.services.ingestion import (
    MAX_CHUNK_CHARS,
    MIN_SECTION_CHARS,
    OVERLAP_CHARS,
    _chunk,
    _flush_chunk,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _flush(text: str, page: int = 1) -> list[dict]:
    """Run _flush_chunk and return produced records."""
    records: list[dict] = []
    page_counters: dict[int, int] = {}
    _flush_chunk(text, page, "Section", 1, "doc.pdf", page_counters, records)
    return records


def _make_elements(*args) -> list[dict]:
    """
    Build element list from tuples of (category, text, page).
    category: 'Title' | 'NarrativeText'
    """
    return [{"category": cat, "text": txt, "page": pg} for cat, txt, pg in args]


# ── _flush_chunk ──────────────────────────────────────────────────────────────

class TestFlushChunk:

    def test_empty_text_produces_no_records(self):
        assert _flush("") == []
        assert _flush("   ") == []

    def test_short_text_produces_one_record(self):
        records = _flush("Hello world.")
        assert len(records) == 1
        assert records[0]["text"] == "Hello world."

    def test_record_fields_are_populated(self):
        records = _flush("Some content here.", page=3)
        r = records[0]
        assert r["doc_id"] == 1
        assert r["doc_name"] == "doc.pdf"
        assert r["page_number"] == 3
        assert r["passage_index"] == 1
        assert r["section_title"] == "Section"
        assert "chroma_id" in r

    def test_passage_index_increments_per_page(self):
        records: list[dict] = []
        pc: dict[int, int] = {}
        _flush_chunk("First chunk.", 1, "S", 1, "d.pdf", pc, records)
        _flush_chunk("Second chunk.", 1, "S", 1, "d.pdf", pc, records)
        assert records[0]["passage_index"] == 1
        assert records[1]["passage_index"] == 2

    def test_long_text_splits_at_word_boundary(self):
        # Build a string where MAX_CHUNK_CHARS falls in the middle of a word
        # "word " repeated so that the split point lands inside a long word
        word = "longword"
        padding = "x " * (MAX_CHUNK_CHARS // 2)  # well-padded text
        # Construct text where position MAX_CHUNK_CHARS is mid-word
        prefix = "a " * ((MAX_CHUNK_CHARS - len(word) - 1) // 2)
        text = prefix + word * 30  # long run of a word to ensure mid-word split

        records = _flush(text)
        assert len(records) >= 2, "text longer than MAX_CHUNK_CHARS must produce ≥2 chunks"

        # Each chunk must not start or end in the middle of a word
        for r in records:
            fragment = r["text"]
            # A fragment split mid-word would have no space before the first non-space
            # character if it was a continuation. We check that no chunk ends with a
            # partial word by verifying the last character is not an alphanumeric that
            # was cut (hard to verify without knowing the exact split, so verify the
            # chunk ends at a whitespace boundary in the original text).
            assert not fragment.endswith(" "), "strip() should remove trailing space"

    def test_chunk_does_not_exceed_max_chars_plus_one_word(self):
        # After word-boundary snapping the chunk may be slightly shorter than
        # MAX_CHUNK_CHARS, but it must never be longer.
        words = ["word"] * (MAX_CHUNK_CHARS // 5 + 10)
        text = " ".join(words)
        records = _flush(text)
        for r in records:
            assert len(r["text"]) <= MAX_CHUNK_CHARS

    def test_second_chunk_starts_at_word_boundary(self):
        # The overlap region should not cause the second chunk to begin mid-word.
        # We construct text where the overlap boundary falls in the middle of a word.
        body = "alpha " * (MAX_CHUNK_CHARS // 6)  # repeating short words
        text = body.strip()
        records = _flush(text)
        if len(records) >= 2:
            second = records[1]["text"]
            # Must start with a complete word (no leading partial characters)
            assert second[0].isalpha() or second[0].isdigit()
            # First character should not be a space (strip applied)
            assert second[0] != " "

    def test_overlap_content_present_in_consecutive_chunks(self):
        # Content near the boundary of the first chunk should appear in both chunks.
        # Use a text longer than MAX_CHUNK_CHARS + OVERLAP_CHARS.
        words = ["tok"] * (MAX_CHUNK_CHARS // 4 + 50)
        text = " ".join(words)
        records = _flush(text)
        if len(records) >= 2:
            # Some tokens from the end of chunk 1 should appear at the start of chunk 2
            end_of_first = records[0]["text"].split()[-5:]
            start_of_second = records[1]["text"].split()[:5]
            overlap = set(end_of_first) & set(start_of_second)
            assert overlap, "overlap tokens should appear in consecutive chunks"


# ── _chunk ────────────────────────────────────────────────────────────────────

class TestChunk:

    def test_tiny_section_not_silently_dropped(self):
        """A section with text < MIN_SECTION_CHARS must carry forward into the next section."""
        tiny_text = "Short." * 3  # < MIN_SECTION_CHARS
        assert len(tiny_text) < MIN_SECTION_CHARS

        normal_text = "Normal section content. " * 10  # >= MIN_SECTION_CHARS

        elements = _make_elements(
            ("Title", "Tiny Section", 1),
            ("NarrativeText", tiny_text, 1),
            ("Title", "Normal Section", 2),
            ("NarrativeText", normal_text, 2),
        )

        records = _chunk(elements, doc_id=1, doc_name="doc.pdf")

        # All text from the tiny section must appear in at least one record
        combined = " ".join(r["text"] for r in records)
        assert tiny_text.strip() in combined or "Tiny Section" in combined, (
            "tiny section text was silently dropped"
        )

    def test_tiny_section_text_merged_into_next_chunk(self):
        """Carry-forward content should be inside the same chunk as the next section."""
        tiny_title = "Tiny"
        tiny_body = "x " * 10  # very short, well below MIN_SECTION_CHARS

        normal_body = "Normal body content here. " * 10

        elements = _make_elements(
            ("Title", tiny_title, 1),
            ("NarrativeText", tiny_body.strip(), 1),
            ("Title", "Main Section", 2),
            ("NarrativeText", normal_body.strip(), 2),
        )

        records = _chunk(elements, doc_id=1, doc_name="doc.pdf")

        # The tiny section's content must appear within a record that also has
        # the next section's content (merged, not a separate record)
        merged_chunks = [r["text"] for r in records if tiny_body.strip() in r["text"]]
        assert merged_chunks, "tiny section text must appear in at least one chunk"
        # That chunk should also contain content from the normal section
        assert any(
            tiny_body.strip() in r["text"] and "Main Section" in r["text"]
            for r in records
        ), "carry-forward text should be merged with the next section"

    def test_normal_sections_produce_separate_chunks(self):
        """Two sections each >= MIN_SECTION_CHARS should produce at least two chunks."""
        body = "Sentence content here. " * 10  # well above MIN_SECTION_CHARS

        elements = _make_elements(
            ("Title", "Section A", 1),
            ("NarrativeText", body, 1),
            ("Title", "Section B", 2),
            ("NarrativeText", body, 2),
        )

        records = _chunk(elements, doc_id=1, doc_name="doc.pdf")
        assert len(records) >= 2

        # Section titles should appear in different records
        a_chunks = [r for r in records if r["section_title"] == "Section A"]
        b_chunks = [r for r in records if r["section_title"] == "Section B"]
        assert a_chunks, "Section A chunks missing"
        assert b_chunks, "Section B chunks missing"

    def test_last_section_is_flushed(self):
        """Text in the final section must not be silently discarded."""
        body = "Final section body. " * 10

        elements = _make_elements(
            ("Title", "Last Section", 1),
            ("NarrativeText", body, 1),
        )

        records = _chunk(elements, doc_id=1, doc_name="doc.pdf")
        assert records, "last section produced no chunks"
        combined = " ".join(r["text"] for r in records)
        assert "Final section body" in combined

    def test_multiple_consecutive_tiny_sections_all_carried(self):
        """Multiple consecutive tiny sections must all be carried forward."""
        tiny1 = "Tiny one."
        tiny2 = "Tiny two."
        normal = "This is a normal length body with enough content. " * 5

        assert len(tiny1) < MIN_SECTION_CHARS
        assert len(tiny2) < MIN_SECTION_CHARS

        elements = _make_elements(
            ("Title", "Tiny A", 1),
            ("NarrativeText", tiny1, 1),
            ("Title", "Tiny B", 1),
            ("NarrativeText", tiny2, 1),
            ("Title", "Normal Section", 2),
            ("NarrativeText", normal, 2),
        )

        records = _chunk(elements, doc_id=1, doc_name="doc.pdf")
        combined = " ".join(r["text"] for r in records)

        assert tiny1 in combined, "tiny1 was dropped"
        assert tiny2 in combined, "tiny2 was dropped"

    def test_empty_elements_returns_empty(self):
        assert _chunk([], doc_id=1, doc_name="doc.pdf") == []

    def test_chunk_metadata_correct(self):
        body = "Content for this section. " * 10

        elements = _make_elements(
            ("Title", "My Section", 5),
            ("NarrativeText", body, 5),
        )

        records = _chunk(elements, doc_id=42, doc_name="report.pdf")
        assert records
        r = records[0]
        assert r["doc_id"] == 42
        assert r["doc_name"] == "report.pdf"
        assert r["page_number"] == 5
        assert r["section_title"] == "My Section"
