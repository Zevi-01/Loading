# -*- coding: utf-8 -*-
"""数据加载：从 Excel 读 LN"""
import pandas as pd
from .models import LN
from .config import MAX_PAL


def load_lns(file_path, ln_col="LN号", pallet_col="卡板数", volume_col="体积"):
    """从 Excel 加载 LN，按 LN号聚合卡板"""
    df = pd.read_excel(file_path)
    missing = {ln_col, pallet_col} - set(df.columns)
    if missing:
        raise ValueError(f"Excel 缺少列: {missing}\n实际列: {list(df.columns)}")
    return _load_from_df(df, ln_col, pallet_col, volume_col)


def load_lns_from_bytes(file_bytes, filename, ln_col="LN号",
                        pallet_col="卡板数", volume_col="体积"):
    """从上传的 bytes 加载 LN（Streamlit Web 用）"""
    import io
    df = pd.read_excel(io.BytesIO(file_bytes))
    return _load_from_df(df, ln_col, pallet_col, volume_col)


def load_lns_from_dataframe(df, ln_col="LN号", pallet_col="卡板数",
                            volume_col="体积"):
    """直接从 DataFrame 加载"""
    missing = {ln_col, pallet_col} - set(df.columns)
    if missing:
        raise ValueError(f"Excel 缺少列: {missing}\n实际列: {list(df.columns)}")
    return _load_from_df(df, ln_col, pallet_col, volume_col)


def _load_from_df(df, ln_col, pallet_col, volume_col):
    df = df.copy()
    df[ln_col] = df[ln_col].astype(str).str.strip()
    agg_pal = df.groupby(ln_col, as_index=False)[pallet_col].sum()
    if volume_col in df.columns:
        agg_vol = df.groupby(ln_col, as_index=False)[volume_col].sum()
        agg = agg_pal.merge(agg_vol, on=ln_col, how="left")
    else:
        agg = agg_pal
        agg[volume_col] = 0.0
    rows = [LN(ln_id=r[ln_col], pallets=int(r[pallet_col]),
               volume=float(r[volume_col])) for _, r in agg.iterrows()]
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
