"""scripts/summarize_field.py (P21): field-test CSV -> evals/field.md.

Driven as a CLI in a subprocess: it is a repo-root script with no `app` imports, and the
thing that must keep working is the command in CLAUDE.md, not an internal function.
"""

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "summarize_field.py"

HEADER = (
    "date,category,rarity,est_minutes,elapsed_seconds,screen_seconds,"
    "screen_share,verification_method,source,voice"
)
# Synthetic field test: 4 quests over 3 days, one of them from the fallback engine.
ROWS = [
    "2026-10-01,naturalist,common,20,1500,60,0.0400,photo,llm,true",
    "2026-10-01,explorer,rare,45,3000,600,0.2000,checkin,llm,true",
    "2026-10-02,foodie,common,15,600,30,0.0500,honor,fallback,false",
    "2026-10-03,mindful,common,30,1200,36,0.0300,photo,llm,true",
]


def write_csv(path: Path, rows: list[str], header: str = HEADER) -> Path:
    path.write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")
    return path


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True, cwd=REPO
    )


@pytest.fixture
def summary(tmp_path: Path) -> str:
    csv = write_csv(tmp_path / "field.csv", ROWS)
    out = tmp_path / "field.md"
    proc = run(str(csv), "--out", str(out))
    assert proc.returncode == 0, proc.stderr
    return out.read_text(encoding="utf-8")


def test_writes_a_markdown_table_the_story_page_can_parse(summary: str) -> None:
    # build_story_data.ts takes the FIRST markdown table: col 1 = label, col 2 = value.
    lines = [line for line in summary.splitlines() if line.startswith("|")]
    assert lines[0] == "| Metric | Value |"
    assert lines[1] == "| --- | --- |"
    rows = dict(
        (c[0].strip(), c[1].strip()) for c in (line.strip("|").split("|") for line in lines[2:])
    )
    assert rows["Quests completed"] == "4"
    assert rows["Days with a quest"] == "3"
    assert rows["Minutes outside"] == "105"  # (1500+3000+600+1200)/60
    assert rows["Median quest length"] == "23 min"  # median of 25, 50, 10, 20


def test_reports_screen_share_voice_and_fallback_rates(summary: str) -> None:
    rows = dict(
        (c[0].strip(), c[1].strip())
        for c in (
            line.strip("|").split("|") for line in summary.splitlines() if line.count("|") >= 2
        )
    )
    assert rows["Median screen share"] == "5%"  # median of 4, 20, 5, 3
    assert rows["p90 screen share"] == "20%"
    assert rows["Quests under 10% screen"] == "75%"
    assert rows["Voice on"] == "75%"
    assert rows["Fallback quests (no model)"] == "25%"
    assert rows["Verified by photo"] == "50%"


def test_marks_the_file_as_generated_and_cites_its_source(summary: str) -> None:
    assert "scripts/summarize_field.py" in summary
    assert "do not hand-edit" in summary
    assert "field.csv" in summary
    assert "No coordinates are recorded." in summary


def test_derives_screen_share_when_the_column_is_blank(tmp_path: Path) -> None:
    csv = write_csv(tmp_path / "f.csv", ["2026-10-01,explorer,common,20,1000,250,,honor,llm,true"])
    out = tmp_path / "f.md"
    assert run(str(csv), "--out", str(out)).returncode == 0
    assert "| Median screen share | 25% |" in out.read_text(encoding="utf-8")


def test_counts_a_quest_once_across_overlapping_exports(tmp_path: Path) -> None:
    first = write_csv(tmp_path / "a.csv", ROWS[:2])
    second = write_csv(tmp_path / "b.csv", ROWS)  # a later export of the same log
    out = tmp_path / "f.md"
    proc = run(str(first), str(second), "--out", str(out))
    assert proc.returncode == 0, proc.stderr
    assert "| Quests completed | 4 |" in out.read_text(encoding="utf-8")
    assert "duplicate" in proc.stderr


def test_skips_unusable_rows_and_says_so(tmp_path: Path) -> None:
    csv = write_csv(tmp_path / "f.csv", [ROWS[0], "2026-10-02,foodie,common,15,,30,,honor,llm,x"])
    out = tmp_path / "f.md"
    proc = run(str(csv), "--out", str(out))
    assert proc.returncode == 0
    text = out.read_text(encoding="utf-8")
    assert "| Quests completed | 1 |" in text
    assert "Rows skipped: 1" in text


def test_a_row_with_no_source_or_voice_omits_those_rates(tmp_path: Path) -> None:
    csv = write_csv(tmp_path / "f.csv", ["2026-10-01,explorer,common,20,1000,250,,honor,,"])
    out = tmp_path / "f.md"
    assert run(str(csv), "--out", str(out)).returncode == 0
    text = out.read_text(encoding="utf-8")
    assert "Fallback quests" not in text
    assert "Voice on" not in text


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    csv = write_csv(tmp_path / "f.csv", ROWS)
    out = tmp_path / "nope.md"
    proc = run(str(csv), "--out", str(out), "--dry-run")
    assert proc.returncode == 0
    assert "Quests completed" in proc.stdout
    assert not out.exists()


def test_rejects_a_csv_without_the_expected_columns(tmp_path: Path) -> None:
    csv = write_csv(tmp_path / "f.csv", ["2026-10-01,20"], header="date,minutes")
    proc = run(str(csv), "--out", str(tmp_path / "f.md"))
    assert proc.returncode != 0
    assert "elapsed_seconds" in proc.stderr


def test_no_rows_is_an_error_not_an_empty_summary(tmp_path: Path) -> None:
    csv = write_csv(tmp_path / "f.csv", [])
    out = tmp_path / "f.md"
    proc = run(str(csv), "--out", str(out))
    assert proc.returncode == 1
    assert not out.exists()


def test_missing_file_exits_two(tmp_path: Path) -> None:
    proc = run(str(tmp_path / "ghost.csv"), "--out", str(tmp_path / "f.md"))
    assert proc.returncode == 2
    assert "No such file" in proc.stderr
