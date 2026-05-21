"""
Deterministic completeness validator for ProgramInfo.

Defines the canonical list of required fields, checks a ProgramInfo object
against them, and generates a targeted follow-up prompt so the agent knows
exactly what to search for next.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Callable
from models import ProgramInfo


@dataclass(frozen=True)
class FieldSpec:
    label: str                          # shown to the agent in the follow-up prompt
    is_missing: Callable[[ProgramInfo], bool]


# Every field in this list is considered mandatory.
# The agent will be asked to find any that are absent.
REQUIRED: list[FieldSpec] = [
    FieldSpec(
        label="application deadline",
        is_missing=lambda i: i.deadline is None,
    ),
    FieldSpec(
        label="TOEFL minimum score",
        is_missing=lambda i: i.language_requirements.toefl_min is None,
    ),
    FieldSpec(
        label="IELTS minimum score",
        is_missing=lambda i: i.language_requirements.ielts_min is None,
    ),
    FieldSpec(
        label="English-institution language test waiver policy "
              "(does a degree from an English-taught institution waive the test?)",
        is_missing=lambda i: i.language_requirements.english_institution_waiver is None,
    ),
    FieldSpec(
        label="funding details (RA/TA availability, stipend amounts)",
        is_missing=lambda i: not i.funding,
    ),
    FieldSpec(
        label="program length in years",
        is_missing=lambda i: i.length_years is None,
    ),
]


def missing_fields(info: ProgramInfo) -> list[str]:
    """Return the labels of all required fields absent from this ProgramInfo."""
    return [f.label for f in REQUIRED if f.is_missing(info)]


def follow_up_prompt(info: ProgramInfo, missing: list[str]) -> str:
    """
    Build a targeted follow-up instruction for the agent.
    The agent should call collect_program_info on a more specific page
    and then synthesise a complete answer.
    """
    items = "\n".join(f"  • {m}" for m in missing)
    return (
        f"The data collected for **{info.school} — {info.program}** is incomplete.\n"
        f"The following required fields were not found:\n{items}\n\n"
        f"Search the official domain ({info.url}) for a more specific admissions or "
        f"requirements page. Call collect_program_info on any promising URL, then "
        f"provide a complete answer that includes ALL required fields — "
        f"state 'not available' explicitly for any field that genuinely cannot be found "
        f"after searching."
    )
