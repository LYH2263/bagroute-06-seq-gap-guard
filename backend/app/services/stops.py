"""Subscriber-stop mutations.

Invariant: within one route, ``seq`` starts at 1, is unique and has no gaps,
i.e. the seqs of the route's stops are exactly ``1..n``. Every write path
(insert, renumber, reseed) goes through :func:`assert_compact` so a gap or a
duplicate can never be persisted — the failure rolls back and existing stops
stay untouched.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import DeliveryRoute, SubscriberStop

# Order used when compacting a route: current seq, then id for determinism.
_STOP_ORDER = (SubscriberStop.seq, SubscriberStop.id)


class SeqError(ValueError):
    """Raised when a write would break the 1..n continuity of a route."""


class StopLookupError(LookupError):
    """Raised when the referenced route or stop does not exist."""


def assert_compact(seqs: list[int]) -> None:
    """Check that ``seqs`` equals ``1..n`` (any order) — unique, no gaps."""
    n = len(seqs)
    seen: set[int] = set()
    for s in seqs:
        if s in seen:
            raise SeqError(f"序号 {s} 重复：同一路线内序号不得冲突")
        seen.add(s)
    missing = sorted(set(range(1, n + 1)) - seen)
    if missing:
        raise SeqError(
            f"序号不连续：当前 {n} 个站点，序号必须为 1..{n}，"
            f"缺少 {'、'.join(map(str, missing))}"
        )
    extra = sorted(s for s in seen if s < 1 or s > n)
    if extra:
        raise SeqError(
            f"序号越界：当前 {n} 个站点，序号必须为 1..{n}，"
            f"异常序号 {'、'.join(map(str, extra))}"
        )


def list_stops(db: Session, route_id: int) -> list[SubscriberStop]:
    return list(
        db.scalars(
            select(SubscriberStop)
            .where(SubscriberStop.route_id == route_id)
            .order_by(*_STOP_ORDER)
        ).all()
    )


def add_stop(
    db: Session,
    route_id: int,
    seq: int,
    name: str,
    weight_kg: float,
    volume_l: float,
) -> SubscriberStop:
    """Create a stop; reject gaps/duplicates, leaving existing stops intact."""
    if not db.get(DeliveryRoute, route_id):
        raise StopLookupError("路线不存在")
    existing = list_stops(db, route_id)
    assert_compact([s.seq for s in existing] + [seq])
    stop = SubscriberStop(
        route_id=route_id,
        seq=seq,
        name=name,
        weight_kg=weight_kg,
        volume_l=volume_l,
    )
    db.add(stop)
    try:
        db.flush()
    except Exception as exc:  # unique constraint race / double submit
        db.rollback()
        raise SeqError(f"序号 {seq} 冲突：同一路线内序号不得重复") from exc
    return stop


def update_stop_seq(db: Session, stop_id: int, seq: int) -> SubscriberStop:
    """Renumber one stop in place; reject gaps/duplicates, keep other stops."""
    stop = db.get(SubscriberStop, stop_id)
    if not stop:
        raise StopLookupError("站点不存在")
    if seq == stop.seq:
        return stop
    seqs = [s.seq for s in list_stops(db, stop.route_id) if s.id != stop_id] + [seq]
    assert_compact(seqs)
    stop.seq = seq
    try:
        db.flush()
    except Exception as exc:
        db.rollback()
        raise SeqError(f"序号 {seq} 冲突：同一路线内序号不得重复") from exc
    return stop


def resequence(db: Session, route_id: int) -> list[SubscriberStop]:
    """Rewrite the route's seqs to 1..n following the current seq order."""
    if not db.get(DeliveryRoute, route_id):
        raise StopLookupError("路线不存在")
    stops = list_stops(db, route_id)
    # Park every row at a temporary seq first so assigning 1..n never fires an
    # intermediate unique-constraint violation (0 can never be a valid seq).
    for i, s in enumerate(stops):
        s.seq = -(i + 1)
    db.flush()
    for i, s in enumerate(stops, start=1):
        s.seq = i
    db.flush()
    return stops


def move_stop(db: Session, stop_id: int, direction: str) -> SubscriberStop:
    """Move a stop one slot toward smaller seq ("up") or larger ("down").

    Swaps seqs with the neighbour, so the route stays exactly 1..n while the
    visiting order changes.
    """
    stop = db.get(SubscriberStop, stop_id)
    if not stop:
        raise StopLookupError("站点不存在")
    stops = list_stops(db, stop.route_id)
    idx = next((i for i, s in enumerate(stops) if s.id == stop_id), -1)
    if direction == "up":
        if idx == 0:
            raise SeqError("已是第一站，无法上移")
        neighbour = stops[idx - 1]
    elif direction == "down":
        if idx == len(stops) - 1:
            raise SeqError("已是最后一站，无法下移")
        neighbour = stops[idx + 1]
    else:
        raise SeqError("direction 只能是 up 或 down")
    # Swap through a temporary seq (0 can never be a valid seq) so neither
    # intermediate UPDATE violates the (route_id, seq) unique constraint.
    stop_seq = stop.seq
    target_seq = neighbour.seq
    neighbour.seq = 0
    db.flush()  # free target_seq
    stop.seq = target_seq
    db.flush()  # stop takes the freed slot, frees stop_seq
    neighbour.seq = stop_seq
    db.flush()
    return stop
