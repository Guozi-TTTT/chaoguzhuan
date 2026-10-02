"""
多市场行情数据获取（A股 / 港股 / 美股）

- A股、港股：AKShare 新浪源
- 美股：yfinance
- 输出统一为中文列：日期/开盘/最高/最低/收盘/成交量/成交额
- 可聚合周线、月线；可选写出 Excel 留档

供 app.py 编排调用；不依赖 risk_metrics。
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Literal

import pandas as pd

# a = 沪深统一入口（内部自动识别 sh/sz）；a_sh / a_sz 仍兼容
Market = Literal["a", "a_sh", "a_sz", "hk", "us"]

OHLC_COLS = ["日期", "开盘", "最高", "最低", "收盘", "成交量", "成交额"]

_MARKET_LABELS = {
    "a": "A股",
    "a_sh": "A股·上海",
    "a_sz": "A股·深圳",
    "hk": "港股",
    "us": "美股",
}


def market_label(market: str) -> str:
    return _MARKET_LABELS.get(market, market)


def resolve_a_exchange(symbol: str) -> str:
    """
    从代码识别沪深交易所。
    6/5/9 开头 → 上海；0/1/2/3 开头 → 深圳。
    已带 sh/sz 前缀时以前缀为准。
    """
    code = str(symbol).strip().lower()
    if code.startswith("sh"):
        return "a_sh"
    if code.startswith("sz"):
        return "a_sz"
    digits = code.removeprefix("sh").removeprefix("sz")
    if not digits.isdigit():
        raise ValueError(f"无法识别 A 股代码: {symbol}")
    if digits[0] in "659":
        return "a_sh"
    if digits[0] in "0123":
        return "a_sz"
    raise ValueError(
        f"无法从代码 {symbol} 判断沪深市场（常见：6/5/9 沪，0/1/2/3 深）"
    )


def _empty_ohlcv() -> pd.DataFrame:
    return pd.DataFrame(columns=OHLC_COLS)


def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """把各数据源列名统一成中文 OHLCV，按日期升序。"""
    if df is None or len(df) == 0:
        return _empty_ohlcv()

    rename = {
        # 英文 / yfinance
        "Date": "日期", "date": "日期", "datetime": "日期",
        "Open": "开盘", "open": "开盘",
        "High": "最高", "high": "最高",
        "Low": "最低", "low": "最低",
        "Close": "收盘", "close": "收盘",
        "Volume": "成交量", "volume": "成交量",
        "amount": "成交额", "Amount": "成交额",
        # akshare 中文
        "开盘": "开盘", "最高": "最高", "最低": "最低", "收盘": "收盘",
        "成交量": "成交量", "成交额": "成交额", "日期": "日期",
    }
    out = df.rename(columns=rename).copy()

    if "日期" not in out.columns:
        if isinstance(out.index, pd.DatetimeIndex):
            out = out.reset_index()
            out = out.rename(columns={out.columns[0]: "日期"})
        else:
            raise ValueError(f"无法识别日期列，原始列: {list(df.columns)}")

    out["日期"] = pd.to_datetime(out["日期"]).dt.tz_localize(None)
    for col in ["开盘", "最高", "最低", "收盘", "成交量"]:
        if col not in out.columns:
            raise ValueError(f"缺少列: {col}")
        out[col] = pd.to_numeric(out[col], errors="coerce")

    if "成交额" not in out.columns:
        out["成交额"] = out["收盘"] * out["成交量"]

    out = (
        out[OHLC_COLS]
        .dropna(subset=["日期", "收盘"])
        .sort_values("日期")
        .reset_index(drop=True)
    )
    return out


def _filter_dates(df: pd.DataFrame, start_date: str | None,
                  end_date: str | None = None) -> pd.DataFrame:
    if df.empty:
        return df
    out = df
    if start_date:
        start = pd.to_datetime(start_date)
        out = out[out["日期"] >= start]
    if end_date:
        end = pd.to_datetime(end_date)
        out = out[out["日期"] <= end]
    return out.reset_index(drop=True)


# ============== 分市场拉取 ==============

def _a_symbol(symbol: str, market: str) -> str:
    code = str(symbol).strip().lower()
    if code.startswith(("sh", "sz")):
        return code
    if market in ("a", "a_sh", "a_sz"):
        exchange = resolve_a_exchange(symbol) if market == "a" else market
    else:
        exchange = market
    prefix = "sh" if exchange == "a_sh" else "sz"
    return f"{prefix}{code}"


def _fetch_a_share(symbol: str, market: str,
                   start_date: str | None) -> pd.DataFrame:
    """A股：优先新浪 stock_zh_a_daily，失败再试 stock_zh_a_hist。"""
    import akshare as ak

    if market == "a":
        market = resolve_a_exchange(symbol)

    prefixed = _a_symbol(symbol, market)
    code = re.sub(r"^(sh|sz)", "", str(symbol).strip().lower())
    start = (start_date or "20100101").replace("-", "")
    end = datetime.today().strftime("%Y%m%d")

    raw = None
    try:
        raw = ak.stock_zh_a_daily(
            symbol=prefixed, start_date=start, end_date=end, adjust="qfq"
        )
        if raw is None or len(raw) == 0:
            raw = None
    except Exception:
        raw = None

    if raw is None:
        raw = ak.stock_zh_a_hist(
            symbol=code, period="daily",
            start_date=start, end_date=end, adjust="qfq",
        )

    return _normalize_ohlcv(raw)


def _fetch_hk(symbol: str, start_date: str | None) -> pd.DataFrame:
    import akshare as ak

    code = str(symbol).strip().zfill(5) if str(symbol).strip().isdigit() \
        else str(symbol).strip()
    start = (start_date or "20100101").replace("-", "")
    end = datetime.today().strftime("%Y%m%d")

    raw = None
    try:
        raw = ak.stock_hk_hist(
            symbol=code, period="daily", start_date=start, end_date=end,
            adjust="qfq",
        )
        if raw is not None and len(raw) == 0:
            raw = None
    except Exception:
        raw = None

    if raw is None or len(raw) == 0:
        raw = ak.stock_hk_daily(symbol=code, adjust="qfq")

    return _normalize_ohlcv(_filter_dates(_normalize_ohlcv(raw),
                                          start_date, None))


def _fetch_us(symbol: str, start_date: str | None) -> pd.DataFrame:
    import time

    code = str(symbol).strip().upper()
    start = start_date or "2010-01-01"
    if start.isdigit():
        start = f"{start[:4]}-{start[4:6]}-{start[6:8]}"

    raw = None
    last_err: Exception | None = None

    # yfinance（主源，可能限流）
    for attempt in range(3):
        try:
            import yfinance as yf

            ticker = yf.Ticker(code)
            raw = ticker.history(start=start, auto_adjust=True)
            if raw is not None and len(raw) > 0:
                break
            raw = yf.download(
                code, start=start, auto_adjust=True,
                progress=False, threads=False,
            )
            if isinstance(getattr(raw, "columns", None), pd.MultiIndex):
                raw.columns = raw.columns.get_level_values(0)
            if raw is not None and len(raw) > 0:
                break
            raw = None
        except Exception as exc:
            last_err = exc
            time.sleep(1.2 * (attempt + 1))

    # AKShare 备用源
    if raw is None or len(raw) == 0:
        try:
            import akshare as ak

            ak_raw = ak.stock_us_daily(symbol=code, adjust="qfq")
            if ak_raw is not None and len(ak_raw) > 0:
                raw = ak_raw
        except Exception as exc:
            last_err = exc

    if raw is None or len(raw) == 0:
        detail = f"：{last_err}" if last_err else ""
        raise RuntimeError(f"美股 {code} 取数失败{detail}")

    return _normalize_ohlcv(raw)


# ============== 周期聚合 ==============

def resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """日线 → 周线/月线等。rule 例: W-FRI / ME"""
    if df is None or len(df) == 0:
        return _empty_ohlcv()
    tmp = df.copy()
    tmp = tmp.set_index("日期")
    agg = tmp.resample(rule).agg({
        "开盘": "first",
        "最高": "max",
        "最低": "min",
        "收盘": "last",
        "成交量": "sum",
        "成交额": "sum",
    }).dropna(subset=["收盘"])
    agg.index.name = "日期"
    return agg.reset_index()


# ============== 统一入口 ==============

def fetch_bars(
    market: Market,
    symbol: str,
    start_date: str | None = "2018-01-01",
    end_date: str | None = None,
) -> dict[str, pd.DataFrame]:
    """
    拉取日线并聚合周线、月线。
    返回: {"daily": df, "weekly": df, "monthly": df}
    """
    symbol = str(symbol).strip()
    if not symbol:
        raise ValueError("股票代码不能为空")

    if market in ("a", "a_sh", "a_sz"):
        daily = _fetch_a_share(symbol, market, start_date)
    elif market == "hk":
        daily = _fetch_hk(symbol, start_date)
    elif market == "us":
        daily = _fetch_us(symbol, start_date)
    else:
        raise ValueError(
            f"不支持的市场: {market}，可选 a（沪深）/ a_sh / a_sz / hk / us"
        )

    daily = _filter_dates(daily, start_date, end_date)
    if daily.empty:
        raise ValueError(f"未获取到 {market_label(market)} {symbol} 的行情数据")

    return {
        "daily": daily,
        "weekly": resample_ohlcv(daily, "W-FRI"),
        "monthly": resample_ohlcv(daily, "ME"),
    }


def save_bars_excel(bars: dict[str, pd.DataFrame], output_path: str | Path) -> Path:
    """可选留档：日/周/月三个 sheet + 自动列宽。"""
    from openpyxl import load_workbook
    from openpyxl.utils import get_column_letter

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(output_path) as writer:
        bars["daily"].to_excel(writer, sheet_name="日线数据", index=False)
        bars["weekly"].to_excel(writer, sheet_name="周线数据", index=False)
        bars["monthly"].to_excel(writer, sheet_name="月线数据", index=False)

    wb = load_workbook(output_path)
    for ws in wb.worksheets:
        for col in ws.columns:
            max_length = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                if cell.value is not None:
                    max_length = max(max_length, len(str(cell.value)))
            ws.column_dimensions[col_letter].width = max_length + 4
    wb.save(output_path)
    return output_path


# ============== 名称/代码搜索 ==============

_CATALOG_CACHE_DIR = Path(__file__).resolve().parent / "data" / "catalog"


def _cache_path(market: str) -> Path:
    return _CATALOG_CACHE_DIR / f"{market}.parquet"


def _save_catalog(market: str, df: pd.DataFrame) -> None:
    try:
        _CATALOG_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        df.to_parquet(_cache_path(market), index=False)
    except Exception:
        try:
            df.to_csv(_cache_path(market).with_suffix(".csv"), index=False)
        except Exception:
            pass


def _load_cached_catalog(market: str) -> pd.DataFrame | None:
    pq = _cache_path(market)
    csv = pq.with_suffix(".csv")
    for path in (pq, csv):
        if not path.exists():
            continue
        try:
            if path.suffix == ".parquet":
                return pd.read_parquet(path)
            return pd.read_csv(path, dtype={"代码": str})
        except Exception:
            continue
    return None


def _pick_col(columns, keywords, fallback_index: int) -> str:
    cols = list(columns)
    for kw in keywords:
        for c in cols:
            if kw in str(c):
                return c
    return cols[fallback_index] if cols else ""


def _load_a_catalog() -> pd.DataFrame:
    """A 股代码-名称目录（代码/名称/交易所）。"""
    import akshare as ak

    raw = ak.stock_info_a_code_name()
    code_col = _pick_col(raw.columns, ("code", "代码"), 0)
    name_col = _pick_col(raw.columns, ("name", "名称", "简称"), 1)
    df = pd.DataFrame({
        "代码": raw[code_col].astype(str).str.strip(),
        "名称": raw[name_col].astype(str).str.strip(),
    })
    df["交易所"] = df["代码"].map(
        lambda c: "上海" if c[:1] in "659" else ("深圳" if c[:1] in "0123" else "其他")
    )
    return df.drop_duplicates("代码").reset_index(drop=True)


def _load_hk_catalog() -> pd.DataFrame:
    """港股代码-名称目录。"""
    import akshare as ak

    raw = None
    for fn in ("stock_hk_spot_em", "stock_hk_spot"):
        try:
            raw = getattr(ak, fn)()
            if raw is not None and len(raw) > 0:
                break
        except Exception:
            raw = None
    if raw is None or len(raw) == 0:
        return pd.DataFrame(columns=["代码", "名称", "交易所"])

    code_col = _pick_col(raw.columns, ("代码", "symbol", "code"), 0)
    name_col = _pick_col(raw.columns, ("名称", "name", "简称"), 1)
    df = pd.DataFrame({
        "代码": raw[code_col].astype(str).str.strip().str.zfill(5),
        "名称": raw[name_col].astype(str).str.strip(),
    })
    df["交易所"] = "香港"
    return df.drop_duplicates("代码").reset_index(drop=True)


def _load_us_catalog() -> pd.DataFrame:
    """美股：常用 ticker + 名称（轻量目录；也支持直接输入 ticker）。"""
    popular = [
        ("AAPL", "苹果 Apple"), ("MSFT", "微软 Microsoft"), ("GOOGL", "谷歌 Alphabet"),
        ("AMZN", "亚马逊 Amazon"), ("NVDA", "英伟达 NVIDIA"), ("META", "Meta"),
        ("TSLA", "特斯拉 Tesla"), ("NFLX", "奈飞 Netflix"), ("AMD", "AMD"),
        ("INTC", "英特尔 Intel"), ("JPM", "摩根大通 JPM"), ("BAC", "美国银行 BAC"),
        ("KO", "可口可乐 KO"), ("PEP", "百事 Pepsi"), ("WMT", "沃尔玛 Walmart"),
        ("DIS", "迪士尼 Disney"), ("BA", "波音 BA"), ("XOM", "埃克森美孚 XOM"),
        ("JNJ", "强生 JNJ"), ("V", "Visa"), ("MA", "万事达 Mastercard"),
        ("ORCL", "甲骨文 Oracle"), ("CRM", "Salesforce"), ("ADBE", "Adobe"),
        ("QQQ", "纳指ETF QQQ"), ("SPY", "标普ETF SPY"),
    ]
    return pd.DataFrame(popular, columns=["代码", "名称"]).assign(交易所="美国")


def load_catalog(market: str, use_cache: bool = True) -> pd.DataFrame:
    """返回 代码/名称/交易所 目录。market: a / hk / us"""
    key = market if market not in ("a_sh", "a_sz") else "a"
    if use_cache:
        cached = _load_cached_catalog(key)
        if cached is not None and len(cached) > 0:
            return cached

    if market in ("a", "a_sh", "a_sz"):
        df = _load_a_catalog()
    elif market == "hk":
        df = _load_hk_catalog()
    elif market == "us":
        df = _load_us_catalog()
    else:
        raise ValueError(f"不支持的市场: {market}")

    if len(df) > 0:
        _save_catalog(key, df)
    return df


def search_stocks(market: str, query: str, limit: int = 20) -> pd.DataFrame:
    """
    按代码或名称模糊搜索。
    query 为空则返回目录前 limit 条（A 股为空时太多，返回空表提示用户输入）。
    """
    q = str(query or "").strip()
    catalog = load_catalog(market)

    if not q:
        if market == "us":
            return catalog.head(limit)
        return catalog.head(0)

    q_lower = q.lower()
    # 代码优先：前缀/包含
    code_hit = catalog[catalog["代码"].str.contains(q_lower, case=False, regex=False)]
    name_hit = catalog[catalog["名称"].str.contains(q, case=False, regex=False, na=False)]
    # 英文名场景
    if market == "us":
        name_hit = catalog[
            catalog["名称"].str.lower().str.contains(q_lower, regex=False, na=False)
        ]

    out = pd.concat([code_hit, name_hit], ignore_index=True).drop_duplicates("代码")
    return out.head(limit).reset_index(drop=True)


def resolve_symbol(market: str, query: str) -> tuple[str, str]:
    """
    把「代码或名称」解析成 (code, name)。
    - 唯一命中：直接返回
    - 多条：若输入本身是合法代码且存在，优先代码；否则抛错并附带候选
    - 无命中：若输入像代码，原样返回；否则报错
    """
    q = str(query or "").strip()
    if not q:
        raise ValueError("请输入股票代码或名称")

    catalog = load_catalog(market)
    q_lower = q.lower()

    # 精确代码
    exact_code = catalog[catalog["代码"].str.lower() == q_lower]
    if len(exact_code) == 1:
        row = exact_code.iloc[0]
        return str(row["代码"]), str(row["名称"])

    # 港股补零
    if market == "hk" and q.isdigit():
        z = q.zfill(5)
        exact_code = catalog[catalog["代码"] == z]
        if len(exact_code) == 1:
            row = exact_code.iloc[0]
            return str(row["代码"]), str(row["名称"])

    # 精确名称
    exact_name = catalog[catalog["名称"] == q]
    if len(exact_name) == 1:
        row = exact_name.iloc[0]
        return str(row["代码"]), str(row["名称"])

    # 模糊
    hits = search_stocks(market, q, limit=8)
    if len(hits) == 1:
        row = hits.iloc[0]
        return str(row["代码"]), str(row["名称"])

    if len(hits) > 1:
        # 名称以关键词开头时选「主板/主名称」：短名优先，人民币柜台（ＷＲ）靠后
        starts = hits[hits["名称"].str.startswith(q)].copy()
        if len(starts) >= 1:
            starts["_wr"] = starts["名称"].str.contains(r"ＷＲ|WR", regex=True)
            starts["_len"] = starts["名称"].str.len()
            starts = starts.sort_values(["_wr", "_len"])
            row = starts.iloc[0]
            return str(row["代码"]), str(row["名称"])

        samples = "、".join(
            f"{r['名称']}({r['代码']})" for _, r in hits.head(5).iterrows()
        )
        raise ValueError(f"「{q}」有多个匹配：{samples}。请补全代码或更完整名称。")

    # 输入像代码就放行（目录可能不全，例如新股/美股）
    if market == "us" and re.fullmatch(r"[A-Za-z.\-]{1,10}", q):
        return q.upper(), q.upper()
    if market in ("a", "a_sh", "a_sz") and re.fullmatch(r"\d{6}", q):
        return q, q
    if market == "hk" and re.fullmatch(r"\d{1,5}", q):
        return q.zfill(5), q.zfill(5)

    raise ValueError(f"未找到「{q}」。可尝试完整代码，或更准确的名称。")


if __name__ == "__main__":
    # 本地自测：默认拉港股小米
    demo = fetch_bars("hk", "01810", start_date="2024-01-01")
    print("日线", len(demo["daily"]), "周线", len(demo["weekly"]), "月线", len(demo["monthly"]))
    print(demo["daily"].tail(3))
