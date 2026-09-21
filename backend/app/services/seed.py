from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import DeliveryRoute, SubscriberStop
from app.services.stop_ops import SeqError, add_stop


def seed_if_empty(db: Session) -> None:
    if db.scalar(select(DeliveryRoute.id).limit(1)):
        return
    r1 = DeliveryRoute(name="城东晨线", max_weight_kg=8.0, max_volume_l=18.0)
    r2 = DeliveryRoute(name="园区午线", max_weight_kg=6.0, max_volume_l=14.0)
    r3 = DeliveryRoute(name="序号自测线", max_weight_kg=8.0, max_volume_l=18.0)
    db.add_all([r1, r2, r3])
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

    # 跳号写入路径：自测线当前只有 1 个站点，直接写 seq=3 必须失败。
    # add_stop 在落库前就抛出 SeqError，失败调用不产生任何待写入数据。
    add_stop(db, r3.id, name="起点岗亭", weight_kg=1.0, volume_l=2.0)
    try:
        add_stop(db, r3.id, name="跳号样例（不应落库）", weight_kg=1.0, volume_l=2.0, seq=3)
    except SeqError:
        pass
    else:
        raise AssertionError("种子自检失败：跳号写入竟然成功，序号连续约束未生效")
    # 约束生效后按规则正常追加为 seq=2。
    add_stop(db, r3.id, name="正常第二站", weight_kg=1.2, volume_l=2.4)

    db.commit()
