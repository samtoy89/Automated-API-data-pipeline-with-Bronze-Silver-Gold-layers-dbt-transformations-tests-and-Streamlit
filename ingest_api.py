import requests
import duckdb
import pandas as pd
import time
from datetime import datetime, timezone

# API endpoint for the data source
API_ENDPOINT = "https://api.coingecko.com/api/v3/coins/markets"
PARAMS = {
    "vs_currency": "usd",
    "ids": "bitcoin,ethereum,cardano,solana,ripple",
    "order": "market_cap_desc",
    "per_page": 10,
    "page": 1,
    "sparkline": False
}

DB_PATH = "analytics.duckdb"

def fetch_crypto_data():
        """
        Fetches live market data from public REST API.
        Returns:
            list: A list of dictionaries containing cryptocurrency data.
        """
        try:
            response = requests.get(API_ENDPOINT, params=PARAMS, timeout=10)
            response.raise_for_status()  # Raise an error for bad responses
            data = response.json()
            return data
        except requests.exceptions.RequestException as e:
            print(f"Error fetching data from API: {e}")
            return []

def ingest_data(data):
    """
    Ingests the fetched data into DuckDB.
    Args:
        data (list): The data to ingest.
    """
    if not data:
        print("No data to ingest.")
        return

    # Convert the data into a DataFrame
    df = pd.DataFrame(data)

    # Ingest the DataFrame into DuckDB
    conn = duckdb.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS bronze_raw_crypto_prices AS SELECT * FROM df")
    conn.close()

def initialize_database():
    """
    Ensure bronze raw schema and landing table exists in DuckDB. If not, create them.
    Initializes the DuckDB database and creates the necessary table if it doesn't exist.
    """
    conn = duckdb.connect(DB_PATH)
    conn.execute("""
        CREATE SCHEMA IF NOT EXISTS bronze_raw;
        CREATE TABLE IF NOT EXISTS bronze_raw_crypto_prices (
            id STRING,
            symbol STRING,
            name STRING,
            current_price DOUBLE,
            market_cap DOUBLE,
            total_volume DOUBLE,
            high_24h DOUBLE,
            low_24h DOUBLE,
            price_change_percentage_24h DOUBLE,
            last_updated TIMESTAMP,
            extraction_timestamp TIMESTAMPTZ
        );
        ALTER TABLE bronze_raw_crypto_prices ADD COLUMN IF NOT EXISTS extraction_timestamp TIMESTAMPTZ;
    """)
    conn.close()

def load_data_incrementally(data):
    """
    Loads data into DuckDB Bronze layer incrementally.
    Args:
        data (list): The data to load.
    """
    if not data:
        print("No data to load.")
        return

    # Convert the data into a DataFrame
    df = pd.DataFrame(data)
    
    # Filter required columns and add extraction timestamp
    df = df[['id', 'symbol', 'name', 'current_price', 'market_cap', 'total_volume', 'high_24h', 'low_24h', 'price_change_percentage_24h', 'last_updated']]
    df['last_updated'] = pd.to_datetime(df['last_updated'], utc=True).dt.tz_localize(None)
    df['extraction_timestamp'] = datetime.now(timezone.utc)

    # Load the DataFrame into DuckDB
    conn = duckdb.connect(DB_PATH)
    conn.execute("INSERT INTO bronze_raw_crypto_prices BY NAME SELECT * FROM df")

    count = conn.execute("SELECT COUNT(*) FROM bronze_raw_crypto_prices").fetchone()[0]
    print(f"Total records in bronze_raw_crypto_prices: {count}")
    conn.close()


if __name__ == "__main__":
    initialize_database()
    while True:
        data = fetch_crypto_data()
        load_data_incrementally(data)
        time.sleep(60)  # Wait for 60 seconds before fetching new data