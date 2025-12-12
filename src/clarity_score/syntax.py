"""Pattern-based syntactic-ambiguity detection.

Replaces starter.md's hand-written 10-word CFG (which only ever parsed its
own toy vocabulary) with detectors for well-documented English
structural-ambiguity classes, run over POS tags / shallow chunks produced
by NLTK. See ../../ARCHITECTURE.md decision #3 for the rationale and the
list of rules still outstanding.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import nltk

from ._nltk_data import ensure_nltk_data

# Cascaded chunk grammar: each stage's pattern can reference the chunk
# labels produced by the previous stage (NP -> P -> V -> PP -> VP), the
# same style as NLTK's own RegexpParser chunking guide.
_CHUNK_GRAMMAR = r"""
    NP: {<DT|PRP\$>?<JJ.*>*<NN.*>+}
    P: {<IN|TO>}
    V: {<VB.*>}
    PP: {<P><NP>}
    VP: {<V><NP|PP>*}
"""

_chunker = nltk.RegexpParser(_CHUNK_GRAMMAR)


@dataclass(frozen=True)
class AmbiguityHit:
    kind: str
    span: str


@dataclass(frozen=True)
class SyntaxReport:
    hits: list[AmbiguityHit] = field(default_factory=list)

    @property
    def ambiguity_score(self) -> float:
        """Number of distinct ambiguity-pattern hits; 0 means no detected
        structural ambiguity, matching the toy script's "single parse"
        baseline (`syntactic_multiplier == 1` -> penalty 0)."""
        return float(len(self.hits))


def _leaves_text(tree: nltk.Tree) -> str:
    return " ".join(tok for tok, _tag in tree.leaves())


def _find_pp_attachment_hits(tree: nltk.Tree) -> list[AmbiguityHit]:
    """Flags verb-phrase chunks shaped like `V NP PP` (e.g. "saw the man
    with the telescope"): the trailing PP could attach to the NP (modifying
    the object) or to the VP (modifying the verb) -- the textbook
    prepositional-phrase attachment ambiguity.
    """
    hits: list[AmbiguityHit] = []
    for subtree in tree.subtrees(lambda t: t.label() == "VP"):
        labels = [child.label() for child in subtree if isinstance(child, nltk.Tree)]
        for i in range(len(labels) - 1):
            if labels[i] == "NP" and labels[i + 1] == "PP":
                hits.append(AmbiguityHit(kind="pp-attachment", span=_leaves_text(subtree)))
                break
    return hits


# TODO(#2): coordination/conjunction-scope ambiguity, e.g. "old men and
# women" ([JJ N] CC N vs JJ [N CC N]). See ARCHITECTURE.md decision #3.
def _find_coordination_scope_hits(tree: nltk.Tree) -> list[AmbiguityHit]:
    return []


# TODO(#3): participle/gerund attachment ambiguity, e.g. sentence-initial
# or post-NP VBG ("Flying planes can be dangerous"). See ARCHITECTURE.md
# decision #3.
def _find_participle_attachment_hits(tree: nltk.Tree) -> list[AmbiguityHit]:
    return []


def analyze_syntax(tagged_tokens: list[tuple[str, str]]) -> SyntaxReport:
    """Runs all syntactic-ambiguity detectors over an already POS-tagged
    sentence (as produced by `tag_sentence`)."""
    tree = _chunker.parse(tagged_tokens)
    hits = [
        *_find_pp_attachment_hits(tree),
        *_find_coordination_scope_hits(tree),
        *_find_participle_attachment_hits(tree),
    ]
    return SyntaxReport(hits=hits)


def tag_sentence(sentence: str) -> list[tuple[str, str]]:
    ensure_nltk_data()
    tokens = nltk.word_tokenize(sentence)
    return nltk.pos_tag(tokens)

__all__ = [
    "AmbiguityHit",
    "SyntaxReport",
    "analyze_syntax",
    "tag_sentence",
]
