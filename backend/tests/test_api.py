import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.models import DeliveryRoute, SubscriberStop


@pytest.fixture()
def ctx():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine)
    db = TestingSession()
    route = DeliveryRoute(name="测试线", max_weight_kg=8.0, max_volume_l=18.0)
    db.add(route)
    db.commit()
    rid = route.id

    def override_get_db():
        s = TestingSession()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_get_db
    # 不使用 with：避免触发 lifespan 去连配置里的 Postgres。
    yield TestClient(app), rid
    app.dependency_overrides.clear()


def _add(client, rid, seq=None):
    body = {"route_id": rid, "name": f"S{seq or 'x'}", "weight_kg": 1.0, "volume_l": 1.0}
    if seq is not None:
        body["seq"] = seq
    return client.post("/api/stops", json=body)


def test_gap_create_returns_400_with_visible_reason(ctx):
    client, rid = ctx
    assert _add(client, rid).status_code == 201
    r = _add(client, rid, seq=3)
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "序号" in detail and "2" in detail
    # 已有站点保持
    rows = client.get(f"/api/stops?route_id={rid}").json()
    assert [s["seq"] for s in rows] == [1]


def test_conflict_create_returns_400(ctx):
    client, rid = ctx
    _add(client, rid)
    _add(client, rid)
    r = _add(client, rid, seq=1)
    assert r.status_code == 400
    assert r.json()["detail"]


def test_patch_seq_shifts_and_out_of_range_fails(ctx):
    client, rid = ctx
    for _ in range(3):
        _add(client, rid)
    rows = client.get(f"/api/stops?route_id={rid}").json()
    first = rows[0]["id"]
    r = client.patch(f"/api/stops/{first}", json={"seq": 3})
    assert r.status_code == 200
    assert r.json()["seq"] == 3
    after = client.get(f"/api/stops?route_id={rid}").json()
    assert [s["seq"] for s in after] == [1, 2, 3]
    moved = next(s for s in after if s["id"] == first)
    assert moved["seq"] == 3

    r = client.patch(f"/api/stops/{first}", json={"seq": 9})
    assert r.status_code == 400
    assert r.json()["detail"]
    # 失败后序号保持 1..3 连续
    after_fail = client.get(f"/api/stops?route_id={rid}").json()
    assert [s["seq"] for s in after_fail] == [1, 2, 3]
    assert next(s for s in after_fail if s["id"] == first)["seq"] == 3


def test_resequence_endpoint_makes_compact(ctx):
    client, rid = ctx
    session = next(app.dependency_overrides[get_db]())
    session.add_all(
        [
            SubscriberStop(route_id=rid, seq=2, name="A", weight_kg=1.0, volume_l=1.0),
            SubscriberStop(route_id=rid, seq=5, name="B", weight_kg=1.0, volume_l=1.0),
        ]
    )
    session.commit()
    session.close()

    r = client.post(f"/api/routes/{rid}/stops/resequence")
    assert r.status_code == 200
    assert [(x["seq"], x["name"]) for x in r.json()] == [(1, "A"), (2, "B")]

    # 重排后再次进入站点页（GET）序号连续
    rows = client.get(f"/api/stops?route_id={rid}").json()
    assert [x["seq"] for x in rows] == [1, 2]


def test_pack_uses_seq_order_not_name(ctx):
    client, rid = ctx
    # 直接写入乱序 seq；名称字典序与 seq 相反
    session = next(app.dependency_overrides[get_db]())
    session.add_all(
        [
            SubscriberStop(route_id=rid, seq=1, name="丁最后", weight_kg=1.0, volume_l=1.0),
            SubscriberStop(route_id=rid, seq=2, name="丙中间", weight_kg=1.0, volume_l=1.0),
            SubscriberStop(route_id=rid, seq=3, name="乙靠前", weight_kg=1.0, volume_l=1.0),
            SubscriberStop(route_id=rid, seq=4, name="甲首位名", weight_kg=1.0, volume_l=1.0),
        ]
    )
    session.commit()
    session.close()

    r = client.post("/api/pack", json={"route_id": rid})
    assert r.status_code == 200
    names = [it["stop_name"] for bag in r.json() for it in bag["items"]]
    assert names == ["丁最后", "丙中间", "乙靠前", "甲首位名"]
