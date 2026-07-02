import streamlit as st
import pandas as pd
import plotly.express as px
from pyathena import connect

# -------------------------------
# CONFIG
# -------------------------------

REGION = "eu-west-2"
S3_STAGING_DIR = "s3://athena-results-801886451424-eu-west-2/"
DATABASE = "entsoe"
TABLE = "generation_clean"

st.set_page_config(page_title="Solar Power Dashboard", layout="wide")
st.title("Solar Power Production – Austria vs Germany (2025–2026)")

# -------------------------------
# LOAD DATA FROM ATHENA
# -------------------------------

@st.cache_data(ttl=3600)
def load_data():

    query = f"""
        SELECT
            country,
            date,
            solar AS solar_mwh
        FROM {DATABASE}.{TABLE}
        WHERE country IN ('AT', 'DE')
          AND date BETWEEN DATE '2025-01-01'
                       AND DATE '2026-12-31'
        ORDER BY date
    """

    conn = connect(
        s3_staging_dir=S3_STAGING_DIR,
        region_name=REGION
    )

    df = pd.read_sql(query, conn)

    df["date"] = pd.to_datetime(df["date"])

    return df


try:
    df = load_data()
except Exception as e:
    st.error("Failed to load data from Athena.")
    st.exception(e)
    st.stop()

# -------------------------------
# SIDEBAR FILTERS
# -------------------------------

st.sidebar.header("Filters")

countries = df["country"].unique()
years = sorted(df["date"].dt.year.unique())

selected_country = st.sidebar.multiselect(
    "Select Country",
    options=countries,
    default=countries
)

selected_year = st.sidebar.multiselect(
    "Select Year",
    options=years,
    default=years
)

filtered = df[
    (df["country"].isin(selected_country)) &
    (df["date"].dt.year.isin(selected_year))
]

# -------------------------------
# DAILY LINE CHART
# -------------------------------

st.subheader("Daily Solar Production (MWh)")

fig_daily = px.line(
    filtered,
    x="date",
    y="solar_mwh",
    color="country"
)

st.plotly_chart(fig_daily, use_container_width=True)

# -------------------------------
# MONTHLY AGGREGATION
# -------------------------------

st.subheader("Monthly Solar Production (MWh)")

monthly = (
    filtered
    .groupby([filtered["date"].dt.to_period("M"), "country"])
    .solar_mwh.sum()
    .reset_index()
)

monthly["date"] = monthly["date"].dt.to_timestamp()

fig_monthly = px.bar(
    monthly,
    x="date",
    y="solar_mwh",
    color="country",
    barmode="group"
)

st.plotly_chart(fig_monthly, use_container_width=True)

# -------------------------------
# SUMMARY METRICS
# -------------------------------

st.subheader("Summary")

col1, col2 = st.columns(2)

with col1:
    st.metric(
        "Total Solar Production (MWh)",
        f"{filtered['solar_mwh'].sum():,.0f}"
    )

with col2:
    st.metric(
        "Average Daily Production (MWh)",
        f"{filtered['solar_mwh'].mean():,.0f}"
    )