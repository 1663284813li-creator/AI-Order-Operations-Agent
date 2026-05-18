# -*- coding: utf-8 -*-
"""数据源层：加载极客云模拟导出 CSV，构建内存索引，供工具查询。

数据来源（data/mock/）：
- orders.csv     极客云订单导出（订单明细，一单多行）
- inventory.csv  极客云库存导出（门店 x SKU 库存）
- returns.csv    极客云售后退货导出（售后单）

设计：
- 懒加载 + 缓存：第一次访问才读文件，之后复用。
- 脏数据剔除：订单/库存文件含真实比例的脏数据（空订单号、负数数量…），
  查询时只返回干净数据；可用 `dirty_stats()` 查看清洗情况。
- 索引：order_id -> Order 列表； (store, sku) -> 库存；order_id -> 物流。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from src.config import settings
from src.domain.models import Order
from src.logger import log

# CSV 列名映射（与极客云导出对齐）
COL_ORDER_ID = "订单号"
COL_ORDER_CREATED = "订单创建时间"
COL_SKU = "商品编码"
COL_NAME = "商品名称"
COL_SPEC = "规格"
COL_QTY = "数量"
COL_PRICE = "单价"
COL_AMOUNT = "商品金额"
COL_STORE = "门店"
COL_CUSTOMER = "收货人"
COL_STATUS = "订单状态"
COL_TRACKING = "物流单号"
COL_INV_QTY = "库存数量"
COL_INV_AVAIL = "可用库存"


@dataclass
class DataSource:
    """极客云模拟数据源（内存索引）。"""

    orders_file: str = ""
    inventory_file: str = ""
    returns_file: str = ""

    _orders: list[Order] = field(default_factory=list, repr=False)
    _orders_by_id: dict[str, list[Order]] = field(default_factory=dict, repr=False)
    _inventory: dict[tuple[str, str], dict] = field(default_factory=dict, repr=False)
    _logistics: dict[str, dict] = field(default_factory=dict, repr=False)
    _loaded: bool = False

    def __post_init__(self) -> None:
        if not self.orders_file:
            self.orders_file = str(settings.mock_dir / "orders.csv")
        if not self.inventory_file:
            self.inventory_file = str(settings.mock_dir / "inventory.csv")
        if not self.returns_file:
            self.returns_file = str(settings.mock_dir / "returns.csv")

    # ------------------------------------------------------------------
    def load(self) -> None:
        """懒加载全部 CSV 并构建索引（幂等）。"""
        if self._loaded:
            return
        # ---- 订单 ----
        try:
            df = pd.read_csv(self.orders_file, encoding="utf-8-sig")
        except FileNotFoundError as e:
            log.error("订单数据文件不存在: %s", self.orders_file)
            raise FileNotFoundError(
                f"缺少订单数据 {self.orders_file}。请将极客云导出 CSV 放入 data/mock/"
            ) from e

        # 清洗：剔除脏行（空订单号/空商品/空门店/数量非法）
        df[COL_QTY] = pd.to_numeric(df[COL_QTY], errors="coerce")
        clean = df.copy()
        clean = clean[clean[COL_ORDER_ID].notna() & (clean[COL_ORDER_ID].astype(str).str.strip() != "")]
        clean = clean[clean[COL_NAME].notna() & (clean[COL_NAME].astype(str).str.strip() != "")]
        clean = clean[clean[COL_STORE].notna() & (clean[COL_STORE].astype(str).str.strip() != "")]
        clean = clean[clean[COL_QTY].notna() & (clean[COL_QTY] > 0)]
        self._dirty_count = len(df) - len(clean)

        # 按订单号聚合多 SKU 明细
        grouped = clean.groupby(COL_ORDER_ID)
        self._orders_by_id = {}
        for oid, g in grouped:
            first = g.iloc[0]
            items = [
                {
                    "sku": row[COL_SKU],
                    "name": row[COL_NAME],
                    "spec": row[COL_SPEC],
                    "qty": int(row[COL_QTY]),
                    "price": float(row[COL_PRICE]) if pd.notna(row[COL_PRICE]) else 0.0,
                }
                for _, row in g.iterrows()
            ]
            order = Order(
                order_id=str(oid),
                customer=str(first.get(COL_CUSTOMER, "")),
                store=str(first.get(COL_STORE, "")),
                amount=float(sum(i["qty"] * i["price"] for i in items)),
                status=str(first.get(COL_STATUS, "")),
                items=items,
                created_at=str(first.get(COL_ORDER_CREATED, "")),
            )
            self._orders_by_id[str(oid)] = order
            self._orders.append(order)

            # 物流（取最先出现的物流单号）
            tracking = str(first.get(COL_TRACKING, "")) if pd.notna(first.get(COL_TRACKING)) else ""
            self._logistics[str(oid)] = {
                "carrier": "极客云物流",
                "tracking_no": tracking or "待分配",
                "status": str(first.get(COL_STATUS, "")),
            }

        # ---- 库存 ----
        try:
            inv = pd.read_csv(self.inventory_file, encoding="utf-8-sig")
        except FileNotFoundError as e:
            raise FileNotFoundError(f"缺少库存数据 {self.inventory_file}") from e
        inv[COL_INV_QTY] = pd.to_numeric(inv[COL_INV_QTY], errors="coerce")
        inv[COL_INV_AVAIL] = pd.to_numeric(inv[COL_INV_AVAIL], errors="coerce")
        inv_clean = inv[
            inv[COL_SKU].notna() & (inv[COL_SKU].astype(str).str.strip() != "")
            & inv[COL_STORE].notna() & (inv[COL_STORE].astype(str).str.strip() != "")
            & inv[COL_INV_QTY].notna() & (inv[COL_INV_QTY] >= 0)
        ]
        for _, row in inv_clean.iterrows():
            key = (str(row[COL_STORE]).strip(), str(row[COL_SKU]).strip())
            # 同 (store, sku) 可能多仓，取可用库存合计
            cur = self._inventory.setdefault(key, {"qty": 0.0, "available": 0.0, "safety": 0.0})
            cur["qty"] += float(row.get(COL_INV_QTY, 0) or 0)
            avail = row.get(COL_INV_AVAIL)
            cur["available"] += float(avail) if pd.notna(avail) else 0.0
            safety = row.get("安全库存")
            cur["safety"] += float(safety) if pd.notna(safety) else 0.0

        # ---- 退货 ----
        self._returns_file = self.returns_file  # 占位，后续退货流程使用

        self._loaded = True
        log.info(
            "数据源加载完成: 订单 %d 个 (清洗 %d 行脏数据) | 库存条目 %d | 物流 %d",
            len(self._orders_by_id), self._dirty_count, len(self._inventory), len(self._logistics),
        )

    # ------------------------------------------------------------------
    def get_order(self, order_id: str) -> Optional[Order]:
        self.load()
        return self._orders_by_id.get(str(order_id).strip())

    def get_logistics(self, order_id: str) -> Optional[dict]:
        self.load()
        return self._logistics.get(str(order_id).strip())

    def get_inventory(self, store: str, sku: str) -> Optional[dict]:
        self.load()
        return self._inventory.get((str(store).strip(), str(sku).strip()))

    def all_orders(self) -> list[Order]:
        self.load()
        return list(self._orders)

    def dirty_stats(self) -> dict:
        """清洗统计（面试可讲：评测集/数据质量）。"""
        self.load()
        return {"orders_dirty_rows_removed": self._dirty_count}

    def order_exists(self, order_id: str) -> bool:
        return self.get_order(order_id) is not None


# 全局数据源实例
data_source = DataSource()