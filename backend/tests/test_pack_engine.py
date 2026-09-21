from app.services.pack_engine import StopItem, pack_route


def test_packs_in_route_order_splitting_bags():
    stops = [
        StopItem(1, 1, 2.0, 3.0),
        StopItem(2, 2, 2.5, 3.0),
        StopItem(3, 3, 1.0, 1.0),
    ]
    result = pack_route(stops, max_weight=4.0, max_volume=10.0)
    assert len(result.bags) == 2
    assert [i.stop_id for i in result.bags[0].items] == [1]
    assert [i.stop_id for i in result.bags[1].items] == [2, 3]
    assert not result.rejects


def test_reject_oversized_stop():
    stops = [StopItem(1, 1, 9.0, 1.0, "大件"), StopItem(2, 2, 1.0, 1.0)]
    result = pack_route(stops, max_weight=5.0, max_volume=5.0)
    assert len(result.rejects) == 1
    assert result.rejects[0][0].stop_id == 1
    assert len(result.bags) == 1
    assert result.bags[0].items[0].stop_id == 2


def test_volume_cap_triggers_new_bag():
    stops = [StopItem(1, 1, 1.0, 4.0), StopItem(2, 2, 1.0, 4.0)]
    result = pack_route(stops, max_weight=10.0, max_volume=5.0)
    assert len(result.bags) == 2


def test_pack_order_follows_seq_not_name_or_input_order():
    # 输入乱序，且名称字典序与 seq 顺序相反；装袋仍严格按 seq 从小到大。
    stops = [
        StopItem(3, 3, 1.0, 1.0, "丙"),
        StopItem(1, 1, 1.0, 1.0, "甲"),
        StopItem(4, 4, 1.0, 1.0, "丁"),
        StopItem(2, 2, 1.0, 1.0, "乙"),
    ]
    result = pack_route(stops, max_weight=2.0, max_volume=10.0)
    flat = [it.stop_id for bag in result.bags for it in bag.items]
    assert flat == [1, 2, 3, 4]
    # 每袋重量上限 2：袋 1=[1,2]，袋 2=[3,4]
    assert [[it.stop_id for it in b.items] for b in result.bags] == [[1, 2], [3, 4]]
