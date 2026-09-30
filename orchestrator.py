import time
import os
import sys
import subprocess
from ingest_api import (
    initialize_database,
    fetch_crypto_data,
    load_data_incrementally
)

# Windows consoles default to cp1252, which can't print emoji
sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DBT_DIR = os.path.join(PROJECT_ROOT, "transformations")

def run_pipeline():
    print("\n" + "-" * 50)
    print("🚀 Triggering Automated Real-Time Pipeline Run...")

    # 1. Ingest
    payload = fetch_crypto_data()
    if payload:
        load_data_incrementally(payload)

    # 2. Transform via dbt
    try:
        subprocess.run(["dbt", "run"], cwd=DBT_DIR, check=True)
        subprocess.run(["dbt", "test"], cwd=DBT_DIR, check=True)
        print("✅ Pipeline run completed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"❌ dbt step failed (exit code {e.returncode}). Retrying next cycle.")

if __name__ == "__main__":
    initialize_database()
    while True:
        run_pipeline()
        print("⏳ Sleeping for 60 seconds before next fetch...")
        time.sleep(60)
