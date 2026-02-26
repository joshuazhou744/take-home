#!/usr/bin/env bash
set -euo pipefail

TASK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

uv run python3 - "$TASK_DIR" << 'EOF'
import sys
import pandas as pd
from pathlib import Path

task_dir = Path(sys.argv[1])

df = pd.read_csv(task_dir / "data" / "apple_global_sales_dataset.csv")

category_revenue = df.groupby("category")["revenue_usd"].sum().sort_values(ascending=False)
top_category = category_revenue.index[0]

region_revenue = df.groupby("region")["revenue_usd"].sum().sort_values(ascending=False)

peak_year, peak_q = df.groupby(["year", "quarter"])["revenue_usd"].sum().idxmax()
peak_quarter = f"{peak_year}-{peak_q}"

top_country_by_units = df.groupby("country")["units_sold"].sum().idxmax()

# Patch the reward path to a writable local directory for testing outside the sandbox
verify_code = (task_dir / "verify.py").read_text().replace(
    '"/logs/verifier/reward.txt"', '"/tmp/verifier/reward.txt"'
)
exec(verify_code)

reward = Path("/tmp/verifier/reward.txt").read_text().strip()
print(f"Reward: {reward}")
EOF
