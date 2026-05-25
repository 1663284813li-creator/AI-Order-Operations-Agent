# -*- coding: utf-8 -*-
"""库存闸门测试：补发前强制校验门店可用库存。"""
import pytest

from src.agent import TicketAgent
from src.data_source import DataSource
from src.domain.models import Action, ActionType, RiskLevel


@pytest.fixture(scope="module")
def ds():
    d = DataSource()
    d.load()
    return d


@pytest.fixture(scope="module")
def agent():
    return TicketAgent(mock=True)


def _reissue(qty, order_id, sku=None):
    params = {"qty": qty, "order_id": order_id}
    if sku:
        params["sku"] = sku
    return Action(ActionType.REISSUE, params, RiskLevel.HIGH)


def test_inventory_gate_blocks_when_insufficient(ds, agent):
    """补发数量远超库存 -> 拦截。"""
    order = ds.all_orders()[0]
    act = _reissue(10_000_000, order.order_id)
    ok, msg = agent._inventory_gate(act, order)
    assert ok is False
    assert "库存" in msg or "人工" in msg


def test_inventory_gate_blocks_unknown_order(ds, agent):
    """订单不存在 -> 保守拦截。"""
    act = _reissue(1, "PO-NOT-EXIST")
    ok, msg = agent._inventory_gate(act, None)
    assert ok is False
    assert "人工" in msg or "定位" in msg


def test_inventory_gate_blocks_invalid_qty(ds, agent):
    """数量非法 -> 拦截。"""
    act = Action(ActionType.REISSUE, {"qty": "abc", "order_id": "PO1"}, RiskLevel.HIGH)
    ok, _ = agent._inventory_gate(act, None)
    assert ok is False


def test_inventory_gate_passes_when_stock_sufficient(ds, agent):
    """单 SKU 订单且库存充足 -> 放行。"""
    order = None
    for o in ds.all_orders():
        if len({it["sku"] for it in o.items}) == 1:
            order = o
            break
    if order is None:
        pytest.skip("数据集中没有单 SKU 订单")
    sku = order.items[0]["sku"]
    inv = ds.get_inventory(order.store, sku)
    if inv is None or inv["available"] <= 0:
        pytest.skip("该商品无库存记录或库存为 0")
    act = _reissue(1, order.order_id, sku=sku)
    ok, msg = agent._inventory_gate(act, order)
    assert ok is True, msg