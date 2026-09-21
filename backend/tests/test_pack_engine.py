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


def test_pack_orders_by_seq_not_name_or_input_order():
    # Input order is reversed and names would sort opposite to seq; weights
    # (3/2/1 kg, cap 4) force the bag boundary after seq 1, making the order
    # observable independent of input/name order.
    stops = [
        StopItem(3, 3, 1.0, 1.0, "C 站"),
        StopItem(2, 2, 2.0, 1.0, "B 站"),
        StopItem(1, 1, 3.0, 1.0, "A 站"),
    ]
    result = pack_route(stops, max_weight=4.0, max_volume=10.0)
    flat = [i.stop_id for bag in result.bags for i in bag.items]
    # strictly ascending seq: seq 1 alone in bag 1; seq 2,3 in bag 2
    assert [i.stop_id for i in result.bags[0].items] == [1]
    assert [i.stop_id for i in result.bags[1].items] == [2, 3]
    assert flat == [1, 2, 3]
    assert [i.seq for i in result.bags[0].items + result.bags[1].items] == [1, 2, 3]
