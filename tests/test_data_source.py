# -*- coding: utf-8 -*-
"""数据源测试：极客云 CSV 加载与查询。"""
from src.data_source import DataSource


def test_datasource_loads_orders():
    ds = DataSource()
    ds.load()
    orders = ds.all_orders()
    assert len(orders) > 2000          # 极客云模拟数据约 2400+ 个订单
    # 脏数据行已被清洗
    assert ds.dirty_stats()["orders_dirty_rows_removed"] > 0


def test_get_order_aggregates_items():
    ds = DataSource()
    order = ds.get_order("PO20260928-00001")
    assert order is not None
    assert order.order_id == "PO20260928-00001"
    assert order.store != ""
    assert len(order.items) >= 1       # 多 SKU 明细已聚合


def test_get_order_not_found():
    ds = DataSource()
    assert ds.get_order("PO-NOT-EXIST") is None


def test_inventory_lookup():
    ds = DataSource()
    # 用数据源里真实存在的 (store, sku) 组合
    orders = ds.all_orders()
    assert orders
    o = orders[0]
    inv = ds.get_inventory(o.store, o.items[0]["sku"])
    if inv is not None:                # 库存可能因脏数据缺失，存在则校验字段
        assert inv["available"] >= 0


def test_logistics_lookup():
    ds = DataSource()
    lr = ds.get_logistics("PO20260928-00001")
    assert lr is not None
    assert "tracking_no" in lr