"""Recovery of plot jobs stranded in LEASED/PLOTTING.

``claim_next_plot_job()`` only ever queries PENDING, so a job interrupted between claim
and completion was never reconsidered: no lease expiry, no reaper, no requeue on start.
Live evidence from hardware testing on 2026-08-07: session ``20260413_192853`` had been
sitting in ``plotting`` for nearly four months -- a real visitor's artwork that would
never be drawn and never released.

The repository is exercised against a minimal Firestore stand-in rather than a live
project, so these assertions describe the query/update contract the recovery depends on.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from neje_oracle.blocks.firebase.repository import FirebaseRemoteRepository
from neje_oracle.shared.models import PlotStatus

NOW = datetime(2026, 8, 7, 16, 0, tzinfo=UTC)


class FakeDocRef:
    def __init__(self, doc: FakeDoc) -> None:
        self._doc = doc

    def update(self, payload: dict[str, Any]) -> None:
        self._doc.updates.append(payload)
        self._doc.data.update(payload)


class FakeDoc:
    def __init__(self, doc_id: str, data: dict[str, Any]) -> None:
        self.id = doc_id
        self.data = dict(data)
        self.updates: list[dict[str, Any]] = []

    def to_dict(self) -> dict[str, Any]:
        return dict(self.data)

    @property
    def reference(self) -> FakeDocRef:
        return FakeDocRef(self)


class FakeQuery:
    def __init__(self, docs: list[FakeDoc]) -> None:
        self._docs = docs

    def where(self, field: str, _op: str, value: Any) -> FakeQuery:
        return FakeQuery([d for d in self._docs if d.data.get(field) == value])

    def limit(self, _n: int) -> FakeQuery:
        return self

    def stream(self) -> list[FakeDoc]:
        return list(self._docs)


class FakeSessionDoc:
    def __init__(self, sink: dict[str, Any]) -> None:
        self._sink = sink

    def set(self, payload: dict[str, Any], merge: bool = False) -> None:
        self._sink.update(payload)


class FakeDb:
    def __init__(self, jobs: list[FakeDoc]) -> None:
        self.jobs = jobs
        self.session_writes: dict[str, dict[str, Any]] = {}

    def collection(self, name: str) -> Any:
        if name == "plot_jobs":
            return FakeQuery(self.jobs)

        class _Sessions:
            def document(_self, doc_id: str) -> FakeSessionDoc:  # noqa: N805
                return FakeSessionDoc(self.session_writes.setdefault(doc_id, {}))

        return _Sessions()


def _repo(jobs: list[FakeDoc]) -> tuple[FirebaseRemoteRepository, FakeDb]:
    repo = FirebaseRemoteRepository.__new__(FirebaseRemoteRepository)
    db = FakeDb(jobs)
    repo._db = db  # type: ignore[attr-defined]
    return repo, db


def test_job_claimed_long_ago_is_requeued() -> None:
    job = FakeDoc("stuck", {"status": PlotStatus.LEASED.value, "leasedAt": NOW - timedelta(hours=3)})
    repo, db = _repo([job])

    requeued = repo.requeue_stale_plot_jobs(stale_after=timedelta(hours=1), now=NOW)

    assert requeued == ["stuck"]
    assert job.data["status"] == PlotStatus.PENDING.value
    assert job.data["consumerId"] == ""
    assert db.session_writes["stuck"]["plotStatus"] == PlotStatus.PENDING.value


def test_job_claimed_recently_is_left_alone() -> None:
    """A sheet takes minutes; a fresh lease is work in progress, not a casualty."""
    job = FakeDoc("running", {"status": PlotStatus.PLOTTING.value, "leasedAt": NOW - timedelta(minutes=2)})
    repo, _ = _repo([job])

    assert repo.requeue_stale_plot_jobs(stale_after=timedelta(hours=1), now=NOW) == []
    assert job.data["status"] == PlotStatus.PLOTTING.value


def test_job_without_a_lease_timestamp_is_treated_as_stale() -> None:
    """Jobs claimed before leases existed carry no leasedAt.

    This is the 20260413_192853 case: a claim with no timestamp cannot be in progress now,
    so it is recoverable rather than permanently lost.
    """
    job = FakeDoc("legacy", {"status": PlotStatus.PLOTTING.value})
    repo, _ = _repo([job])

    assert repo.requeue_stale_plot_jobs(stale_after=timedelta(hours=1), now=NOW) == ["legacy"]
    assert job.data["status"] == PlotStatus.PENDING.value


def test_finished_and_pending_jobs_are_untouched() -> None:
    jobs = [
        FakeDoc("done", {"status": PlotStatus.PRINTED.value}),
        FakeDoc("waiting", {"status": PlotStatus.PENDING.value}),
        FakeDoc("skipped", {"status": PlotStatus.SKIPPED.value}),
    ]
    repo, _ = _repo(jobs)

    assert repo.requeue_stale_plot_jobs(stale_after=timedelta(hours=1), now=NOW) == []
    assert [j.updates for j in jobs] == [[], [], []]
