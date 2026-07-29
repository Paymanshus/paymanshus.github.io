"""
Tests for scripts/sync_resume.py — pure helpers only (no Gemini / no network).

Run: cd <repo-root> && agent/.venv/bin/python -m pytest scripts/test_sync_resume.py -q
"""

import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sync_resume as sr  # noqa: E402


def test_sha256_matches_hashlib(tmp_path):
    f = tmp_path / "a.pdf"
    f.write_bytes(b"hello pdf bytes")
    assert sr._sha256(f) == hashlib.sha256(b"hello pdf bytes").hexdigest()


def test_find_pdf_explicit_relative(monkeypatch):
    # An explicit --pdf that exists should resolve against the repo root.
    rel = sr.ASSETS_DIR.glob("*.pdf")
    first = next(rel, None)
    if first is None:
        pytest.skip("no PDF asset present")
    got = sr._find_pdf(str(first))
    assert got == first.resolve()


def test_find_pdf_missing_explicit_exits():
    with pytest.raises(SystemExit):
        sr._find_pdf("does/not/exist.pdf")


def test_print_diff_detects_no_change(capsys):
    assert sr._print_diff("same\n", "same\n") is False
    out = capsys.readouterr().out
    assert "No differences" in out


def test_print_diff_detects_change(capsys):
    assert sr._print_diff("old line\n", "new line\n") is True
    out = capsys.readouterr().out
    assert "-old line" in out and "+new line" in out


def test_model_chain_has_fallbacks():
    # Mirror of token_server: primary + rolling alias + explicit fallback.
    assert "gemini-flash-lite-latest" in sr.MODEL_CHAIN
    assert len(sr.MODEL_CHAIN) >= 3


def test_paths_point_into_repo():
    assert sr.RESUME_MD.name == "resumedump.md"
    assert sr.RESUME_MD.parent.name == "content"
    assert sr.HASH_CACHE.name == ".resume_pdf_hash"


# ─── Change-set application ─────────────────────────────────────────
# This is the machinery that edits the owner's hand-formatted markdown, so the
# bar is: additive or in-place only, exact anchors, and anything uncertain is
# rejected rather than guessed.

SAMPLE = """\
# Paymanshu Sharma

## Experience

### Maersk — *Machine Learning Engineer*
**April 2025 – Present | Bangalore, India**
- Built **agentic AI** insight systems.
- Shipped a LangGraph pipeline.

### Hike — *Machine Learning Engineer*
**December 2024 – April 2025 | Remote**
- Built a voice bot.

## Education
- B.Tech, Some University
"""


def test_list_anchors_returns_every_heading():
    anchors = sr.list_anchors(SAMPLE)
    assert "# Paymanshu Sharma" in anchors
    assert "## Experience" in anchors
    assert "### Maersk — *Machine Learning Engineer*" in anchors
    assert all(a.startswith("#") for a in anchors)


def test_add_bullet_appends_within_the_right_section():
    out, applied, rejected = sr.apply_changeset(SAMPLE, [
        {"action": "add_bullet",
         "anchor": "### Maersk — *Machine Learning Engineer*",
         "text": "- Led **RAG** evaluation work."},
    ])
    assert rejected == [] and len(applied) == 1
    lines = out.splitlines()
    i = lines.index("- Led **RAG** evaluation work.")
    # Must land after Maersk's last bullet and before the next role.
    assert lines[i - 1] == "- Shipped a LangGraph pipeline."
    assert "### Hike — *Machine Learning Engineer*" in lines[i + 1:]


def test_unknown_anchor_is_rejected_not_guessed():
    out, applied, rejected = sr.apply_changeset(SAMPLE, [
        {"action": "add_bullet", "anchor": "### Maersk", "text": "- nope"},
    ])
    assert out == SAMPLE, "a rejected change must not touch the file"
    assert applied == []
    assert "anchor not found" in rejected[0]


def test_only_the_targeted_lines_change():
    """The whole point of the rewrite: everything the model didn't ask to change
    must survive byte-for-byte."""
    out, applied, _ = sr.apply_changeset(SAMPLE, [
        {"action": "add_bullet", "anchor": "## Education", "text": "- M.S., Elsewhere"},
    ])
    before, after = SAMPLE.splitlines(), out.splitlines()
    added = [l for l in after if l not in before]
    removed = [l for l in before if l not in after]
    assert added == ["- M.S., Elsewhere"]
    assert removed == []


def test_update_bullet_replaces_in_place():
    out, applied, rejected = sr.apply_changeset(SAMPLE, [
        {"action": "update_bullet",
         "anchor": "### Maersk — *Machine Learning Engineer*",
         "find": "LangGraph",
         "text": "- Shipped a **LangGraph + ReAct** pipeline."},
    ])
    assert rejected == [] and len(applied) == 1
    assert "- Shipped a **LangGraph + ReAct** pipeline." in out
    assert "- Shipped a LangGraph pipeline." not in out
    assert len(out.splitlines()) == len(SAMPLE.splitlines())


def test_update_bullet_rejects_ambiguous_find():
    out, _, rejected = sr.apply_changeset(SAMPLE, [
        {"action": "update_bullet",
         "anchor": "### Maersk — *Machine Learning Engineer*",
         "find": "-", "text": "- collapsed"},
    ])
    assert out == SAMPLE
    assert "matched 2 lines" in rejected[0]


def test_update_bullet_rejects_find_outside_its_section():
    """'find' is scoped to the anchor's own block, so a substring that only
    exists elsewhere must not be silently edited."""
    out, _, rejected = sr.apply_changeset(SAMPLE, [
        {"action": "update_bullet",
         "anchor": "### Maersk — *Machine Learning Engineer*",
         "find": "voice bot", "text": "- wrong section"},
    ])
    assert out == SAMPLE
    assert "matched nothing" in rejected[0]


def test_add_role_inserts_a_subsection():
    out, applied, rejected = sr.apply_changeset(SAMPLE, [
        {"action": "add_role", "anchor": "## Experience",
         "heading": "### NewCo — *Staff Engineer*",
         "bullets": ["- Did a thing.", "- Did another thing."]},
    ])
    assert rejected == [] and len(applied) == 1
    lines = out.splitlines()
    i = lines.index("### NewCo — *Staff Engineer*")
    assert lines[i + 1] == "- Did a thing."
    # Appended to Experience, so it must still precede the next H2.
    assert "## Education" in lines[i:]


def test_add_role_rejects_heading_not_deeper_than_anchor():
    out, _, rejected = sr.apply_changeset(SAMPLE, [
        {"action": "add_role", "anchor": "## Experience",
         "heading": "## Sneaky Top Level", "bullets": ["- x"]},
    ])
    assert out == SAMPLE
    assert "must be deeper" in rejected[0]


def test_bullets_must_start_with_dash():
    out, _, rejected = sr.apply_changeset(SAMPLE, [
        {"action": "add_bullet", "anchor": "## Education", "text": "## Not a bullet"},
    ])
    assert out == SAMPLE
    assert "must start with" in rejected[0]


def test_unknown_action_is_rejected():
    out, _, rejected = sr.apply_changeset(SAMPLE, [
        {"action": "delete_section", "anchor": "## Education"},
    ])
    assert out == SAMPLE
    assert "unknown action" in rejected[0]


def test_oversized_changeset_is_refused_wholesale():
    """A model proposing dozens of edits is rewriting the document one anchor at
    a time — exactly what this design exists to prevent."""
    changes = [
        {"action": "add_bullet", "anchor": "## Education", "text": f"- item {i}"}
        for i in range(sr.MAX_CHANGES + 1)
    ]
    out, applied, rejected = sr.apply_changeset(SAMPLE, changes)
    assert out == SAMPLE
    assert applied == []
    assert "--rewrite" in rejected[0]


def test_multiple_changes_do_not_corrupt_each_others_anchors():
    """Changes are applied bottom-up so an earlier insertion can't shift a later
    anchor's index."""
    out, applied, rejected = sr.apply_changeset(SAMPLE, [
        {"action": "add_bullet", "anchor": "## Education", "text": "- late section"},
        {"action": "add_bullet",
         "anchor": "### Maersk — *Machine Learning Engineer*", "text": "- early section"},
    ])
    assert rejected == [] and len(applied) == 2
    lines = out.splitlines()
    assert lines.index("- early section") < lines.index("- late section")
    assert lines[lines.index("- early section") - 1] == "- Shipped a LangGraph pipeline."


# ─── Change-set parsing ─────────────────────────────────────────────

def test_parse_changeset_plain_json():
    assert sr.parse_changeset('[{"action": "add_bullet"}]') == [{"action": "add_bullet"}]


def test_parse_changeset_strips_code_fences():
    assert sr.parse_changeset('```json\n[{"a": 1}]\n```') == [{"a": 1}]


def test_parse_changeset_recovers_from_leading_prose():
    assert sr.parse_changeset('Here you go:\n[{"a": 1}]\nHope that helps!') == [{"a": 1}]


def test_parse_changeset_empty_array_means_up_to_date():
    assert sr.parse_changeset("[]") == []


def test_parse_changeset_rejects_non_array():
    with pytest.raises(ValueError):
        sr.parse_changeset('{"action": "add_bullet"}')


def test_parse_changeset_rejects_garbage():
    with pytest.raises(ValueError):
        sr.parse_changeset("I could not complete this request.")


def test_real_resume_anchors_are_unique():
    """apply_changeset rejects ambiguous anchors, so duplicate headings in the
    real file would make those sections un-editable."""
    if not sr.RESUME_MD.exists():
        pytest.skip("resumedump.md not present")
    anchors = sr.list_anchors(sr.RESUME_MD.read_text(encoding="utf-8"))
    dupes = {a for a in anchors if anchors.count(a) > 1}
    assert not dupes, f"duplicate headings would be unaddressable: {dupes}"


def test_insert_goes_before_trailing_rule():
    """`---` rules close a section, so appended content must land ABOVE them —
    otherwise a new bullet visually belongs to the next section."""
    md = "## A\n- one\n\n---\n\n## B\n- two\n"
    out, applied, rejected = sr.apply_changeset(md, [
        {"action": "add_bullet", "anchor": "## A", "text": "- inserted"},
    ])
    assert rejected == [] and len(applied) == 1
    lines = out.splitlines()
    assert lines.index("- inserted") < lines.index("---")
    assert lines[lines.index("- inserted") - 1] == "- one"


def test_trailing_newline_state_is_preserved():
    """Normalising it would produce a spurious diff line on every run."""
    without = "## A\n- one"
    with_nl = "## A\n- one\n"
    change = [{"action": "add_bullet", "anchor": "## A", "text": "- two"}]
    assert not sr.apply_changeset(without, change)[0].endswith("\n")
    assert sr.apply_changeset(with_nl, change)[0].endswith("\n")
