#!/usr/bin/env python3
"""
sync_resume.py — keep content/resumedump.md in sync with the source PDF resume.

The owner maintains ONE resume: the PDF in public/assets/. This script detects
when that PDF changes, extracts its text, and asks an LLM what CHANGED — then
applies those changes itself.

WHY A CHANGE-SET AND NOT A REWRITE
    This script used to send the whole PDF text plus the whole existing markdown
    and ask for a complete regenerated document (~8K output tokens), then
    overwrite the file with whatever came back. That handed ownership of the
    owner's hand-tuned formatting to the model on every single run: headings,
    section order, `---` separators and bold conventions were only preserved
    because the prompt asked nicely.

    Now the model returns a small JSON change-set — "add this bullet under that
    heading" — and Python applies it against anchors that must match exactly.
    Consequences:
      - Formatting is owned by code. Structure cannot drift.
      - Output drops from ~8K tokens to a few hundred, which is what makes a
        free model viable for this at all.
      - The task narrows to "spot what's new", which small models do reliably.
      - Anything referencing an anchor that doesn't exist is REJECTED and
        reported, never guessed at.

    `--rewrite` still does the old full regeneration, for the rare case where the
    resume is genuinely restructured rather than incrementally updated.

MODELS
    Uses llm_models.SYNC_LADDER, which is FREE-ONLY on purpose — this runs a
    handful of times a year, so there is no reason for it to be able to spend
    money. If every free entry fails, the script exits 1 rather than escalating
    to something paid.

USAGE (run inside the agent venv so the LLM deps are available):

    # Dry run — extract, compute a change-set, print a unified diff. Writes only
    # resumedump.md.new.
    cd <repo-root>
    agent/.venv/bin/python scripts/sync_resume.py

    # Apply — overwrite resumedump.md, update the hash cache, run the BM25 suite.
    agent/.venv/bin/python scripts/sync_resume.py --apply

    # Force a regenerate even if the PDF hash is unchanged.
    agent/.venv/bin/python scripts/sync_resume.py --force

    # Full-document regeneration (the old behaviour). Model owns formatting.
    agent/.venv/bin/python scripts/sync_resume.py --rewrite

    # Point at a different PDF explicitly.
    agent/.venv/bin/python scripts/sync_resume.py --pdf path/to/resume.pdf

BEHAVIOR / SAFETY:
  - Change detection: sha256 of the PDF is cached in content/.resume_pdf_hash.
    If unchanged (and no --force), the script exits 0 quietly — safe to wire
    into a dev-server start or a predeploy step.
  - Default run is a DRY RUN: it never overwrites resumedump.md. It writes the
    candidate to resumedump.md.new and prints a diff. Only --apply overwrites.
  - The hash cache is only updated on a successful --apply, so an aborted dry
    run keeps re-detecting the change on the next run.
  - NEVER auto-apply in CI. CI should run the dry run at most (diff as signal).
  - After --apply, the resume_context test suite is run; if the structure
    drifted, those tests fail. The apply is NOT rolled back, so inspect the diff
    and re-run if needed.

Exit codes: 0 = success or no-op; 1 = error (extraction / LLM / validation).
"""

from __future__ import annotations

import argparse
import asyncio
import difflib
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = REPO_ROOT / "content"
RESUME_MD = CONTENT_DIR / "resumedump.md"
RESUME_MD_NEW = CONTENT_DIR / "resumedump.md.new"
HASH_CACHE = CONTENT_DIR / ".resume_pdf_hash"
ASSETS_DIR = REPO_ROOT / "public" / "assets"
AGENT_DIR = REPO_ROOT / "agent"

sys.path.insert(0, str(AGENT_DIR))

# The model ladder now lives in agent/llm_models.py (SYNC_LADDER), shared with
# the terminal and voice paths. MODEL_CHAIN is retained as the plain Gemini
# fallback used when the agent modules aren't importable — e.g. running this
# script outside the agent venv.
MODEL_CHAIN = [
    os.environ.get("RESUME_SYNC_MODEL", "gemini-3.1-flash-lite"),
    "gemini-flash-lite-latest",
    "gemini-3.5-flash",
]

# A model that wants to change more than this many things is not doing an
# incremental update — it is rewriting the document one anchor at a time, which
# is exactly what this rewrite was meant to prevent.
MAX_CHANGES = 40

RESTRUCTURE_SYSTEM = """\
You are a resume-formatting tool. You are given (1) the RAW extracted text of a
resume PDF and (2) an EXAMPLE markdown file showing the exact target structure.

Rewrite the raw text into markdown that matches the EXAMPLE's structure exactly:
- Same heading levels: `#` for the name, `##` for top-level sections
  (Experience, Projects and Research Work, Achievements, Technical Skills,
  Education, Relevant Coursework, Misc. Activities), and one `###` per role
  inside Experience.
- Keep the same section names and the same ordering as the EXAMPLE.
- Keep the same contact line, `---` separators, and bullet / bold conventions.

HARD RULES:
- Preserve every fact, name, date, number, and metric VERBATIM from the RAW
  text. Do not summarize, shorten, round, or invent anything.
- If the RAW text contains something the EXAMPLE has no section for, place it in
  the closest matching section rather than inventing a new heading.
- If a section in the EXAMPLE has no corresponding content in the RAW text, omit
  that section rather than fabricating content.
- Each bullet in the RAW text maps to EXACTLY ONE output bullet. Never duplicate,
  split, or re-phrase a bullet into two. Do not add bullets that are not present
  in the RAW text.
- The EXAMPLE bolds key phrases with **...**. The RAW text has no bold markup, so
  you may re-apply **bold** to the same key technical phrases the EXAMPLE
  emphasizes, but never change the wording to do so.
- Output ONLY the markdown. No code fences, no commentary, no preamble.
"""

RESTRUCTURE_USER = """\
=== EXAMPLE STRUCTURE (match this skeleton exactly) ===
{example}

=== RAW EXTRACTED PDF TEXT (preserve every fact) ===
{raw}

=== OUTPUT ===
Emit the restructured markdown now.
"""

# ─── Change-set mode (default) ─────────────────────────────────────

CHANGESET_SYSTEM = """\
You compare a resume PDF against an existing markdown file and report ONLY what
is missing from the markdown, as a JSON change-set. You never rewrite the
document — a program applies your changes.

Emit a JSON array. Each element is one of:

  {"action": "add_bullet", "anchor": "<exact heading line>", "text": "- ..."}
      Append one bullet to the end of that heading's section.

  {"action": "update_bullet", "anchor": "<exact heading line>",
   "find": "<distinctive substring of the existing line>", "text": "- ..."}
      Replace one existing bullet under that heading.

  {"action": "add_role", "anchor": "<exact ## section heading>",
   "heading": "### Company — *Title*", "bullets": ["- ...", "- ..."]}
      Append a new role/subsection to the end of that section.

HARD RULES:
- `anchor` MUST be copied character-for-character from the ANCHORS list below.
  Anything else is rejected outright.
- Preserve every fact, name, date, number and metric VERBATIM from the PDF text.
  Never summarise, round, or invent.
- Every `text` value must start with "- ".
- Match the existing bold conventions: **bold** the same kinds of key technical
  phrases the surrounding bullets bold.
- Report ONLY genuine differences. If the markdown already covers something,
  say nothing about it.
- If the markdown is already up to date, emit exactly: []
- Output ONLY the JSON array. No code fences, no commentary.
"""

CHANGESET_USER = """\
=== ANCHORS (the only valid values for "anchor") ===
{anchors}

=== CURRENT MARKDOWN ===
{current}

=== RAW EXTRACTED PDF TEXT ===
{raw}

=== OUTPUT ===
Emit the JSON change-set now.
"""


def _heading_level(line: str) -> int:
    """Markdown heading level, or 0 if the line isn't a heading."""
    m = re.match(r"^(#{1,6})\s+\S", line)
    return len(m.group(1)) if m else 0


def list_anchors(markdown: str) -> list[str]:
    """Every heading line, verbatim — the closed set of legal anchors."""
    return [ln.rstrip() for ln in markdown.splitlines() if _heading_level(ln)]


def _find_anchor(lines: list[str], anchor: str) -> int:
    """Index of the unique line equal to `anchor`.

    Raises ValueError when missing or ambiguous. Both are rejections rather than
    best-effort guesses: applying a change to the wrong section silently corrupts
    the file, and this runs unattended enough that a wrong guess could ship.
    """
    anchor = anchor.strip()
    hits = [i for i, ln in enumerate(lines) if ln.strip() == anchor]
    if not hits:
        raise ValueError(f"anchor not found: {anchor!r}")
    if len(hits) > 1:
        raise ValueError(f"anchor is ambiguous ({len(hits)} matches): {anchor!r}")
    return hits[0]


def _block_end(lines: list[str], start: int) -> int:
    """Index just past the section owned by the heading at `start`.

    The section ends at the next heading of the same or higher level, or EOF.
    """
    level = _heading_level(lines[start])
    for i in range(start + 1, len(lines)):
        lvl = _heading_level(lines[i])
        if lvl and lvl <= level:
            return i
    return len(lines)


def _insert_point(lines: list[str], start: int) -> int:
    """Where to append inside a section.

    Walks back past trailing blank lines AND trailing `---` rules. The rules are
    decorative separators that belong at the *end* of a section, so appending
    after them would put new content on the far side of the divider — visually
    part of the next section.
    """
    i = _block_end(lines, start)
    while i > start + 1 and (
        not lines[i - 1].strip() or re.match(r"^-{3,}\s*$", lines[i - 1])
    ):
        i -= 1
    return i


def _validate_text(text: str) -> str:
    text = (text or "").rstrip()
    if not text.startswith("- "):
        raise ValueError(f"bullet must start with '- ': {text[:60]!r}")
    if "\n" in text:
        raise ValueError("bullet must be a single line")
    return text


def apply_changeset(markdown: str, changes: list) -> tuple[str, list[str], list[str]]:
    """Apply a change-set. Returns (new_markdown, applied, rejected).

    Changes are applied bottom-up (by anchor position, descending) so that
    inserting into an earlier section can't invalidate a later section's index.
    Every change is additive or in-place: nothing here can delete content.
    """
    lines = markdown.splitlines()
    applied: list[str] = []
    rejected: list[str] = []

    if len(changes) > MAX_CHANGES:
        rejected.append(
            f"refusing {len(changes)} changes (max {MAX_CHANGES}) — that is a "
            f"rewrite, not an update; re-run with --rewrite if that is intended"
        )
        return markdown, applied, rejected

    # Resolve anchors first so ordering is computed against the original file.
    resolved = []
    for change in changes:
        if not isinstance(change, dict):
            rejected.append(f"not an object: {str(change)[:60]}")
            continue
        try:
            idx = _find_anchor(lines, str(change.get("anchor", "")))
        except ValueError as e:
            rejected.append(str(e))
            continue
        resolved.append((idx, change))

    for idx, change in sorted(resolved, key=lambda x: x[0], reverse=True):
        action = change.get("action")
        anchor = str(change.get("anchor", "")).strip()
        try:
            if action == "add_bullet":
                text = _validate_text(change.get("text", ""))
                lines.insert(_insert_point(lines, idx), text)
                applied.append(f"add_bullet under {anchor!r}: {text[:60]}")

            elif action == "update_bullet":
                find = str(change.get("find", "")).strip()
                if not find:
                    raise ValueError("update_bullet requires a non-empty 'find'")
                text = _validate_text(change.get("text", ""))
                end = _block_end(lines, idx)
                hits = [i for i in range(idx + 1, end) if find in lines[i]]
                if not hits:
                    raise ValueError(f"'find' matched nothing under {anchor!r}: {find[:50]!r}")
                if len(hits) > 1:
                    raise ValueError(f"'find' matched {len(hits)} lines under {anchor!r}")
                old = lines[hits[0]]
                lines[hits[0]] = text
                applied.append(f"update_bullet under {anchor!r}: {old[:40]} → {text[:40]}")

            elif action == "add_role":
                heading = str(change.get("heading", "")).rstrip()
                if _heading_level(heading) == 0:
                    raise ValueError(f"add_role heading is not a heading: {heading[:60]!r}")
                if _heading_level(heading) <= _heading_level(lines[idx]):
                    raise ValueError(
                        f"add_role heading {heading[:40]!r} must be deeper than its anchor"
                    )
                bullets = [_validate_text(b) for b in (change.get("bullets") or [])]
                if not bullets:
                    raise ValueError("add_role requires at least one bullet")
                block = [heading, *bullets, ""]
                lines[_insert_point(lines, idx):_insert_point(lines, idx)] = block
                applied.append(f"add_role under {anchor!r}: {heading[:60]}")

            else:
                raise ValueError(f"unknown action {action!r}")
        except ValueError as e:
            rejected.append(str(e))

    # Preserve the source's trailing-newline state. Normalising it would show up
    # as a spurious diff on every single run, which trains you to skim the diff.
    out = "\n".join(lines)
    if markdown.endswith("\n"):
        out += "\n"
    return out, applied, rejected


def _strip_fences(text: str) -> str:
    """Models add code fences even when told not to."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[: -3]
    return text.strip()


def parse_changeset(raw_output: str) -> list:
    """Parse the model's JSON array, tolerating fences and leading prose."""
    text = _strip_fences(raw_output)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Fall back to the outermost [...] span.
        start, end = text.find("["), text.rfind("]")
        if start == -1 or end <= start:
            raise ValueError(f"no JSON array in model output: {text[:160]!r}")
        data = json.loads(text[start : end + 1])
    if not isinstance(data, list):
        raise ValueError(f"change-set must be a JSON array, got {type(data).__name__}")
    return data


def _load_env() -> None:
    """Load GOOGLE_API_KEY from agent/.env.local if not already in the env."""
    if os.environ.get("GOOGLE_API_KEY"):
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(AGENT_DIR / ".env.local")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _find_pdf(explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit)
        if not p.is_absolute():
            p = (REPO_ROOT / p).resolve()
        if not p.exists():
            sys.exit(f"error: PDF not found: {p}")
        return p
    pdfs = sorted(ASSETS_DIR.glob("*.pdf"))
    if not pdfs:
        sys.exit(f"error: no PDF found in {ASSETS_DIR}")
    if len(pdfs) > 1:
        print(f"note: multiple PDFs found, using {pdfs[0].name}", file=sys.stderr)
    return pdfs[0]


def _extract_text(pdf: Path) -> str:
    try:
        import fitz  # PyMuPDF
    except ImportError:
        sys.exit("error: pymupdf not installed. Run: agent/.venv/bin/python -m pip install pymupdf")
    doc = fitz.open(pdf)
    try:
        pages = [page.get_text("text") for page in doc]
    finally:
        doc.close()
    text = "\n".join(pages).strip()
    if not text:
        sys.exit("error: no text extracted from PDF (is it a scanned image?)")
    return text


def _run_ladder(system: str, user: str, *, max_tokens: int) -> str:
    """Send one prompt down SYNC_LADDER and return the text.

    SYNC_LADDER is free-only by design, so exhausting it exits 1 rather than
    quietly escalating to a paid model — this script should never be able to
    spend money on its own.
    """
    try:
        import llm_context
        import llm_ladder
        import llm_models
    except ImportError as e:
        sys.exit(
            f"error: agent modules not importable ({e}). "
            "Run inside the agent venv: agent/.venv/bin/python scripts/sync_resume.py"
        )

    ctx = llm_context.BuiltContext(
        mode="full_only", system=system, turns=[{"role": "user", "text": user}]
    )

    def _log(entry, outcome):
        if isinstance(outcome, llm_ladder.LLMError):
            print(f"  {entry.label} failed [{outcome.kind}]: {outcome.message[:120]}",
                  file=sys.stderr)
        else:
            print(f"  {entry.label} → {outcome.completion_tokens} tokens", file=sys.stderr)

    print(f"→ asking {[e.label for e in llm_models.SYNC_LADDER]} ...", file=sys.stderr)
    result = asyncio.run(
        llm_ladder.generate(
            ctx,
            ladder=llm_models.SYNC_LADDER,
            surface="sync",
            max_tokens=max_tokens,
            temperature=0.1,
            on_attempt=_log,
        )
    )
    if result is None:
        sys.exit(
            "error: every free model in SYNC_LADDER failed. This script is "
            "deliberately free-only — set SYNC_LADDER if you want to change that."
        )
    return result.text


def _restructure(raw: str, example: str) -> str:
    """Full-document regeneration (--rewrite). The model owns formatting here,
    which is why it is no longer the default."""
    out = _strip_fences(_run_ladder(RESTRUCTURE_SYSTEM,
                                    RESTRUCTURE_USER.format(example=example, raw=raw),
                                    max_tokens=8192))
    if not out:
        sys.exit("error: model returned an empty document")
    return out + "\n"


def _compute_changeset(raw: str, current: str) -> list:
    anchors = list_anchors(current)
    user = CHANGESET_USER.format(
        anchors="\n".join(anchors), current=current, raw=raw
    )
    # A few hundred tokens is plenty for a real change-set, and the cap doubles
    # as a guard against the model drifting back into rewriting the document.
    out = _run_ladder(CHANGESET_SYSTEM, user, max_tokens=1500)
    return parse_changeset(out)


def _print_diff(old: str, new: str) -> bool:
    diff = list(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile="content/resumedump.md (current)",
            tofile="content/resumedump.md (regenerated)",
        )
    )
    if not diff:
        print("No differences — regenerated content matches current resumedump.md.")
        return False
    sys.stdout.writelines(diff)
    if not diff[-1].endswith("\n"):
        print()
    return True


def _run_validation() -> int:
    print("\n→ running resume_context test suite ...", file=sys.stderr)
    proc = subprocess.run(
        [".venv/bin/python", "-m", "pytest", "tests/test_resume_context.py", "-q"],
        cwd=AGENT_DIR,
    )
    if proc.returncode != 0:
        print(
            "\nWARNING: resume_context tests FAILED after apply. The generated "
            "structure likely drifted (section names / heading levels). Inspect "
            "the diff above and tighten the prompt, then re-run.",
            file=sys.stderr,
        )
    else:
        print("Validation passed — section structure preserved.", file=sys.stderr)
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync resumedump.md from the source PDF.")
    parser.add_argument("--apply", action="store_true", help="overwrite resumedump.md (default: dry run)")
    parser.add_argument("--force", action="store_true", help="regenerate even if the PDF hash is unchanged")
    parser.add_argument("--pdf", default=None, help="path to the source PDF (default: public/assets/*.pdf)")
    parser.add_argument(
        "--rewrite", action="store_true",
        help="regenerate the whole document instead of applying a change-set. "
             "Hands formatting ownership to the model — use only for a genuine "
             "restructure, not an incremental update.",
    )
    args = parser.parse_args()

    _load_env()

    pdf = _find_pdf(args.pdf)
    pdf_hash = _sha256(pdf)
    cached = HASH_CACHE.read_text().strip() if HASH_CACHE.exists() else ""

    if pdf_hash == cached and not args.force:
        print(f"PDF unchanged ({pdf.name}) — nothing to do.")
        return 0

    if not RESUME_MD.exists():
        sys.exit(f"error: {RESUME_MD} missing — need it as the formatting example.")

    print(f"PDF: {pdf}  (sha256 {pdf_hash[:12]}…)", file=sys.stderr)
    raw = _extract_text(pdf)
    current = RESUME_MD.read_text(encoding="utf-8")

    if args.rewrite:
        print("MODE: full rewrite — the model owns formatting for this run.",
              file=sys.stderr)
        generated = _restructure(raw, current)
    else:
        changes = _compute_changeset(raw, current)
        if not changes:
            print("\nModel reports no changes: the markdown already covers the PDF.")
            if args.apply:
                HASH_CACHE.write_text(pdf_hash + "\n", encoding="utf-8")
                print("Hash cache updated.", file=sys.stderr)
            return 0

        generated, applied, rejected = apply_changeset(current, changes)

        print(f"\nChange-set: {len(changes)} proposed, {len(applied)} applied, "
              f"{len(rejected)} rejected", file=sys.stderr)
        for line in applied:
            print(f"  + {line}", file=sys.stderr)
        for line in rejected:
            print(f"  ! REJECTED: {line}", file=sys.stderr)
        if rejected and not applied:
            sys.exit(
                "error: every proposed change was rejected. Nothing was written. "
                "This usually means the model invented anchors — inspect the "
                "rejections above."
            )

    RESUME_MD_NEW.write_text(generated, encoding="utf-8")
    print(f"Wrote candidate → {RESUME_MD_NEW}", file=sys.stderr)

    changed = _print_diff(current, generated)

    if not args.apply:
        print(
            "\nDRY RUN — resumedump.md was NOT modified. Review the diff above, "
            "then re-run with --apply to commit.",
            file=sys.stderr,
        )
        return 0

    if not changed:
        # Nothing to write, but still record the hash so we stop re-detecting.
        HASH_CACHE.write_text(pdf_hash + "\n", encoding="utf-8")
        RESUME_MD_NEW.unlink(missing_ok=True)
        print("Applied: no content change; hash cache updated.", file=sys.stderr)
        return 0

    RESUME_MD.write_text(generated, encoding="utf-8")
    RESUME_MD_NEW.unlink(missing_ok=True)
    HASH_CACHE.write_text(pdf_hash + "\n", encoding="utf-8")
    print(f"Applied: {RESUME_MD} overwritten; hash cache updated.", file=sys.stderr)

    return _run_validation()


if __name__ == "__main__":
    sys.exit(main())
