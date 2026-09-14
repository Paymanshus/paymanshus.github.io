"""
Section-aware markdown retrieval with BM25 scoring.

This module parses structured markdown files into heading-delimited sections,
builds an in-memory BM25 index, and provides keyword-based search.

Currently used to index content/resumedump.md (the resume), but designed to
scale to the entire content/ directory — blog posts, project notes, etc.
See "Expanding to Full Website Content" in docs/voice-feature/02-resume-context-system.md.

Usage:
    index = ContentIndex("content/resumedump.md")
    result = index.search("voice agent experience", top_k=3)
    print(result)

    # Or use the pre-built singleton:
    result = get_resume_index().search("voice agent experience")

Design notes:
- Heading-aware chunking preserves semantic coherence of sections
- Hierarchical paths give the LLM "where am I" context
- BM25 scoring handles term importance naturally (IDF for rare terms)
- In-memory operation: ~0.1ms per query on a 150-line document
- Each Section records its source_file for future multi-source routing
- No embedding model, no vector DB, no external dependencies

BM25 formula (Okapi BM25):
  score(D,Q) = Σ IDF(qi) · (tf(qi,D) · (k1+1)) / (tf(qi,D) + k1·(1-b+b·|D|/avgdl))
  k1 = 1.5 — term frequency saturation
  b  = 0.75 — document length normalization
"""

import os
import re
import math
import time
import logging
from pathlib import Path
from collections import Counter
from dataclasses import dataclass, field

logger = logging.getLogger("resume-context")


@dataclass
class Section:
    """A heading-delimited section of a markdown document."""
    path: str           # e.g., "Experience > Maersk — Machine Learning Engineer"
    heading: str        # e.g., "Maersk — Machine Learning Engineer"
    level: int          # Heading level (1=H1, 2=H2, 3=H3)
    content: str        # Full text content including bullets, etc.
    source_file: str    # Which file this came from (for future multi-source routing)
    tokens: list[str] = field(default_factory=list)


class ContentIndex:
    """In-memory BM25 index over one or more markdown files.

    Accepts a single file path, a list of file paths, or a directory path.
    When given a directory, all *.md files in it (non-recursive) are indexed.

    Thread-safe for read operations. The index is built once at construction
    and never mutated.

    Currently instantiated with only content/resumedump.md, but the same
    class can index blog posts or any other markdown content by passing
    additional paths. See docs/voice-feature/02-resume-context-system.md
    for the planned multi-content expansion.
    """

    def __init__(
        self,
        sources: "str | list[str]",
        label: str = "content",
        section_tags: "dict[str, list[str]] | None" = None,
        query_synonyms: "dict[str, list[str]] | None" = None,
    ):
        """Build the index from one or more markdown sources.

        Args:
            sources:         A file path, list of file paths, or directory path.
                             Directories are scanned for *.md files (non-recursive).
            label:           A human-readable label for logging (e.g. "resume", "blog").
            section_tags:    Optional mapping of path substring → extra tokens to inject
                             into matching sections at index time. Keys are matched as
                             case-insensitive substrings of each section's full path.
                             Example: {"Education": ["college", "university", "degree"]}
            query_synonyms:  Optional mapping of token → expanded tokens applied to the
                             query at search time. Fixes abbreviation and vocabulary gaps.
                             Example: {"college": ["education", "university"]}

        Raises:
            FileNotFoundError: If any specified file doesn't exist.
        """
        self.label = label
        self.sections: list[Section] = []
        self.full_text: str = ""   # Concatenated full text (used as fallback context)
        self._idf: dict[str, float] = {}
        self._avg_dl: float = 0.0
        self._section_tags: dict[str, list[str]] = section_tags or {}
        self._query_synonyms: dict[str, list[str]] = query_synonyms or {}

        paths = self._resolve_paths(sources)
        for p in paths:
            self._parse_file(p)

        self._build_bm25_index()
        logger.info(
            f"[{label}] Index built: {len(self.sections)} sections, "
            f"{len(self._idf)} unique tokens from {len(paths)} file(s)"
        )

    # ─── Path resolution ───────────────────────────────────────────

    def _resolve_paths(self, sources: "str | list[str]") -> list[Path]:
        if isinstance(sources, str):
            sources = [sources]
        paths: list[Path] = []
        for s in sources:
            p = Path(s)
            if p.is_dir():
                paths.extend(sorted(p.glob("*.md")))
            else:
                if not p.exists():
                    raise FileNotFoundError(f"Content file not found: {p}")
                paths.append(p)
        return paths

    # ─── Parsing ───────────────────────────────────────────────────

    def _tokenize(self, text: str) -> list[str]:
        """Tokenize into lowercase words, preserving hyphens and dots.

        Preserves: 'real-time', 'multi-modal', 'node.js', 'v2.6.0'.
        """
        return re.findall(r'\b[a-z0-9]+(?:[\.\-][a-z0-9]+)*\b', text.lower())

    def _parse_file(self, path: Path):
        """Parse one markdown file into sections and append to self.sections."""
        raw = path.read_text(encoding="utf-8")
        self.full_text += raw + "\n"

        lines = raw.split("\n")
        heading_stack: list[tuple[int, str]] = []  # [(level, text), ...]
        current_lines: list[str] = []

        def flush():
            content = "\n".join(current_lines).strip()
            if content and heading_stack:
                path_str = " > ".join(text for _, text in heading_stack)
                heading = heading_stack[-1][1]
                level = heading_stack[-1][0]
                # Score on content + heading only — not path_str.
                # path_str is for LLM display; including it inflates parent-heading
                # tokens (e.g. "AI" from a job title) and distorts BM25 ranking.
                tokens = self._tokenize(content + " " + heading)
                # Inject section anchor tags if any tag key matches this section's path.
                # Tags extend the token bag at index time (single occurrence each).
                for tag_key, tag_tokens in self._section_tags.items():
                    if tag_key.lower() in path_str.lower():
                        tokens.extend(tag_tokens)
                self.sections.append(Section(
                    path=path_str,
                    heading=heading,
                    level=level,
                    content=content,
                    source_file=str(path),
                    tokens=tokens,
                ))

        for line in lines:
            m = re.match(r'^(#{1,3})\s+(.+)', line)
            if m:
                flush()
                current_lines = []
                level = len(m.group(1))
                heading_text = m.group(2).strip()
                while heading_stack and heading_stack[-1][0] >= level:
                    heading_stack.pop()
                heading_stack.append((level, heading_text))
            elif re.match(r'^---+\s*$', line):
                # Skip bare horizontal-rule lines — they're decorative separators
                # in the source markdown, not semantic content.
                pass
            else:
                current_lines.append(line)

        flush()

    # ─── BM25 index ────────────────────────────────────────────────

    def _build_bm25_index(self):
        n = len(self.sections)
        if n == 0:
            logger.warning(f"[{self.label}] No sections parsed — check markdown format.")
            return

        for token in {t for s in self.sections for t in set(s.tokens)}:
            df = sum(1 for s in self.sections if token in set(s.tokens))
            self._idf[token] = math.log((n - df + 0.5) / (df + 0.5) + 1)

        self._avg_dl = sum(len(s.tokens) for s in self.sections) / n

    # ─── Search ────────────────────────────────────────────────────

    def search(self, query: str, top_k: int = 3) -> str:
        """Search the indexed content for sections relevant to the query.

        Uses BM25 (k1=1.5, b=0.75).

        Returns formatted text of the top-k matching sections, separated by
        "---". Falls back to full text if nothing matches.
        """
        return self.search_scored(query, top_k=top_k)[0]

    def search_scored(self, query: str, top_k: int = 3) -> "tuple[str, float]":
        """Like search(), but also returns the top BM25 score as a retrieval
        confidence signal.

        Returns:
            (context_text, top_score) — top_score is 0.0 when nothing matched
            (the context is then the full document text). Callers can route on
            the score: below a threshold, inject the full document instead of
            trusting the retrieved sections.

        Score scale note: BM25 scores are corpus-relative, not probabilities.
        On this index a single strong keyword match lands around 2-4; multi-term
        matches reach 6-15. Empirically (see tests) a threshold around 2.5
        separates "confident section hit" from "weak/incidental overlap".
        """
        start = time.perf_counter_ns()

        query_tokens = self._tokenize(query)

        # Expand query tokens with configured synonyms (query-side vocabulary fix).
        # E.g. "college" → also scores against "education", "university".
        if self._query_synonyms:
            expanded = list(query_tokens)
            for t in query_tokens:
                if t in self._query_synonyms:
                    expanded.extend(self._query_synonyms[t])
            query_tokens = expanded

        if not query_tokens:
            logger.warning(f"[{self.label}] Empty query, returning full text as fallback")
            return self.full_text, 0.0

        k1, b = 1.5, 0.75
        scores: list[tuple[float, Section]] = []

        for section in self.sections:
            score = 0.0
            dl = len(section.tokens)
            tf_counter = Counter(section.tokens)
            for qt in query_tokens:
                tf = tf_counter.get(qt, 0)
                if tf == 0:
                    continue
                idf = self._idf.get(qt, 0.0)
                score += idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * (dl / self._avg_dl)))
            if score > 0:
                scores.append((score, section))

        scores.sort(key=lambda x: x[0], reverse=True)
        top = scores[:top_k]

        elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000
        top_score = top[0][0] if top else 0.0
        logger.info(
            f"[{self.label}] search: query='{query}' → {len(scores)} hits, "
            f"top {len(top)} returned, top_score={top_score:.2f}, latency={elapsed_ms:.2f}ms"
        )

        if not top:
            logger.info(f"[{self.label}] No matches, returning full text as fallback")
            return self.full_text, 0.0

        context = "\n\n---\n\n".join(
            f"[{s.path}]\n{s.content}" for _, s in top
        )
        return context, top_score

    def get_section_paths(self) -> list[str]:
        """Return all section paths (for debugging/testing)."""
        return [s.path for s in self.sections]


# ─── Resume domain configuration ──────────────────────────────────
# Resume-specific section tags and query synonyms injected into the
# ContentIndex for the resume index only. Blog or other content indices
# don't use these — they pass nothing (or their own config).
#
# section_tags: injected into the token bag at index time so BM25 can
#   match conversational vocabulary ("college") to resume headings ("Education").
#   Keys are case-insensitive substrings matched against section paths.
#
# query_synonyms: expanded at query time to bridge abbreviation gaps.
#   E.g. "ml" → also scores "machine" and "learning" in the section tokens.

RESUME_SECTION_TAGS: dict[str, list[str]] = {
    "Education":    ["college", "university", "studied", "degree", "school",
                     "bachelor", "undergrad", "grad"],
    "Experience":   ["job", "work", "role", "career", "employer", "company"],
    "Maersk":       ["current", "recent", "latest", "now", "today", "agentic"],
    "Hike":         ["voice", "bot", "call", "phone", "sip", "outreach"],
    "Mphasis":      ["research", "lab", "enterprise", "sagemaker", "marketplace"],
    "Skills":       ["know", "familiar", "technologies", "stack", "tools", "tech"],
    "Achievements": ["won", "award", "prize", "recognition", "competition",
                     "hackathon", "medal", "kaggle"],
    "Projects":     ["built", "made", "created", "side", "personal", "hobby"],
    "Coursework":   ["studied", "learned", "course", "class", "subject"],
    "Misc":         ["volunteer", "community", "social", "club", "extracurricular"],
}

RESUME_QUERY_SYNONYMS: dict[str, list[str]] = {
    "college":  ["education", "university"],
    "school":   ["education"],
    "job":      ["experience"],
    "ml":       ["machine", "learning"],
    "nlp":      ["natural", "language", "processing"],
    "ai":       ["artificial", "intelligence"],
    "llm":      ["language", "model"],
    "cv":       ["computer", "vision"],
    "dl":       ["deep", "learning"],
}


# ─── Singleton registry ────────────────────────────────────────────
# Named indices loaded once at agent startup and reused across sessions.
# Currently only "resume" is used. Future: add "blog", "all", etc.

_indices: dict[str, ContentIndex] = {}


def resume_dump_candidates(here: Path | None = None) -> list[Path]:
    """Paths to try for resumedump.md, first existing wins.

    Layouts we actually run:
      1. RESUME_CONTENT_PATH — explicit override
      2. <this dir>/content/resumedump.md — Docker: agent files are copied
         into /app, so resume_context.py lives at /app/resume_context.py and
         the Dockerfile places the dump at /app/content/resumedump.md
      3. <this dir>/../content/resumedump.md — local: agent/resume_context.py
         with the dump at repo-root content/resumedump.md
    """
    here = (here or Path(__file__).resolve().parent)
    ordered: list[Path] = []
    env = os.environ.get("RESUME_CONTENT_PATH", "").strip()
    if env:
        ordered.append(Path(env))
    ordered.append(here / "content" / "resumedump.md")
    ordered.append(here.parent / "content" / "resumedump.md")
    seen: set[str] = set()
    unique: list[Path] = []
    for p in ordered:
        key = str(p)
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def resolve_resume_dump_path(here: Path | None = None) -> Path:
    """Return the first candidate that exists, or raise with every path tried."""
    tried = resume_dump_candidates(here)
    for p in tried:
        if p.exists():
            return p
    raise FileNotFoundError(
        "Content file not found. Tried: " + ", ".join(str(p) for p in tried)
    )


def get_resume_index() -> ContentIndex:
    """Get (or create) the resume-only index singleton.

    Builds with RESUME_SECTION_TAGS and RESUME_QUERY_SYNONYMS for domain-
    specific routing. Path is resolved from this file (and RESUME_CONTENT_PATH)
    so it works from a local `agent/` checkout and from the flattened Docker
    image at /app.
    """
    if "resume" not in _indices:
        resume_path = resolve_resume_dump_path()
        _indices["resume"] = ContentIndex(
            str(resume_path),
            label="resume",
            section_tags=RESUME_SECTION_TAGS,
            query_synonyms=RESUME_QUERY_SYNONYMS,
        )
    return _indices["resume"]


# Convenience alias used by tests that import ResumeIndex by name
ResumeIndex = ContentIndex
