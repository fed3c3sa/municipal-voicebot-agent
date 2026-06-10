"""Unit tests for retrieval helpers and the Italian answer formatting."""

from __future__ import annotations

from municipal_mcp.models import SearchResult
from municipal_mcp.retrieval import should_use_vector
from municipal_mcp.tools.documentation import format_results


def _result(content: str, title: str = "Documento", heading: str | None = None) -> SearchResult:
    return SearchResult(
        score=1.0,
        content=content,
        heading_path=heading,
        chunk_index=0,
        full_text=None,
        title=title,
        category=None,
        source_url=None,
        doc_date=None,
    )


def test_vector_arm_disabled_when_alpha_zero():
    assert should_use_vector(0.0, True) is False


def test_vector_arm_disabled_when_flag_off():
    assert should_use_vector(0.8, False) is False


def test_vector_arm_enabled_when_weight_and_flag():
    assert should_use_vector(0.5, True) is True


def test_format_results_empty_is_italian():
    message = format_results([])
    assert "Non ho trovato" in message
    assert "0432 824500" in message


def test_format_results_lists_passages_with_section():
    results = [_result("Il costo e' di 22,21 euro.", title="CIE", heading="CIE > Costi")]
    message = format_results(results)
    assert "CIE" in message
    assert "Costi" in message
    assert "22,21" in message
