"""
save_program_md: persist collected program data as a structured Markdown file.

Output path: schools/{school-slug}/{program-slug}.md

The files are designed to be fed as context ("skills") to an LLM during the
application process — each section maps directly to a field the LLM will need
when helping draft SOPs, compare programs, or check eligibility.
"""

from __future__ import annotations
import re
from datetime import date
from pathlib import Path
from models import ProgramInfo, ApplicationExample

_SCHOOLS_DIR = Path(__file__).parent.parent / "schools"


def _slugify(text: str) -> str:
    """'Stanford University' → 'stanford-university'"""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text.strip("-")


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
    """
    school_dir = _SCHOOLS_DIR / _slugify(info.school)
    school_dir.mkdir(parents=True, exist_ok=True)
    out_path = school_dir / f"{_slugify(info.program)}.md"

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

    lines += [
        "",
        "## Funding",
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
                    f"**Source:** {ex.source_url}",
                    "",
                    ex.content_summary,
                    "",
                ]

        if stats:
            lines += ["## Admission Statistics", ""]
            for ex in stats:
                lines += [
                    f"### Source: {ex.source_url}",
                    "",
                    ex.content_summary,
                    "",
                ]

    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path
