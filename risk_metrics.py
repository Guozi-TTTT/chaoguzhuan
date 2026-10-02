"""
风险指标计算模块
基于 data_fetcher.py 生成的日线数据，计算以下指标：
- 多回看窗口 ATR / 多周期 ATR(14)
- 夏普比率
- 最大回撤
- 年化收益率
- 年化波动率
- 快照保存到 Excel
"""

import pandas as pd
import numpy as np
from pathlib import Path

# ============== 数据加载 ==============

def load_daily_data(excel_path: str) -> pd.DataFrame:
    """从 data_fetcher 生成的 Excel 中读取日线数据"""
    df = pd.read_excel(excel_path, sheet_name="日线数据")
    df["日期"] = pd.to_datetime(df["日期"])
    df = df.sort_values("日期").reset_index(drop=True)
    return df


def _filter_period(df: pd.DataFrame, period_days: int = None) -> pd.DataFrame:
    """按最近 N 天截取数据，None 表示全周期"""
    if period_days is None:
        return df.copy()
    cutoff = df["日期"].max() - pd.Timedelta(days=period_days)
    return df[df["日期"] >= cutoff].reset_index(drop=True)


# ============== ATR 计算 ==============

def calc_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """ATR = TR 的 period 期 EMA"""
    high = df["最高"]
    low = df["最低"]
    prev_close = df["收盘"].shift(1)

    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)

    return tr.ewm(span=period, adjust=False).mean()


def calc_atr_multi(df: pd.DataFrame) -> dict:
    """多回看窗口 ATR 最新值"""
    windows = {
        "1周(5日)": 5,
        "1月(22日)": 22,
        "1季(66日)": 66,
        "1年(252日)": 252,
        "3年(756日)": 756,
        "5年(1260日)": 1260,
        "10年(2520日)": 2520,
    }
    return {label: round(calc_atr(df, p).iloc[-1], 4)
            for label, p in windows.items()}


def _resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """将日线 resample 为指定周期的 K 线"""
    tmp = df.copy()
    tmp.set_index("日期", inplace=True)
    agg = tmp.resample(rule).agg({
        "开盘": "first", "最高": "max", "最低": "min",
        "收盘": "last", "成交量": "sum", "成交额": "sum"
    }).dropna(subset=["收盘"])
    agg.index.name = "日期"
    agg = agg.reset_index()
    return agg


def calc_atr_by_period(df: pd.DataFrame) -> dict:
    """周线 / 月线 / 季度线各自的 ATR(14)"""
    result = {}
    for label, rule in [("周线", "W-FRI"), ("月线", "ME"), ("季度线", "QE")]:
        resampled = _resample(df, rule)
        if len(resampled) < 2:
            result[label] = "数据不足"
        else:
            result[label] = round(calc_atr(resampled, 14).iloc[-1], 4)
    return result


# ============== 风险指标 ==============

def calc_max_drawdown(df: pd.DataFrame) -> float:
    close = df["收盘"]
    return ((close - close.cummax()) / close.cummax()).min()


def calc_annualized_return(df: pd.DataFrame, trading_days: int = 252) -> float:
    log_ret = np.log(df["收盘"] / df["收盘"].shift(1)).dropna()
    total = np.log(df["收盘"].iloc[-1] / df["收盘"].iloc[0])
    return total / len(log_ret) * trading_days


def calc_annualized_volatility(df: pd.DataFrame, trading_days: int = 252) -> float:
    log_ret = np.log(df["收盘"] / df["收盘"].shift(1)).dropna()
    return log_ret.std() * np.sqrt(trading_days)


def calc_sharpe_ratio(df: pd.DataFrame, risk_free_rate: float = 0.02,
                      trading_days: int = 252) -> float:
    ann_ret = calc_annualized_return(df, trading_days)
    ann_vol = calc_annualized_volatility(df, trading_days)
    if ann_vol == 0:
        return 0.0
    return (ann_ret - risk_free_rate) / ann_vol


# ============== 汇总入口 ==============

def compute_all_from_df(df: pd.DataFrame, risk_free_rate: float = 0.02,
                        period_days: int = None) -> dict:
    """
    从日线 DataFrame 计算全部风险指标（不依赖 Excel）。
    :param period_days: None 全周期，传数字看最近 N 天
    """
    work = df.copy()
    if "日期" in work.columns:
        work["日期"] = pd.to_datetime(work["日期"])
        work = work.sort_values("日期").reset_index(drop=True)
    work = _filter_period(work, period_days)
    if work.empty:
        raise ValueError("指标计算失败：区间内无数据")

    return {
        "数据区间": f"{work['日期'].iloc[0].date()} ~ {work['日期'].iloc[-1].date()}",
        "样本数": int(len(work)),
        "ATR(14)": round(calc_atr(work).iloc[-1], 4),
        "夏普比率": round(calc_sharpe_ratio(work, risk_free_rate), 4),
        "最大回撤 (%)": round(calc_max_drawdown(work) * 100, 2),
        "年化收益率 (%)": round(calc_annualized_return(work) * 100, 2),
        "年化波动率 (%)": round(calc_annualized_volatility(work) * 100, 2),
        "ATR_多窗口": calc_atr_multi(work),
        "ATR_多周期": calc_atr_by_period(work),
    }


def compute_all(excel_path: str, risk_free_rate: float = 0.02,
                period_days: int = None) -> dict:
    """
    一次性计算所有风险指标（Excel 入口，便于留档流程复用）
    :param period_days: None 全周期，传数字看最近 N 天
    """
    df = load_daily_data(excel_path)
    return compute_all_from_df(df, risk_free_rate, period_days)


# ============== 快照保存 ==============

def _auto_fit_columns(writer, sheet_name: str, df: pd.DataFrame):
    """自动适配列宽"""
    ws = writer.sheets[sheet_name]
    for i, col in enumerate(df.columns):
        max_len = max(
            df[col].astype(str).str.len().max(),
            len(str(col))
        )
        ws.set_column(i, i, min(max_len + 4, 40))


def save_to_excel(metrics: dict, data_excel_path: str):
    """将风险指标写入原始数据 Excel 的新工作表"风险指标"，列宽自动适配"""
    # 展平嵌套字典
    flat = {}
    for k, v in metrics.items():
        if isinstance(v, dict):
            for sub_k, sub_v in v.items():
                flat[f"{k}_{sub_k}"] = sub_v
        else:
            flat[k] = v

    df = pd.DataFrame([flat])
    df.insert(0, "计算时间", pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"))

    with pd.ExcelWriter(data_excel_path, engine="openpyxl", mode="a",
                        if_sheet_exists="replace") as writer:
        df.to_excel(writer, sheet_name="风险指标", index=False)
        _auto_fit_columns(writer, "风险指标", df)

    print(f"风险指标已写入 {data_excel_path} [风险指标]")


def save_snapshot(metrics: dict, snapshot_path: str = r"G:\炒股传\risk_snapshots.xlsx"):
    """将指标结果追加到快照 Excel，每行一条记录带日期，列宽自动适配"""
    now = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")

    # 展平嵌套字典
    flat = {"时间": now}
    for k, v in metrics.items():
        if isinstance(v, dict):
            for sub_k, sub_v in v.items():
                flat[f"{k}_{sub_k}"] = sub_v
        else:
            flat[k] = v

    new_row = pd.DataFrame([flat])

    path = Path(snapshot_path)
    if path.exists():
        old = pd.read_excel(path)
        df = pd.concat([old, new_row], ignore_index=True)
    else:
        df = new_row

    with pd.ExcelWriter(snapshot_path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
        _auto_fit_columns(writer, "Sheet1", df)

    print(f"快照已追加到 {snapshot_path}")


# ============== 输出工具 ==============

def _print_section(title: str, metrics: dict):
    print(f"{'=' * 50}")
    print(f"  {title}")
    print(f"{'=' * 50}")
    for k, v in metrics.items():
        if isinstance(v, dict):
            print(f"  {k}:")
            for sub_k, sub_v in v.items():
                print(f"    {sub_k:<16}  {sub_v}")
        else:
            print(f"  {k:<18}  {v}")
    print()


# ============== 主程序 ==============

if __name__ == "__main__":
    excel_path = r"G:\炒股传\小米股票数据.xlsx"

    full = compute_all(excel_path)
    yearly = compute_all(excel_path, period_days=365)

    # —— ATR 多回看窗口表格 ——
    print(f"{'=' * 55}")
    print("  ATR 多回看窗口")
    print(f"{'=' * 55}")
    print(f"  {'窗口':<16}  {'全周期':>12}  {'近一年':>12}")
    print(f"  {'-'*16}  {'-'*12}  {'-'*12}")
    for label in full["ATR_多窗口"]:
        fv = full["ATR_多窗口"].get(label, "-")
        yv = yearly["ATR_多窗口"].get(label, "-")
        print(f"  {label:<16}  {str(fv):>12}  {str(yv):>12}")
    print()

    # —— 多周期 ATR(14) 对比 ——
    print(f"{'=' * 55}")
    print("  ATR(14) 多周期")
    print(f"{'=' * 55}")
    print(f"  {'周期':<16}  {'全周期':>12}  {'近一年':>12}")
    print(f"  {'-'*16}  {'-'*12}  {'-'*12}")
    for label in full["ATR_多周期"]:
        fv = full["ATR_多周期"][label]
        yv = yearly["ATR_多周期"].get(label, "-")
        print(f"  {label:<16}  {str(fv):>12}  {str(yv):>12}")
    print()

    # —— 核心风险指标 ——
    for period_label, m in [("全周期", full), ("近一年", yearly)]:
        _print_section(f"{period_label} 核心指标", {
            k: v for k, v in m.items()
            if not k.startswith("ATR_")
        })

    # 保存到原始 Excel + 快照
    save_to_excel(full, excel_path)
    save_snapshot(full)
    save_snapshot(yearly)
