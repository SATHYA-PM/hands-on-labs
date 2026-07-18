"""
StyleVault — loads plain-text style-guide rules into a FAISS index so
individual story scenes can be checked for tone/format compliance.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


class StyleVault:
    """
    FAISS + sentence-transformers style guide checker.
    Falls back to a stub (always passes) if dependencies are missing.
    """

    def __init__(self) -> None:
        self._index = None
        self._texts: list[str] = []
        self._model = None
        self._ready = False
        self._try_init()

    def _try_init(self) -> None:
        try:
            import faiss  # type: ignore  # noqa: F401
            from sentence_transformers import SentenceTransformer  # type: ignore

            self._model = SentenceTransformer("all-MiniLM-L6-v2")
            self._ready = True
        except ImportError:
            self._ready = False

    def load_rules_dir(self, rules_dir: str) -> None:
        if not self._ready:
            return
        import numpy as np
        import faiss  # type: ignore

        texts: list[str] = []
        for path in sorted(Path(rules_dir).glob("*.txt")):
            content = path.read_text(encoding="utf-8")
            # Split into paragraphs / sentences for granular matching
            chunks = [c.strip() for c in content.split("\n\n") if c.strip()]
            texts.extend(chunks)

        if not texts:
            return

        self._texts = texts
        embeddings = self._model.encode(texts, convert_to_numpy=True)
        embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)

        dim = embeddings.shape[1]
        self._index = faiss.IndexFlatIP(dim)  # inner-product → cosine on L2-norm'd vecs
        self._index.add(embeddings.astype("float32"))

    def query(self, text: str, k: int = 3) -> list[tuple[float, str]]:
        """Return [(score, rule_text), …] for the k nearest style rules."""
        if not self._ready or self._index is None or not self._texts:
            return []

        import numpy as np

        vec = self._model.encode([text], convert_to_numpy=True)
        vec = vec / np.linalg.norm(vec, axis=1, keepdims=True)
        scores, indices = self._index.search(vec.astype("float32"), k)

        results: list[tuple[float, str]] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:
                continue
            results.append((float(score), self._texts[idx]))
        return results

    def add_rule(self, rule_text: str) -> None:
        """Dynamically add a single rule at runtime."""
        if not self._ready:
            return
        import numpy as np

        self._texts.append(rule_text)
        vec = self._model.encode([rule_text], convert_to_numpy=True)
        vec = vec / np.linalg.norm(vec, axis=1, keepdims=True)
        if self._index is None:
            import faiss  # type: ignore
            self._index = faiss.IndexFlatIP(vec.shape[1])
        self._index.add(vec.astype("float32"))
