import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from cjdata import LocalData

matplotlib.rcParams["font.sans-serif"] = [
    "SimHei",
    "Microsoft YaHei",
    "Arial Unicode MS",
]
matplotlib.rcParams["axes.unicode_minus"] = False

try:
    import seaborn as sns

    HAS_SEABORN = True
except ImportError:
    HAS_SEABORN = False
    from scipy import stats

local_data = LocalData("c:/github/cjdata/data/stock_data_hfq.db")

sectors = {
    "沪深300": local_data.get_stock_data_frame_in_sector(
        "沪深300", "20260303", "20260303", adj="hfq"
    ),
    "中证500": local_data.get_stock_data_frame_in_sector(
        "中证500", "20260303", "20260303", adj="hfq"
    ),
    "中证1000": local_data.get_stock_data_frame_in_sector(
        "中证1000", "20260303", "20260303", adj="hfq"
    ),
}
local_data.close()


def calculate_market(df):
    valid_turn = df["turn"] != 0
    df.loc[(df["tradestatus"] == 1) & valid_turn, "market"] = (
        df["amount"] / df["turn"] / 1e6
    )
    return df.sort_values("market", ascending=False)["market"].dropna()


colors = ["steelblue", "coral", "seagreen"]
markets = {name: calculate_market(data.copy()) for name, data in sectors.items()}

fig, axes = plt.subplots(2, 3, figsize=(18, 8))

for i, (name, market) in enumerate(markets.items()):
    axes[0, i].hist(market, bins=30, edgecolor="black", alpha=0.7, color=colors[i])
    axes[0, i].set_title(f"{name} 市值分布 (直方图)")
    axes[0, i].set_xlabel("市值 (亿)")
    axes[0, i].set_ylabel("频数")

    if HAS_SEABORN:
        sns.histplot(market.values, kde=True, bins=30, ax=axes[1, i], color=colors[i])
    else:
        kde = stats.gaussian_kde(market)
        x_range = np.linspace(market.min(), market.max(), 100)
        axes[1, i].hist(
            market, bins=30, density=True, alpha=0.7, edgecolor="black", color=colors[i]
        )
        axes[1, i].plot(x_range, kde(x_range), "r-", linewidth=2)
    axes[1, i].set_title(f"{name} 市值分布 (直方图 + KDE)")
    axes[1, i].set_xlabel("市值 (亿)")
    axes[1, i].set_ylabel("密度")

plt.tight_layout()
plt.show()
