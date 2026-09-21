"""站点序号连续约束：同一路线内 seq 必须从 1 起连续且不重复。

- 新增：只能追加为 n+1，跳号/冲突一律失败。
- 改序号：在 1..n 内移动，途经站点顺延，结果仍是 1..n；越界即跳号，失败。
- 重排：按现有顺序（seq 升序）整体重写成 1..n。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import SubscriberStop


class SeqError(ValueError):
    """序号约束失败，消息可直接展示给前端。"""


def list_stops(db: Session, route_id: int) -> list[SubscriberStop]:
    return list(
        db.scalars(
            select(SubscriberStop)
            .where(SubscriberStop.route_id == route_id)
            .order_by(SubscriberStop.seq)
        ).all()
    )


def _require_route(db: Session, route_id: int):
    from app.models.models import DeliveryRoute

    route = db.get(DeliveryRoute, route_id)
    if not route:
        raise SeqError("路线不存在")
    return route


def assert_compact(stops: list[SubscriberStop]) -> None:
    """校验现状是否 1..n 连续；已有数据保持，不自动修复。"""
    seqs = sorted(s.seq for s in stops)
    expected = list(range(1, len(seqs) + 1))
    if seqs != expected:
        missing = sorted(set(expected) - set(seqs))
        raise SeqError(
            f"当前路线序号不连续（期望 1..{len(seqs)}，缺失 {missing or '存在重复'}），请先执行重排"
        )


def add_stop(
    db: Session,
    route_id: int,
    name: str,
    weight_kg: float,
    volume_l: float,
    seq: int | None = None,
) -> SubscriberStop:
    _require_route(db, route_id)
    stops = list_stops(db, route_id)
    assert_compact(stops)
    next_seq = len(stops) + 1
    if seq is not None and seq != next_seq:
        raise SeqError(f"新增站点必须追加到队尾，序号应为 {next_seq}，不能为 {seq}（不允许跳号或插队）")
    stop = SubscriberStop(
        route_id=route_id,
        seq=next_seq,
        name=name,
        weight_kg=weight_kg,
        volume_l=volume_l,
    )
    db.add(stop)
    db.flush()
    return stop


def update_seq(db: Session, stop_id: int, seq: int) -> SubscriberStop:
    stop = db.get(SubscriberStop, stop_id)
    if not stop:
        raise SeqError("站点不存在")
    if not isinstance(seq, int) or seq < 1:
        raise SeqError("序号必须是不小于 1 的整数")

    stops = list_stops(db, stop.route_id)
    assert_compact(stops)
    n = len(stops)
    if seq > n:
        raise SeqError(f"序号 {seq} 超出范围 1..{n}，会造成跳号；如需追加请新增站点")

    by_id = {s.id: s for s in stops}
    current = by_id[stop.id].seq
    if seq == current:
        return stop

    # 区间内顺移，避开 (route_id, seq) 唯一约束：
    # 先把受影响站点（含拖动项）全部退到不冲突的临时号并落库，再写最终序号。
    lo, hi = min(current, seq), max(current, seq)
    offset = n + 1000
    affected = [s for s in stops if lo <= s.seq <= hi]
    for s in affected:
        s.seq = s.seq + offset
    db.flush()
    direction = 1 if current > seq else -1
    for s in affected:
        if s.id != stop.id:
            s.seq = s.seq - offset + direction
    stop.seq = seq
    db.flush()
    assert_compact(list_stops(db, stop.route_id))
    return stop


def resequence(db: Session, route_id: int) -> list[SubscriberStop]:
    """把当前路线站点按现有顺序（seq 升序）重写成 1..n。"""
    from app.models.models import DeliveryRoute

    route = db.get(DeliveryRoute, route_id)
    if not route:
        raise SeqError("路线不存在")
    stops = list_stops(db, route_id)
    # 先全部退到不冲突的临时号，再按现有顺序写 1..n。
    for i, s in enumerate(stops):
        s.seq = len(stops) + i + 1000
    db.flush()
    for i, s in enumerate(stops, start=1):
        s.seq = i
    db.flush()
    return list_stops(db, route_id)
