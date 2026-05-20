"""
Tests for backend/services/snippet.py and backend/routers/snippets.py
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# _make_search_phrase
# ---------------------------------------------------------------------------

class TestMakeSearchPhrase:

    def test_first_n_words(self):
        from backend.services.snippet import _make_search_phrase
        result = _make_search_phrase("one two three four five six seven eight", n=6)
        assert result == "one two three four five six"

    def test_newlines_treated_as_whitespace(self):
        from backend.services.snippet import _make_search_phrase
        result = _make_search_phrase("word1\nword2\nword3\nword4\nword5\nword6\nword7", n=6)
        assert result == "word1 word2 word3 word4 word5 word6"

    def test_empty_text(self):
        from backend.services.snippet import _make_search_phrase
        assert _make_search_phrase("", n=6) == ""

    def test_fewer_words_than_n(self):
        from backend.services.snippet import _make_search_phrase
        assert _make_search_phrase("only three words", n=6) == "only three words"

    def test_all_single_char_words_returns_empty(self):
        # All single-char words are too short to be reliable → returns empty
        from backend.services.snippet import _make_search_phrase
        assert _make_search_phrase("a b c d e f", n=6) == ""

    def test_skips_leading_fragment(self):
        # First word is a single char (chunk-boundary fragment); should skip it
        from backend.services.snippet import _make_search_phrase
        result = _make_search_phrase("d in order to best organize information clearly", n=6)
        assert result == "in order to best organize information"

    def test_short_phrase_returns_empty(self):
        # Even though words pass the length check, the joined phrase is too short
        from backend.services.snippet import _make_search_phrase
        assert _make_search_phrase("ab cd", n=6) == ""


# ---------------------------------------------------------------------------
# _word_level_search
# ---------------------------------------------------------------------------

class TestWordLevelSearch:

    def _make_page_mock(self, word_entries):
        """Build a mock fitz.Page whose get_text('words') returns *word_entries*."""
        page = MagicMock()
        page.get_text.return_value = word_entries
        return page

    def _make_word_entries(self, words):
        """Return minimal fitz word-list tuples for *words*."""
        return [
            (float(i * 50), 100.0, float(i * 50 + 40), 120.0, w, 0, 0, i)
            for i, w in enumerate(words)
        ]

    def test_exact_match_returns_rects(self):
        import fitz
        from backend.services.snippet import _word_level_search
        entries = self._make_word_entries(["The", "quick", "brown", "fox", "jumps", "over"])
        page = self._make_page_mock(entries)
        rects = _word_level_search(page, "quick brown fox jumps")
        assert len(rects) == 4
        assert all(isinstance(r, fitz.Rect) for r in rects)

    def test_case_insensitive_match(self):
        from backend.services.snippet import _word_level_search
        entries = self._make_word_entries(["Tables", "Tabulated", "information", "has", "been"])
        page = self._make_page_mock(entries)
        rects = _word_level_search(page, "tables tabulated information")
        assert len(rects) == 3

    def test_no_match_returns_empty(self):
        from backend.services.snippet import _word_level_search
        entries = self._make_word_entries(["hello", "world"])
        page = self._make_page_mock(entries)
        assert _word_level_search(page, "foo bar baz") == []

    def test_empty_phrase_returns_empty(self):
        from backend.services.snippet import _word_level_search
        entries = self._make_word_entries(["hello", "world"])
        page = self._make_page_mock(entries)
        assert _word_level_search(page, "") == []

    def test_empty_word_list_returns_empty(self):
        from backend.services.snippet import _word_level_search
        page = self._make_page_mock([])
        assert _word_level_search(page, "some phrase here") == []


# ---------------------------------------------------------------------------
# render_page_png (DB-level errors)
# ---------------------------------------------------------------------------

class TestRenderPagePngErrors:

    def _mock_db(self, doc=None):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = doc
        return db

    def test_doc_not_found_raises(self):
        from backend.services.snippet import SnippetError, render_page_png
        db = self._mock_db(doc=None)
        with pytest.raises(SnippetError, match="not found"):
            render_page_png("missing.pdf", 1, "some text", db)

    def test_docx_raises_snippet_error(self):
        from backend.services.snippet import SnippetError, render_page_png
        doc = MagicMock()
        doc.file_type = "docx"
        doc.filename = "test.docx"
        db = self._mock_db(doc=doc)
        with pytest.raises(SnippetError, match="(?i)only supported for pdf"):
            render_page_png("test.docx", 1, "some text", db)

    def test_passage_index_lookup_uses_chunk_text(self):
        """When passage_index is supplied, stored chunk text replaces the caller's text."""
        from backend.services.snippet import render_page_png

        doc = MagicMock()
        doc.id = 1
        doc.file_type = "pdf"
        doc.filename = "doc.pdf"

        chunk = MagicMock()
        chunk.text = "The real stored chunk text from the database"

        db = MagicMock()

        def mock_query(model):
            m = MagicMock()
            from backend.models import Document, Chunk as ChunkModel
            if model is Document:
                m.filter.return_value.first.return_value = doc
            else:  # Chunk — single .filter(...) with multiple conditions
                m.filter.return_value.first.return_value = chunk
            return m

        db.query.side_effect = mock_query

        with patch("backend.services.snippet._render_cached") as mock_render:
            mock_render.return_value = b"\x89PNG\r\n\x1a\n"
            render_page_png("doc.pdf", 5, "LLM-paraphrased text", db, passage_index=2)
            # _render_cached must be called with the chunk's real text, not the paraphrased one
            mock_render.assert_called_once_with("doc.pdf", 4, chunk.text)


# ---------------------------------------------------------------------------
# _render_cached (mocked fitz)
# ---------------------------------------------------------------------------

class TestRenderCached:

    def _make_fitz_mocks(self, page_count=5, search_rects=None):
        """Build a fake fitz document/page hierarchy."""
        mock_page = MagicMock()
        mock_page.search_for.return_value = search_rects if search_rects is not None else []
        # word-level fallback: return empty word list by default
        mock_page.get_text.return_value = []
        mock_annot = MagicMock()
        mock_page.add_highlight_annot.return_value = mock_annot
        mock_pixmap = MagicMock()
        mock_pixmap.tobytes.return_value = b"\x89PNG\r\n\x1a\n"  # minimal PNG header
        mock_page.get_pixmap.return_value = mock_pixmap

        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=page_count)
        mock_doc.__getitem__ = MagicMock(return_value=mock_page)

        return mock_doc, mock_page, mock_annot

    def test_returns_png_bytes(self, tmp_path):
        from backend.services.snippet import _render_cached
        _render_cached.cache_clear()

        mock_doc, mock_page, _ = self._make_fitz_mocks(search_rects=[MagicMock()])

        with patch("backend.services.snippet.fitz.open", return_value=mock_doc), \
             patch("backend.services.snippet.Path") as mock_path_cls:
            mock_path_cls.return_value.__truediv__ = lambda s, o: tmp_path / o
            result = _render_cached("test.pdf", 0, "search phrase here in document")

        assert result == b"\x89PNG\r\n\x1a\n"
        _render_cached.cache_clear()

    def test_highlight_added_when_search_matches(self, tmp_path):
        from backend.services.snippet import _render_cached
        _render_cached.cache_clear()

        fake_rect = MagicMock()
        mock_doc, mock_page, mock_annot = self._make_fitz_mocks(search_rects=[fake_rect])

        with patch("backend.services.snippet.fitz.open", return_value=mock_doc), \
             patch("backend.services.snippet.Path") as mock_path_cls:
            mock_path_cls.return_value.__truediv__ = lambda s, o: tmp_path / o
            # passage_text must yield a phrase >= 15 chars with first word >= 2 chars
            _render_cached("test2.pdf", 0, "some meaningful text to highlight in document")

        mock_page.add_highlight_annot.assert_called_once_with([fake_rect])
        mock_annot.set_colors.assert_called_once_with({"stroke": [1.0, 0.95, 0.0]})
        _render_cached.cache_clear()

    def test_no_highlight_when_search_empty(self, tmp_path):
        from backend.services.snippet import _render_cached
        _render_cached.cache_clear()

        mock_doc, mock_page, _ = self._make_fitz_mocks(search_rects=[])

        with patch("backend.services.snippet.fitz.open", return_value=mock_doc), \
             patch("backend.services.snippet.Path") as mock_path_cls:
            mock_path_cls.return_value.__truediv__ = lambda s, o: tmp_path / o
            _render_cached("test3.pdf", 0, "")

        mock_page.add_highlight_annot.assert_not_called()
        _render_cached.cache_clear()

    def test_page_out_of_range_raises(self, tmp_path):
        from backend.services.snippet import SnippetError, _render_cached
        _render_cached.cache_clear()

        mock_doc, _, _ = self._make_fitz_mocks(page_count=3)

        with patch("backend.services.snippet.fitz.open", return_value=mock_doc), \
             patch("backend.services.snippet.Path") as mock_path_cls:
            mock_path_cls.return_value.__truediv__ = lambda s, o: tmp_path / o
            with pytest.raises(SnippetError, match="out of range"):
                _render_cached("test4.pdf", 99, "text")

        _render_cached.cache_clear()

    def test_word_level_fallback_used_when_search_for_fails(self, tmp_path):
        """When search_for returns nothing, word-level fallback is tried."""
        from backend.services.snippet import _render_cached
        _render_cached.cache_clear()

        import fitz as real_fitz
        fake_rect = real_fitz.Rect(0, 0, 50, 20)

        mock_doc, mock_page, mock_annot = self._make_fitz_mocks(search_rects=[])
        # search_for returns nothing; word-level returns a rect
        mock_page.get_text.return_value = [
            (0.0, 0.0, 40.0, 20.0, "some", 0, 0, 0),
            (50.0, 0.0, 100.0, 20.0, "meaningful", 0, 0, 1),
            (110.0, 0.0, 160.0, 20.0, "text", 0, 0, 2),
            (170.0, 0.0, 200.0, 20.0, "to", 0, 0, 3),
            (210.0, 0.0, 270.0, 20.0, "highlight", 0, 0, 4),
            (280.0, 0.0, 300.0, 20.0, "in", 0, 0, 5),
            (310.0, 0.0, 380.0, 20.0, "document", 0, 0, 6),
        ]

        with patch("backend.services.snippet.fitz.open", return_value=mock_doc), \
             patch("backend.services.snippet.Path") as mock_path_cls:
            mock_path_cls.return_value.__truediv__ = lambda s, o: tmp_path / o
            _render_cached("test5.pdf", 0, "some meaningful text to highlight in document")

        # highlight was added (via word-level fallback)
        mock_page.add_highlight_annot.assert_called_once()
        _render_cached.cache_clear()


# ---------------------------------------------------------------------------
# HTTP router tests
# ---------------------------------------------------------------------------

class TestSnippetRouter:

    def _get_client(self):
        from backend.main import app
        return TestClient(app)

    def test_404_when_doc_not_found(self):
        client = self._get_client()
        with patch("backend.routers.snippets.render_page_png") as mock_render:
            from backend.services.snippet import SnippetError
            mock_render.side_effect = SnippetError("Document not found: 'ghost.pdf'")
            resp = client.get("/api/snippets/render?doc_name=ghost.pdf&page=1&text=hello")
        assert resp.status_code == 404

    def test_501_for_docx(self):
        client = self._get_client()
        with patch("backend.routers.snippets.render_page_png") as mock_render:
            from backend.services.snippet import SnippetError
            mock_render.side_effect = SnippetError("Snippet rendering is only supported for PDF files (got 'docx')")
            resp = client.get("/api/snippets/render?doc_name=report.docx&page=1")
        assert resp.status_code == 501

    def test_200_returns_png(self):
        client = self._get_client()
        png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        with patch("backend.routers.snippets.render_page_png", return_value=png_bytes):
            resp = client.get("/api/snippets/render?doc_name=doc.pdf&page=3&text=some+text")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
        assert resp.content == png_bytes

    def test_200_with_passage_index(self):
        client = self._get_client()
        png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        with patch("backend.routers.snippets.render_page_png", return_value=png_bytes) as mock_render:
            resp = client.get("/api/snippets/render?doc_name=doc.pdf&page=3&text=some+text&passage_index=2")
        assert resp.status_code == 200
        # passage_index must be forwarded to the service
        mock_render.assert_called_once()
        _, kwargs = mock_render.call_args
        assert kwargs.get("passage_index") == 2

    def test_422_missing_required_params(self):
        client = self._get_client()
        resp = client.get("/api/snippets/render")
        assert resp.status_code == 422

    def test_422_page_less_than_1(self):
        client = self._get_client()
        resp = client.get("/api/snippets/render?doc_name=doc.pdf&page=0")
        assert resp.status_code == 422

    def test_422_passage_index_less_than_1(self):
        client = self._get_client()
        resp = client.get("/api/snippets/render?doc_name=doc.pdf&page=1&passage_index=0")
        assert resp.status_code == 422
