from __future__ import annotations

from datetime import UTC, datetime

from neje_oracle.blocks.firebase.repository import summarize_plot_job_counts


def test_summarize_plot_job_counts_separates_baseline_and_hidden_jobs() -> None:
    baseline = datetime(2026, 5, 7, 12, 0, tzinfo=UTC)
    counts = summarize_plot_job_counts(
        [
            {"status": "pending", "createdAt": "2026-05-07T11:59:00+00:00"},
            {"status": "pending", "createdAt": "2026-05-07T12:01:00+00:00", "queue": "user"},
            {"status": "pending", "createdAt": "2026-05-07T12:01:30+00:00", "queue": "filler", "priority": "filler"},
            {"status": "pending", "createdAt": "2026-05-07T12:02:00+00:00", "visibleInQueue": False},
            {"status": "leased", "createdAt": "2026-05-07T12:03:00+00:00"},
            {"status": "plotting", "createdAt": "2026-05-07T12:04:00+00:00"},
            {"status": "failed", "createdAt": "2026-05-07T12:05:00+00:00"},
            {"status": "skipped", "createdAt": "2026-05-07T12:06:00+00:00"},
            {"status": "unexpected", "createdAt": "2026-05-07T12:07:00+00:00"},
        ],
        run_started_at=baseline,
        limited_to=500,
    )

    assert counts["total"] == 9
    assert counts["pending"] == 4
    assert counts["pendingBeforeBaseline"] == 1
    assert counts["pendingAfterBaseline"] == 2
    assert counts["pendingUserAfterBaseline"] == 1
    assert counts["pendingFillerAfterBaseline"] == 1
    assert counts["hidden"] == 1
    assert counts["leased"] == 1
    assert counts["plotting"] == 1
    assert counts["failed"] == 1
    assert counts["skipped"] == 1
    assert counts["unknown"] == 1
    assert counts["limitedTo"] == 500
