"""Monte Carlo simulation of demand to test how robust the optimal network is.

For each run, every market's demand is multiplied by a random factor
N(1, sigma), the network design model is re-solved, and we record which
plants are opened and the total cost.

Usage:  python src/monte_carlo.py [n_runs] [sigma] [seed]
        (defaults: 200 runs, sigma = 0.15, seed = 42)
Outputs: results/mc_open_frequency.csv, results/mc_costs.csv, results/mc_summary.png
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from network_design_pulp import load, solve, ROOT  # noqa: E402


def run(n_runs=200, sigma=0.15, seed=42):
    plants, markets, freight = load()
    rng = np.random.default_rng(seed)
    base_demand = markets["demand_units_month"].to_numpy(dtype=float)
    opened = pd.DataFrame(0, index=range(n_runs), columns=plants.index)
    costs = []
    for i in range(n_runs):
        factor = np.clip(rng.normal(1.0, sigma, len(markets)), 0.3, None)
        demand = pd.Series((base_demand * factor).round(), index=markets.index)
        cost, open_ids, _ = solve(plants, markets, freight, demand=demand)
        opened.loc[i, open_ids] = 1
        costs.append(cost)
    return opened, pd.Series(costs, name="total_cost_usd_month")


def main():
    n_runs = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    sigma = float(sys.argv[2]) if len(sys.argv) > 2 else 0.15
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 42
    opened, costs = run(n_runs, sigma, seed)

    freq = (opened.mean() * 100).round(1).rename("pct_of_runs_open").to_frame()
    freq.to_csv(ROOT / "results/mc_open_frequency.csv")
    costs.to_csv(ROOT / "results/mc_costs.csv", index=False)

    print(f"{n_runs} runs, demand sigma = {sigma:.0%}, seed = {seed}")
    print(freq.sort_values("pct_of_runs_open", ascending=False).to_string())
    print(f"\nTotal cost ($/month): mean {costs.mean():,.0f} | "
          f"P5 {costs.quantile(.05):,.0f} | P95 {costs.quantile(.95):,.0f}")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        f = freq.sort_values("pct_of_runs_open")
        fig, (a, b) = plt.subplots(1, 2, figsize=(12, 4.6), dpi=160)
        a.barh(f.index, f["pct_of_runs_open"],
               color=["#2e7d32" if v >= 80 else "#e0a030" if v >= 20 else "#9aa5b5"
                      for v in f["pct_of_runs_open"]])
        a.set_xlim(0, 100); a.set_xlabel("% of runs where the plant is open")
        a.set_title("How often each plant is opened")
        b.hist(costs / 1e6, bins=25, color="#2d5be3", alpha=.8)
        b.set_xlabel("Total cost ($ million / month)"); b.set_title("Distribution of total cost")
        fig.suptitle(f"Monte Carlo: {n_runs} runs, demand noise {sigma:.0%}", fontweight="bold")
        fig.tight_layout(); fig.savefig(ROOT / "results/mc_summary.png")
    except ImportError:
        print("matplotlib not installed: skipped the chart")


if __name__ == "__main__":
    main()
