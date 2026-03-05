from cjdata import LocalData

local_data = LocalData("../data/stock_data_hfq.db")
df = local_data.get_daily("600519.SH", "20241107", "20251107", adj="hfq")
print(df)
local_data.close()