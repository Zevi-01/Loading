# -*- coding: utf-8 -*-
"""数据类定义"""
from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass
class LN:
    ln_id: str            # Loading 号（原 LN号，不拆分硬约束）
    pallets: int          # Plt QTY（卡板数）
    volume: float = 0.0
    booking_seq: str = "" # Booking Sequence（软约束：尽量同车）


@dataclass
class VehiclePlan:
    vtype_name: str
    max_pallets: int
    cost_q: int
    lns: List[LN] = field(default_factory=list)

    @property
    def used_pallets(self) -> int:
        return sum(ln.pallets for ln in self.lns)

    @property
    def pallet_util(self) -> float:
        return self.used_pallets / self.max_pallets if self.max_pallets else 0.0


@dataclass
class PlanResult:
    vehicles: List[VehiclePlan] = field(default_factory=list)
    total_cost: int = 0
    total_pallets: int = 0
    oversized_lns: List[LN] = field(default_factory=list)

    def summary(self) -> str:
        from collections import Counter
        lines = ["=" * 60, "排车结果（严格全局最优·卡板约束·Q最低）", "=" * 60,
                 f"派车总数   : {len(self.vehicles)}",
                 f"总卡板数   : {self.total_pallets}",
                 f"总费用 Q   : {self.total_cost:,}"]
        tc = Counter(v.vtype_name for v in self.vehicles)
        lines.append(f"车型分布   : {dict(tc)}")
        for v in self.vehicles:
            lines.append(
                f"  {v.vtype_name:5s} Q={v.cost_q:6d}  "
                f"{v.used_pallets:2d}/{v.max_pallets}板  "
                f"利用率={v.pallet_util*100:.0f}%  "
                f"装: {[ln.ln_id for ln in v.lns]}"
            )
        if self.oversized_lns:
            from .config import MAX_PAL
            lines.append(f"⚠ 卡板>{MAX_PAL} : {[ln.ln_id for ln in self.oversized_lns]}")
        lines.append("=" * 60)
        return "\n".join(lines)
