import traceback

import data_fetcher as d
import risk_metrics as r

cases = [
    ("a_sh", "600519"),
    ("a_sz", "000001"),
    ("hk", "01810"),
    ("us", "AAPL"),
    ("us", "TSLA"),
]

for market, symbol in cases:
    try:
        bars = d.fetch_bars(market, symbol, start_date="2024-01-01")
        m = r.compute_all_from_df(bars["daily"], period_days=None)
        y = r.compute_all_from_df(bars["daily"], period_days=365)
        print(
            "OK",
            market,
            symbol,
            len(bars["daily"]),
            "dd",
            m["最大回撤 (%)"],
            "sharpe",
            m["夏普比率"],
            "yoy_dd",
            y["最大回撤 (%)"],
        )
    except Exception as e:
        print("FAIL", market, symbol, type(e).__name__, e)
        traceback.print_exc()
