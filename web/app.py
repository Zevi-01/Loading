# -*- coding: utf-8 -*-
"""
LN 排车优化 —— Streamlit Web 界面（拖拽上传版）
运行：streamlit run web/app.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
import io, time
from collections import Counter, defaultdict

from src.config import VEHICLE_TYPES, MAX_PAL
from src.models import LN
from src.solver import plan_optimal
from src.data_loader import load_lns_from_bytes
from src.exporter import save_result_to_bytes


# ============================================================
# 页面配置
# ============================================================
st.set_page_config(
    page_title="LN 入仓排车优化",
    page_icon="🚛",
    layout="wide",
)

st.markdown("""
<style>
    .upload-section {
        border: 3px dashed #4e8cff;
        border-radius: 16px;
        padding: 40px 30px;
        text-align: center;
        background: linear-gradient(135deg, #f0f6ff 0%, #e8f0fe 100%);
        margin: 10px 0;
        transition: all 0.3s;
    }
    .upload-section:hover {
        border-color: #1a5fff;
        background: linear-gradient(135deg, #e8f0fe 0%, #dbeafe 100%);
    }
    .upload-icon { font-size: 48px; }
    .divider-thick { height: 3px; background: linear-gradient(90deg, #4e8cff, transparent); border: none; margin: 20px 0; }
</style>
""", unsafe_allow_html=True)


# ============================================================
# 侧边栏
# ============================================================
with st.sidebar:
    st.header("⚙️ 车型配置")
    vt_df = pd.DataFrame(VEHICLE_TYPES, columns=["车型", "卡板上限", "Q值"])
    st.dataframe(vt_df, use_container_width=True, hide_index=True)
    st.info(f"超过 {MAX_PAL} 板的 Loading 无法装下")
    st.divider()
    st.markdown("""
    **约束层级：**
    1️⃣ Q 值最低（硬目标）
    2️⃣ 同 Loading 不拆分（硬约束）
    3️⃣ 同 Booking Sequence 尽量同车（软约束）
    """)


# ============================================================
# 主标题
# ============================================================
st.title("🚛 LN 入仓排车优化 · Q 值最低全局最优")
st.caption("Loading 不拆分 · Q 值最低 · 同 Booking Sequence 尽量同车")
st.markdown("---")


# ============================================================
# Step 1：拖拽上传区
# ============================================================
st.markdown("### 📤 Step 1：上传数据")

col_left, col_right = st.columns([2, 1])
with col_left:
    st.markdown("""
    <div class="upload-section">
        <div class="upload-icon">📁 ↓</div>
        <div style="font-size:18px; font-weight:bold; margin:8px 0;">
            把 Excel 文件拖到这里
        </div>
        <div style="color:#666; font-size:14px;">
            或点击下方按钮选择文件 · 支持 .xlsx / .xls
        </div>
    </div>
    """, unsafe_allow_html=True)

with col_right:
    st.markdown("**📝 新模板表头：**")
    template_df = pd.DataFrame({
        "Loading": ["L-001", "L-002", "L-003"],
        "Booking Sequence": ["BK-001", "BK-001", "BK-002"],
        "Plt QTY": [20, 15, 8],
        "Case Qty": [100, 75, 40],
        "GW": [1200, 900, 480],
        "Vol": [60, 45, 24],
    })
    template_buf = io.BytesIO()
    template_df.to_excel(template_buf, index=False, engine="openpyxl")
    template_buf.seek(0)
    st.download_button(
        "⬇️ 下载 Excel 模板",
        data=template_buf.getvalue(),
        file_name="Loading排车_数据模板.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
    st.caption("必需列：**Loading** + **Plt QTY**\n可选：**Booking Sequence**（同组尽量同车）")

# 真正的上传
uploaded = st.file_uploader(
    "**拖拽 Excel 到这里 ↑**  （.xlsx / .xls）",
    type=["xlsx", "xls"],
    key="file_uploader_main",
    label_visibility="collapsed",
)

# 演示数据
st.markdown("<div style='text-align:center; color:#888; margin:10px 0;'>— 或者 —</div>",
            unsafe_allow_html=True)
demo_col1, demo_col2, demo_col3 = st.columns([1, 2, 1])
with demo_col2:
    use_demo = st.button("🎯 用演示数据试跑（20 条 Loading + Booking Sequence）", use_container_width=True)


# ============================================================
# 数据加载
# ============================================================
lns = None

if uploaded:
    try:
        lns = load_lns_from_bytes(uploaded.getvalue(), uploaded.name)
        has_bs = any(ln.booking_seq for ln in lns)
        bs_info = f"，含 {len(set(ln.booking_seq for ln in lns if ln.booking_seq))} 组 Booking Sequence" if has_bs else ""
        st.success(f"✅ 加载成功：**{len(lns)} 条 Loading**（按 Loading 已聚合卡板{bs_info}）")
    except Exception as e:
        st.error(f"❌ 读取失败：{e}")
        lns = None

elif use_demo:
    demo_pallets = [21, 7, 12, 18, 2, 9, 10, 7, 20, 16, 14, 11, 5, 7, 3, 4, 10, 15, 2, 8]
    lns = [LN(f"L-{i:03d}", p, booking_seq=f"BK-{i % 4 + 1:03d}")
           for i, p in enumerate(demo_pallets)]
    st.success(f"🎯 已载入演示数据：**{len(lns)} 条 Loading** + Booking Sequence")


# ============================================================
# Step 2：数据诊断 + 运行
# ============================================================
if lns:
    st.markdown('<hr class="divider-thick">', unsafe_allow_html=True)
    st.markdown("### 📊 Step 2：数据检查 & 开始排车")

    total_pal = sum(ln.pallets for ln in lns)
    min_q_theory = -(-total_pal // MAX_PAL) * 16600
    oversize = [ln for ln in lns if ln.pallets > MAX_PAL]
    bk_counter = Counter(ln.booking_seq for ln in lns if ln.booking_seq)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Loading 条数", len(lns))
    c2.metric("总卡板数", total_pal)
    c3.metric("理论最低Q（下界）", f"{min_q_theory:,}")
    c4.metric(f"卡板>{MAX_PAL} 异常", len(oversize),
              delta="⚠ 需人工处理" if oversize else "✅ 无")

    if bk_counter:
        st.markdown(f"**📋 Booking Sequence 分布**：{len(bk_counter)} 组 → "
                     + " · ".join(f"`{k}`×{v}" for k, v in sorted(bk_counter.items())))

    with st.expander("📋 点击查看所有 Loading 明细", expanded=False):
        df_show = pd.DataFrame([
            {"Loading": ln.ln_id, "Plt QTY": ln.pallets,
             "Booking Sequence": ln.booking_seq or "—",
             "异常": f"卡板>{MAX_PAL}" if ln.pallets > MAX_PAL else "✅"}
            for ln in sorted(lns, key=lambda x: -x.pallets)
        ])
        st.dataframe(df_show, use_container_width=True, hide_index=True)

    st.markdown("")
    run_clicked = st.button(
        "🚀 **开始排车**（枚举全局最优 + Booking Sequence 同组）",
        type="primary",
        use_container_width=True,
    )

    if run_clicked:
        with st.spinner("⏳ 枚举车型组合 + Booking Sequence 同组优先..."):
            t0 = time.time()
            result = plan_optimal(lns, verbose=False)
            elapsed = time.time() - t0

        st.success(f"✅ 排车完成！耗时 **{elapsed:.1f} 秒**")

        # ============================================================
        # Step 3：结果展示
        # ============================================================
        st.markdown('<hr class="divider-thick">', unsafe_allow_html=True)
        st.markdown("### 🏆 Step 3：最优排车结果")

        # Booking Sequence 集中度
        seq_cars = defaultdict(set)
        for vh in result.vehicles:
            for ln in vh.lns:
                if ln.booking_seq:
                    seq_cars[ln.booking_seq].add(id(vh))
        scattered = sum(len(cars) - 1 for cars in seq_cars.values())
        perfectly_together = sum(1 for cars in seq_cars.values() if len(cars) == 1)

        r1, r2, r3, r4 = st.columns(4)
        r1.metric("派车总数", f"{len(result.vehicles)} 辆")
        r2.metric("总费用 Q", f"{result.total_cost:,}",
                  delta=f"距下界 {result.total_cost - min_q_theory:,}")
        avg_util = (result.total_pallets / sum(v.max_pallets for v in result.vehicles) * 100) if result.vehicles else 0
        r3.metric("平均卡板利用率", f"{avg_util:.0f}%")
        if seq_cars:
            r4.metric("Booking 同组同车", f"{perfectly_together}/{len(seq_cars)}组",
                      delta=f"分散 {scattered}" if scattered else "✅ 全部集中")
        else:
            r4.metric("Booking Sequence", "无数据")

        # 车型分布
        tc = Counter(v.vtype_name for v in result.vehicles)
        if tc:
            st.markdown("**车型分布**")
            chart_col, info_col = st.columns([3, 1])
            with chart_col:
                st.bar_chart(pd.Series(tc), height=180)
            with info_col:
                st.markdown("**费用分布**")
                for tname, cnt in sorted(tc.items()):
                    tq = sum(v.cost_q for v in result.vehicles if v.vtype_name == tname)
                    st.markdown(f"- **{tname}** ×{cnt}辆 = `{tq:,}`")

        # 每辆车详情（按 Booking Sequence 分组高亮）
        st.markdown("#### 🚚 每辆车明细")
        for i, vh in enumerate(result.vehicles, 1):
            with st.container():
                left, right = st.columns([1, 3])
                with left:
                    st.markdown(f"**#{i}**  `{vh.vtype_name}`")
                    st.caption(f"Q = **{vh.cost_q:,}**")
                    st.caption(f"卡板 {vh.used_pallets}/{vh.max_pallets} "
                               f"({vh.pallet_util*100:.0f}%)")
                with right:
                    # 按 booking_seq 分组显示
                    bk_groups = defaultdict(list)
                    for ln in vh.lns:
                        bk_groups[ln.booking_seq or "(无 Booking Seq)"].append(ln)
                    parts = []
                    for bk, group in bk_groups.items():
                        lns_str = ", ".join(f"`{ln.ln_id}`({ln.pallets})" for ln in group)
                        parts.append(f"**{bk}**: {lns_str}")
                    st.markdown("  |  ".join(parts))

        # 下载
        st.markdown("")
        xlsx_bytes = save_result_to_bytes(result)
        st.download_button(
            "📥 **下载完整 Excel**（成本汇总 + 派车明细 + 异常警告 + Booking 集中度）",
            data=xlsx_bytes,
            file_name=f"排车结果_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

        if result.oversized_lns:
            st.error(f"⚠ 以下 Loading 卡板>{MAX_PAL}，无法装下，需人工处理："
                     f"**{', '.join(ln.ln_id for ln in result.oversized_lns)}**")

        if st.button("🔄 重新排车（换一批数据）", use_container_width=True):
            st.rerun()


# ============================================================
# 底部说明
# ============================================================
st.markdown("---")
st.markdown(
    "💡 **算法**：穷举所有车型组合（Q 升序） → 贪心+回溯求可行装配 → 同 Q 时取 Booking Sequence 最集中的。"
    "20~50 条 Loading 秒级出严格全局最优解。"
)
