from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import DeliveryRoute, SubscriberStop
from app.services.stops import SeqError, add_stop


def seed_if_empty(db: Session) -> None:
    if db.scalar(select(DeliveryRoute.id).limit(1)):
        return
    r1 = DeliveryRoute(name="城东晨线", max_weight_kg=8.0, max_volume_l=18.0)
    r2 = DeliveryRoute(name="园区午线", max_weight_kg=6.0, max_volume_l=14.0)
    db.add_all([r1, r2])
    db.flush()
    db.add_all(
        [
            SubscriberStop(route_id=r1.id, seq=1, name="松林里 3 栋", weight_kg=2.2, volume_l=4.0),
            SubscriberStop(route_id=r1.id, seq=2, name="梧桐苑门岗", weight_kg=3.5, volume_l=5.5),
            SubscriberStop(route_id=r1.id, seq=3, name="地铁口快递柜", weight_kg=1.8, volume_l=3.0),
            SubscriberStop(route_id=r1.id, seq=4, name="超大件样例", weight_kg=9.5, volume_l=6.0),
            SubscriberStop(route_id=r1.id, seq=5, name="咖啡店后门", weight_kg=2.0, volume_l=4.5),
            SubscriberStop(route_id=r2.id, seq=1, name="A 座前台", weight_kg=1.5, volume_l=3.0),
            SubscriberStop(route_id=r2.id, seq=2, name="B 座茶水间", weight_kg=2.0, volume_l=4.0),
            SubscriberStop(route_id=r2.id, seq=3, name="地下车库岗亭", weight_kg=2.8, volume_l=5.0),
        ]
    )

    # 第三条线演示“跳号写入必须失败”：先落两个连续站点并提交。
    r3 = DeliveryRoute(name="序号试排线", max_weight_kg=5.0, max_volume_l=12.0)
    db.add(r3)
    db.flush()
    add_stop(db, r3.id, 1, "北门岗亭", 1.2, 2.0)
    add_stop(db, r3.id, 2, "食堂侧门", 1.8, 3.2)
    db.commit()

    # 试图把新站直接写成 seq=4（跳过 3）：必须被序号连续约束拒绝；
    # 捕获后回滚本次写入，已有的 1、2 两站保持不变。
    try:
        add_stop(db, r3.id, 4, "跳号样例(应失败)", 1.0, 1.0)
    except SeqError:
        db.rollback()
    else:  # 约束失效才会走到这里：清掉误写入并直接报错
        db.rollback()
        raise RuntimeError("跳号写入未被拒绝，路线序号连续约束失效")

    db.commit()
