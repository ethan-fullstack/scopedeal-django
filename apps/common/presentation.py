from decimal import Decimal

from django.db.models import Count

from apps.proposals.models import Proposal
from integrations.exchange_rates import current_snapshot

STATUS_COLORS = {
    "DRAFT": "#64748b",
    "SUBMITTED": "#1769f5",
    "NEGOTIATING": "#d97706",
    "ACCEPTED": "#059669",
    "REJECTED": "#dc2626",
    "SUPERSEDED": "#7c3aed",
}


def status_chart(proposals):
    counts = {
        row["status"]: row["count"]
        for row in proposals.order_by().values("status").annotate(count=Count("pk"))
    }
    count = sum(counts.values())
    start = Decimal(0)
    segments, legend = [], []
    for code, label in Proposal.STATES:
        value = counts.get(code, 0)
        end = start + (Decimal(value) * 100 / count if count else 0)
        segments.append(f"{STATUS_COLORS[code]} {start:.4f}% {end:.4f}%")
        legend.append(
            {"status": code, "label": label, "count": value, "color": STATUS_COLORS[code]}
        )
        start = end
    return {
        "count": count,
        "legend": legend,
        "gradient": ", ".join(segments) if count else "#e2e8f0 0% 100%",
    }


def bar_rows(rows, value_key="cost", label_key="number"):
    rows = list(rows)
    maximum = max((row[value_key] or Decimal(0) for row in rows), default=Decimal(0))
    for row in rows:
        row["percent"] = (
            (Decimal(row[value_key] or 0) * 100 / maximum).quantize(Decimal("0.01"))
            if maximum
            else 0
        )
        row["chart_label"] = f"Sprint {row[label_key]}"
    return rows


def exchange_context():
    rate = current_snapshot(24)
    stale = False
    if not rate:
        rate = current_snapshot(168)
        stale = bool(rate)
    return {"rate": rate, "stale": stale}
