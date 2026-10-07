from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.reviews.models import Review


class Command(BaseCommand):
    help = "Print a review's verdict, findings, usage and the context pack (pack inspector)."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("review_id", type=int)
        parser.add_argument("--text", action="store_true", help="Also print each item's text")

    def handle(self, *args: Any, **options: Any) -> None:
        review = Review.objects.select_related("repository").filter(pk=options["review_id"]).first()
        if review is None:
            raise CommandError("Review not found")
        out = self.stdout.write
        out(f"{review.repository.full_name}#{review.pr_number}  [{review.mode}] {review.status}")
        out(f"verdict: {review.verdict or '-'}   risk: {review.risk or '-'}")
        for reason in review.verdict_reasons:
            out(f"  - {'BLOCKING ' if reason.get('blocking') else ''}{reason.get('text')}")
        out(
            f"tokens in/out: {review.tokens_in}/{review.tokens_out}  cost: ${review.cost_usd:.6f}"
            f"  latency: {review.latency_ms}ms"
        )
        pack = review.pack or {}
        out(
            f"\ncontext pack: {pack.get('tokens_used', 0)}/{pack.get('budget', 0)} tokens, "
            f"diff complete: {pack.get('diff_complete')}"
        )
        for item in pack.get("items", []):
            out(f"  [{item['section']:<8}] {item['tokens']:>5}t  {item['title']}")
            out(f"      because: {item['reason']}")
            if options["text"]:
                out("      " + item["text"].replace("\n", "\n      "))
        for dropped in pack.get("dropped", []):
            out(f"  dropped [{dropped['section']}] {dropped['title']}: {dropped['reason']}")
        out("\nfindings:")
        for f in review.findings.order_by("-confidence"):
            out(f"  {f.severity:<8} {f.path}:{f.line}  {f.title}  ({f.confidence:.2f})")
