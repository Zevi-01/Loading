# -*- coding: utf-8 -*-
"""
命令行入口：python run.py [LN数据.xlsx] [输出.xlsx]
"""
import sys, os, time, math

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config import VEHICLE_TYPES, MAX_PAL
from src.models import LN
from src.solver import plan_optimal
from src.data_loader import load_lns
from src.exporter import save_result


def main():
    input_excel = sys.argv[1] if len(sys.argv) > 1 else "LN数据.xlsx"
    output_excel = sys.argv[2] if len(sys.argv) > 2 else "排车结果.xlsx"

    try:
        lns = load_lns(input_excel)
    except Exception as e:
        print(f"⚠ 读取 '{input_excel}' 失败 ({e})，用演示数据跑...")
        lns = [LN(f"LN-A{i:02d}", p, booking_seq=f"BK-{i % 4 + 1:03d}")
               for i, p in enumerate(
            [21, 7, 12, 18, 2, 9, 10, 7, 20, 16, 14, 11, 5, 7, 3, 4, 10, 15, 2, 8])]

    total_pal = sum(ln.pallets for ln in lns)
    min_q_theory = math.ceil(total_pal / MAX_PAL) * 16600

    # 统计 Booking Sequence
    from collections import Counter
    bk_counter = Counter(ln.booking_seq for ln in lns if ln.booking_seq)

    print(f"\n{'='*60}")
    print(f"数据诊断")
    print(f"{'='*60}")
    print(f"Loading 条数       : {len(lns)}")
    print(f"总卡板数           : {total_pal}")
    print(f"理论最低Q（下界）   : {min_q_theory:,}")
    if bk_counter:
        print(f"Booking Sequence   : {len(bk_counter)} 组 → {dict(bk_counter)}")
    print(f"--- 每条 Loading 明细 ---")
    for ln in sorted(lns, key=lambda x: -x.pallets):
        flag = "⚠超34" if ln.pallets > MAX_PAL else ""
        bk = f" BK={ln.booking_seq}" if ln.booking_seq else ""
        print(f"  {ln.ln_id:12s} 卡板={ln.pallets:2d}{bk} {flag}")
    print(f"{'='*60}\n")

    print(f"[1/2] 开始排车...")
    t0 = time.time()
    res = plan_optimal(lns)
    print(f"[2/2] 完成（耗时 {time.time()-t0:.1f}s）")

    print(res.summary())
    save_result(res, output_excel)
    print(f"\n✅ 已输出: {output_excel}")


if __name__ == "__main__":
    main()
