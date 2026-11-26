# -*- coding: utf-8 -*-
"""数据加载：从 Excel 读 Loading / Booking Sequence / Plt QTY

自动识别新旧表头：
  Loading   / LN号   → ln_id
  Plt QTY   / 卡板数 / Pallets / PltQty → pallets
  Booking Sequence / Booking Seq / Booking → booking_seq  （可选）
  Volume    / 体积 / Vol → volume  （可选）
"""
import pandas as pd
from .models import LN
from .config import MAX_PAL


# ===== 列名别名映射（按优先级）=====
LN_ID_ALIASES    = ["Loading", "Loading No", "LN号", "LN", "loading", "ln_id"]
PALLET_ALIASES   = ["Plt QTY", "PltQty", "Pallets", "pallets", "卡板数", "Plt", "plt_qty"]
BOOKING_ALIASES  = ["Booking Sequence", "Booking Seq", "Booking", "booking", "booking_seq"]
VOLUME_ALIASES   = ["Volume", "Vol", "体积", "volume", "vol"]


def _detect_col(df_columns, alias_list, required=False):
    """从 alias 列表中匹配 DataFrame 的实际列名，返回 None 表示没找到"""
    # 先精确匹配（忽略空格和大小写）
    normalized = {c.strip().lower(): c for c in df_columns}
    for alias in alias_list:
        key = alias.strip().lower()
        if key in normalized:
            return normalized[key]
    # 再模糊包含匹配
    for alias in alias_list:
        key = alias.strip().lower()
        for nc, orig in normalized.items():
            if key in nc or nc in key:
                return orig
    if required:
        raise ValueError(f"Excel 缺少必需列之一: {alias_list}\n实际列: {list(df_columns)}")
    return None


def load_lns(file_path):
    """从 Excel 加载 LN，自动识别表头"""
    df = pd.read_excel(file_path)
    return _load_from_df(df)


def load_lns_from_bytes(file_bytes, filename):
    """从上传的 bytes 加载 LN（Streamlit Web 用）"""
    import io
    df = pd.read_excel(io.BytesIO(file_bytes))
    return _load_from_df(df)


def load_lns_from_dataframe(df):
    """直接从 DataFrame 加载"""
    return _load_from_df(df)


def _load_from_df(df):
    df = df.copy()

    # 自动识别列名
    ln_col     = _detect_col(df.columns, LN_ID_ALIASES, required=True)
    pal_col    = _detect_col(df.columns, PALLET_ALIASES, required=True)
    book_col   = _detect_col(df.columns, BOOKING_ALIASES, required=False)
    vol_col    = _detect_col(df.columns, VOLUME_ALIASES, required=False)

    print(f"      识别表头 → Loading={ln_col}, PltQTY={pal_col}, "
          f"Booking={book_col or '无'}, Vol={vol_col or '无'}")

    df[ln_col]  = df[ln_col].astype(str).str.strip()
    if book_col:
        df[book_col] = df[book_col].astype(str).str.strip()

    # 按 Loading 号聚合（硬约束：同 Loading 号不拆分）
    agg_dict = {pal_col: "sum"}
    if vol_col:
        agg_dict[vol_col] = "sum"
    if book_col:
        agg_dict[book_col] = "first"  # 同 Loading 号的 Booking Sequence 应相同

    agg = df.groupby(ln_col, as_index=False).agg(agg_dict)

    rows = []
    for _, r in agg.iterrows():
        bseq = str(r.get(book_col, "")).strip() if book_col else ""
        vol  = float(r[vol_col]) if vol_col else 0.0
        rows.append(LN(
            ln_id=str(r[ln_col]).strip(),
            pallets=int(r[pal_col]),
            volume=vol,
            booking_seq=bseq,
        ))
    print(f"      Excel 原始 {len(df)} 行 → 按 Loading 聚合后 {len(rows)} 条")
    return rows


def preprocess(lns):
    """分离正常 LN 和超上限 LN"""
    valid, oversize = [], []
    for ln in lns:
        if ln.pallets > MAX_PAL:
            oversize.append(ln)
        else:
            valid.append(ln)
    return valid, oversize
