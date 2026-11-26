# -*- coding: utf-8 -*-
"""核心排车算法：车型组合枚举 + 回溯搜索 + 贪心兜底"""
import time, math
from itertools import combinations, product
from typing import List, Tuple, Optional

from .config import VEHICLE_TYPES, MAX_PAL, ENUM_TIMEOUT
from .models import LN, VehiclePlan, PlanResult


def plan_optimal(lns: List[LN], verbose: bool = True) -> PlanResult:
    """主入口：给定 LN 列表，返回最优排车方案"""
    from .data_loader import preprocess
    valid, oversize = preprocess(lns)

    if verbose:
        print(f"      枚举所有车型组合求全局最优...")
    vehicles = enumerate_best_fleet(valid, verbose=verbose)

    return PlanResult(
        vehicles=vehicles,
        total_cost=sum(v.cost_q for v in vehicles),
        total_pallets=sum(v.used_pallets for v in vehicles),
        oversized_lns=oversize,
    )


# ===== 车型组合枚举 =====

def enumerate_best_fleet(valid_lns: List[LN], verbose: bool = True) -> List[VehiclePlan]:
    total_pal = sum(ln.pallets for ln in valid_lns)
    n = len(valid_lns)

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
    checked = 0
    t_start = time.time()

    for fleet_q, k, fleet in all_fleets:
        if time.time() - t_start > ENUM_TIMEOUT:
            if verbose:
                print(f"      ⏱ 超时 {ENUM_TIMEOUT}s，停止枚举...")
            break

        if fleet_q >= best_q:
            continue

        result = solve_with_fleet_fast(valid_lns, fleet)
        checked += 1

        if result is not None:
            total_ln_pal = sum(sum(ln.pallets for ln in v.lns) for v in result)
            if total_ln_pal == total_pal:
                if fleet_q < best_q:
                    best_q = fleet_q
                    best_result = result
                    if verbose:
                        print(f"      ✅ Q={fleet_q:,} 可行（已检查 {checked} 种）")

    if verbose:
        print(f"      共检查 {checked} 种车型组合")

    if best_result is None:
        if verbose:
            print(f"⚠ 枚举法找不到可行解 → 切到保底贪心")
        return _greedy(valid_lns)
    return best_result


# ===== 内层装配（贪心 + 回溯）=====

def solve_with_fleet_fast(valid_lns, fleet):
    """先贪心快速试，失败再回溯"""
    result = _solve_greedy(valid_lns, fleet)
    if result is not None:
        return result
    return _solve_backtrack(valid_lns, fleet)


def _solve_greedy(valid_lns, fleet):
    """贪心 Best Fit 快速试装"""
    total_cap = sum(f[1] for f in fleet)
    total_pal = sum(ln.pallets for ln in valid_lns)
    if total_cap < total_pal:
        return None

    sorted_lns = sorted(valid_lns, key=lambda x: -x.pallets)
    truck_rem = [f[1] for f in fleet]
    truck_lns = [[] for _ in range(len(fleet))]

    for ln in sorted_lns:
        best_j, best_rem = -1, float('inf')
        for j in range(len(fleet)):
            if truck_rem[j] >= ln.pallets and truck_rem[j] < best_rem:
                best_rem, best_j = truck_rem[j], j
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
    """回溯搜索 + 剪枝（保证找到可行解，如果存在）"""
    total_cap = sum(f[1] for f in fleet)
    total_pal = sum(ln.pallets for ln in valid_lns)
    if total_cap < total_pal:
        return None

    sorted_lns = sorted(valid_lns, key=lambda x: -x.pallets)
    K = len(fleet)
    truck_rem = [f[1] for f in fleet]
    truck_lns = [[] for _ in range(K)]

    def backtrack(idx: int) -> bool:
        if idx == len(sorted_lns):
            return True
        ln = sorted_lns[idx]
        tried = set()
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


# ===== 保底贪心 =====

def _greedy(valid_lns: List[LN], verbose: bool = True) -> List[VehiclePlan]:
    remaining = sorted(valid_lns, key=lambda x: -x.pallets)
    vehicles: List[VehiclePlan] = []

    while remaining and len(vehicles) < len(valid_lns) + 5:
        ln = remaining.pop(0)
        best_idx, best_util = -1, -1
        for vi, vh in enumerate(vehicles):
            if vh.used_pallets + ln.pallets <= vh.max_pallets:
                nu = (vh.used_pallets + ln.pallets) / vh.max_pallets
                if nu > best_util:
                    best_util, best_idx = nu, vi
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
                for oi, tv in enumerate(all_other):
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
