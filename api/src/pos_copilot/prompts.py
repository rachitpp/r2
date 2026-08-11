"""Loading prompts from files, and hashing what was actually sent.

ADR-0008: prompts are files, substitution is `str.format()`, and every eval run
records the SHA-256 of each prompt file it used. Without the hashes a published
accuracy number cannot be traced to the prompt that produced it, and quietly
stops describing anything.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
CONTEXT_DIR = PROMPTS_DIR / "context"


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class PromptBundle:
    """A prompt template plus the context files injected into it.

    `hashes` covers every file whose content reached the model, so a result
    file records the whole input surface rather than just the template.
    """

    template: str
    context: dict[str, str]
    hashes: dict[str, str]

    def render(self, **fields: object) -> str:
        merged = {**self.context, **fields}
        try:
            return self.template.format(**merged)
        except KeyError as exc:
            raise KeyError(
                f"prompt needs placeholder {exc} which was not supplied. "
                "Add it here or document it in api/prompts/README.md."
            ) from exc


def load_sql_prompt() -> PromptBundle:
    """sql_generate.md with business_context.md and schema.md injected."""
    template_path = PROMPTS_DIR / "sql_generate.md"
    context_paths = {
        "business_context": CONTEXT_DIR / "business_context.md",
        "schema": CONTEXT_DIR / "schema.md",
    }

    missing = [
        str(p) for p in [template_path, *context_paths.values()] if not p.exists()
    ]
    if missing:
        raise FileNotFoundError(
            "missing prompt files: " + ", ".join(missing) + ". "
            "schema.md is generated — run `make schema-doc`."
        )

    hashes = {template_path.name: sha256_of(template_path)}
    context = {}
    for key, path in context_paths.items():
        context[key] = path.read_text(encoding="utf-8")
        hashes[f"context/{path.name}"] = sha256_of(path)

    return PromptBundle(
        template=template_path.read_text(encoding="utf-8"),
        context=context,
        hashes=hashes,
    )


def load_extract_prompt() -> PromptBundle:
    """extract.md, with no context files injected.

    Deliberately context-free, unlike the SQL prompt. `business_context.md` and
    `schema.md` describe the database, and extraction must record what a document
    says rather than what the database would expect it to say — injecting them
    would give the model the answers it is being measured on reconstructing, and
    a plausible value copied from context is exactly the failure this step is
    scored for.

    The consequence for cost is worth stating: the extraction fingerprint is
    therefore independent of the two context documents, so the corrections gated
    in `HANDOFF.md` can land without voiding a single extracted document.
    """
    template_path = PROMPTS_DIR / "extract.md"
    if not template_path.exists():
        raise FileNotFoundError(f"missing prompt file: {template_path}")
    return PromptBundle(
        template=template_path.read_text(encoding="utf-8"),
        context={},
        hashes={template_path.name: sha256_of(template_path)},
    )


def bundle_fingerprint(hashes: dict[str, str]) -> str:
    """One short id for the whole prompt surface.

    The eval cache is keyed on this: change any prompt or context file and
    every cached response for it is invalidated, because it no longer describes
    what the model would be sent.
    """
    joined = "|".join(f"{name}:{digest}" for name, digest in sorted(hashes.items()))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]
