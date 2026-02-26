# Apple Global Sales Analysis

Load `/data/apple_global_sales_dataset.csv`, this is a dataset of Apple's global sales in a 3 year time span.

### Key columns
| column | type | description |
|---|---|---|
| `year` | int | 2022, 2023, 2024 |
| `quarter` | str | Q1–Q4 |
| `month` | str | month name |
| `country` | str | sale country |
| `region` | str | geographic region (e.g. Europe, Asia, North America) |
| `category` | str | iPhone, Mac, iPad, Apple Watch, AirPods, Accessories |
| `product_name` | str | specific product |
| `units_sold` | int | units in this transaction |
| `revenue_usd` | float | revenue in USD |
| `sales_channel` | str | e.g. Online, Apple Store, Third-Party Retailer |
| `customer_segment` | str | Consumer, Business, Education, Government |
| `customer_rating` | float | 1.0–5.0 |
| `return_status` | str | Kept or Returned |

## Your tasks
Load the CSV and compute the following. Store each result as the named variable.
1. `category_revenue` — `pd.Series`: total `revenue_usd` per category, sorted descending. Make the index the category name.
2. `top_category` — `str`: category with the highest total revenue.
3. `region_revenue` — `pd.Series`: total `revenue_usd` per region, sorted descending. Make the index the region name.
4. `peak_quarter` — `str`: the year and quarter with the highest total revenue, formatted as `"YYYY-QN"`.
5. `top_country_by_units` — `str`: the country with the most total `units_sold`.
