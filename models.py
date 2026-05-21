from __future__ import annotations
from pydantic import BaseModel, HttpUrl


class SearchResult(BaseModel):
    school: str
    program: str
    url: str
    title: str
    description: str


class LanguageRequirements(BaseModel):
    toefl_min: int | None = None
    ielts_min: float | None = None
    english_institution_waiver: bool = False
    notes: str = ""


class ProgramInfo(BaseModel):
    school: str
    program: str
    url: str
    deadline: str | None = None
    language_requirements: LanguageRequirements = LanguageRequirements()
    funding: str = ""
    length_years: float | None = None
    courses: list[str] = []


class ApplicationExample(BaseModel):
    school: str
    program: str
    type: str  # "SOP" | "personal_statement" | "admission_stats"
    source_url: str
    content_summary: str
