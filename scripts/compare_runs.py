"""Compare finished investigations side by side, from what each saved: the numbers used to
compare the researcher agent with the fixed rounds (AG1b-AC8). It reads only saved files
and makes no network or model calls.

Usage: uv run python -m scripts.compare_runs <id> [<id> ...] [--data-dir var]
"""

import argparse
import sys
from collections.abc import Sequence

from lantern.models import Investigation
from lantern.store import Store

COLUMNS = (
    "Run",
    "Question",
    "Mode",
    "Status",
    "Answered",
    "Items",
    "Corroborated",
    "Claims",
    "Pages",
    "Posts",
    "Records",
    "Links",
    "Tokens",
    "Minutes",
)


def row(inv: Investigation) -> list[str]:
    usage = inv.usage
    answered = sum(finding.status == "answered" for finding in inv.findings)
    minutes = ""
    if inv.finished_at is not None:
        minutes = f"{(inv.finished_at - inv.created_at).total_seconds() / 60:.1f}"
    return [
        inv.id,
        inv.brief[:48],
        "agent" if usage.research_steps else "fixed",
        inv.status,
        f"{answered}/{len(inv.questions)}",
        str(len(inv.items)),
        str(sum(item.status == "corroborated" for item in inv.items)),
        str(len(inv.claims)),
        str(usage.pages_fetched),
        str(usage.posts_saved),
        str(sum(source.kind == "record" for source in inv.sources)),
        str(len(inv.links)),
        f"{usage.tokens_in + usage.tokens_out:,}",
        minutes,
    ]


def table(investigations: Sequence[Investigation]) -> str:
    """A Markdown table, one row per investigation, in the order given."""
    lines = [
        "| " + " | ".join(COLUMNS) + " |",
        "|" + "---|" * len(COLUMNS),
        *("| " + " | ".join(row(inv)) + " |" for inv in investigations),
    ]
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare saved investigations side by side")
    parser.add_argument("ids", nargs="+", help="investigation ids, as in var/investigations")
    parser.add_argument("--data-dir", default="var", help="Lantern's data folder")
    arguments = parser.parse_args(argv)
    store = Store(arguments.data_dir)
    found = [(run_id, store.load(run_id)) for run_id in arguments.ids]
    missing = [run_id for run_id, inv in found if inv is None]
    if missing:
        sys.stderr.write(f"No saved investigation with id {', '.join(missing)}.\n")
        return 1
    sys.stdout.write(table([inv for _, inv in found if inv is not None]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
