-- ================================================================
-- NLDC Power Grid Data Schema
-- Run this in your existing Supabase project SQL editor
-- Creates a separate 'nldc' schema to keep it isolated from
-- your existing CarobInsights/FADA tables
-- ================================================================

-- Create dedicated schema
CREATE SCHEMA IF NOT EXISTS nldc;

-- ── 1. Daily Summary (one row per day) ───────────────────────
CREATE TABLE IF NOT EXISTS nldc.daily_summary (
  id              BIGSERIAL PRIMARY KEY,
  report_date     DATE NOT NULL UNIQUE,

  -- Regional peak demand at 20:00 evening peak (MW)
  nr_peak_mw      INTEGER,
  wr_peak_mw      INTEGER,
  sr_peak_mw      INTEGER,
  er_peak_mw      INTEGER,
  ner_peak_mw     INTEGER,
  all_peak_mw     INTEGER,

  -- Shortage at evening peak (MW)
  nr_shortage_mw  INTEGER DEFAULT 0,
  wr_shortage_mw  INTEGER DEFAULT 0,
  sr_shortage_mw  INTEGER DEFAULT 0,
  er_shortage_mw  INTEGER DEFAULT 0,
  ner_shortage_mw INTEGER DEFAULT 0,
  all_shortage_mw INTEGER DEFAULT 0,

  -- Daily energy met (MU)
  nr_energy_mu    DECIMAL(8,2),
  wr_energy_mu    DECIMAL(8,2),
  sr_energy_mu    DECIMAL(8,2),
  er_energy_mu    DECIMAL(8,2),
  ner_energy_mu   DECIMAL(8,2),
  all_energy_mu   DECIMAL(8,2),
  all_energy_shortage_mu DECIMAL(7,2) DEFAULT 0,

  -- Max demand during the day (MW) — from 1-min SCADA
  nr_max_mw       INTEGER,
  wr_max_mw       INTEGER,
  sr_max_mw       INTEGER,
  er_max_mw       INTEGER,
  ner_max_mw      INTEGER,
  max_demand_mw   INTEGER,
  max_demand_time TIME,

  -- Hydro generation (MU)
  hydro_nr_mu     DECIMAL(7,2),
  hydro_wr_mu     DECIMAL(7,2),
  hydro_sr_mu     DECIMAL(7,2),
  hydro_er_mu     DECIMAL(7,2),
  hydro_ner_mu    DECIMAL(7,2),
  hydro_mu        DECIMAL(7,2),
  hydro_gen_mu    DECIMAL(7,2),   -- from section G (gross, incl. PSP)

  -- Wind generation (MU)
  wind_mu         DECIMAL(7,2),   -- All India total

  -- Solar generation (MU)
  solar_nr_mu     DECIMAL(7,2),
  solar_wr_mu     DECIMAL(7,2),
  solar_sr_mu     DECIMAL(7,2),
  solar_er_mu     DECIMAL(7,2),
  solar_ner_mu    DECIMAL(7,2),
  solar_mu        DECIMAL(7,2),   -- All India total

  -- Sourcewise generation (MU) — Section G gross figures
  coal_mu         DECIMAL(7,2),
  lignite_mu      DECIMAL(7,2),
  nuclear_mu      DECIMAL(7,2),
  gas_mu          DECIMAL(7,2),
  res_mu          DECIMAL(7,2),   -- Wind + Solar + Biomass
  total_gen_mu    DECIMAL(7,2),

  -- Frequency profile
  freq_fvi        DECIMAL(6,3),   -- Frequency Variation Index
  freq_below_497  DECIMAL(6,3),   -- % time < 49.7 Hz
  freq_497_498    DECIMAL(6,3),
  freq_498_499    DECIMAL(6,3),
  freq_band_pct   DECIMAL(6,3),   -- % time in 49.9-50.05 Hz (IEGC band)
  freq_above_5005 DECIMAL(6,3),

  -- Generation outage (MW)
  central_outage_mw INTEGER,
  state_outage_mw   INTEGER,
  total_outage_mw   INTEGER,

  -- RES metrics
  res_share_pct         DECIMAL(5,2),
  non_fossil_share_pct  DECIMAL(5,2),

  -- Diversity factors
  diversity_factor_regional DECIMAL(5,3),
  diversity_factor_state    DECIMAL(5,3),

  -- Solar / Non-solar hour analysis
  solar_hr_peak_mw      INTEGER,
  solar_hr_peak_time    TIME,
  solar_hr_shortage_mw  INTEGER DEFAULT 0,
  non_solar_peak_mw     INTEGER,
  non_solar_peak_time   TIME,
  non_solar_shortage_mw INTEGER DEFAULT 0,

  -- Metadata
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ── 2. SCADA 15-minute data ───────────────────────────────────
CREATE TABLE IF NOT EXISTS nldc.scada_15min (
  id              BIGSERIAL PRIMARY KEY,
  report_date     DATE NOT NULL,
  time_block      TIME NOT NULL,

  -- Grid metrics
  frequency_hz          DECIMAL(5,2),
  demand_mw             INTEGER,
  storage_demand_mw     INTEGER,    -- PSP pumping + BESS charging
  net_demand_mw         INTEGER,    -- demand minus storage_demand

  -- Generation by source (MW)
  nuclear_mw            INTEGER,
  wind_mw               INTEGER,
  solar_mw              INTEGER,
  hydro_mw              INTEGER,
  gas_mw                INTEGER,
  thermal_mw            INTEGER,
  storage_discharge_mw  INTEGER,    -- PSP + BESS discharging
  others_mw             INTEGER,    -- Biomass, small IPPs

  -- Totals
  total_gen_mw          INTEGER,
  transnational_mw      INTEGER,    -- positive = import, negative = export

  created_at            TIMESTAMPTZ DEFAULT NOW(),

  UNIQUE(report_date, time_block)
);

-- ── 3. State daily snapshot ───────────────────────────────────
CREATE TABLE IF NOT EXISTS nldc.state_daily (
  id              BIGSERIAL PRIMARY KEY,
  report_date     DATE NOT NULL,
  state           VARCHAR(60) NOT NULL,
  region          VARCHAR(5),       -- NR/WR/SR/ER/NER

  -- Demand
  peak_demand_mw        INTEGER,
  shortage_peak_mw      INTEGER DEFAULT 0,

  -- Energy
  energy_met_mu         DECIMAL(7,2),
  energy_shortage_mu    DECIMAL(7,2) DEFAULT 0,

  -- Grid discipline
  drawal_schedule_mu    DECIMAL(8,2),
  od_ud_mu              DECIMAL(8,2),    -- positive = overdrawal, negative = underdrawal
  max_od_mw             INTEGER,
  max_ud_mw             INTEGER,

  created_at            TIMESTAMPTZ DEFAULT NOW(),

  UNIQUE(report_date, state)
);

-- ── Indexes for common query patterns ────────────────────────
CREATE INDEX IF NOT EXISTS idx_daily_date
  ON nldc.daily_summary(report_date DESC);

CREATE INDEX IF NOT EXISTS idx_daily_demand
  ON nldc.daily_summary(max_demand_mw DESC);

CREATE INDEX IF NOT EXISTS idx_scada_date
  ON nldc.scada_15min(report_date DESC);

CREATE INDEX IF NOT EXISTS idx_scada_date_time
  ON nldc.scada_15min(report_date, time_block);

CREATE INDEX IF NOT EXISTS idx_scada_solar
  ON nldc.scada_15min(report_date, solar_mw);

CREATE INDEX IF NOT EXISTS idx_state_date
  ON nldc.state_daily(report_date DESC);

CREATE INDEX IF NOT EXISTS idx_state_name
  ON nldc.state_daily(state, report_date DESC);

CREATE INDEX IF NOT EXISTS idx_state_region
  ON nldc.state_daily(region, report_date DESC);

-- ── Helper views ──────────────────────────────────────────────

-- Daily RES share view
CREATE OR REPLACE VIEW nldc.v_daily_res AS
SELECT
  report_date,
  max_demand_mw,
  all_energy_mu,
  solar_mu,
  wind_mu,
  hydro_mu,
  nuclear_mu,
  coal_mu,
  res_share_pct,
  non_fossil_share_pct,
  freq_band_pct,
  total_outage_mw,
  non_solar_shortage_mw
FROM nldc.daily_summary
ORDER BY report_date;

-- Duck curve view — daily solar profile
CREATE OR REPLACE VIEW nldc.v_duck_curve AS
SELECT
  s.report_date,
  s.time_block,
  s.demand_mw,
  s.solar_mw,
  s.wind_mw,
  s.thermal_mw,
  s.hydro_mw,
  s.gas_mw,
  s.storage_discharge_mw,
  s.demand_mw - s.solar_mw AS net_demand_mw,
  s.frequency_hz,
  d.max_demand_mw AS day_peak_mw
FROM nldc.scada_15min s
JOIN nldc.daily_summary d ON s.report_date = d.report_date
ORDER BY s.report_date, s.time_block;

-- State energy ranking view
CREATE OR REPLACE VIEW nldc.v_state_rank AS
SELECT
  report_date,
  state,
  region,
  peak_demand_mw,
  energy_met_mu,
  od_ud_mu,
  CASE
    WHEN od_ud_mu < -50  THEN 'Strong Exporter'
    WHEN od_ud_mu < 0    THEN 'Mild Exporter'
    WHEN od_ud_mu < 50   THEN 'Balanced'
    ELSE 'Importer'
  END AS grid_role
FROM nldc.state_daily
ORDER BY report_date, energy_met_mu DESC;

-- ── Trigger: updated_at ───────────────────────────────────────
CREATE OR REPLACE FUNCTION nldc.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_daily_summary_updated
BEFORE UPDATE ON nldc.daily_summary
FOR EACH ROW EXECUTE FUNCTION nldc.set_updated_at();
