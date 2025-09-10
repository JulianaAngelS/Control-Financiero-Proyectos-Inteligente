import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from app.utils import load_data, compute_kpis, flag_risk, summary_table
import locale

# --- UI settings
st.set_page_config(page_title="Control Financiero Proyectos - Dashboard", layout="wide")
locale.setlocale(locale.LC_ALL, '')  # Try to use system locale for numbers (may vary)

DATA_PATH = "data/proyectos_sample.csv"

@st.cache_data
def get_data():
    return load_data(DATA_PATH)

df = get_data()

st.title("📈 Control Financiero de Proyectos — Dashboard")
st.markdown("Dashboard interactivo para seguimiento presupuestal, proyecciones y alertas tempranas.")

# Sidebar - selection
st.sidebar.header("Filtros")
project_list = df["project_id"].unique().tolist()
project_choice = st.sidebar.selectbox("Seleccionar proyecto", options=["Todos"] + project_list)
variance_threshold = st.sidebar.slider("Umbral desviación (%)", min_value=0.0, max_value=50.0, value=10.0, step=1.0)
risk_threshold = st.sidebar.slider("Umbral riesgo (score)", min_value=0.0, max_value=100.0, value=5.0, step=1.0)

if project_choice == "Todos":
    st.subheader("Vista general — todos los proyectos")
    summary = summary_table(df)
    # Format columns
    summary["budget"] = summary["budget"].map("${:,.0f}".format)
    summary["latest_spend"] = summary["latest_spend"].map("${:,.0f}".format)
    summary["pct_execution"] = (summary["pct_execution"] * 100).map("{:.1f}%".format)
    summary["variance_pct"] = (summary["variance_pct"] * 100).map("{:.1f}%".format)
    summary["forecast_to_complete"] = summary["forecast_to_complete"].map("${:,.0f}".format)
    st.dataframe(summary.reset_index(drop=True), use_container_width=True)

    # Top risk bar
    topn = summary.nlargest(5, "risk_score")
    fig_bar = px.bar(topn, x="project_name", y="risk_score", title="Top proyectos por score de riesgo")
    st.plotly_chart(fig_bar, use_container_width=True)

else:
    proj_df = df[df["project_id"] == project_choice].copy()
    st.subheader(f"Proyecto: {proj_df['project_name'].iloc[0]} ({project_choice})")

    # Compute KPIs
    kpis = compute_kpis(proj_df)
    risky, message = flag_risk(kpis, variance_threshold/100.0, risk_threshold)
    # KPI cards
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Presupuesto", f"${kpis['budget']:,.0f}")
    col2.metric("Gasto actual", f"${kpis['latest_spend']:,.0f}", delta=f"{kpis['pct_execution']*100:.1f}%")
    col3.metric("Proyección cierre", f"${kpis['forecast_to_complete']:,.0f}")
    col4.metric("Riesgo (score)", f"{kpis['risk_score']:.1f}", delta=None)

    # Alert
    if risky:
        st.error(f"⚠️ ALERTAS: {message}")
    else:
        st.success(f"✅ Estado estable: {message}")

    # Time series: Budget vs cumulative spend
    fig = go.Figure()
    # budget line (flat)
    dates = proj_df["date"].dt.date.unique()
    fig.add_trace(go.Scatter(x=proj_df["date"], y=[kpis["budget"]]*len(proj_df), mode="lines", name="Presupuesto", line=dict(dash="dash")))
    fig.add_trace(go.Scatter(x=proj_df["date"], y=proj_df["cumulative_spend"], mode="lines+markers", name="Gasto acumulado"))
    fig.update_layout(title="Presupuesto vs Gasto acumulado", xaxis_title="Fecha", yaxis_title="Valor")
    st.plotly_chart(fig, use_container_width=True)

    # Milestones table
    st.markdown("**Hitos del proyecto**")
    ms = proj_df[["milestone", "milestone_date"]].dropna().drop_duplicates()
    st.table(ms.reset_index(drop=True))

    # Forecast visualization: show shaded band for simple +/-10% scenario
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=proj_df["date"], y=proj_df["cumulative_spend"], mode="lines+markers", name="Gasto actual"))
    # Forecast point at end
    fig2.add_trace(go.Scatter(x=[proj_df["date"].max()], y=[kpis["forecast_to_complete"]], mode="markers+text", name="Forecast", text=[f"${kpis['forecast_to_complete']:,.0f}"], textposition="top center"))
    fig2.update_layout(title="Proyección simple de cierre", xaxis_title="Fecha", yaxis_title="Valor")
    st.plotly_chart(fig2, use_container_width=True)

    # Table of monthly progression
    st.markdown("**Evolución**")
    evo = proj_df[["date", "cumulative_spend"]].copy()
    evo["date"] = evo["date"].dt.date
    evo["cumulative_spend"] = evo["cumulative_spend"].map("${:,.0f}".format)
    st.table(evo.reset_index(drop=True))

    # Recommendations (simple heuristics)
    st.markdown("**Recomendaciones rápidas**")
    recs = []
    if kpis["variance_pct"] > (variance_threshold/100.0):
        recs.append(f"- Revisar partidas con mayor desviación. Desviación actual {kpis['variance_pct']*100:.1f}%.")
    if kpis["forecast_to_complete"] > kpis["budget"]:
        recs.append(f"- Evaluar medidas de contención: renegociar proveedores o reasignar partidas. Forecast > presupuesto.")
    if kpis["days_elapsed"] / kpis["days_total"] < 0.5 and kpis["pct_execution"] > 0.7:
        recs.append("- Alta ejecución temprana: revisar ritmo de gasto y sincronizar cronograma.")
    if not recs:
        recs.append("- Mantener control y seguimiento regular; no se detectan acciones urgentes.")
    for r in recs:
        st.write(r)

# Footer
st.markdown("---")
st.markdown("**Control-Financiero-Proyectos-Inteligente** — Demo creada por Juliana Ángel. Datos de ejemplo.")
