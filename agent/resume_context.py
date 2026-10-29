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

# An HTML comment in content markdown; group 1 is its text minus a "keywords:" label.
_COMMENT_RE = re.compile(r"<!--\s*(?:keywords:)?(.*?)-->", re.DOTALL)

# Sections never indexed: a post's link list matches topic words ("fine-tuning",
# "LLMs") in paper titles but has nothing the agent can answer from.
_UNINDEXED_HEADINGS = {"references"}


@dataclass
class Section:
    """A heading-delimited section of a markdown document."""
    path: str           # e.g., "Experience > Maersk — Machine Learning Engineer"
    heading: str        # e.g., "Maersk — Machine Learning Engineer"
    level: int          # Heading level (1=H1, 2=H2, 3=H3)
    content: str        # Full text content including bullets, etc.
    source_file: str    # Which file this came from (for future multi-source routing)
    tokens: list[str] = field(default_factory=list)
    keywords: str = ""  # from a "<!-- keywords: ... -->" line; indexed, not shown


def _split_front_matter(raw: str) -> "tuple[dict[str, str], str]":
    """Top-level `key: value` pairs from a leading --- block, and the body.

    Deliberately not a YAML parser: only scalar fields are read (title,
    summary, excerpt, published); lists and nested blocks are ignored.
    """
    if not raw.startswith("---"):
        return {}, raw
    lines = raw.split("\n")
    for end in range(1, len(lines)):
        if re.match(r"^---\s*$", lines[end]):
            break
    else:
        return {}, raw
    meta: dict[str, str] = {}
    for line in lines[1:end]:
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*?)\s*$", line)
        if m and m.group(2):
            meta[m.group(1)] = m.group(2).strip("\"'")
    return meta, "\n".join(lines[end + 1:])


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
        stopwords: "frozenset[str] | None" = None,
        extra_markdown: "list[tuple[str, str]] | None" = None,
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
                             A key starting with "#" matches the section's own heading
                             only, not its children: {"#Maersk": [...]} tags the role
                             header but not the project sections nested under it.
            extra_markdown:  Optional (source_label, markdown) pairs indexed after the
                             files, for sections generated at startup rather than
                             read from disk (the /cooking overview).
            stopwords:       Optional query tokens to drop before scoring. Without them,
                             "what are you working on" ranks whichever section happens to
                             repeat "working on", not the one the question is about.

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
        self._stopwords: frozenset[str] = stopwords or frozenset()

        paths = self._resolve_paths(sources)
        for p in paths:
            self._parse_file(p)
        for source, text in extra_markdown or []:
            self._parse_text(text, source)

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
                # "_template.md" and friends are scaffolding, not content.
                paths.extend(q for q in sorted(p.glob("*.md")) if not q.name.startswith("_"))
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
        """Parse one markdown file into sections and append to self.sections.

        A file with YAML front matter (blog posts, /cooking projects) becomes a
        "# title" heading with its summary/excerpt as the first line, so every
        section carries the post's name in its path. `published: false` files
        are skipped, matching what the site shows.
        """
        raw = path.read_text(encoding="utf-8")
        meta, body = _split_front_matter(raw)
        if meta:
            if meta.get("published", "").lower() == "false":
                return
            title = meta.get("title") or path.stem
            intro = meta.get("summary") or meta.get("excerpt") or ""
            raw = f"# {title}\n{intro}\n{body}"
        self._parse_text(raw, str(path))

    def _parse_text(self, raw: str, source: str):
        """Split markdown text into heading-delimited sections."""
        self.full_text += raw + "\n"

        lines = raw.split("\n")
        heading_stack: list[tuple[int, str]] = []  # [(level, text), ...]
        current_lines: list[str] = []

        def flush():
            content = "\n".join(current_lines).strip()
            # "<!-- keywords: ... -->" lines (content/about notes) are indexed
            # for recall but never shown to the model.
            keywords = " ".join(_COMMENT_RE.findall(content))
            content = _COMMENT_RE.sub("", content).strip()
            if content and heading_stack and heading_stack[-1][1].lower() not in _UNINDEXED_HEADINGS:
                path_str = " > ".join(text for _, text in heading_stack)
                heading = heading_stack[-1][1]
                level = heading_stack[-1][0]
                # Score on content + heading only — not path_str.
                # path_str is for LLM display; including it inflates parent-heading
                # tokens (e.g. "AI" from a job title) and distorts BM25 ranking.
                tokens = self._tokenize(content + " " + heading + " " + keywords)
                # Inject section anchor tags if any tag key matches this section's path.
                # Tags extend the token bag at index time (single occurrence each).
                for tag_key, tag_tokens in self._section_tags.items():
                    if tag_key.startswith("#"):
                        hit = tag_key[1:].lower() in heading.lower()
                    else:
                        hit = tag_key.lower() in path_str.lower()
                    if hit:
                        tokens.extend(tag_tokens)
                self.sections.append(Section(
                    path=path_str,
                    heading=heading,
                    level=level,
                    content=content,
                    source_file=source,
                    tokens=tokens,
                    keywords=keywords,
                ))

        for line in lines:
            m = re.match(r'^(#{1,4})\s+(.+)', line)
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
        top = self.search_sections(query, top_k=top_k)
        elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000
        top_score = top[0][0] if top else 0.0
        logger.info(
            f"[{self.label}] search: query='{query}' → "
            f"top {len(top)} returned, top_score={top_score:.2f}, latency={elapsed_ms:.2f}ms"
        )

        if not top:
            logger.info(f"[{self.label}] No matches, returning full text as fallback")
            return self.full_text, 0.0

        context = "\n\n---\n\n".join(
            f"[{s.path}]\n{s.content}" for _, s in top
        )
        return context, top_score

    def query_tokens(self, query: str) -> list[str]:
        """The query's tokens minus stopwords (synonyms are added at search time)."""
        return [t for t in self._tokenize(query) if t not in self._stopwords]

    def search_sections(self, query: str, top_k: int = 3) -> "list[tuple[float, Section]]":
        """BM25-ranked (score, section) pairs with a positive score, best first."""
        query_tokens = self.query_tokens(query)

        # Expand query tokens with configured synonyms (query-side vocabulary fix).
        # E.g. "college" → also scores against "education", "university".
        if self._query_synonyms:
            expanded = list(query_tokens)
            for t in query_tokens:
                if t in self._query_synonyms:
                    expanded.extend(self._query_synonyms[t])
            query_tokens = expanded

        if not query_tokens:
            return []

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
        return scores[:top_k]

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
    # Broad "what do you do / tell me about yourself" questions land on the
    # Summary, which names every current track, instead of on whichever Maersk
    # project happens to share a word with the question.
    "Summary":      ["yourself", "about", "do", "doing", "overview", "intro",
                     "introduce", "who", "currently", "nowadays", "background",
                     "working", "lately", "recently"],
    # The role header names both current tracks, so "current role" lands there
    # rather than on one project. "#" = this heading only, not its children.
    "#Maersk":      ["current", "recent", "latest", "now", "today", "role"],
    "Payments automation": ["p2r", "payment", "payments", "invoices", "ocr",
                            "scale", "production", "reliability"],
    "Shipment CoCaptain":  ["cocaptain", "copilot", "insights", "finance",
                            "agent", "agentic"],
    "Patent":       ["patent", "patented", "invention", "ip"],
    "#Side projects": ["working", "building", "currently", "cooking", "stove",
                       "weekends", "outside"],
    "AI-first org": ["leadership", "hiring", "fde", "workshop", "strategy"],
    "Hike":         ["voice", "bot", "call", "phone", "sip", "outreach"],
    "Mphasis":      ["research", "lab", "enterprise", "sagemaker", "marketplace"],
    "Skills":       ["know", "familiar", "technologies", "stack", "tools", "tech"],
    "Achievements": ["won", "award", "prize", "recognition", "competition",
                     "hackathon", "medal", "kaggle"],
    "Projects":     ["built", "made", "created", "side", "personal", "hobby"],
    "Coursework":   ["studied", "learned", "course", "class", "subject"],
    "Misc":         ["volunteer", "community", "social", "club", "extracurricular"],
}

# Function words that carry no topic. "do", "who" and "about" are kept on
# purpose: the Summary is tagged with them so broad questions find it.
QUERY_STOPWORDS: frozenset[str] = frozenset("""
    a an the and or but if so of to in on at by for from with as into onto
    is are was were be been being am i me my mine you your yours we our us
    it its this that these those there here what which whom whose when where
    why how can could would should will shall may might must does did done
    have has had having not no yes just really very also tell give show please
    any some anything something all more most much many lot bit kind sort like
    hey hi hello ok okay um uh well then than too let lets get got go going
    day days per
""".split())

RESUME_QUERY_SYNONYMS: dict[str, list[str]] = {
    "college":  ["education", "university"],
    "school":   ["education"],
    "job":      ["experience"],
    "ml":       ["machine", "learning"],
    "nlp":      ["natural", "language", "processing"],
    "ai":       ["artificial", "intelligence"],
    "llm":      ["language", "model"],
    "cv":       ["computer", "vision"],
    "p2r":      ["pay", "release"],
    "captain":  ["cocaptain"],
    "working":  ["currently"],
    "building": ["currently"],
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


def cooking_overview(cooking_dir: Path) -> str:
    """A "## Side projects in progress" section from content/cooking, one line
    per project in the /cooking page's order (_order.txt, top = latest), so
    "what are you working on" can cover side projects as well as work.
    Generated at startup, so it never drifts from the page. "" when missing."""
    order_file = cooking_dir / "_order.txt"
    if not order_file.exists():
        return ""
    lines = []
    for slug in order_file.read_text(encoding="utf-8").splitlines():
        slug = slug.strip()
        path = cooking_dir / f"{slug}.md"
        if not slug or slug.startswith("#") or not path.exists():
            continue
        meta, _ = _split_front_matter(path.read_text(encoding="utf-8"))
        title, summary = meta.get("title") or slug, meta.get("summary", "")
        lines.append(f"- **{title}**: {summary}".rstrip(": "))
    if not lines:
        return ""
    return (
        "## Side projects in progress\n\n"
        "Personal projects on the /cooking page of this site, most recent first:\n\n"
        + "\n".join(lines) + "\n"
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
        overview = cooking_overview(resume_path.parent / "cooking")
        _indices["resume"] = ContentIndex(
            str(resume_path),
            label="resume",
            section_tags=RESUME_SECTION_TAGS,
            query_synonyms=RESUME_QUERY_SYNONYMS,
            stopwords=QUERY_STOPWORDS,
            extra_markdown=[("content/cooking", overview)] if overview else None,
        )
    return _indices["resume"]


# Convenience alias used by tests that import ResumeIndex by name
ResumeIndex = ContentIndex


# ─── Knowledge index (own writing, side projects) ──────────────────
# Blog posts, /cooking projects and content/about/*.md (notes in the owner's
# own words). Searched separately from the resume and used only on a strong
# match, so it answers "tell me about keypsake" or "how does quantization
# save memory" without ever crowding out the resume on ordinary questions.

KNOWLEDGE_SUBDIRS = ("blog", "cooking", "about")

# BM25 here runs over a different corpus than the resume, so its scores are
# on their own scale. Calibrated in tests/test_resume_context.py: topic
# questions ("what is keypsake", "on-device LLMs on android") clear it;
# resume questions and small talk don't.
KNOWLEDGE_SCORE_THRESHOLD = float(os.environ.get("KNOWLEDGE_SCORE_THRESHOLD", "6.0"))
# Lower bar when the question names the post or project itself ("what is
# keypsake"): one rare word scores ~5, but naming the title is unambiguous.
KNOWLEDGE_NAMED_THRESHOLD = 3.0
# content/about notes are short, curated and carry keyword comments, so a
# plain "any hobbies?" (~4.8) should reach them; resume questions and small
# talk stay under ~3.5 against them (see tests).
KNOWLEDGE_NOTES_THRESHOLD = 4.0

# On top of QUERY_STOPWORDS: words that are fine resume signals but say
# nothing about which post or project a question is about.
KNOWLEDGE_STOPWORDS: frozenset[str] = QUERY_STOPWORDS | frozenset("""
    do who about you yourself work worked working job role build built make
    made use used using think know project projects thing things stuff
    experience company current currently now anywhere recently
""".split())

# Questions made only of stopwords whose meaning is still clear: the matching
# word is appended to the query before lookup.
KNOWLEDGE_PHRASES = (
    (re.compile(r"\bwhere\b.*\b(you|u|you're)\s+(from|grow up|grew up)\b", re.I), "hometown"),
    (re.compile(r"\b(what else do (you|u) do|(outside|apart from|besides|other than) (of )?work|just work)\b", re.I), "hobbies"),
)

# A knowledge hit is a supplement, so it is capped: one section, trimmed.
KNOWLEDGE_MAX_CHARS = 1200


def content_dir_candidates(here: Path | None = None) -> list[Path]:
    """Where content/ lives: KNOWLEDGE_CONTENT_DIR, then next to this file
    (Docker, /app/content), then the repo root (local)."""
    here = (here or Path(__file__).resolve().parent)
    ordered: list[Path] = []
    env = os.environ.get("KNOWLEDGE_CONTENT_DIR", "").strip()
    if env:
        ordered.append(Path(env))
    ordered += [here / "content", here.parent / "content"]
    return ordered


def get_knowledge_index() -> "ContentIndex | None":
    """The knowledge index singleton, or None when there is nothing to index
    (a deploy without content/blog etc. must still answer from the resume)."""
    if "knowledge" not in _indices:
        sources: list[str] = []
        for base in content_dir_candidates():
            dirs = [base / d for d in KNOWLEDGE_SUBDIRS if (base / d).is_dir()]
            if dirs:
                sources = [str(d) for d in dirs]
                break
        index = None
        if sources:
            index = ContentIndex(sources, label="knowledge", stopwords=KNOWLEDGE_STOPWORDS)
            if not index.sections:
                index = None
        _indices["knowledge"] = index
    return _indices["knowledge"]


def _clears_bar(index, query_tokens: set, score: float, section, threshold: float) -> bool:
    if Path(section.source_file).parent.name == "about":
        # Notes are short, so one common word ("pay", "honestly", "right")
        # scores high against them. They count only when the question shares
        # a word with the note's heading or keyword line.
        anchors = set(index._tokenize(section.heading + " " + section.keywords))
        return score >= min(threshold, KNOWLEDGE_NOTES_THRESHOLD) and bool(anchors & query_tokens)
    title_tokens = set(index._tokenize(section.path.split(" > ")[0]))
    named = bool(title_tokens & query_tokens)
    return score >= threshold or (named and score >= KNOWLEDGE_NAMED_THRESHOLD)


def knowledge_lookup(query: str, threshold: float | None = None) -> "tuple[str, float]":
    """The best knowledge section (of the top 3) for `query` that clears its
    bar, else ("", best score). Never falls back to full text."""
    index = get_knowledge_index()
    if index is None:
        return "", 0.0
    threshold = KNOWLEDGE_SCORE_THRESHOLD if threshold is None else threshold
    query = " ".join([query] + [word for rx, word in KNOWLEDGE_PHRASES if rx.search(query)])
    top = index.search_sections(query, top_k=3)
    if not top:
        return "", 0.0
    query_tokens = set(index.query_tokens(query))
    hit = next(((sc, sec) for sc, sec in top if _clears_bar(index, query_tokens, sc, sec, threshold)), None)
    if hit is None:
        return "", top[0][0]
    score, section = hit
    context = f"[{section.path}]\n{section.content}"
    if len(context) > KNOWLEDGE_MAX_CHARS:
        context = context[:KNOWLEDGE_MAX_CHARS].rsplit(" ", 1)[0] + " ..."
    return context, score


# How a knowledge hit is shown to the model, in the terminal and on voice.
# Framed as optional so a loosely related hit doesn't hijack the answer.
KNOWLEDGE_BLOCK = (
    "\n\nPossibly relevant, from my own notes, blog posts and side projects (use it only "
    "if the question is actually about this):\n{context}"
)


def knowledge_block(query: str) -> str:
    """KNOWLEDGE_BLOCK for `query`, or "" when nothing clears the bar."""
    context, _ = knowledge_lookup(query)
    return KNOWLEDGE_BLOCK.format(context=context) if context else ""
