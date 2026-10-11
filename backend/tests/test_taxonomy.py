import re
from pathlib import Path

from app.schemas.compliance import ReviewStatus
from app.schemas.taxonomy import (
    TAXONOMY,
    TAXONOMY_VERSION,
    DarkPatternCategory,
    legal_reference,
)

SQL_PATH = (
    Path(__file__).resolve().parents[2]
    / "database"
    / "migrations"
    / "001_initial_schema.sql"
)


def _sql_enum_values(type_name: str) -> list[str]:
    sql = SQL_PATH.read_text(encoding="utf-8")
    pattern = rf"CREATE TYPE public\.{type_name} AS ENUM \((.*?)\);"
    match = re.search(pattern, sql, flags=re.DOTALL)
    assert match is not None, f"enum {type_name} not found in migration"
    return re.findall(r"'([A-Z_]+)'", match.group(1))


def test_thirteen_categories():
    assert len(DarkPatternCategory) == 13


def test_every_category_has_taxonomy_entry():
    assert set(TAXONOMY) == set(DarkPatternCategory)


def test_annexure_numbers_are_one_to_thirteen_and_unique():
    numbers = sorted(info.annexure_number for info in TAXONOMY.values())
    assert numbers == list(range(1, 14))


def test_category_enum_matches_sql_enum_in_order():
    assert [c.value for c in DarkPatternCategory] == _sql_enum_values(
        "ccpa_dark_pattern_category"
    )


def test_review_status_enum_matches_sql_enum_in_order():
    assert [s.value for s in ReviewStatus] == _sql_enum_values(
        "finding_review_status"
    )


def test_taxonomy_version_matches_sql_default():
    sql = SQL_PATH.read_text(encoding="utf-8")
    assert f"DEFAULT '{TAXONOMY_VERSION}'" in sql


def test_legal_reference_names_item_and_category():
    reference = legal_reference(DarkPatternCategory.BAIT_AND_SWITCH)
    assert "Annexure 1" in reference
    assert "item 7" in reference
    assert "Bait and Switch" in reference


def test_legal_reference_does_not_claim_a_violation():
    for category in DarkPatternCategory:
        assert "violat" not in legal_reference(category).lower()
