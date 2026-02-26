import pandas as pd
from pathlib import Path

_reward_path = Path("/logs/verifier/reward.txt")
_reward_path.parent.mkdir(parents=True, exist_ok=True)

try:
    # category_revenue: pandas Series that shows the total revenue of each category
    assert "category_revenue" in vars(), "category_revenue is not defined"
    assert isinstance(category_revenue, pd.Series), f"category_revenue must be a pd.Series, got {type(category_revenue)}"
    expected_cat_order = ["Mac", "iPhone", "iPad", "Apple Watch", "AirPods", "Accessories"]
    assert list(category_revenue.index) == expected_cat_order, (
        f"category_revenue order wrong: got {list(category_revenue.index)}"
    )
    assert abs(category_revenue["Mac"] - 8369961.42) < 1.0, f"Mac revenue off: {category_revenue['Mac']}"
    assert abs(category_revenue["iPhone"] - 5734154.34) < 1.0, f"iPhone revenue off: {category_revenue['iPhone']}"

    # top_category: category with highest total revienue
    assert "top_category" in vars(), "top_category is not defined"
    assert top_category == "Mac", f"top_category should be 'Mac', got {top_category!r}"

    # region_revenue: pandas Series of total revenue per region
    assert "region_revenue" in vars(), "region_revenue is not defined"
    assert isinstance(region_revenue, pd.Series), f"region_revenue must be a pd.Series, got {type(region_revenue)}"
    expected_reg_order = ["Europe", "Asia", "South America", "Africa", "North America", "Middle East", "Europe/Asia", "Oceania"]
    assert list(region_revenue.index) == expected_reg_order, (
        f"region_revenue order wrong: got {list(region_revenue.index)}"
    )
    assert abs(region_revenue["Europe"] - 6210935.78) < 1.0, f"Europe revenue off: {region_revenue['Europe']}"

    # peak_quarter: year and quarter of highest revenue
    assert "peak_quarter" in vars(), "peak_quarter is not defined"
    assert peak_quarter == "2024-Q4", f"peak_quarter should be '2024-Q4', got {peak_quarter!r}"

    # top_country_by_units: country with the most total units sold
    assert "top_country_by_units" in vars(), "top_country_by_units is not defined"
    assert top_country_by_units == "Japan", f"top_country_by_units should be 'Japan', got {top_country_by_units!r}"

    _reward_path.write_text("1.0")

except AssertionError as e:
    _reward_path.write_text(f"0.0\n{e}")
