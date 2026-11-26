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
from collections import Counter

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

# 自定义 CSS：让上传区域更大更显眼
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
    .big-metric { font-size: 28px; font-weight: bold; }
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
    st.info(f"超过 {MAX_PAL} 板的 LN 无法装下")
    st.divider()
    st.markdown("**流程：**\n1️⃣ 拖 Excel 到右侧\n2️⃣ 确认数据无误\n3️⃣ 点「开始排车」\n4️⃣ 下载结果")


# ============================================================
# 主标题
# ============================================================
st.title("🚛 LN 入仓排车优化 · Q 值最低全局最优")
st.caption("卡板约束 · 不拆分 LN 号 · 枚举所有车型组合 · 严格全局最优解")
st.markdown("---")


# ============================================================
# Step 1：拖拽上传区
# ============================================================
st.markdown("### 📤 Step 1：上传 LN 数据")

# 模板下载按钮（和上传并排）
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
    st.markdown("**📝 没有模板？点下面下载：**")
    # 生成模板 Excel
    template_df = pd.DataFrame({
        "LN号": ["LN-示例001", "LN-示例002", "LN-示例003"],
        "卡板数": [20, 15, 8],
        "体积": [60, 45, 24],
    })
    template_buf = io.BytesIO()
    template_df.to_excel(template_buf, index=False, engine="openpyxl")
    template_buf.seek(0)
    st.download_button(
        "⬇️ 下载 Excel 模板",
        data=template_buf.getvalue(),
        file_name="LN排车_数据模板.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
    st.caption("只需要 **LN号** 和 **卡板数** 两列，体积可选")

# 真正的上传（Streamlit 原生，支持拖拽 + 点击）
uploaded = st.file_uploader(
    "**拖拽 Excel 到这里 ↑**  （.xlsx / .xls）",
    type=["xlsx", "xls"],
    key="file_uploader_main",
    label_visibility="collapsed",
)

# 演示数据按钮
st.markdown("<div style='text-align:center; color:#888; margin:10px 0;'>— 或者 —</div>",
            unsafe_allow_html=True)
demo_col1, demo_col2, demo_col3 = st.columns([1, 2, 1])
with demo_col2:
    use_demo = st.button("🎯 用演示数据试跑（20 条 LN）", use_container_width=True)


# ============================================================
# 数据加载
# ============================================================
lns = None

if uploaded:
    try:
        lns = load_lns_from_bytes(uploaded.getvalue(), uploaded.name)
        st.success(f"✅ 加载成功：**{len(lns)} 条 LN**（按 LN号 已自动聚合卡板）")
    except Exception as e:
        st.error(f"❌ 读取失败：{e}")
        lns = None

elif use_demo:
    demo_pallets = [21, 7, 12, 18, 2, 9, 10, 7, 20, 16, 14, 11, 5, 7, 3, 4, 10, 15, 2, 8]
    lns = [LN(f"LN-A{i:02d}", p) for i, p in enumerate(demo_pallets)]
    st.success(f"🎯 已载入演示数据：**{len(lns)} 条 LN**")


# ============================================================
# Step 2：数据诊断 + 运行
# ============================================================
if lns:
    st.markdown('<hr class="divider-thick">', unsafe_allow_html=True)
    st.markdown("### 📊 Step 2：数据检查 & 开始排车")

    total_pal = sum(ln.pallets for ln in lns)
    min_q_theory = -(-total_pal // MAX_PAL) * 16600
    oversize = [ln for ln in lns if ln.pallets > MAX_PAL]

    # 四个关键指标
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("LN 条数", len(lns))
    c2.metric("总卡板数", total_pal)
    c3.metric("理论最低Q（下界）", f"{min_q_theory:,}")
    c4.metric(f"卡板>{MAX_PAL} 异常", len(oversize),
              delta="⚠ 需人工处理" if oversize else "✅ 无")

    # LN 明细表格
    with st.expander("📋 点击查看所有 LN 明细", expanded=False):
        df_show = pd.DataFrame([
            {"LN号": ln.ln_id, "卡板": ln.pallets,
             "异常": f"卡板>{MAX_PAL}" if ln.pallets > MAX_PAL else "✅"}
            for ln in sorted(lns, key=lambda x: -x.pallets)
        ])
        st.dataframe(df_show, use_container_width=True, hide_index=True)

    # 开始排车按钮
    st.markdown("")
    run_clicked = st.button(
        "🚀 **开始排车**（枚举所有车型组合 + 回溯搜索求全局最优）",
        type="primary",
        use_container_width=True,
    )

    if run_clicked:
        with st.spinner("⏳ 枚举车型组合中...（30 秒内出结果）"):
            t0 = time.time()
            result = plan_optimal(lns, verbose=False)
            elapsed = time.time() - t0

        st.success(f"✅ 排车完成！耗时 **{elapsed:.1f} 秒**")

        # ============================================================
        # Step 3：结果展示
        # ============================================================
        st.markdown('<hr class="divider-thick">', unsafe_allow_html=True)
        st.markdown("### 🏆 Step 3：最优排车结果")

        r1, r2, r3, r4 = st.columns(4)
        r1.metric("派车总数", f"{len(result.vehicles)} 辆")
        r2.metric("总费用 Q", f"{result.total_cost:,}",
                  delta=f"距理论下界 {result.total_cost - min_q_theory:,}")
        avg_util = (result.total_pallets / sum(v.max_pallets for v in result.vehicles) * 100) if result.vehicles else 0
        r3.metric("平均卡板利用率", f"{avg_util:.0f}%")
        r4.metric("车型数", f"{len(set(v.vtype_name for v in result.vehicles))} 种")

        # 车型分布图
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

        # 每辆车详细卡片
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
                    lns_str = "  |  ".join(
                        f"`{ln.ln_id}` ({ln.pallets}板)" for ln in vh.lns)
                    st.markdown(lns_str)

        # 下载
        st.markdown("")
        xlsx_bytes = save_result_to_bytes(result)
        st.download_button(
            "📥 **下载完整 Excel**（成本汇总 + 派车明细 + 异常警告）",
            data=xlsx_bytes,
            file_name=f"排车结果_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

        if result.oversized_lns:
            st.error(f"⚠ 以下 LN 卡板>{MAX_PAL}，无法装下，需人工处理："
                     f"**{', '.join(ln.ln_id for ln in result.oversized_lns)}**")

        # 重新运行按钮
        if st.button("🔄 重新排车（换一批数据）", use_container_width=True):
            st.rerun()


# ============================================================
# 底部说明
# ============================================================
st.markdown("---")
st.markdown(
    "💡 **算法说明**：穷举所有合理车型数量组合 → 按 Q 升序尝试 → 内层回溯搜索保证可行装配。"
    "20~30 条 LN 秒级出严格全局最优解。"
)
