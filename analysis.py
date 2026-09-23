"""
Woolworths Dark Store Shelf Planner — analysis
================================================

Reproduces the numbers that drive the two HTML tools:
  1. a customer x category spend matrix and its Pearson correlation,
  2. seed aisles from average-linkage hierarchical clustering (k = 4),
  3. product ordering within each category (seriation by spend correlation),
  4. per-product stats for the planner cards.

The output (data.json) is what the two HTML files embed, so they run with
zero setup. Run this only to regenerate or verify that data.

Usage:
    pip install -r requirements.txt
    python analysis.py
"""

import json
import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import linkage, fcluster, leaves_list
from scipy.spatial.distance import squareform

DATA_FILE = "data/Woolies_dark_stores_shelf_planner_-_Data.xlsx"
OUT_FILE = "data.json"
N_AISLES = 4  # clusters to seed the floor plan with


def load() -> pd.DataFrame:
    df = pd.read_excel(DATA_FILE, sheet_name="data")
    # Spend per order line. Duplicate lines are kept as genuine: there is no
    # line id to tell a data error from a real repeat line, so dropping them
    # would be inventing a judgement about the data.
    df["spend"] = df["quantity"] * df["unit_price"]
    return df


def correlation(df: pd.DataFrame, cats: list[str]) -> pd.DataFrame:
    """Pearson correlation between categories across customers, on total spend."""
    piv = df.pivot_table(
        index="cust_id", columns="product_category",
        values="spend", aggfunc="sum", fill_value=0,   # unbought = real $0, no imputation
    )[cats]
    return piv.corr(method="pearson")


def seed_aisles(corr: pd.DataFrame, k: int) -> list[list[str]]:
    """Average-linkage hierarchical clustering on distance (1 - r), cut at k."""
    cats = list(corr.columns)
    D = 1 - corr.values
    np.fill_diagonal(D, 0)
    D = (D + D.T) / 2                       # enforce symmetry
    Z = linkage(squareform(D, checks=False), method="average")
    labels = fcluster(Z, k, criterion="maxclust")
    groups: dict[int, list[str]] = {}
    for cat, lab in zip(cats, labels):
        groups.setdefault(int(lab), []).append(cat)
    # order aisles so their sequence follows the business order (A..J)
    return [sorted(v) for _, v in sorted(groups.items(), key=lambda kv: min(kv[1]))]


def order_products(df: pd.DataFrame, cats: list[str]) -> dict[str, list[str]]:
    """Order products within a category so correlated products sit adjacent."""
    prod_spend = df.pivot_table(
        index="cust_id", columns="product_name",
        values="spend", aggfunc="sum", fill_value=0,
    )
    out: dict[str, list[str]] = {}
    for c in cats:
        prods = sorted(df.loc[df.product_category == c, "product_name"].unique())
        if len(prods) > 2:  # seriate with >2 products; trivial otherwise
            pc = prod_spend[prods].corr("pearson").fillna(0).values
            Dp = 1 - pc
            np.fill_diagonal(Dp, 0)
            Dp = (Dp + Dp.T) / 2
            order = leaves_list(linkage(squareform(Dp, checks=False), method="average"))
            prods = [prods[i] for i in order]
        out[c] = prods
    return out


def product_stats(df: pd.DataFrame) -> dict[str, dict]:
    stats: dict[str, dict] = {}
    for p, sub in df.groupby("product_name"):
        stats[p] = {
            "units": int(sub.quantity.sum()),
            "spend": round(float(sub.spend.sum()), 2),
            "avg_price": round(float(sub.unit_price.mean()), 2),
            "customers": int(sub.cust_id.nunique()),
        }
    return stats


def togetherness(aisles: list[list[str]], corr: pd.DataFrame) -> float:
    """Average Pearson r over every category pair sharing an aisle, scaled to 0-100."""
    idx = {c: i for i, c in enumerate(corr.columns)}
    vals = [
        corr.values[idx[a[i]], idx[a[j]]]
        for a in aisles
        for i in range(len(a))
        for j in range(i + 1, len(a))
    ]
    return 0.0 if not vals else round((np.mean(vals) + 1) / 2 * 100, 1)


def main() -> None:
    df = load()
    cats = sorted(df.product_category.unique())          # A..J = business order
    labels = {c: c.split(".", 1)[1] for c in cats}

    corr = correlation(df, cats)
    aisles = seed_aisles(corr, N_AISLES)

    export = {
        "categories": cats,
        "labels": labels,
        "corr": corr.round(4).values.tolist(),
        "seed_aisles": aisles,
        "cat_products": order_products(df, cats),
        "prod_stats": product_stats(df),
        "meta": {
            "customers": int(df.cust_id.nunique()),
            "orders": int(df.order_id.nunique()),
            "lines": int(len(df)),
            "products": int(df.product_name.nunique()),
        },
    }
    with open(OUT_FILE, "w") as f:
        json.dump(export, f)

    print(f"Wrote {OUT_FILE}")
    print(f"  {export['meta']['lines']:,} lines, {export['meta']['orders']:,} orders, "
          f"{export['meta']['customers']} customers, {export['meta']['products']} products")
    print("  Seed aisles:")
    for i, a in enumerate(aisles, 1):
        print(f"    Aisle {i}: {', '.join(labels[c] for c in a)}")
    print(f"  Seed togetherness score: {togetherness(aisles, corr):.0f}/100")


if __name__ == "__main__":
    main()
