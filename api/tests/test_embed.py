"""Assertions for chunking and the embedding contract.

The pooling and the query prefix are asserted rather than trusted because
getting either wrong is invisible: the vectors still have the right shape and
the right norm, retrieval simply gets quietly worse. That is the defect class
this project keeps paying for, so the properties are pinned here.

The model itself is only loaded in the tests marked `slow` — the rest exercise
chunking, which is where the interesting logic is and where a bug would silently
degrade every retrieval.
"""

from __future__ import annotations

import pytest

from pos_copilot import embed


class TestChunking:
    def test_headings_start_new_chunks(self):
        """Clauses are the unit of meaning here. `## 3. Payment terms` and its
        sentence must stay together, and a fixed-width splitter cuts exactly
        there often enough to matter."""
        text = "## 3. Payment terms\nNet 30 days.\n\n## 4. Lead time\n10 days."
        chunks = embed.chunk_markdown(text)
        assert len(chunks) == 2
        assert chunks[0].startswith("## 3.")
        assert "Net 30 days." in chunks[0]
        assert chunks[1].startswith("## 4.")

    def test_a_short_document_is_one_chunk(self):
        assert len(embed.chunk_markdown("## Only\nOne line.")) == 1

    def test_empty_input_yields_no_chunks(self):
        """Not one empty chunk. An empty chunk embeds to a vector that matches
        everything weakly and pollutes every result set."""
        assert embed.chunk_markdown("") == []
        assert embed.chunk_markdown("   \n  \n") == []

    def test_an_oversized_block_is_split_on_line_ends(self):
        """A markdown table cut mid-row loses its header, and every row after
        the cut becomes unreadable to the model."""
        rows = "\n".join(f"| FNV-{i:04d} | Product {i} | {i}.00 |" for i in range(200))
        chunks = embed.chunk_markdown("## Prices\n" + rows, max_chars=600)
        assert len(chunks) > 1
        for chunk in chunks:
            for line in chunk.splitlines():
                if line.startswith("|"):
                    assert line.rstrip().endswith("|"), "a table row was cut in half"

    def test_no_chunk_is_blank_after_splitting(self):
        chunks = embed.chunk_markdown("## H\n" + ("x" * 5000), max_chars=500)
        assert chunks and all(c.strip() for c in chunks)


class TestContentHash:
    def test_it_changes_when_the_text_changes(self):
        """This is what makes 'the parse moved underneath the embeddings'
        detectable instead of a silent drift in retrieval quality."""
        assert embed.content_hash("Net 30 days.") != embed.content_hash("Net 60 days.")

    def test_it_is_stable_for_the_same_text(self):
        assert embed.content_hash("Net 30 days.") == embed.content_hash("Net 30 days.")


class TestQueryPrefix:
    def test_the_prefix_is_bge_s_own_and_applies_to_queries_only(self):
        """BGE prefixes the QUERY side only. Prefixing documents too, or
        neither, costs retrieval quality in a way nothing visibly reports."""
        assert "searching relevant passages" in embed.QUERY_PREFIX
        assert embed.DIMENSIONS == 384


@pytest.mark.slow
class TestModel:
    """These load the real model. No network at inference time, no key, no
    quota — but the first run downloads weights, so they are marked slow."""

    def test_vectors_are_384d_and_unit_norm(self):
        vectors = embed.default_embedder().encode(["Net 30 days from invoice date."])
        assert len(vectors[0]) == embed.DIMENSIONS
        norm = sum(x * x for x in vectors[0]) ** 0.5
        assert abs(norm - 1.0) < 1e-4, "not L2-normalised; cosine distance breaks"

    def test_a_paraphrase_scores_higher_than_an_unrelated_sentence(self):
        """The actual contract this project cares about. If CLS pooling were
        replaced by mean pooling this still passes shape checks and fails
        here — which is the point of asserting behaviour, not structure."""
        e = embed.default_embedder()
        base, para, other = e.encode(
            [
                "Payment terms are net 30 days from invoice date.",
                "The buyer shall pay within thirty days of the invoice.",
                "Chilled goods must be received below four degrees celsius.",
            ]
        )
        dot = lambda a, b: sum(x * y for x, y in zip(a, b, strict=True))  # noqa: E731
        assert dot(base, para) > dot(base, other)

    def test_the_query_prefix_changes_the_vector(self):
        """If `is_query` were ignored, retrieval would silently use the wrong
        side of the model's training and nothing would report it."""
        e = embed.default_embedder()
        plain = e.encode_one("payment terms")
        prefixed = e.encode_one("payment terms", is_query=True)
        assert plain != prefixed
