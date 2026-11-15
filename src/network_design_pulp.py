"""Facility location / network design written with PuLP.

Usage:  pip install "pulp<4" pandas && python src/network_design_pulp.py
Requires PuLP 3.x (PuLP 4 changed the variable API).

Solves the base case and a few what-if scenarios, prints a summary and writes
results/scenarios.csv and results/flows_<scenario>.csv.
"""
from pathlib import Path
import pandas as pd
import pulp

ROOT = Path(__file__).resolve().parents[1]
UNITS_PER_CONTAINER = 1000


def load():
    plants = pd.read_csv(ROOT / "data/plants.csv").set_index("plant_id")
    markets = pd.read_csv(ROOT / "data/markets.csv").set_index("market")
    freight = pd.read_csv(ROOT / "data/freight.csv", index_col="origin")
    return plants, markets, freight


def solve(plants, markets, freight, freight_mult=1.0, fixed_mult=None, demand=None):
    """Build and solve the model. Returns (total_cost, open_plants, flows)."""
    fixed_mult = fixed_mult or {}
    demand = markets["demand_units_month"] if demand is None else demand

    # 1) model + variables (plain LpVariable(...) so it works on PuLP 3.x)
    model = pulp.LpProblem("network_design", pulp.LpMinimize)
    y = {p: pulp.LpVariable(f"open_{i}", cat="Binary")
         for i, p in enumerate(plants.index)}
    x = {(p, m): pulp.LpVariable(f"flow_{i}_{j}", lowBound=0)
         for i, p in enumerate(plants.index)
         for j, m in enumerate(markets.index)}

    # 2) objective: fixed costs + (production + freight per unit) * flow
    model += (
        pulp.lpSum(plants.loc[p, "fixed_cost_usd_month"] * fixed_mult.get(p, 1.0) * y[p]
                   for p in plants.index)
        + pulp.lpSum(
            (plants.loc[p, "variable_cost_usd_unit"]
             + freight.loc[plants.loc[p, "country"], m] * freight_mult / UNITS_PER_CONTAINER)
            * x[(p, m)]
            for p in plants.index for m in markets.index)
    )

    # 3) constraints
    for m in markets.index:   # every market's demand is met
        model += pulp.lpSum(x[(p, m)] for p in plants.index) >= float(demand[m])
    for p in plants.index:    # capacity, and only open plants can ship
        model += (pulp.lpSum(x[(p, m)] for m in markets.index)
                  <= plants.loc[p, "capacity_units_month"] * y[p])

    # 4) solve and read the results
    model.solve(pulp.PULP_CBC_CMD(msg=False))
    status = pulp.LpStatus[model.status]
    if status != "Optimal":
        raise RuntimeError(f"Solver status: {status}")
    open_plants = [p for p in plants.index if y[p].value() > 0.5]
    flows = pd.DataFrame(
        {m: {p: round(x[(p, m)].value() or 0) for p in open_plants} for m in markets.index})
    return pulp.value(model.objective), open_plants, flows


def main():
    plants, markets, freight = load()
    scenarios = {
        "base": dict(),
        "freight_x5": dict(freight_mult=5),
        "double_fixed_IND_HIGH": dict(fixed_mult={"IND_HIGH": 2}),
    }
    out, base_cost = [], None
    (ROOT / "results").mkdir(exist_ok=True)
    for name, kw in scenarios.items():
        cost, opened, flows = solve(plants, markets, freight, **kw)
        base_cost = base_cost or cost
        out.append(dict(scenario=name, total_cost_usd_month=round(cost),
                        change_vs_base_pct=round((cost / base_cost - 1) * 100, 1),
                        open_plants=", ".join(opened)))
        flows.to_csv(ROOT / f"results/flows_{name}.csv", index_label="plant_id")
    df = pd.DataFrame(out)
    df.to_csv(ROOT / "results/scenarios.csv", index=False)
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
