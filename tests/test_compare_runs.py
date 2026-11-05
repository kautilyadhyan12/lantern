"""The run comparison reads saved investigations only and prints one row per run."""

from datetime import timedelta

from lantern.models import Finding, Investigation, Item, Question, Source, now
from lantern.store import Store
from scripts.compare_runs import main, table


def saved(store, run_id, *, agent):
    inv = Investigation(id=run_id, brief="What happened in the district floods?", status="done")
    inv.finished_at = inv.created_at + timedelta(minutes=3)
    inv.questions = [Question(ref="Q1", text="What happened?"), Question(ref="Q2", text="Who?")]
    inv.findings = [Finding(question_ref="Q1", status="answered", answer="Floods.")]
    inv.items = [
        Item(
            question_ref="Q2",
            name="Camp",
            summary="s",
            claim_refs=["C1"],
            origins=["a", "b"],
            best_grade="B",
            status="corroborated",
        )
    ]
    inv.sources = [
        Source(
            ref="S1",
            url="https://ofac.example",
            domain="ofac.example",
            kind="record",
            fetched_at=now(),
            sha256="x",
            text_sha256="y",
            size=1,
            reliability="A",
            reliability_reason="r",
        )
    ]
    inv.usage.tokens_in, inv.usage.tokens_out = 30_000, 1_234
    inv.usage.research_steps = 4 if agent else 0
    store.save(inv)
    return inv


def test_the_table_has_one_row_per_run_in_order(tmp_path):
    store = Store(tmp_path)
    runs = [saved(store, "aaaaaaaaaaaa", agent=False), saved(store, "bbbbbbbbbbbb", agent=True)]
    lines = table(runs).splitlines()
    assert lines[0].startswith("| Run | Question | Mode | Status | Answered | Items |")
    assert lines[2].startswith(
        "| aaaaaaaaaaaa | What happened in the district floods? | fixed | done"
    )
    assert "| 1/2 | 1 | 1 |" in lines[3]
    assert lines[3].endswith("| 1 | 0 | 31,234 | 3.0 |")
    assert "| agent |" in lines[3]


def test_unknown_ids_are_reported(tmp_path, capsys):
    store = Store(tmp_path)
    saved(store, "aaaaaaaaaaaa", agent=True)
    assert main(["aaaaaaaaaaaa", "--data-dir", str(tmp_path)]) == 0
    assert "| aaaaaaaaaaaa |" in capsys.readouterr().out
    assert main(["aaaaaaaaaaaa", "missing", "--data-dir", str(tmp_path)]) == 1
    assert "No saved investigation with id missing." in capsys.readouterr().err
