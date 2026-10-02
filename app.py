"""
炒股传 · Streamlit 分析应用

输入任意 A股 / 港股 / 美股代码 → 按需取数 → 风险指标 + K 线。
本文件是唯一编排层：可同时调用 data_fetcher 与 risk_metrics。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import data_fetcher as dfetch  # noqa: E402
import risk_metrics as rm  # noqa: E402

st.set_page_config(
    page_title="炒股传 · 股票风险分析",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

MARKET_OPTIONS = {
    "A股（沪深）": "a",
    "港股": "hk",
    "美股": "us",
}

FREQ_OPTIONS = {
    "日线": "daily",
    "周线": "weekly",
    "月线": "monthly",
}

PLACEHOLDERS = {
    "a": "如 600519 / 贵州茅台 / 平安银行",
    "hk": "如 01810 / 小米集团 / 腾讯",
    "us": "如 AAPL / TSLA / 苹果",
}


@st.cache_data(ttl=60 * 60 * 12, show_spinner=False)
def _cached_search(market: str, query: str) -> pd.DataFrame:
    try:
        return dfetch.search_stocks(market, query, limit=15)
    except Exception:
        return pd.DataFrame(columns=["代码", "名称", "交易所"])


@st.cache_data(ttl=60 * 60, show_spinner=False)
def _cached_resolve(market: str, query: str) -> tuple[str, str]:
    return dfetch.resolve_symbol(market, query)


def _sidebar() -> dict:
    st.sidebar.title("炒股传")
    st.sidebar.caption("按需分析 A股 / 港股 / 美股 · 支持名称搜索")

    market_label = st.sidebar.selectbox("市场", list(MARKET_OPTIONS.keys()), index=1)
    market = MARKET_OPTIONS[market_label]

    query = st.sidebar.text_input(
        "代码或名称",
        value="01810" if market == "hk" else ("AAPL" if market == "us" else "600519"),
        help=f"A股沪深已合并，代码自动识别交易所。支持名称，例如：{PLACEHOLDERS[market]}",
        placeholder=PLACEHOLDERS[market],
    )

    query_s = query.strip()
    resolved_code = query_s
    resolved_name = query_s
    match_note = None

    if query_s:
        hits = _cached_search(market, query_s)
        if len(hits) >= 1:
            labels = [
                f"{row['名称']}（{row['代码']}·{row['交易所']}）"
                for _, row in hits.iterrows()
            ]
            default_idx = 0
            try:
                code0, name0 = _cached_resolve(market, query_s)
                for i, lab in enumerate(labels):
                    if code0 in lab:
                        default_idx = i
                        break
                resolved_code, resolved_name = code0, name0
            except Exception as exc:
                # 多候选或目录不全：仍展示列表供点选
                match_note = str(exc)
                resolved_code = str(hits.iloc[0]["代码"])
                resolved_name = str(hits.iloc[0]["名称"])

            pick = st.sidebar.selectbox(
                "匹配结果",
                options=labels,
                index=default_idx,
                help="按名称输入时，从候选中点选确认",
            )
            if pick and "（" in pick:
                inner = pick.split("（", 1)[1].rstrip("）")
                resolved_code = inner.split("·", 1)[0].strip()
                resolved_name = pick.split("（", 1)[0].strip()

        else:
            try:
                resolved_code, resolved_name = _cached_resolve(market, query_s)
            except Exception as exc:
                match_note = str(exc)

        if match_note and not resolved_code:
            st.sidebar.warning(match_note)
        elif match_note:
            st.sidebar.caption(match_note)

    start_date = st.sidebar.date_input(
        "起始日期",
        value=pd.Timestamp("2018-01-01"),
        min_value=pd.Timestamp("2000-01-01"),
        max_value=pd.Timestamp.today(),
    )
    risk_free = st.sidebar.number_input(
        "无风险利率", min_value=0.0, max_value=0.2, value=0.02, step=0.005,
        format="%.3f",
    )
    show_volume = st.sidebar.checkbox("显示成交量", value=True)
    show_save = st.sidebar.checkbox("允许下载 Excel 留档", value=True)

    st.sidebar.markdown("---")
    st.sidebar.markdown(
        "数据源：AKShare（新浪）· yfinance（美股）  \n"
        "仅供学习交流，不构成投资建议"
    )

    return {
        "market": market,
        "market_label": market_label,
        "symbol": resolved_code,
        "symbol_name": resolved_name,
        "query": query_s,
        "start_date": pd.Timestamp(start_date).strftime("%Y-%m-%d"),
        "risk_free": float(risk_free),
        "show_volume": show_volume,
        "show_save": show_save,
        "match_note": match_note,
    }


@st.cache_data(ttl=60 * 30, show_spinner=False)
def load_bars(market: str, symbol: str, start_date: str) -> dict[str, pd.DataFrame]:
    bars = dfetch.fetch_bars(market, symbol, start_date=start_date)
    # cache 需要可序列化，显式拷贝
    return {k: v.copy() for k, v in bars.items()}


def make_candle(df: pd.DataFrame, title: str, show_volume: bool) -> go.Figure:
    rows = 2 if show_volume else 1
    heights = [0.72, 0.28] if show_volume else [1.0]
    fig = make_subplots(
        rows=rows, cols=1, shared_xaxes=True,
        vertical_spacing=0.06, row_heights=heights,
    )
    fig.add_trace(
        go.Candlestick(
            x=df["日期"], open=df["开盘"], high=df["最高"],
            low=df["最低"], close=df["收盘"], name="K线",
            increasing_line_color="#c23531", decreasing_line_color="#2f9e44",
            increasing_fillcolor="rgba(194,53,49,0.55)",
            decreasing_fillcolor="rgba(47,158,68,0.55)",
        ),
        row=1, col=1,
    )
    if show_volume:
        colors = [
            "#c23531" if c >= o else "#2f9e44"
            for o, c in zip(df["开盘"], df["收盘"])
        ]
        fig.add_trace(
            go.Bar(x=df["日期"], y=df["成交量"], name="成交量",
                   marker_color=colors, opacity=0.65),
            row=2, col=1,
        )
    fig.update_layout(
        title=title,
        xaxis_rangeslider_visible=False,
        height=520 if show_volume else 420,
        margin=dict(l=20, r=20, t=48, b=20),
        legend_orientation="h",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    fig.update_xaxes(type="category", nticks=8)
    return fig


def metric_compare(full: dict, yearly: dict) -> None:
    """全周期 | 近一年 两列并排；近一年列高亮（更贴近当前风险）。"""
    rows = [
        ("最大回撤 (%)", "最大回撤", True),
        ("夏普比率", "夏普", False),
        ("年化收益率 (%)", "年化收益 %", False),
        ("年化波动率 (%)", "年化波动 %", False),
        ("ATR(14)", "ATR(14)", False),
        ("样本数", "样本数", False),
    ]

    def fmt(v) -> str:
        if isinstance(v, float):
            return f"{v:.2f}"
        if v is None:
            return "—"
        return str(v)

    data = []
    for key, label, _ in rows:
        data.append({
            "指标": label,
            "近一年 (365日)": fmt(yearly.get(key)),
            "全周期": fmt(full.get(key)),
        })

    df = pd.DataFrame(data)
    st.caption("近一年 = 最近 365 个自然日内的交易数据；全周期 = 起始日至今。**近一年更贴近当前风险。**")
    st.dataframe(
        df,
        width="stretch",
        hide_index=True,
        column_config={
            "指标": st.column_config.TextColumn("指标", width="small"),
            "近一年 (365日)": st.column_config.TextColumn(
                "近一年 (365日)",
                width="medium",
                help="最近 365 日，通常更值得优先参考",
            ),
            "全周期": st.column_config.TextColumn("全周期", width="medium"),
        },
    )


def atr_tables(full: dict, yearly: dict) -> None:
    st.subheader("ATR 多回看窗口 / 多周期")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**多回看窗口 ATR**")
        rows = []
        for k, v in full.get("ATR_多窗口", {}).items():
            rows.append({
                "窗口": k,
                "近一年": yearly.get("ATR_多窗口", {}).get(k, "-"),
                "全周期": v,
            })
        if rows:
            st.dataframe(
                pd.DataFrame(rows), width="stretch", hide_index=True,
                column_config={c: st.column_config.TextColumn(c, width="small")
                               for c in rows[0].keys()},
            )
    with c2:
        st.markdown("**周线 / 月线 / 季度线 ATR(14)**")
        rows = []
        for k, v in full.get("ATR_多周期", {}).items():
            rows.append({
                "周期": k,
                "近一年": yearly.get("ATR_多周期", {}).get(k, "-"),
                "全周期": v,
            })
        if rows:
            st.dataframe(
                pd.DataFrame(rows), width="stretch", hide_index=True,
                column_config={c: st.column_config.TextColumn(c, width="small")
                               for c in rows[0].keys()},
            )


def main() -> None:
    cfg = _sidebar()
    display_name = cfg.get("symbol_name") or cfg["symbol"]
    st.title("股票风险分析")
    st.caption(
        f"市场：{cfg['market_label']} · 标的：{display_name}（{cfg['symbol'] or '—'}） · "
        f"起始：{cfg['start_date']} · 指标：全周期 vs 近一年"
    )

    if not cfg["symbol"]:
        st.info("请在左侧输入股票**代码或名称**，并从匹配结果中选择。")
        return

    with st.spinner("正在拉取行情并计算指标…"):
        try:
            bars = load_bars(cfg["market"], cfg["symbol"], cfg["start_date"])
        except Exception as exc:
            st.error(f"取数失败：{exc}")
            st.markdown(
                "常见原因：\n"
                "- 代码或市场不匹配（港股 5 位，如 `01810`；美股大写，如 `AAPL`）\n"
                "- 数据源临时不可用，稍后重试\n"
                "- 起始日期过早或标的尚未上市"
            )
            return

        daily = bars["daily"]
        try:
            full = rm.compute_all_from_df(
                daily, risk_free_rate=cfg["risk_free"], period_days=None
            )
            yearly = rm.compute_all_from_df(
                daily, risk_free_rate=cfg["risk_free"], period_days=365
            )
        except Exception as exc:
            st.error(f"指标计算失败：{exc}")
            return

    latest = daily.iloc[-1]
    prev = daily.iloc[-2] if len(daily) > 1 else latest
    chg = latest["收盘"] - prev["收盘"]
    chg_pct = (chg / prev["收盘"] * 100) if prev["收盘"] else 0.0

    st.markdown("### 行情概览")
    m = st.columns(4)
    m[0].metric("最新收盘", f"{latest['收盘']:.2f}", f"{chg:.2f} ({chg_pct:.2f}%)")
    m[1].metric("数据截至", pd.Timestamp(latest["日期"]).strftime("%Y-%m-%d"))
    m[2].metric("区间", full.get("数据区间", "-"))
    m[3].metric("日线样本", f"{len(daily)}")

    st.markdown("### 核心风险指标")
    metric_compare(full, yearly)

    freq_label = st.radio("K 线周期", list(FREQ_OPTIONS.keys()), horizontal=True)
    series = bars[FREQ_OPTIONS[freq_label]]
    if series.empty:
        st.warning(f"{freq_label}数据为空")
    else:
        st.plotly_chart(
            make_candle(
                series,
                f"{display_name} {cfg['symbol']} · {freq_label}（{cfg['market_label']}）",
                cfg["show_volume"],
            ),
            use_container_width=True,
        )

    atr_tables(full, yearly)

    with st.expander("全指标明细（全周期 / 近一年）"):
        def flatten(m: dict, prefix: str) -> dict:
            out = {}
            for k, v in m.items():
                if isinstance(v, dict):
                    for sk, sv in v.items():
                        out[f"{prefix}_{k}_{sk}"] = sv
                else:
                    out[f"{prefix}_{k}"] = v
            return out

        st.dataframe(pd.DataFrame([flatten(full, "全"), flatten(yearly, "年")]).T,
                     width="stretch")

    if cfg["show_save"]:
        from io import BytesIO

        buf = BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            daily.to_excel(writer, sheet_name="日线数据", index=False)
            bars["weekly"].to_excel(writer, sheet_name="周线数据", index=False)
            bars["monthly"].to_excel(writer, sheet_name="月线数据", index=False)
            flat = flatten(full, "指标")
            pd.DataFrame([flat]).to_excel(writer, sheet_name="风险指标", index=False)
        st.download_button(
            "下载本票 Excel（日/周/月 + 风险指标）",
            data=buf.getvalue(),
            file_name=f"{cfg['market']}_{cfg['symbol']}_bars.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    st.markdown("---")
    st.caption(
        "数据来源：AKShare 新浪源 / Yahoo Finance。前复权口径可能与券商软件略有差异。"
        "本工具仅供学习与研究使用，不构成任何投资建议。市场有风险，决策需谨慎。"
    )


if __name__ == "__main__":
    main()
