import time
from datetime import datetime, timezone

import duckdb
import pandas as pd
import plotly.express as px
import streamlit as st

DB_PATH = "analytics.duckdb"
REFRESH_SECONDS = 15
STALE_AFTER_SECONDS = 180  # orchestrator runs every 60s; flag if 3 cycles missed

st.set_page_config(page_title="Crypto Pipeline Monitor", page_icon="📈", layout="wide")


def query(sql, retries=5):
    """
    Runs a read-only query against DuckDB.
    The orchestrator briefly holds a write lock on each cycle, so retry on lock errors.
    """
    for attempt in range(retries):
        try:
            with duckdb.connect(DB_PATH, read_only=True) as conn:
                return conn.execute(sql).df()
        except duckdb.IOException:
            if attempt == retries - 1:
                raise
            time.sleep(0.5)


def load_data():
    latest = query("select * from fct_latest_prices order by market_cap_usd desc")
    history = query("""
        select ticker, price_usd, price_timestamp
        from stg_crypto_prices
        where price_timestamp >= now()::timestamp - interval 24 hour
        order by price_timestamp
    """)
    health = query("""
        select
            count(*) as total_records,
            count(distinct extraction_timestamp) as total_runs,
            max(extraction_timestamp) as last_ingested_at,
            count(*) filter (where extraction_timestamp >= now() - interval 1 hour) as records_last_hour
        from bronze_raw_crypto_prices
    """).iloc[0]
    return latest, history, health


def format_usd(value):
    if value >= 1e9:
        return f"${value / 1e9:,.2f}B"
    if value >= 1e6:
        return f"${value / 1e6:,.2f}M"
    if value >= 1:
        return f"${value:,.2f}"
    return f"${value:,.4f}"


st.title("📈 Real-Time Crypto Pipeline Monitor")
st.caption(
    f"Bronze → Silver → Gold with Python, dbt and DuckDB · refreshes every {REFRESH_SECONDS}s. "
    "Start the pipeline with `python orchestrator.py`."
)


@st.fragment(run_every=REFRESH_SECONDS)
def dashboard():
    try:
        latest, history, health = load_data()
    except duckdb.IOException:
        st.warning("Database is busy (the orchestrator is writing). Retrying on next refresh...")
        return
    except duckdb.CatalogException:
        st.error("dbt models not found. Run `dbt build` in the transformations folder first.")
        return

    # --- Pipeline health ---
    st.subheader("Pipeline Health")
    last_ingested = pd.Timestamp(health["last_ingested_at"])
    if last_ingested.tzinfo is None:
        last_ingested = last_ingested.tz_localize("UTC")
    age_seconds = (datetime.now(timezone.utc) - last_ingested).total_seconds()

    h1, h2, h3, h4 = st.columns(4)
    if age_seconds <= STALE_AFTER_SECONDS:
        h1.metric("Status", "🟢 Live", f"last load {age_seconds:.0f}s ago", delta_color="off")
    else:
        h1.metric("Status", "🔴 Stale", f"last load {age_seconds / 60:.0f} min ago", delta_color="off")
    h2.metric("Bronze records", f"{int(health['total_records']):,}")
    h3.metric("Ingestion runs", f"{int(health['total_runs']):,}")
    h4.metric("Records (last hour)", f"{int(health['records_last_hour']):,}")

    # --- Latest prices (Gold layer) ---
    st.subheader("Latest Prices")
    cols = st.columns(len(latest))
    for col, row in zip(cols, latest.itertuples()):
        col.metric(
            f"{row.ticker} · {row.asset_name}",
            format_usd(row.price_usd),
            f"{row.pct_change_24h:+.2f}% (24h)",
        )

    # --- Price history (Silver layer) ---
    st.subheader("Price History (last 24h)")
    tickers = latest["ticker"].tolist()
    selected = st.segmented_control(
        "Coin", tickers, default=tickers[0], key="selected_ticker", label_visibility="collapsed"
    ) or tickers[0]
    coin_history = history[history["ticker"] == selected]

    if coin_history.empty:
        st.info("No price history in the last 24 hours yet.")
    else:
        fig = px.line(coin_history, x="price_timestamp", y="price_usd", markers=len(coin_history) < 60)
        fig.update_layout(
            xaxis_title=None, yaxis_title="Price (USD)", height=380, margin=dict(l=0, r=0, t=10, b=0)
        )
        st.plotly_chart(fig, width="stretch")

    # --- Market overview ---
    left, right = st.columns([1, 1])
    with left:
        st.subheader("Market Cap Share")
        fig = px.pie(latest, names="ticker", values="market_cap_usd", hole=0.5)
        fig.update_layout(height=320, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig, width="stretch")
    with right:
        st.subheader("24h Change")
        fig = px.bar(
            latest.sort_values("pct_change_24h"), x="pct_change_24h", y="ticker", orientation="h",
            color=latest.sort_values("pct_change_24h")["pct_change_24h"] >= 0,
            color_discrete_map={True: "#16a34a", False: "#dc2626"},
        )
        fig.update_layout(
            height=320, margin=dict(l=0, r=0, t=10, b=0), showlegend=False,
            xaxis_title="% change", yaxis_title=None,
        )
        st.plotly_chart(fig, width="stretch")

    # --- Gold table ---
    st.subheader("fct_latest_prices")
    st.dataframe(
        latest,
        hide_index=True,
        width="stretch",
        column_config={
            "price_usd": st.column_config.NumberColumn("Price", format="$%.4f"),
            "market_cap_usd": st.column_config.NumberColumn("Market cap", format="compact"),
            "volume_24h_usd": st.column_config.NumberColumn("24h volume", format="compact"),
            "pct_change_24h": st.column_config.NumberColumn("24h %", format="%.2f%%"),
            "price_timestamp": st.column_config.DatetimeColumn("Updated", format="YYYY-MM-DD HH:mm:ss"),
        },
    )
    st.caption(f"Last refreshed {datetime.now().strftime('%H:%M:%S')}")


dashboard()
