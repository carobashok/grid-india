# NLDC Daily PSP Pipeline

Parse NLDC Daily PSP PDFs → load into Supabase

## Setup

### 1. Install dependencies
```bash
pip install pdfplumber supabase python-dotenv
```

### 2. Create .env file
```bash
cp .env.example .env
# Edit .env with your Supabase credentials
```

### 3. Run schema in Supabase SQL editor
```sql
-- Paste contents of supabase_schema.sql into Supabase SQL editor
-- This creates the nldc schema + 3 tables + indexes + views
```

### 4. Organise your PDFs
Rename each downloaded PDF using the DATA date (not report date):
```
pdfs/
  raw/
    2026-04-01_NLDC_PSP.pdf    ← contains Apr 01 data
    2026-04-02_NLDC_PSP.pdf
    ...
    2026-08-21_NLDC_PSP.pdf
    2026-08-22_NLDC_PSP.pdf
```

Note: NLDC publishes each day's report the following morning.
The report dated 22-Aug-2026 contains 21-Aug-2026 data.
Name your file after the DATA date (21-Aug).

## Running

### Historical bulk load (all PDFs in a folder)
```bash
python run_pipeline.py --folder ./pdfs/raw
```

### Single file
```bash
python run_pipeline.py --file ./pdfs/raw/2026-08-21_NLDC_PSP.pdf
```

### Dry run (parse only, test without loading)
```bash
python run_pipeline.py --folder ./pdfs/raw --dry-run
```

### Daily automation (add to cron)
```bash
# Download yesterday's PDF, rename it, then:
python run_pipeline.py --daily --pdf-folder ./pdfs/raw

# Cron: run every morning at 8am
0 8 * * * cd /path/to/nldc_pipeline && python run_pipeline.py --daily
```

### Force reprocess (ignore processed.json)
```bash
python run_pipeline.py --folder ./pdfs/raw --force
```

## What Gets Loaded

| Table | Rows per day | Key columns |
|-------|-------------|-------------|
| nldc.daily_summary | 1 | 60+ fields: regional demand, energy, RES mix, frequency, outage |
| nldc.scada_15min | 96 | demand, solar, wind, thermal, gas, hydro, frequency per 15-min |
| nldc.state_daily | ~34 | peak demand, energy met, drawal schedule, OD/UD per state |

## Useful Queries

```sql
-- Daily duck curve for a specific date
SELECT time_block, demand_mw, solar_mw, demand_mw - solar_mw AS net_demand
FROM nldc.scada_15min
WHERE report_date = '2026-08-21'
ORDER BY time_block;

-- Peak demand trend
SELECT report_date, max_demand_mw, all_energy_mu, solar_mu, freq_band_pct
FROM nldc.daily_summary
ORDER BY report_date;

-- States with highest shortage
SELECT report_date, state, region, energy_shortage_mu, shortage_peak_mw
FROM nldc.state_daily
WHERE energy_shortage_mu > 0
ORDER BY energy_shortage_mu DESC;

-- Non-fossil share trend
SELECT report_date, res_share_pct, non_fossil_share_pct, non_solar_shortage_mw
FROM nldc.daily_summary
ORDER BY report_date;
```

## Files

| File | Purpose |
|------|---------|
| nldc_parser.py | PDF parsing — no external dependencies except pdfplumber |
| nldc_loader.py | Supabase upserts |
| run_pipeline.py | CLI runner — bulk, single, daily modes |
| supabase_schema.sql | Run once in Supabase SQL editor |
| .env.example | Environment variable template |
