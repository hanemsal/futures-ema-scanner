# scripts/backfill_risk.py

⚠️ One-time migration script

This script is used to backfill `risk_level`, `risk_score`, and `risk_reasons`
columns for existing records in the `signals` table.

It should only be executed manually when:

* new risk fields are added
* historical data needs to be updated

❗ Do NOT run continuously or integrate into worker/production loop.

Usage:
python scripts/backfill_risk.py
