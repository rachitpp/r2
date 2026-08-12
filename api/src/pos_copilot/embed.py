"""Local sentence embeddings. bge-small-en-v1.5, CPU, no quota and no key.

**Why local, permanently.** CLAUDE.md rule 2: the system a reader runs must
never need paid inference, and embeddings are the one component that would
otherwise be called once per chunk at ingest and once per query at serve time.
That is the shape that turns a free-tier demo into a bill. Local at every tier,
and 384 dimensions on CPU is fast enough that no cache is needed.

**No sentence-transformers.** `torch`, `transformers` and `tokenizers` are
already in this project via Docling, and bge-small is a BERT encoder — the whole
of what sentence-transformers would add here is CLS pooling and L2
normalisation, which are four lines each and are written out below where they
can be read. `pyproject.toml` argues for every dependency it has; this one did
not need to be added.

**The pooling is not a detail.** BGE models are trained with CLS pooling and
normalised embeddings, and the query side expects an instruction prefix
(`QUERY_PREFIX`). Mean-pooling them instead, or skipping the prefix, produces
embeddings that are not wrong in any way you can see — retrieval simply gets
quietly worse. That is exactly the class of defect this project keeps finding, so
it is asserted in `test_embed.py` rather than trusted.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    pass

MODEL_NAME = "BAAI/bge-small-en-v1.5"
DIMENSIONS = 384

# BGE's own guidance: prefix the QUERY side only, never the documents. Prefixing
# both, or neither, is a measurable retrieval loss that looks like nothing.
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


@dataclass
class Embedder:
    """Wraps the model. Loaded once — the load costs seconds, the calls do not."""

    model_name: str = MODEL_NAME
    _tokenizer: object = field(default=None, repr=False)
    _model: object = field(default=None, repr=False)

    def _load(self) -> None:
        if self._model is not None:
            return
        import torch
        from transformers import AutoModel, AutoTokenizer

        self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self._model = AutoModel.from_pretrained(self.model_name)
        self._model.eval()
        torch.set_grad_enabled(False)

    def encode(self, texts: list[str], *, is_query: bool = False) -> list[list[float]]:
        """Return one 384-dimension unit vector per input.

        `is_query` adds BGE's retrieval prefix. Documents must NOT get it.
        """
        if not texts:
            return []
        import torch

        self._load()
        prepared = [QUERY_PREFIX + t if is_query else t for t in texts]
        batch = self._tokenizer(
            prepared,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt",
        )
        output = self._model(**batch)
        # CLS pooling: BGE is trained on the first token, not the mean.
        pooled = output.last_hidden_state[:, 0]
        normed = torch.nn.functional.normalize(pooled, p=2, dim=1)
        return [row.tolist() for row in normed]

    def encode_one(self, text: str, *, is_query: bool = False) -> list[float]:
        return self.encode([text], is_query=is_query)[0]


@lru_cache(maxsize=1)
def default_embedder() -> Embedder:
    return Embedder()


def content_hash(text: str) -> str:
    """Hash of the exact bytes embedded.

    Stored beside the vector so a re-embed can skip unchanged chunks, and so
    "the parse moved underneath the embeddings" is detectable rather than a
    silent drift in retrieval quality.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chunk_markdown(
    text: str, *, max_chars: int = 1200, overlap: int = 150
) -> list[str]:
    """Split parsed markdown on headings, then on size.

    Heading-first because these documents are clauses: `## 3. Payment terms` and
    its sentence belong together, and a fixed-width splitter cuts exactly there
    often enough to matter. A clause split across two chunks retrieves as two
    partial answers, which reads like the model being vague.

    Markdown tables are held whole where they fit — an invoice line table split
    mid-rows loses the header, and every row after the cut becomes unreadable.
    """
    if not text.strip():
        return []

    blocks: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if line.startswith("#") and current:
            blocks.append("\n".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        blocks.append("\n".join(current).strip())

    chunks: list[str] = []
    for block in blocks:
        if not block:
            continue
        if len(block) <= max_chars:
            chunks.append(block)
            continue
        start = 0
        while start < len(block):
            end = start + max_chars
            window = block[start:end]
            # Prefer to break at a line end so a table row is never cut in half.
            if end < len(block):
                newline = window.rfind("\n")
                if newline > max_chars // 2:
                    end = start + newline
                    window = block[start:end]
            chunks.append(window.strip())
            if end >= len(block):
                break
            start = max(end - overlap, start + 1)
    return [c for c in chunks if c]
