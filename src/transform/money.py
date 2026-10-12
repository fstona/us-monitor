"""Money and Fed-balance-sheet liquidity.

Warsh ("money matters"): M2 growth should be compatible with nominal GDP
growth at 2% inflation; velocity tells how fast each dollar turns over.
"""
from __future__ import annotations

import pandas as pd


def fed_liquidity(total_assets_mn: pd.Series, tga_mn: pd.Series,
                  rrp_bn: pd.Series, reserves_mn: pd.Series) -> pd.DataFrame:
    """Weekly balance-sheet frame in US$ trillions.

    Net liquidity = Fed assets − TGA − ON RRP (the market-practitioner proxy
    for the liquidity the Fed's balance sheet leaves in private hands).
    H.4.1 weeklies are Wednesday levels; the daily RRP is taken as of each
    Wednesday. Units: WALCL/WTREGEN/WRESBAL in $mn, RRPONTSYD in $bn.
    """
    df = pd.DataFrame({
        "Fed total assets": total_assets_mn / 1e6,
        "TGA": tga_mn / 1e6,
        "Reserves": reserves_mn / 1e6,
    }).dropna()
    df["ON RRP"] = (rrp_bn / 1e3).reindex(df.index, method="ffill").fillna(0.0)
    df["Net liquidity"] = df["Fed total assets"] - df["TGA"] - df["ON RRP"]
    return df
