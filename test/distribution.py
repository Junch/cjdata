from cjdata import LocalData
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

try:
    import seaborn as sns

    HAS_SEABORN = True
except ImportError:
    HAS_SEABORN = False
    from scipy import stats

local_data = LocalData("c:/github/cjdata/data/stock_data_hfq.db")
df = local_data.get_stock_data_frame_in_sector(
    "沪深300", "20260303", "20260303", adj="hfq"
)
local_data.close()  # Close the database connection after fetching data

valid_turn = df["turn"] != 0
df.loc[(df["tradestatus"] == 1) & valid_turn, "market"] = (
    df["amount"] / df["turn"] / 1e8
)

df.sort_values("market", ascending=False, inplace=True)

with pd.option_context('display.max_rows', None, 
                       'display.max_columns', None,
                       'display.max_colwidth', None):
    print(df[["stock_code", "market", "turn", "amount"]])

market_values = df["market"].dropna()

fig, axes = plt.subplots(1, 2, figsize=(14, 5))

axes[0].hist(market_values, bins=30, edgecolor="black", alpha=0.7)
axes[0].set_title("Market Value Distribution (Histogram)")
axes[0].set_xlabel("Market Value (10 BILLION CNY)")
axes[0].set_ylabel("Frequency")

if HAS_SEABORN:
    sns.histplot(market_values, kde=True, bins=30, ax=axes[1])
    axes[1].set_title("Market Value Distribution (Histogram + KDE)")
else:
    kde = stats.gaussian_kde(market_values)
    x_range = np.linspace(market_values.min(), market_values.max(), 100)
    axes[1].hist(market_values, bins=30, density=True, alpha=0.7, edgecolor="black")
    axes[1].plot(x_range, kde(x_range), "r-", linewidth=2)
    axes[1].set_title("Market Value Distribution (Histogram + KDE)")

axes[1].set_xlabel("Market Value (10 BILLON CNY)")
axes[1].set_ylabel("Density")

plt.tight_layout()
# plt.savefig("market_distribution.png", dpi=150)
# print("Saved to market_distribution.png")
plt.show()
