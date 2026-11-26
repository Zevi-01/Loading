# -*- coding: utf-8 -*-
"""核心排车算法：车型组合枚举 + 回溯搜索 + 贪心兜底
Booking Sequence 同组软约束：Q 最低前提下，同 Booking Sequence 尽量同车
"""
import time, math
from itertools import combinations, product
from typing import List, Tuple, Optional
from collections import defaultdict

from .config import VEHICLE_TYPES, MAX_PAL, ENUM_TIMEOUT
from .models import LN, VehiclePlan, PlanResult


# ============================================================
# Booking Sequence 集中度评分（同组软约束的评分函数）
# 分越高越好：同 booking_seq 的 LN 越集中在同一辆车分数越高
# ============================================================
def _booking_score(vehicles: List[VehiclePlan]) -> int:
    """
    返回同 Booking Sequence 的 LN 中有多少对被分到了不同的车 → 越小越好
    （0 = 完美，全部同组都在一起）
    """
    from collections import defaultdict
    # 统计每个 booking_seq 出现在多少辆车里
    seq_cars = defaultdict(set)
    for vh in vehicles:
        for ln in vh.lns:
            if ln.booking_seq:  # 空的不算
                seq_cars[ln.booking_seq].add(id(vh))
    # 分散度 = Σ (出现车辆数 - 1)，0 表示完美集中
    scattered = sum(len(cars) - 1 for cars in seq_cars.values())
    return scattered


def _has_booking_data(lns: List[LN]) -> bool:
    """是否存在有效 Booking Sequence 数据"""
    return any(ln.booking_seq for ln in lns)


def _optimize_booking(vehicles: List[VehiclePlan]) -> List[VehiclePlan]:
    """
    后处理：在不改变 Q（不改变车型和数量）的前提下，
    通过 LN 移动/交换来降低 Booking Sequence 分散度。
    纯局部搜索，快且有效。
    """
    # 把 vehicles 转成可修改的 list[list[LN]]
    truck_lns = [list(vh.lns) for vh in vehicles]
    truck_rem = [vh.max_pallets - sum(ln.pallets for ln in vh.lns) for vh in vehicles]
    K = len(vehicles)

    def scatter_score() -> int:
        seq_cars = defaultdict(set)
        for j in range(K):
            for ln in truck_lns[j]:
                if ln.booking_seq:
                    seq_cars[ln.booking_seq].add(j)
        return sum(len(cars) - 1 for cars in seq_cars.values())

    improved = True
    rounds = 0
    while improved and rounds < 20:
        improved = False
        rounds += 1
        cur_scatter = scatter_score()

        # 操作1：把 LN 从车 A 移到车 B（如果 B 已有相同 booking_seq）
        for a in range(K):
            for ln_idx, ln in enumerate(truck_lns[a]):
                if not ln.booking_seq:
                    continue
                for b in range(K):
                    if a == b:
                        continue
                    if truck_rem[b] < ln.pallets:
                        continue
                    # 车 B 必须已经有相同 booking_seq 的 LN（才有意义）
                    if not any(x.booking_seq == ln.booking_seq for x in truck_lns[b]):
                        continue
                    # 执行移动
                    truck_lns[a].pop(ln_idx)
                    truck_lns[b].append(ln)
                    truck_rem[a] += ln.pallets
                    truck_rem[b] -= ln.pallets
                    new_scatter = scatter_score()
                    if new_scatter < cur_scatter:
                        improved = True
                        break
                    else:
                        # 回滚
                        truck_lns[b].pop()
                        truck_lns[a].insert(ln_idx, ln)
                        truck_rem[b] += ln.pallets
                        truck_rem[a] -= ln.pallets
                if improved:
                    break
            if improved:
                break

        # 操作2：交换两辆车的 LN（使得双方都更集中）
        if not improved:
            for a in range(K):
                for b in range(a + 1, K):
                    for ia, lna in enumerate(truck_lns[a]):
                        if not lna.booking_seq:
                            continue
                        for ib, lnb in enumerate(truck_lns[b]):
                            if not lnb.booking_seq:
                                continue
                            a_has_bseq = any(x.booking_seq == lnb.booking_seq for x in truck_lns[a])
                            b_has_aseq = any(x.booking_seq == lna.booking_seq for x in truck_lns[b])
                            if not a_has_bseq and not b_has_aseq:
                                continue
                            # 检查交换后两车都不超上限
                            used_a = sum(x.pallets for x in truck_lns[a])
                            used_b = sum(x.pallets for x in truck_lns[b])
                            if used_a - lna.pallets + lnb.pallets > vehicles[a].max_pallets:
                                continue
                            if used_b - lnb.pallets + lna.pallets > vehicles[b].max_pallets:
                                continue
                            # 执行交换
                            truck_lns[a][ia] = lnb
                            truck_lns[b][ib] = lna
                            new_scatter = scatter_score()
                            if new_scatter < cur_scatter:
                                improved = True
                                break
                            else:
                                # 回滚
                                truck_lns[a][ia] = lna
                                truck_lns[b][ib] = lnb
                        if improved:
                            break
                    if improved:
                        break
                if improved:
                    break

    # 重建 vehicles
    new_vehicles = []
    for j in range(K):
        vh = vehicles[j]
        new_vehicles.append(VehiclePlan(
            vtype_name=vh.vtype_name, max_pallets=vh.max_pallets,
            cost_q=vh.cost_q, lns=truck_lns[j]))
    return new_vehicles


# ============================================================
# 主入口
# ============================================================
def plan_optimal(lns: List[LN], verbose: bool = True) -> PlanResult:
    from .data_loader import preprocess
    valid, oversize = preprocess(lns)

    has_bs = _has_booking_data(valid)
    if verbose:
        print(f"      枚举所有车型组合求全局最优...")
        if has_bs:
            print(f"      ✨ 启用 Booking Sequence 同组软约束")
    vehicles = enumerate_best_fleet(valid, verbose=verbose)

    return PlanResult(
        vehicles=vehicles,
        total_cost=sum(v.cost_q for v in vehicles),
        total_pallets=sum(v.used_pallets for v in vehicles),
        oversized_lns=oversize,
    )


# ============================================================
# 车型组合枚举（Q 升序，同 Q 取 Booking Sequence 更集中的）
# ============================================================
def enumerate_best_fleet(valid_lns: List[LN], verbose: bool = True) -> List[VehiclePlan]:
    total_pal = sum(ln.pallets for ln in valid_lns)
    n = len(valid_lns)
    has_bs = _has_booking_data(valid_lns)

    min_k = math.ceil(total_pal / MAX_PAL)
    max_k = min(n, math.ceil(total_pal / VEHICLE_TYPES[0][1]))

    if verbose:
        print(f"      车辆数范围: {min_k} ~ {max_k}")

    # 生成所有车型组合（Q 升序）
    all_fleets = []
    for k in range(min_k, max_k + 1):
        ranges = [range(0, k + 1) for _ in VEHICLE_TYPES]
        for counts in product(*ranges):
            if sum(counts) != k:
                continue
            fleet = []
            for ti, cnt in enumerate(counts):
                for _ in range(cnt):
                    vt = VEHICLE_TYPES[ti]
                    fleet.append((vt[0], vt[1], vt[2]))
            fleet_q = sum(f[2] for f in fleet)
            all_fleets.append((fleet_q, k, fleet))

    all_fleets.sort(key=lambda x: x[0])
    if verbose:
        print(f"      共 {len(all_fleets)} 种车型组合，按 Q 升序枚举...")

    best_result = None
    best_q = float('inf')
    best_scatter = float('inf')
    checked = 0
    t_start = time.time()

    for fleet_q, k, fleet in all_fleets:
        if time.time() - t_start > ENUM_TIMEOUT:
            if verbose:
                print(f"      ⏱ 超时 {ENUM_TIMEOUT}s，停止枚举...")
            break

        if fleet_q > best_q:
            continue

        result = solve_with_fleet_fast(valid_lns, fleet)
        checked += 1

        if result is not None:
            total_ln_pal = sum(sum(ln.pallets for ln in v.lns) for v in result)
            if total_ln_pal == total_pal:
                # 后处理：Booking Sequence 集中化（不增加 Q）
                if has_bs:
                    result = _optimize_booking(result)
                scatter = _booking_score(result) if has_bs else 0
                if fleet_q < best_q or (fleet_q == best_q and scatter < best_scatter):
                    best_q = fleet_q
                    best_scatter = scatter
                    best_result = result
                    if verbose:
                        bs_info = f", 分散度={scatter}" if has_bs else ""
                        print(f"      ✅ Q={fleet_q:,} 可行（已检查 {checked} 种{bs_info}）")

    if verbose:
        print(f"      共检查 {checked} 种车型组合")

    if best_result is None:
        if verbose:
            print(f"⚠ 枚举法找不到可行解 → 切到保底贪心")
        return _greedy(valid_lns)
    return best_result


# ============================================================
# 内层装配：贪心 + 回溯
# ============================================================
def solve_with_fleet_fast(valid_lns, fleet):
    """先贪心快速试，失败再回溯"""
    result = _solve_greedy(valid_lns, fleet)
    if result is not None:
        return result
    return _solve_backtrack(valid_lns, fleet)


def _solve_greedy(valid_lns, fleet):
    """
    贪心 Best Fit + Booking Sequence 黏性偏好
    - 同 booking_seq 的 LN 优先挨着装（排序时聚在一起）
    - 装车时，已有相同 booking_seq 的车有额外"黏性加分"
    """
    total_cap = sum(f[1] for f in fleet)
    total_pal = sum(ln.pallets for ln in valid_lns)
    if total_cap < total_pal:
        return None

    has_bs = _has_booking_data(valid_lns)

    # LN 排序：先按 booking_seq 分组（空串排最后），同组内卡板大的先装
    if has_bs:
        sorted_lns = sorted(valid_lns,
                            key=lambda x: (x.booking_seq == "", x.booking_seq, -x.pallets))
    else:
        sorted_lns = sorted(valid_lns, key=lambda x: -x.pallets)

    truck_rem = [f[1] for f in fleet]
    truck_lns = [[] for _ in range(len(fleet))]

    for ln in sorted_lns:
        best_j, best_score = -1, float('-inf')
        for j in range(len(fleet)):
            if truck_rem[j] < ln.pallets:
                continue
            # 基础分 = -剩余空间（Best Fit：剩余越少越好）
            score = -truck_rem[j]
            # Booking Sequence 黏性加分：这辆车已经装了相同 booking_seq 的 LN
            if has_bs and ln.booking_seq:
                same_seq_count = sum(1 for x in truck_lns[j]
                                     if x.booking_seq == ln.booking_seq)
                score += same_seq_count * 10000  # 黏性加分远大于 Best Fit 分
            if score > best_score:
                best_score, best_j = score, j
        if best_j < 0:
            return None
        truck_rem[best_j] -= ln.pallets
        truck_lns[best_j].append(ln)

    vehicles = []
    for j in range(len(fleet)):
        if truck_lns[j]:
            vehicles.append(VehiclePlan(
                vtype_name=fleet[j][0], max_pallets=fleet[j][1],
                cost_q=fleet[j][2], lns=truck_lns[j]))
    return vehicles


def _solve_backtrack(valid_lns, fleet):
    """
    回溯搜索 + 剪枝 + Booking Sequence 优先
    - 同 booking_seq 的 LN 先尝试装进已有同组的车
    - 保证找到可行解（如果存在）
    """
    total_cap = sum(f[1] for f in fleet)
    total_pal = sum(ln.pallets for ln in valid_lns)
    if total_cap < total_pal:
        return None

    has_bs = _has_booking_data(valid_lns)

    if has_bs:
        sorted_lns = sorted(valid_lns,
                            key=lambda x: (x.booking_seq == "", x.booking_seq, -x.pallets))
    else:
        sorted_lns = sorted(valid_lns, key=lambda x: -x.pallets)

    K = len(fleet)
    truck_rem = [f[1] for f in fleet]
    truck_lns = [[] for _ in range(K)]

    def backtrack(idx: int) -> bool:
        if idx == len(sorted_lns):
            return True
        ln = sorted_lns[idx]
        tried = set()

        # 车辆尝试顺序：
        # 1. 已有相同 booking_seq 的车（黏性优先）
        # 2. 剩余空间少的车（Best Fit）
        if has_bs and ln.booking_seq:
            def sort_key(j):
                has_same = any(x.booking_seq == ln.booking_seq for x in truck_lns[j])
                return (not has_same, truck_rem[j])
            truck_order = sorted(range(K), key=sort_key)
        else:
            truck_order = sorted(range(K), key=lambda j: truck_rem[j])

        for j in truck_order:
            key = (fleet[j][1], truck_rem[j])
            if key in tried:
                continue
            tried.add(key)
            if truck_rem[j] >= ln.pallets:
                truck_rem[j] -= ln.pallets
                truck_lns[j].append(ln)
                if backtrack(idx + 1):
                    return True
                truck_lns[j].pop()
                truck_rem[j] += ln.pallets
        return False

    if backtrack(0):
        vehicles = []
        for j in range(K):
            if truck_lns[j]:
                vehicles.append(VehiclePlan(
                    vtype_name=fleet[j][0], max_pallets=fleet[j][1],
                    cost_q=fleet[j][2], lns=truck_lns[j]))
        return vehicles
    return None


# ============================================================
# 保底贪心（含 Booking Sequence 黏性）
# ============================================================
def _greedy(valid_lns: List[LN], verbose: bool = True) -> List[VehiclePlan]:
    has_bs = _has_booking_data(valid_lns)

    if has_bs:
        remaining = sorted(valid_lns,
                           key=lambda x: (x.booking_seq == "", x.booking_seq, -x.pallets))
    else:
        remaining = sorted(valid_lns, key=lambda x: -x.pallets)
    vehicles: List[VehiclePlan] = []

    while remaining and len(vehicles) < len(valid_lns) + 5:
        ln = remaining.pop(0)
        best_idx, best_score = -1, float('-inf')
        for vi, vh in enumerate(vehicles):
            if vh.used_pallets + ln.pallets <= vh.max_pallets:
                # 利用率分
                util = (vh.used_pallets + ln.pallets) / vh.max_pallets
                score = util * 100
                # Booking Sequence 黏性加分
                if has_bs and ln.booking_seq:
                    same_cnt = sum(1 for x in vh.lns if x.booking_seq == ln.booking_seq)
                    score += same_cnt * 1000
                if score > best_score:
                    best_score, best_idx = score, vi
        if best_idx >= 0:
            vehicles[best_idx].lns.append(ln)
            continue
        best_vt, best_q = None, float('inf')
        for vt in VEHICLE_TYPES:
            if vt[1] >= ln.pallets and vt[2] < best_q:
                best_q, best_vt = vt[2], vt
        if best_vt:
            vehicles.append(VehiclePlan(vtype_name=best_vt[0], max_pallets=best_vt[1],
                                         cost_q=best_vt[2], lns=[ln]))

    if verbose:
        print(f"      初始贪心: {len(vehicles)} 辆, Q={sum(v.cost_q for v in vehicles):,}")

    any_change = True
    rounds = 0
    while any_change and rounds < 200:
        any_change = False
        rounds += 1

        # 消小车
        for kill_i in sorted(range(len(vehicles)),
                             key=lambda x: vehicles[x].pallet_util):
            if vehicles[kill_i].pallet_util >= 0.50:
                break
            all_other = []
            for j in range(len(vehicles)):
                if j != kill_i:
                    all_other.append([v for v in vehicles[j].lns])
            temp_vehicles = [vehicles[j] for j in range(len(vehicles)) if j != kill_i]
            ok = True
            for ln in vehicles[kill_i].lns:
                placed = False
                # 优先装进已有相同 booking_seq 的车
                order = list(range(len(all_other)))
                if has_bs and ln.booking_seq:
                    order.sort(key=lambda oi: -sum(
                        1 for x in all_other[oi] if x.booking_seq == ln.booking_seq))
                for oi in order:
                    tv = all_other[oi]
                    used = sum(l.pallets for l in tv)
                    if used + ln.pallets <= temp_vehicles[oi].max_pallets:
                        tv.append(ln)
                        placed = True
                        break
                if not placed:
                    ok = False
                    break
            if ok:
                for oi, tv in enumerate(all_other):
                    temp_vehicles[oi].lns = tv
                vehicles = temp_vehicles
                any_change = True
                break

        if not any_change:
            n = len(vehicles)
            for k in range(n, 1, -1):
                done = False
                for combo in combinations(range(n), k):
                    all_lns = []
                    for i in combo:
                        all_lns.extend(vehicles[i].lns)
                    tp = sum(ln.pallets for ln in all_lns)
                    tq_old = sum(vehicles[i].cost_q for i in combo)
                    for vt in VEHICLE_TYPES:
                        if vt[1] >= tp and vt[2] < tq_old:
                            new_vh = VehiclePlan(vtype_name=vt[0], max_pallets=vt[1],
                                                 cost_q=vt[2], lns=all_lns)
                            for i in sorted(combo, reverse=True):
                                vehicles.pop(i)
                            vehicles.append(new_vh)
                            any_change = True
                            done = True
                            break
                    if done:
                        break
                if done:
                    break

        if not any_change:
            for vh in vehicles:
                tp = vh.used_pallets
                for vt in VEHICLE_TYPES:
                    if vt[1] >= tp and vt[2] < vh.cost_q:
                        vh.vtype_name = vt[0]
                        vh.max_pallets = vt[1]
                        vh.cost_q = vt[2]
                        any_change = True
                        break

    if verbose:
        print(f"      后处理后: {len(vehicles)} 辆（{rounds}轮）, Q={sum(v.cost_q for v in vehicles):,}")
    return vehicles
