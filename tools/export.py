"""
save_program_md: persist collected program data as a structured Markdown file.

Output path: schools/{School Full Name}/{Program Full Name}.md

Folder and file names preserve the original casing and spaces — only
characters that are illegal on common filesystems are stripped.
A slug-based deduplication check prevents duplicate school directories
when the agent is called with an abbreviation vs. the full name
(e.g. "HKUST" vs. "Hong Kong University of Science and Technology").
"""

from __future__ import annotations
import re
from datetime import date
from pathlib import Path
from models import ProgramInfo, ApplicationExample

_SCHOOLS_DIR = Path(__file__).parent.parent / "schools"

# Characters that are illegal on macOS / Windows / Linux filesystems.
_UNSAFE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def _safe(text: str) -> str:
    """Strip filesystem-unsafe characters; preserve spaces and original case."""
    return _UNSAFE.sub("", text).strip()


def _slugify(text: str) -> str:
    """Lowercase hyphenated slug used only for deduplication comparisons."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text.strip("-")


def _resolve_school_dir(school: str) -> Path:
    """
    Return the directory for this school.

    If a slug-equivalent directory already exists (e.g. the full-name folder
    was created before and now the agent passes an abbreviation, or vice versa),
    reuse the existing directory to avoid duplicates.
    """
    target_slug = _slugify(school)
    if _SCHOOLS_DIR.exists():
        for d in _SCHOOLS_DIR.iterdir():
            if d.is_dir() and _slugify(d.name) == target_slug:
                return d
    return _SCHOOLS_DIR / _safe(school)


def save_program_md(
    info: ProgramInfo,
    examples: list[ApplicationExample] | None = None,
) -> Path:
    """
    Write (or overwrite) a Markdown file for one program.

    Args:
        info:     Structured program data from collect_program_info.
        examples: Optional list from fetch_application_examples.

    Returns:
        Path of the written file.

    Raises:
        ValueError: if info.url (source) is empty.
    """
    if not info.url:
        raise ValueError(
            f"source URL is required but missing for {info.school} — {info.program}"
        )

    school_dir = _resolve_school_dir(info.school)
    school_dir.mkdir(parents=True, exist_ok=True)
    out_path = school_dir / f"{_safe(info.program)}.md"

    lr = info.language_requirements
    waiver = (
        "Yes" if lr.english_institution_waiver is True
        else "No" if lr.english_institution_waiver is False
        else "Not specified"
    )

    lines: list[str] = [
        "---",
        f"school: {info.school}",
        f"program: {info.program}",
        f"source: {info.url}",
        f"updated: {date.today()}",
        "---",
        "",
        f"# {info.school} — {info.program}",
        "",
        f"> Source: <{info.url}>  ",
        f"> Updated: {date.today()}",
        "",
        "## Application Deadline",
        "",
        info.deadline or "Not available",
        "",
        "## Language Requirements",
        "",
        f"- **TOEFL minimum:** {lr.toefl_min if lr.toefl_min is not None else 'Not available'}",
        f"- **IELTS minimum:** {lr.ielts_min if lr.ielts_min is not None else 'Not available'}",
        f"- **English-institution waiver:** {waiver}",
    ]

    if lr.notes:
        lines.append(f"- **Notes:** {lr.notes}")

    t = info.tuition
    lines += [
        "",
        "## Tuition & Funding",
        "",
        "### Tuition",
        f"- **Local / domestic:** {t.local or 'Not available'}",
        f"- **International / non-local:** {t.international or 'Not available'}",
    ]
    if t.notes:
        lines.append(f"- **Notes:** {t.notes}")

    lines += [
        "",
        "### Funding",
        "",
        info.funding or "Not available",
        "",
        "## Program Length",
        "",
        (f"{info.length_years} years" if info.length_years else "Not available"),
        "",
        "## Courses",
        "",
    ]

    if info.courses:
        lines += [f"- {c}" for c in info.courses]
    else:
        lines.append("Not listed on official page")

    if examples:
        sops  = [e for e in examples if e.type in ("SOP", "personal_statement")]
        stats = [e for e in examples if e.type == "admission_stats"]

        if sops:
            lines += ["", "## Statements of Purpose / Personal Statements", ""]
            for ex in sops:
                label = "SOP" if ex.type == "SOP" else "Personal Statement"
                lines += [
                    f"### {label}",
                    f"**Source:** <{ex.source_url}>",
                    "",
                    ex.content_summary,
                    "",
                ]

        if stats:
            lines += ["", "## Admission Statistics", ""]
            for ex in stats:
                lines += [
                    f"### Source: <{ex.source_url}>",
                    "",
                    ex.content_summary,
                    "",
                ]

    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path
