from typing import Tuple
import pandas as pd
import numpy as np
from datetime import datetime

def load_data(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["start_date", "end_date", "date", "milestone_date"])
    # Ensure types
    df["budget"] = pd.to_numeric(df["budget"], errors="coerce")
    df["cumulative_spend"] = pd.to_numeric(df["cumulative_spend"], errors="coerce")
    return df.sort_values(["project_id", "date"]).reset_index(drop=True)

def compute_kpis(df_proj: pd.DataFrame) -> dict:
    """
    Expect df_proj for a single project (multiple dates)
    Returns dict with KPIs: latest_spend, budget, %execution, variance%, burn_rate, days_elapsed, days_total, forecast_to_complete, risk_score
    """
    df = df_proj.copy()
    budget = float(df["budget"].iloc[0])
    start = df["start_date"].min()
    end = df["end_date"].max()
    latest = df.sort_values("date").iloc[-1]
    latest_date = latest["date"]
    latest_spend = float(latest["cumulative_spend"])
    days_total = (end - start).days if (end - start).days > 0 else 1
    days_elapsed = (latest_date - start).days if (latest_date - start).days > 0 else 1
    pct_execution = latest_spend / budget if budget else 0
    variance_pct = (latest_spend - budget) / budget if budget else 0

    # Burn rate: spend per elapsed day
    burn_rate = latest_spend / days_elapsed if days_elapsed else 0

    # Simple forecast: linear fit cumulative_spend ~ days_elapsed -> forecast at days_total
    try:
        x = (df["date"] - start).dt.days.values.astype(float)
        y = df["cumulative_spend"].values.astype(float)
        if len(x) >= 2 and all(np.isfinite(x)) and all(np.isfinite(y)):
            coef = np.polyfit(x, y, 1)
            slope, intercept = coef[0], coef[1]
            forecast = float(slope * days_total + intercept)
        else:
            forecast = latest_spend * (days_total / days_elapsed)
    except Exception:
        forecast = latest_spend * (days_total / days_elapsed)

    forecast_to_complete = forecast
    # risk score: normalized combination of variance and forecast overload
    overload = (forecast_to_complete - budget) / budget if budget else 0
    risk_score = float(np.clip((variance_pct * 0.6 + overload * 0.4) * 100, -1000, 1000))
    return {
        "budget": budget,
        "latest_spend": latest_spend,
        "pct_execution": pct_execution,
        "variance_pct": variance_pct,
        "burn_rate": burn_rate,
        "days_elapsed": days_elapsed,
        "days_total": days_total,
        "forecast_to_complete": forecast_to_complete,
        "risk_score": risk_score,
        "latest_date": latest_date
    }

def flag_risk(kpis: dict, variance_threshold: float = 0.10, risk_threshold: float = 5.0) -> Tuple[bool, str]:
    """
    Returns (is_risky, message)
    variance_threshold: absolute variance fraction e.g., 0.10 -> 10%
    risk_threshold: risk_score threshold
    """
    is_var = abs(kpis.get("variance_pct", 0)) >= variance_threshold
    is_risk = abs(kpis.get("risk_score", 0)) >= risk_threshold
    messages = []
    if is_var:
        messages.append(f"Desviación actual {kpis['variance_pct']*100:.1f}% vs presupuesto.")
    if is_risk:
        messages.append(f"Riesgo estimado {kpis['risk_score']:.1f}.")
    if kpis.get("forecast_to_complete", 0) > kpis.get("budget", 0):
        messages.append("Proyección indica posible sobrecosto.")
    if not messages:
        messages.append("No se detectan riesgos relevantes en umbrales actuales.")
    return (is_var or is_risk or (kpis.get("forecast_to_complete", 0) > kpis.get("budget", 0))), " | ".join(messages)

def summary_table(df: pd.DataFrame) -> pd.DataFrame:
    projects = []
    for pid, grp in df.groupby("project_id"):
        k = compute_kpis(grp)
        projects.append({
            "project_id": pid,
            "project_name": grp["project_name"].iloc[0],
            "budget": k["budget"],
            "latest_spend": k["latest_spend"],
            "pct_execution": k["pct_execution"],
            "variance_pct": k["variance_pct"],
            "forecast_to_complete": k["forecast_to_complete"],
            "risk_score": k["risk_score"]
        })
    return pd.DataFrame(projects).sort_values("risk_score", ascending=False)
