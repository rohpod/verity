"""A small valid content tree for the loader and linter tests, as plain dicts per file.

Each test copies it, breaks one thing and checks the linter names that thing. The text is
invented for the tests: it is not verified legal or ISO content.
"""

import copy
from datetime import date
from pathlib import Path

import yaml

VERIFIED = date(2026, 11, 5)
EU_VERSION = "2024/1689 as amended by 2026/1744"
RATIONALE = "The control asks for the same outcome in different words, and goes a little further."


def good_files() -> dict[str, dict]:
    return {
        "frameworks/euaia.yaml": {
            "framework": {
                "slug": "euaia",
                "name": "EU AI Act",
                "source_url": "https://eur-lex.example.org/eu-ai-act",
                "source_version": EU_VERSION,
                "last_verified": VERIFIED,
            },
            "requirements": [
                {
                    "id": "art4",
                    "ref": "Art. 4",
                    "summary": "People who run AI systems support the AI literacy of their staff.",
                    "verified_against": "primary_text",
                },
                {
                    "id": "art9",
                    "ref": "Art. 9",
                    "summary": "A risk management system covers the whole lifecycle.",
                    "verified_against": "primary_text",
                },
                {
                    "id": "art9-2a",
                    "ref": "Art. 9(2)(a)",
                    "parent": "art9",
                    "summary": "Known and foreseeable risks to people are identified.",
                    "verified_against": "primary_text",
                },
                {
                    "id": "art25",
                    "ref": "Art. 25",
                    "summary": "Responsibilities along the AI value chain.",
                    "verified_against": "primary_text",
                },
                {
                    "id": "art50-1",
                    "ref": "Art. 50(1)",
                    "summary": "People are told when they are talking to an AI system.",
                    "verified_against": "primary_text",
                },
            ],
        },
        "frameworks/iso42001.yaml": {
            "framework": {
                "slug": "iso42001",
                "name": "ISO/IEC 42001",
                "source_url": "https://www.iso.example.org/42001",
                "source_version": "ISO/IEC 42001:2023",
                "last_verified": VERIFIED,
                "copyrighted": True,
            },
            "requirements": [
                {
                    "id": "A.6",
                    "ref": "A.6",
                    "summary": "Controls for the AI system lifecycle.",
                    "verified_against": "public_listing",
                    "listing_sources": [
                        "https://one.example.org/iso-42001",
                        "https://two.example.org/iso-42001-annex",
                    ],
                },
                {
                    "id": "A.6.2.4",
                    "ref": "A.6.2.4",
                    "parent": "A.6",
                    "summary": "Verification and validation of the system before release.",
                    "verified_against": "public_listing",
                    "listing_sources": [
                        "https://one.example.org/iso-42001",
                        "https://two.example.org/iso-42001-annex",
                    ],
                },
                {
                    "id": "A.8.2",
                    "ref": "A.8.2",
                    "summary": "Information given to the people who use the system.",
                    "verified_against": "public_listing",
                    "listing_sources": [
                        "https://one.example.org/iso-42001",
                        "https://two.example.org/iso-42001-annex",
                    ],
                },
            ],
        },
        "controls.yaml": {
            "controls": [
                {
                    "code": "VC-001",
                    "title": "AI literacy",
                    "summary": "Staff who work with AI systems get suitable training.",
                    "kind": "organisational",
                    "scope_level": "organisation",
                },
                {
                    "code": "VC-012",
                    "title": "AI interaction disclosure",
                    "summary": "The system tells people they are dealing with an AI.",
                    "kind": "technical",
                    "automatable": True,
                    "scope_level": "system",
                },
                {
                    "code": "VC-014",
                    "title": "Human oversight",
                    "summary": "A named person can review and override the output.",
                    "kind": "organisational",
                    "scope_level": "system",
                },
                {
                    "code": "VC-021",
                    "title": "Risk identification",
                    "summary": "Risks to people are written down and kept up to date.",
                    "kind": "organisational",
                    "scope_level": "system",
                },
            ]
        },
        "mappings/euaia.yaml": {
            "framework": "euaia",
            "mappings": [
                _mapping("art4", "VC-001", "subset_of", 6, "full"),
                _mapping("art9-2a", "VC-021", "subset_of", 7, "full"),
                _mapping("art50-1", "VC-012", "subset_of", 8, "full"),
                {
                    "requirement": "art25",
                    "control": "VC-014",
                    "strm": "no_relationship",
                    "rationale_type": "semantic",
                    "rationale": "Value chain duties are about contracts, not about oversight.",
                },
            ],
        },
        "mappings/iso42001.yaml": {
            "framework": "iso42001",
            "mappings": [
                _mapping("A.6.2.4", "VC-014", "subset_of", 7, "full"),
                _mapping("A.8.2", "VC-012", "intersects_with", 5, "partial"),
            ],
        },
        "rules/obligation_dates.yaml": {
            "dates": [
                {
                    "id": "euaia-example",
                    "date": date(2027, 12, 2),
                    "covers": "An invented date used only by these tests.",
                    "source_url": "https://eur-lex.example.org/eu-ai-act",
                    "last_verified": VERIFIED,
                }
            ]
        },
    }


def _mapping(requirement, control, strm, strength, sufficiency) -> dict:
    return {
        "requirement": requirement,
        "control": control,
        "strm": strm,
        "strength": strength,
        "rationale_type": "semantic",
        "rationale": RATIONALE,
        "sufficiency": sufficiency,
    }


def write_tree(root: Path, files: dict[str, dict]) -> Path:
    for name, data in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
    return root


def broken(mutate) -> dict[str, dict]:
    """The good files, changed by `mutate(files)`."""
    files = copy.deepcopy(good_files())
    mutate(files)
    return files


def requirement(files: dict, framework: str, slug: str) -> dict:
    return next(r for r in files[f"frameworks/{framework}.yaml"]["requirements"] if r["id"] == slug)


def mapping(files: dict, framework: str, slug: str) -> dict:
    return next(
        m for m in files[f"mappings/{framework}.yaml"]["mappings"] if m["requirement"] == slug
    )
