import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.models import DeliveryRoute, SubscriberStop
from app.services.stop_ops import SeqError, add_stop, list_stops, resequence, update_seq


def _db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    route = DeliveryRoute(name="测试线", max_weight_kg=8.0, max_volume_l=18.0)
    db.add(route)
    db.commit()
    return db, route.id


def _seqs(db, rid):
    return [s.seq for s in list_stops(db, rid)]


def test_add_must_append_rejects_gap():
    db, rid = _db()
    add_stop(db, rid, "甲", 1.0, 1.0)
    # 只有 1 个站点时写 seq=3 属于跳号，必须失败
    with pytest.raises(SeqError):
        add_stop(db, rid, "跳号", 1.0, 1.0, seq=3)
    db.commit()
    assert _seqs(db, rid) == [1]
    assert [s.name for s in list_stops(db, rid)] == ["甲"]
    # 失败后已有站点保持，正常追加得到 seq=2
    add_stop(db, rid, "乙", 1.0, 1.0)
    db.commit()
    assert _seqs(db, rid) == [1, 2]


def test_add_rejects_seq_conflict():
    db, rid = _db()
    for name in ("甲", "乙", "丙"):
        add_stop(db, rid, name, 1.0, 1.0)
    db.commit()
    with pytest.raises(SeqError):
        add_stop(db, rid, "插队", 1.0, 1.0, seq=2)
    db.commit()
    assert _seqs(db, rid) == [1, 2, 3]
    add_stop(db, rid, "丁", 1.0, 1.0)
    db.commit()
    assert _seqs(db, rid) == [1, 2, 3, 4]


def test_update_seq_shifts_within_range_and_keeps_compact():
    db, rid = _db()
    for name in ("甲", "乙", "丙", "丁"):
        add_stop(db, rid, name, 1.0, 1.0)
    db.commit()
    first = list_stops(db, rid)[0]
    update_seq(db, first.id, 3)
    db.commit()
    order = [(s.seq, s.name) for s in list_stops(db, rid)]
    assert order == [(1, "乙"), (2, "丙"), (3, "甲"), (4, "丁")]

    last = list_stops(db, rid)[-1]
    update_seq(db, last.id, 1)
    db.commit()
    order = [(s.seq, s.name) for s in list_stops(db, rid)]
    assert order == [(1, "丁"), (2, "乙"), (3, "丙"), (4, "甲")]


def test_update_seq_out_of_range_fails_and_keeps_existing():
    db, rid = _db()
    for name in ("甲", "乙"):
        add_stop(db, rid, name, 1.0, 1.0)
    db.commit()
    first = list_stops(db, rid)[0]
    with pytest.raises(SeqError):
        update_seq(db, first.id, 5)
    db.commit()
    assert [(s.seq, s.name) for s in list_stops(db, rid)] == [(1, "甲"), (2, "乙")]


def test_resequence_rewrites_gap_to_compact():
    db, rid = _db()
    db.add_all(
        [
            SubscriberStop(route_id=rid, seq=1, name="甲", weight_kg=1.0, volume_l=1.0),
            SubscriberStop(route_id=rid, seq=3, name="乙", weight_kg=1.0, volume_l=1.0),
            SubscriberStop(route_id=rid, seq=7, name="丙", weight_kg=1.0, volume_l=1.0),
        ]
    )
    db.commit()
    rows = resequence(db, rid)
    db.commit()
    assert [(s.seq, s.name) for s in rows] == [(1, "甲"), (2, "乙"), (3, "丙")]
    # 重排后再追加只能接 4
    add_stop(db, rid, "丁", 1.0, 1.0)
    db.commit()
    assert _seqs(db, rid) == [1, 2, 3, 4]


def test_add_on_corrupt_route_requires_resequence_first():
    db, rid = _db()
    db.add_all(
        [
            SubscriberStop(route_id=rid, seq=1, name="甲", weight_kg=1.0, volume_l=1.0),
            SubscriberStop(route_id=rid, seq=4, name="乙", weight_kg=1.0, volume_l=1.0),
        ]
    )
    db.commit()
    with pytest.raises(SeqError):
        add_stop(db, rid, "丙", 1.0, 1.0)
    db.rollback()
    resequence(db, rid)
    db.commit()
    add_stop(db, rid, "丙", 1.0, 1.0)
    db.commit()
    assert _seqs(db, rid) == [1, 2, 3]
