# -*- coding: utf-8 -*-
"""Excel 输出"""
import io
import pandas as pd
from collections import Counter
from .models import PlanResult
from .config import MAX_PAL


def save_result(result: PlanResult, output_path: str):
    """保存到 Excel 文件"""
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        _write_summary(writer, result)
        _write_detail(writer, result)
        _write_warn(writer, result)


def save_result_to_bytes(result: PlanResult) -> bytes:
    """保存到 bytes（Streamlit Web 下载用）"""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        _write_summary(writer, result)
        _write_detail(writer, result)
        _write_warn(writer, result)
    return buf.getvalue()


def _write_summary(writer, result):
    summary = [
        {"项目": "派车总数", "数值": len(result.vehicles)},
        {"项目": "总卡板数", "数值": result.total_pallets},
        {"项目": "总费用Q", "数值": result.total_cost},
    ]
    for tn, cnt in sorted(Counter(v.vtype_name for v in result.vehicles).items()):
        q = sum(v.cost_q for v in result.vehicles if v.vtype_name == tn)
        summary.append({"项目": f"  {tn} 辆数", "数值": cnt})
        summary.append({"项目": f"  {tn} 费用", "数值": q})
    pd.DataFrame(summary).to_excel(writer, sheet_name="成本汇总", index=False)


def _write_detail(writer, result):
    detail = []
    for i, vh in enumerate(result.vehicles, 1):
        for ln in vh.lns:
            detail.append({
                "车辆序号": i, "车型": vh.vtype_name, "该车Q": vh.cost_q,
                "卡板合计": f"{vh.used_pallets}/{vh.max_pallets}",
                "卡板利用率": f"{vh.pallet_util*100:.0f}%",
                "LN号": ln.ln_id, "LN卡板": ln.pallets, "LN体积m³": ln.volume,
            })
    pd.DataFrame(detail or [{"提示": "无派车"}]).to_excel(
        writer, sheet_name="派车明细", index=False)


def _write_warn(writer, result):
    warn = []
    for ln in result.oversized_lns:
        warn.append({"LN号": ln.ln_id, "卡板": ln.pallets, "异常": f"卡板>{MAX_PAL}"})
    if warn:
        pd.DataFrame(warn).to_excel(writer, sheet_name="异常警告", index=False)
        from openpyxl.styles import PatternFill
        red = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
        ws = writer.sheets["异常警告"]
        for row in ws.iter_rows(min_row=2, max_row=ws.max_row,
                                min_col=1, max_col=ws.max_column):
            for cell in row:
                cell.fill = red
    else:
        pd.DataFrame([{"提示": "无异常"}]).to_excel(
            writer, sheet_name="异常警告", index=False)
