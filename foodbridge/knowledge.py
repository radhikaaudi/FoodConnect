"""Knowledge base + retrieval — the RAG layer.

FoodBridge grounds its trickiest judgments (food safety, donor liability, allergens,
transport rules) in a curated knowledge base of guideline passages (``data/knowledge/*.md``,
each with YAML-ish frontmatter: id, title, source). The agent retrieves the most relevant
passages and *cites them* in its reasoning and escalations, so a coordinator can check the
rule behind every call.

Retrieval is a dependency-free lexical ranker (TF-style term overlap with an IDF weight —
BM25's core idea, standard library only) so it runs offline and on AgentCore alike. The
LLM never has to remember regulations; it looks them up — and when the model is offline the
same citations still ground the deterministic brain's messages. Swapping in vector
embeddings (e.g. Bedrock Titan or Ollama embeddings) is a one-function change in
``_score``.
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

_WORD = re.compile(r"[a-z0-9°]+")
_STOP = frozenset(
    "a an and are as at be by for from has have if in is it its of on or that the this to "
    "was we what when which with should must may not no".split()
)


@dataclass
class Passage:
    id: str
    title: str
    source: str
    text: str

    def cite(self) -> str:
        return f"{self.title} ({self.source})"


def _tokens(text: str) -> List[str]:
    return [w for w in _WORD.findall(text.lower()) if w not in _STOP]


class KnowledgeBase:
    def __init__(self, passages: List[Passage]):
        self.passages = passages
        self._docs = [set(_tokens(p.title + " " + p.text)) for p in passages]
        n = max(len(passages), 1)
        df: Dict[str, int] = {}
        for doc in self._docs:
            for t in doc:
                df[t] = df.get(t, 0) + 1
        self._idf = {t: math.log(1 + n / c) for t, c in df.items()}

    @classmethod
    def load(cls, folder: str) -> "KnowledgeBase":
        passages: List[Passage] = []
        if os.path.isdir(folder):
            for fname in sorted(os.listdir(folder)):
                if not fname.endswith(".md"):
                    continue
                raw = open(os.path.join(folder, fname), encoding="utf-8").read()
                meta = dict(re.findall(r"^(\w+):\s*(.+)$", raw.split("---")[1], re.M)) \
                    if raw.startswith("---") else {}
                body = raw.split("---", 2)[-1].strip()
                passages.append(Passage(
                    id=meta.get("id", fname[:-3]),
                    title=meta.get("title", fname[:-3]).strip('"'),
                    source=meta.get("source", "knowledge base"),
                    text=body,
                ))
        return cls(passages)

    def _score(self, query: str, doc: set) -> float:
        return sum(self._idf.get(t, 0.0) for t in set(_tokens(query)) if t in doc)

    def retrieve(self, query: str, k: int = 2) -> List[Passage]:
        """Top-k most relevant passages for a natural-language query."""
        scored = sorted(
            ((self._score(query, doc), p) for doc, p in zip(self._docs, self.passages)),
            key=lambda x: x[0], reverse=True,
        )
        return [p for s, p in scored[:k] if s > 0]

    def ground(self, query: str) -> Optional[str]:
        """One-line citation for the best-matching passage, or None."""
        hits = self.retrieve(query, k=1)
        return f"Per {hits[0].cite()}" if hits else None


_DEFAULT: Optional[KnowledgeBase] = None


def default_kb() -> KnowledgeBase:
    """The project knowledge base, loaded once from data/knowledge/."""
    global _DEFAULT
    if _DEFAULT is None:
        folder = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "data", "knowledge")
        _DEFAULT = KnowledgeBase.load(folder)
    return _DEFAULT
