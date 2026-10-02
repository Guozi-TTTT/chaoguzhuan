# 炒股传 · 股票风险分析（Streamlit）

输入 **A股 / 港股 / 美股** 的代码或名称，按需拉取行情，查看 K 线与风险指标（回撤、夏普、年化、ATR 等），对比 **全周期 vs 近一年**。

仅供学习交流，不构成投资建议。

## 本地运行

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 部署（Streamlit Community Cloud）

1. 推送本仓库到 GitHub
2. 打开 [share.streamlit.io](https://share.streamlit.io) → New app
3. 选择仓库与分支，Main file path 填 `app.py`
4. Deploy，获得公网网址发给朋友即可

依赖见 `requirements.txt`。A股/港股走 AKShare（新浪），美股走 yfinance。
