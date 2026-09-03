-- ============================================================
-- NLDC VRE / REMC Report Schema
-- CarobInsights Power Sector Analytics
-- ============================================================

CREATE SCHEMA IF NOT EXISTS nldc_vre;

-- ── Table 1: All India daily VRE summary (Section 1) ────────
CREATE TABLE IF NOT EXISTS nldc_vre.daily_summary (
    id                          SERIAL PRIMARY KEY,
    report_date                 DATE NOT NULL UNIQUE,

    -- Solar hours block (0600-1800)
    solar_hrs_max_demand_mw     NUMERIC,
    solar_hrs_max_demand_time   TIME,
    solar_hrs_wind_mw           NUMERIC,
    solar_hrs_solar_mw          NUMERIC,
    solar_hrs_vre_mw            NUMERIC,
    solar_hrs_wind_pct          NUMERIC,
    solar_hrs_solar_pct         NUMERIC,
    solar_hrs_vre_pct           NUMERIC,

    -- Non-solar hours block
    non_solar_hrs_max_demand_mw NUMERIC,
    non_solar_hrs_max_demand_time TIME,
    non_solar_hrs_wind_mw       NUMERIC,
    non_solar_hrs_vre_mw        NUMERIC,
    non_solar_hrs_wind_pct      NUMERIC,
    non_solar_hrs_vre_pct       NUMERIC,

    -- Daily max generation
    daily_max_wind_mw           NUMERIC,
    daily_max_wind_time         TIME,
    daily_max_solar_mw          NUMERIC,
    daily_max_solar_time        TIME,
    daily_max_vre_mw            NUMERIC,
    daily_max_vre_time          TIME,

    -- Daily max penetration %
    daily_max_wind_pct          NUMERIC,
    daily_max_wind_pct_time     TIME,
    daily_max_solar_pct         NUMERIC,
    daily_max_solar_pct_time    TIME,
    daily_max_vre_pct           NUMERIC,
    daily_max_vre_pct_time      TIME,

    -- All-time records (as reported that day)
    alltime_max_wind_mw         NUMERIC,
    alltime_max_wind_date       DATE,
    alltime_max_solar_mw        NUMERIC,
    alltime_max_solar_date      DATE,
    alltime_max_vre_mw          NUMERIC,
    alltime_max_vre_date        DATE,
    alltime_max_wind_pct        NUMERIC,
    alltime_max_wind_pct_date   DATE,
    alltime_max_solar_pct       NUMERIC,
    alltime_max_solar_pct_date  DATE,
    alltime_max_vre_pct         NUMERIC,
    alltime_max_vre_pct_date    DATE,

    created_at                  TIMESTAMPTZ DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ DEFAULT NOW()
);

-- ── Table 2: Region-wise REMC monitored profile (Section 2) ─
CREATE TABLE IF NOT EXISTS nldc_vre.region_profile (
    id                      SERIAL PRIMARY KEY,
    report_date             DATE NOT NULL,
    region                  TEXT NOT NULL,           -- NR, WR, SR, Total
    source                  TEXT DEFAULT 'remc',     -- remc or ists

    wind_installed_mw       NUMERIC,
    wind_available_mw       NUMERIC,
    solar_installed_mw      NUMERIC,
    solar_available_mw      NUMERIC,
    total_installed_mw      NUMERIC,
    total_available_mw      NUMERIC,

    wind_day_max_mw         NUMERIC,
    wind_day_max_time       TIME,
    wind_day_min_mw         NUMERIC,
    wind_day_min_time       TIME,
    solar_day_max_mw        NUMERIC,
    solar_day_max_time      TIME,
    total_day_max_mw        NUMERIC,
    total_day_max_time      TIME,
    total_day_min_mw        NUMERIC,
    total_day_min_time      TIME,

    wind_schedule_mu        NUMERIC,
    wind_actual_mu          NUMERIC,
    wind_deviation_mu       NUMERIC,
    wind_cuf_pct            NUMERIC,
    solar_schedule_mu       NUMERIC,
    solar_actual_mu         NUMERIC,
    solar_deviation_mu      NUMERIC,
    solar_cuf_pct           NUMERIC,
    total_schedule_mu       NUMERIC,
    total_actual_mu         NUMERIC,
    total_deviation_mu      NUMERIC,
    total_cuf_pct           NUMERIC,

    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE (report_date, region, source)
);

-- ── Table 3: State-wise intra-state profile (Sections 4+5) ──
CREATE TABLE IF NOT EXISTS nldc_vre.state_profile (
    id                      SERIAL PRIMARY KEY,
    report_date             DATE NOT NULL,
    state                   TEXT NOT NULL,
    region                  TEXT,
    section                 TEXT,                    -- remc_intrastate / non_remc_regional / non_remc_intrastate

    wind_installed_mw       NUMERIC,
    wind_available_mw       NUMERIC,
    solar_installed_mw      NUMERIC,
    solar_available_mw      NUMERIC,
    total_installed_mw      NUMERIC,
    total_available_mw      NUMERIC,

    wind_day_max_mw         NUMERIC,
    wind_day_max_time       TIME,
    wind_day_min_mw         NUMERIC,
    wind_day_min_time       TIME,
    solar_day_max_mw        NUMERIC,
    solar_day_max_time      TIME,
    total_day_max_mw        NUMERIC,
    total_day_max_time      TIME,
    total_day_min_mw        NUMERIC,
    total_day_min_time      TIME,

    wind_schedule_mu        NUMERIC,
    wind_actual_mu          NUMERIC,
    wind_deviation_mu       NUMERIC,
    wind_cuf_pct            NUMERIC,
    solar_schedule_mu       NUMERIC,
    solar_actual_mu         NUMERIC,
    solar_deviation_mu      NUMERIC,
    solar_cuf_pct           NUMERIC,
    total_schedule_mu       NUMERIC,
    total_actual_mu         NUMERIC,
    total_deviation_mu      NUMERIC,
    total_cuf_pct           NUMERIC,

    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE (report_date, state, section)
);

-- ── Indexes ──────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_vre_region_date  ON nldc_vre.region_profile (report_date);
CREATE INDEX IF NOT EXISTS idx_vre_region_name  ON nldc_vre.region_profile (region);
CREATE INDEX IF NOT EXISTS idx_vre_state_date   ON nldc_vre.state_profile (report_date);
CREATE INDEX IF NOT EXISTS idx_vre_state_name   ON nldc_vre.state_profile (state);

-- ── Views ─────────────────────────────────────────────────────

-- Daily VRE penetration trend
CREATE OR REPLACE VIEW nldc_vre.v_daily_vre_trend AS
SELECT
    report_date,
    daily_max_vre_pct,
    daily_max_vre_pct_time,
    daily_max_solar_pct,
    daily_max_wind_pct,
    solar_hrs_vre_pct,
    solar_hrs_solar_pct,
    solar_hrs_wind_pct,
    alltime_max_vre_pct,
    alltime_max_vre_date
FROM nldc_vre.daily_summary
ORDER BY report_date;

-- Region-wise actual generation trend
CREATE OR REPLACE VIEW nldc_vre.v_region_generation AS
SELECT
    r.report_date,
    r.region,
    r.wind_actual_mu,
    r.solar_actual_mu,
    r.total_actual_mu,
    r.wind_cuf_pct,
    r.solar_cuf_pct,
    r.total_cuf_pct,
    r.wind_deviation_mu,
    r.solar_deviation_mu,
    d.daily_max_vre_pct
FROM nldc_vre.region_profile r
JOIN nldc_vre.daily_summary d USING (report_date)
WHERE r.source = 'remc'
ORDER BY r.report_date, r.region;

-- State solar CUF ranking
CREATE OR REPLACE VIEW nldc_vre.v_state_solar_cuf AS
SELECT
    report_date,
    state,
    region,
    solar_actual_mu,
    solar_cuf_pct,
    wind_actual_mu,
    wind_cuf_pct,
    total_actual_mu
FROM nldc_vre.state_profile
WHERE solar_cuf_pct IS NOT NULL
ORDER BY report_date, solar_cuf_pct DESC;
