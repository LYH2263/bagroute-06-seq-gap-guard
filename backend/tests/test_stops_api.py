"""Seq-continuity invariant: gap/duplicate writes fail, reseed compacts,
packing follows seq. Uses the SQLite-backed TestClient from conftest."""

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import DeliveryRoute, SubscriberStop
from app.services.seed import seed_if_empty


def make_route(db: Session, name: str = "测试线", w: float = 8.0, v: float = 20.0) -> int:
    r = DeliveryRoute(name=name, max_weight_kg=w, max_volume_l=v)
    db.add(r)
    db.commit()
    db.refresh(r)
    return r.id


def add_direct(db: Session, rid: int, seq: int, name: str, w: float = 1.0, v: float = 1.0) -> None:
    db.add(SubscriberStop(route_id=rid, seq=seq, name=name, weight_kg=w, volume_l=v))
    db.commit()


def seqs_of(client: TestClient, rid: int) -> list[int]:
    rows = client.get(f"/api/stops?route_id={rid}").json()
    return [s["seq"] for s in rows]


def names_of(client: TestClient, rid: int) -> list[str]:
    rows = client.get(f"/api/stops?route_id={rid}").json()
    return [s["name"] for s in rows]


# ---- failures must reject and preserve existing stops ----

def test_create_with_gap_fails_and_keeps_existing(client: TestClient, db: Session):
    rid = make_route(db)
    assert client.post("/api/stops", json={"route_id": rid, "seq": 1, "name": "甲", "weight_kg": 1.0, "volume_l": 1.0}).status_code == 201
    assert client.post("/api/stops", json={"route_id": rid, "seq": 2, "name": "乙", "weight_kg": 1.0, "volume_l": 1.0}).status_code == 201

    r = client.post("/api/stops", json={"route_id": rid, "seq": 4, "name": "跳号", "weight_kg": 1.0, "volume_l": 1.0})
    assert r.status_code == 409
    assert "不连续" in r.json()["detail"]

    # existing stops untouched: still exactly 1..2
    assert seqs_of(client, rid) == [1, 2]


def test_create_duplicate_seq_fails_and_keeps_existing(client: TestClient, db: Session):
    rid = make_route(db)
    client.post("/api/stops", json={"route_id": rid, "seq": 1, "name": "甲", "weight_kg": 1.0, "volume_l": 1.0})
    client.post("/api/stops", json={"route_id": rid, "seq": 2, "name": "乙", "weight_kg": 1.0, "volume_l": 1.0})

    r = client.post("/api/stops", json={"route_id": rid, "seq": 2, "name": "冲突", "weight_kg": 1.0, "volume_l": 1.0})
    assert r.status_code == 409
    assert "重复" in r.json()["detail"]
    assert seqs_of(client, rid) == [1, 2]
    assert names_of(client, rid) == ["甲", "乙"]


def test_renumber_into_gap_or_dup_fails_and_preserves(client: TestClient, db: Session):
    rid = make_route(db)
    for i, n in enumerate(["甲", "乙", "丙"], start=1):
        client.post("/api/stops", json={"route_id": rid, "seq": i, "name": n, "weight_kg": 1.0, "volume_l": 1.0})
    first = client.get(f"/api/stops?route_id={rid}").json()[0]

    # jump to seq 5 leaves a gap -> reject
    r = client.patch(f"/api/stops/{first['id']}", json={"seq": 5})
    assert r.status_code == 409
    assert seqs_of(client, rid) == [1, 2, 3]

    # collide with seq 2 -> reject
    r = client.patch(f"/api/stops/{first['id']}", json={"seq": 2})
    assert r.status_code == 409
    assert seqs_of(client, rid) == [1, 2, 3]

    # same seq is a no-op, not an error
    r = client.patch(f"/api/stops/{first['id']}", json={"seq": 1})
    assert r.status_code == 200
    assert seqs_of(client, rid) == [1, 2, 3]


def test_first_seq_must_start_at_one(client: TestClient, db: Session):
    rid = make_route(db)
    r = client.post("/api/stops", json={"route_id": rid, "seq": 3, "name": "不从1开始", "weight_kg": 1.0, "volume_l": 1.0})
    assert r.status_code == 409
    assert seqs_of(client, rid) == []


def test_unknown_route_and_stop_404(client: TestClient, db: Session):
    r = client.post("/api/stops", json={"route_id": 999, "seq": 1, "name": "x", "weight_kg": 1.0, "volume_l": 1.0})
    assert r.status_code == 404
    assert client.post("/api/routes/999/stops/resequence").status_code == 404
    assert client.post("/api/stops/999/move", json={"direction": "up"}).status_code == 404


# ---- resequence ----

def test_resequence_compacts_gaps_then_stays_continuous(client: TestClient, db: Session):
    rid = make_route(db)
    # legacy/direct rows with gaps and non-trivial order
    add_direct(db, rid, 5, "丙")
    add_direct(db, rid, 1, "甲")
    add_direct(db, rid, 9, "戊")

    r = client.post(f"/api/routes/{rid}/stops/resequence")
    assert r.status_code == 200
    rows = r.json()
    assert [s["seq"] for s in rows] == [1, 2, 3]
    # current seq order is preserved (1,5,9 -> 1,2,3)
    assert [s["name"] for s in rows] == ["甲", "丙", "戊"]

    # re-entering the stops page reads the same continuous numbering
    assert seqs_of(client, rid) == [1, 2, 3]
    r2 = client.post(f"/api/routes/{rid}/stops/resequence")
    assert [s["seq"] for s in r2.json()] == [1, 2, 3]
    assert seqs_of(client, rid) == [1, 2, 3]


def test_reorder_then_resequence_keeps_visiting_order(client: TestClient, db: Session):
    rid = make_route(db)
    ids = {}
    for i, n in enumerate(["A", "B", "C"], start=1):
        resp = client.post("/api/stops", json={"route_id": rid, "seq": i, "name": n, "weight_kg": 1.0, "volume_l": 1.0})
        ids[n] = resp.json()["id"]

    # move C up twice: C should become seq 1
    assert client.post(f"/api/stops/{ids['C']}/move", json={"direction": "up"}).status_code == 200
    assert client.post(f"/api/stops/{ids['C']}/move", json={"direction": "up"}).status_code == 200
    assert seqs_of(client, rid) == [1, 2, 3]
    assert names_of(client, rid) == ["C", "A", "B"]

    # boundary moves are rejected
    assert client.post(f"/api/stops/{ids['C']}/move", json={"direction": "up"}).status_code == 409
    assert client.post(f"/api/stops/{ids['B']}/move", json={"direction": "down"}).status_code == 409

    # reseed keeps the reordered visiting sequence and continuous seqs
    r = client.post(f"/api/routes/{rid}/stops/resequence")
    assert [(s["seq"], s["name"]) for s in r.json()] == [(1, "C"), (2, "A"), (3, "B")]
    assert seqs_of(client, rid) == [1, 2, 3]


# ---- packing strictly by seq ----

def test_pack_follows_seq_not_name(client: TestClient, db: Session):
    rid = make_route(db, w=5.0, v=20.0)
    # names sort opposite to seq; weights force the boundary after seq 1
    # (3+3 > 5) while seq 2+3 share a bag (3+2 <= 5)
    add_direct(db, rid, 1, "Z 站", w=3.0)
    add_direct(db, rid, 2, "A 站", w=3.0)
    add_direct(db, rid, 3, "M 站", w=2.0)

    r = client.post("/api/pack", json={"route_id": rid})
    assert r.status_code == 200
    bags = r.json()
    assert [[i["stop_name"] for i in b["items"]] for b in bags] == [
        ["Z 站"],
        ["A 站", "M 站"],
    ]

    # bags page must expose the same seq-driven order, not name order
    bags_page = client.get("/api/bags").json()
    route_bags = [b for b in bags_page if b["route_id"] == rid]
    flat = [i["stop_name"] for b in route_bags for i in b["items"]]
    assert flat == ["Z 站", "A 站", "M 站"]


def test_pack_after_reorder_uses_new_seq_order(client: TestClient, db: Session):
    rid = make_route(db, w=10.0, v=20.0)
    add_direct(db, rid, 1, "第一", w=1.0)
    add_direct(db, rid, 2, "第二", w=1.0)
    rows = client.get(f"/api/stops?route_id={rid}").json()
    second_id = next(s["id"] for s in rows if s["name"] == "第二")

    # move 第二 up, then pack: visiting order must be 第二 → 第一
    client.post(f"/api/stops/{second_id}/move", json={"direction": "up"})
    r = client.post("/api/pack", json={"route_id": rid})
    bag0 = r.json()[0]["items"]
    assert [i["stop_name"] for i in bag0] == ["第二", "第一"]


# ---- seed contains a failing gap write ----

def test_seed_gap_write_is_rejected_existing_kept(db: Session):
    seed_if_empty(db)
    routes = db.scalars(select(DeliveryRoute).order_by(DeliveryRoute.id)).all()
    assert len(routes) == 3

    r3 = db.scalars(select(DeliveryRoute).where(DeliveryRoute.name == "序号试排线")).one()
    got = db.scalars(
        select(SubscriberStop).where(SubscriberStop.route_id == r3.id).order_by(SubscriberStop.seq)
    ).all()
    # the seq=4 attempt never landed; only the pre-existing 1,2 remain
    assert [(s.seq, s.name) for s in got] == [(1, "北门岗亭"), (2, "食堂侧门")]

    # the ordinary seeded routes are still exactly 1..n
    r1 = db.scalars(select(DeliveryRoute).where(DeliveryRoute.name == "城东晨线")).one()
    r1_seqs = [s.seq for s in db.scalars(
        select(SubscriberStop).where(SubscriberStop.route_id == r1.id)
    ).all()]
    assert sorted(r1_seqs) == [1, 2, 3, 4, 5]
