from __future__ import annotations
from pydantic import BaseModel


class SearchResult(BaseModel):
    school: str
    program: str
    url: str
    title: str
    description: str


class LanguageRequirements(BaseModel):
    toefl_min: int | None = None
    ielts_min: float | None = None
    english_institution_waiver: bool | None = None  # None = not found on page
    other_tests: list[str] = []   # e.g. ["Duolingo: 120+", "PTE Academic: 65+"]
    notes: str = ""


class Tuition(BaseModel):
    local: str | None = None           # annual cost for domestic/local students
    international: str | None = None   # annual cost for international/non-local students
    notes: str = ""                    # e.g. currency, per-credit vs flat, fee waivers


class ProgramInfo(BaseModel):
    school: str
    program: str
    url: str
    deadline: str | None = None
    language_requirements: LanguageRequirements = LanguageRequirements()
    tuition: Tuition = Tuition()
    funding: str = ""
    length_years: float | None = None
    courses: list[str] = []


class ApplicationExample(BaseModel):
    school: str
    program: str
    type: str  # "SOP" | "personal_statement" | "admission_stats"
    source_url: str
    content_summary: str
