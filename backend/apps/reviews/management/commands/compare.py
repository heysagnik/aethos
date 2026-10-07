from __future__ import annotations

import csv
import sys
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.repos.models import Repository
from apps.reviews import pipeline
from apps.reviews.models import Review, ReviewMode


class Command(BaseCommand):
    help = (
        "Run a pull request through Aethos and the naive baseline (dry run, nothing is posted) "
        "and print tokens, cost and latency side by side."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--repo", required=True, help="owner/name of an installed repository")
        parser.add_argument("--pr", required=True, type=int)
        parser.add_argument("--csv", action="store_true", help="Print CSV instead of a table")

    def handle(self, *args: Any, **options: Any) -> None:
        repo = (
            Repository.objects.select_related("installation")
            .filter(full_name=options["repo"])
            .first()
        )
        if repo is None:
            raise CommandError("Repository is not installed")

        rows = []
        for mode in (ReviewMode.AETHOS, ReviewMode.BASELINE):
            Review.objects.filter(
                repository=repo, pr_number=options["pr"], trigger_comment_id=0, mode=mode
            ).delete()
            for step, payload in (
                (
                    "triage",
                    {
                        "repo_id": repo.pk,
                        "pr_number": options["pr"],
                        "comment_id": 0,
                        "dry_run": True,
                        "mode": mode.value,
                    },
                ),
            ):
                pipeline.run_step_chain(step, payload)
            review = Review.objects.filter(
                repository=repo, pr_number=options["pr"], trigger_comment_id=0, mode=mode
            ).latest("id")
            rows.append(review)

        header = [
            "mode",
            "status",
            "verdict",
            "tokens_in",
            "tokens_out",
            "cost_usd",
            "latency_ms",
            "context_tokens",
            "findings",
        ]
        table = [
            [
                r.mode,
                r.status,
                r.verdict or "-",
                r.tokens_in,
                r.tokens_out,
                f"{r.cost_usd:.6f}",
                r.latency_ms,
                (r.pack or {}).get("tokens_used", 0),
                r.findings.count(),
            ]
            for r in rows
        ]
        if options["csv"]:
            writer = csv.writer(sys.stdout)
            writer.writerow(header)
            writer.writerows(table)
        else:
            widths = [max(len(str(x)) for x in col) for col in zip(header, *table, strict=True)]
            for line in [header, *table]:
                self.stdout.write(
                    "  ".join(str(v).ljust(w) for v, w in zip(line, widths, strict=True))
                )
        aethos, baseline = rows
        if baseline.tokens_in and aethos.tokens_in:
            saved = 100 * (baseline.tokens_in - aethos.tokens_in) / baseline.tokens_in
            self.stdout.write(f"\nInput tokens saved by Aethos vs baseline: {saved:.1f}%")
