# AGENTS.md

## Project overview

「炒股传」— 按需分析 A 股 / 港股 / 美股的工具。用户输入任意代码 → 拉取行情 → 计算风险指标 → Web 可视化。

核心流水线：`data_fetcher.py`（多市场取数）→ `risk_metrics.py`（指标）→ `app.py`（Streamlit 壳，唯一编排层）。

架构详见 [ARCHITECTURE.md](ARCHITECTURE.md)。

## Key files

| 文件 | 职责 |
|------|------|
| `data_fetcher.py` | A/港/美日线 + 周线/月线聚合；统一中文 OHLCV 列 |
| `risk_metrics.py` | ATR（多窗口/多周期）、夏普、最大回撤、年化收益/波动；`compute_all_from_df` 供应用调用 |
| `app.py` | Streamlit UI：输代码 → K 线 + 风险看板 + Excel 下载 |
| `requirements.txt` | 依赖清单 |
| `ARCHITECTURE.md` | 模块边界、数据流、上线路径 |

历史 Excel（`小米股票数据.xlsx` 等）与练习脚本不属于主流程。

## Setup

```bash
cd G:\炒股传
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

## Run

```bash
# 本地预览（手机需与电脑同一网络，或改用 --server.address 0.0.0.0）
.venv\Scripts\python.exe -m streamlit run app.py --server.port 8501

# 冒烟测试（会访问网络）
.venv\Scripts\python.exe _smoke_test.py
```

## Module rules

- `data_fetcher` 与 `risk_metrics` **互不 import**。
- 只有 `app.py`（未来 API）可以编排二者。
- 展示不依赖历史 Excel；Excel 仅作可选留档/下载。

## Data sources

- **A 股**：市场选「A股（沪深）」即可，按代码自动识别交易所（6/5/9→沪，0/1/2/3→深）。AKShare 新浪源（`stock_zh_a_daily` 等）。东财接口不用。
- **港股**：AKShare；代码可 5 位（`01810`）。
- **美股**：yfinance 为主，AKShare `stock_us_daily` 备用（yfinance 可能限流）。
- **名称搜索**：支持输入中文名（如 `贵州茅台` / `小米`）；目录缓存在 `data/catalog/`。多候选时侧边栏「匹配结果」可点选；主名优先（短名、非人民币柜台）。

## Gotchas

- 美股 yfinance 可能 `YFRateLimitError`，已内置重试 + AKShare 回落；仍失败则稍后再试。
- 港股名称搜索首次会拉全量列表（较慢），之后走 `data/catalog` 缓存。
- 复权口径与券商软件可能略有差异。
- `risk_metrics.save_snapshot` 会**追加**写入 `risk_snapshots.xlsx`（应用主路径不强制使用）。
- 无正式测试框架；`_smoke_test.py` / `_smoke_search.py` 做网络连通性验证。
- 免责声明必须保留在 UI 页脚：仅供学习交流，不构成投资建议。

## Roadmap（未做）

- `macro_data.py` 宏观红绿灯（VIX / 利差 / PMI）
- `portfolio.py` 相关性、凯利仓位
- Streamlit Cloud 部署给远程用户
- 手机网页 App 壳（复用核心模块）
