"""
nldc_vre_parser.py — NLDC VRE / REMC Daily Report Parser
CarobInsights Power Sector Analytics

Parses NLDC Renewable Energy Management Centre (REMC) daily PDF reports
into three datasets:
  1. daily_summary   — All India VRE metrics (Section 1)
  2. region_profile  — Region-wise REMC + ISTS profiles (Sections 2 & 3)
  3. state_profile   — State-wise intra-state profiles (Sections 4 & 5)

Filename formats supported:
  DD_MM_YYYY_NLDC_REMC_REPORT_NNN.pdf
  DD_MM_YY_NLDC_REMC_REPORT_NNN.pdf
  DD.MM.YY_NLDC_REMC_REPORT_NNN.pdf
  YYYY-MM-DD_NLDC_REMC.pdf
  (with optional upload numeric prefix, e.g. 1787662498942_DD_MM_YYYY_...)
"""

import re
import sys
import json
import pdfplumber
from pathlib import Path
from datetime import date, datetime


# ── helpers ──────────────────────────────────────────────────────────────────

def _nums(line: str) -> list[float | None]:
    """Extract numbers from line, stripping time tokens to avoid HH:MM splits."""
    clean = re.sub(r'\b\d{1,2}:\d{2}\b', '', line)
    raw = re.findall(r'-?[\d,]+\.?\d*', clean)
    result = []
    for v in raw:
        try:
            result.append(float(v.replace(',', '')))
        except ValueError:
            pass
    return result

def _times(line: str) -> list[str]:
    """Extract HH:MM time strings from line."""
    return re.findall(r'\d{1,2}:\d{2}', line)

def _f(val) -> float | None:
    if val is None:
        return None
    try:
        return float(str(val).replace(',', '').replace('%', '').strip())
    except (ValueError, AttributeError):
        return None

def _t(val: str | None) -> str | None:
    if not val:
        return None
    m = re.search(r'(\d{1,2}):(\d{2})', str(val))
    if m:
        return f"{int(m.group(1)):02d}:{int(m.group(2)):02d}"
    return None

def _d(val: str | None) -> str | None:
    """Parse date string → ISO YYYY-MM-DD."""
    if not val:
        return None
    val = str(val).strip()
    val = re.split(r'\s+\d{1,2}:\d{2}', val)[0].strip()
    # Named month: 27-Mar-2026, 29-July-2025
    m = re.search(r'(\d{1,2})[- ]([A-Za-z]+)[- ](\d{2,4})', val)
    if m:
        yr = m.group(3)
        if len(yr) == 2:
            yr = str(2000 + int(yr)) if int(yr) < 50 else str(1900 + int(yr))
        try:
            return datetime.strptime(
                f"{m.group(1)}-{m.group(2)[:3]}-{yr}", '%d-%b-%Y'
            ).strftime('%Y-%m-%d')
        except ValueError:
            pass
    # DD-MM-YYYY or DD/MM/YYYY
    m = re.search(r'(\d{2})[-/](\d{2})[-/](\d{4})', val)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return None

def _date_from_filename(path: Path) -> date | None:
    """Extract report date from VRE PDF filename, stripping upload numeric prefix."""
    name = path.stem.upper()
    name = re.sub(r'^\d+_', '', name)   # strip upload prefix like 1787662498942_
    # DD_MM_YYYY_NLDC_REMC_...
    m = re.match(r'(\d{2})[._](\d{2})[._](\d{4})_NLDC_REMC', name)
    if m:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    # DD_MM_YY_NLDC_REMC_...
    m = re.match(r'(\d{2})[._](\d{2})[._](\d{2})_NLDC_REMC', name)
    if m:
        d2, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        yr = 2000 + y if y < 50 else 1900 + y
        return date(yr, mo, d2)
    # YYYY-MM-DD_NLDC_REMC
    m = re.match(r'(\d{4})-(\d{2})-(\d{2})_NLDC_REMC', name)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None

def _date_from_text(text: str) -> date | None:
    """Extract 'Report for: DD-Mon-YY' — the actual data date, not publishing date."""
    m = re.search(r'Report for\s*:\s*([\d\-A-Za-z./ ]+)', text)
    if m:
        return _d(m.group(1).strip())
    return None


# ── text extraction ──────────────────────────────────────────────────────────

def _extract_pages(pdf_path: Path) -> list[str]:
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or '')
    return pages


# ── Section 1: All India daily summary ──────────────────────────────────────

def _parse_daily_summary(text: str, report_date: date) -> dict:
    rec = {'report_date': str(report_date)}
    lines_list = text.split('\n')

    def _fill_solar_hrs(ln):
        clean = re.sub(r'\(0600-1800hrs?\)', '', ln)
        n2 = _nums(clean); t2 = _times(clean)
        pcts2 = re.findall(r'([\d.]+)%', clean)
        if len(n2) >= 4 and n2[0] > 50000:
            rec['solar_hrs_max_demand_mw']   = n2[0]
            rec['solar_hrs_max_demand_time'] = _t(t2[0]) if t2 else None
            rec['solar_hrs_wind_mw']         = n2[1]
            rec['solar_hrs_wind_pct']        = _f(pcts2[0]) if pcts2 else None
            rec['solar_hrs_solar_mw']        = n2[2]
            rec['solar_hrs_solar_pct']       = _f(pcts2[1]) if len(pcts2) > 1 else None
            rec['solar_hrs_vre_mw']          = n2[3]
            rec['solar_hrs_vre_pct']         = _f(pcts2[2]) if len(pcts2) > 2 else None
            return True
        return False

    def _fill_non_solar_hrs(ln):
        n2 = _nums(ln); t2 = _times(ln)
        pcts2 = re.findall(r'([\d.]+)%', ln)
        if len(n2) >= 2 and n2[0] > 50000:
            rec['non_solar_hrs_max_demand_mw']   = n2[0]
            rec['non_solar_hrs_max_demand_time'] = _t(t2[0]) if t2 else None
            rec['non_solar_hrs_wind_mw']         = n2[1]
            rec['non_solar_hrs_wind_pct']        = _f(pcts2[0]) if pcts2 else None
            rec['non_solar_hrs_vre_mw']          = n2[2] if len(n2) > 2 else None
            rec['non_solar_hrs_vre_pct']         = _f(pcts2[1]) if len(pcts2) > 1 else None
            return True
        return False

    for i, line in enumerate(lines_list):
        if 'Solar hrs' in line and '0600' in line:
            # Try same line first, then PREVIOUS line (data before label), then next line
            if not _fill_solar_hrs(line):
                if i > 0 and not _fill_solar_hrs(lines_list[i-1]):
                    if i + 1 < len(lines_list): _fill_solar_hrs(lines_list[i+1])

        elif 'Non Solar hrs' in line:
            if not _fill_non_solar_hrs(line):
                if i > 0 and not _fill_non_solar_hrs(lines_list[i-1]):
                    if i + 1 < len(lines_list): _fill_non_solar_hrs(lines_list[i+1])

    # Daily max generation + penetration: single data row with 6+ numbers + 6 times
    # Pattern: wind_mw time  solar_mw time  vre_mw time  wind_pct time  solar_pct time  vre_pct time
    for line in text.split('\n'):
        n = _nums(line)
        t = _times(line)
        pcts = re.findall(r'(\d{1,2}\.\d{1,2})%', line)
        if len(n) >= 3 and len(t) >= 4 and len(pcts) >= 3:
            # Likely the daily max row
            large = [x for x in n if x > 1000]
            if len(large) >= 3:
                rec['daily_max_wind_mw']        = large[0]
                rec['daily_max_wind_time']       = _t(t[0])
                rec['daily_max_solar_mw']        = large[1]
                rec['daily_max_solar_time']      = _t(t[1])
                rec['daily_max_vre_mw']          = large[2]
                rec['daily_max_vre_time']        = _t(t[2])
                rec['daily_max_wind_pct']        = _f(pcts[0])
                rec['daily_max_wind_pct_time']   = _t(t[3]) if len(t) > 3 else None
                rec['daily_max_solar_pct']       = _f(pcts[1])
                rec['daily_max_solar_pct_time']  = _t(t[4]) if len(t) > 4 else None
                rec['daily_max_vre_pct']         = _f(pcts[2])
                rec['daily_max_vre_pct_time']    = _t(t[5]) if len(t) > 5 else None
                break

    # All-time records row: 3 large MW values + multiple dates + 3 pcts
    for line in text.split('\n'):
        n = _nums(line)
        pcts = re.findall(r'(\d{1,2}\.\d{1,2})%', line)
        dates = re.findall(r'\d{1,2}[-/][A-Za-z\d]+[-/][\d]+', line)
        large = [x for x in n if x > 1000]
        if len(large) >= 3 and len(pcts) >= 3 and len(dates) >= 3:
            rec['alltime_max_wind_mw']        = large[0]
            rec['alltime_max_wind_date']      = _d(dates[0])
            rec['alltime_max_solar_mw']       = large[1]
            rec['alltime_max_solar_date']     = _d(dates[1])
            rec['alltime_max_vre_mw']         = large[2]
            rec['alltime_max_vre_date']       = _d(dates[2])
            rec['alltime_max_wind_pct']       = _f(pcts[0])
            rec['alltime_max_wind_pct_date']  = _d(dates[3]) if len(dates) > 3 else None
            rec['alltime_max_solar_pct']      = _f(pcts[1])
            rec['alltime_max_solar_pct_date'] = _d(dates[4]) if len(dates) > 4 else None
            rec['alltime_max_vre_pct']        = _f(pcts[2])
            rec['alltime_max_vre_pct_date']   = _d(dates[5]) if len(dates) > 5 else None
            break

    return rec


# ── Section 2 & 3: Region profile ────────────────────────────────────────────

REGION_KEYS = {
    'NR': 'NR', 'WR': 'WR', 'SR': 'SR', 'ER': 'ER', 'NER': 'NER',
    'उत्तर': 'NR', 'पश्चिम': 'WR', 'पधिम': 'WR', 'दक्षिण': 'SR',
    'दधक्षण': 'SR', 'पूर्व': 'ER', 'पवू': 'ER',
    'पूर्वोत्तर': 'NER', 'पवू ो': 'NER', 'Total': 'Total',
}

def _region_code(line: str) -> str | None:
    for k, v in REGION_KEYS.items():
        if k in line:
            return v
    return None

def _parse_region_section(text: str, report_date: date, source: str) -> list[dict]:
    """
    Parse one region section (REMC or ISTS).
    Region name appears on the Solar row; Wind row immediately precedes it.
    """
    lines = text.split('\n')
    results = []
    current_region = None
    rec = {}
    pending_wind = None   # buffer wind line until region is known

    for line in lines:
        rc = _region_code(line)
        is_wind  = ('Wind' in line or 'पवन' in line) and 'Total' not in line and 'कुल' not in line
        is_solar = ('Solar' in line or 'सौर' in line) and 'Total' not in line and 'कुल' not in line
        is_total = 'Total' in line or ('कुल' in line and ('Wind' in line or 'Solar' in line or 'पवन' in line or 'सौर' in line))

        if is_wind and not is_solar:
            pending_wind = line   # buffer; region unknown yet

        elif is_solar and not is_wind:
            if rc and rc != current_region:
                # Save previous record
                if rec and current_region:
                    results.append(rec)
                current_region = rc
                rec = {'report_date': str(report_date), 'region': rc, 'source': source}
                # Apply buffered wind
                if pending_wind:
                    n = _nums(pending_wind); t = _times(pending_wind)
                    if len(n) >= 6:
                        rec['wind_installed_mw'] = n[0]
                        rec['wind_available_mw'] = n[1]
                        rec['wind_day_max_mw']   = n[2]
                        rec['wind_day_max_time'] = _t(t[0]) if t else None
                        rec['wind_day_min_mw']   = n[3]
                        rec['wind_day_min_time'] = _t(t[1]) if len(t) > 1 else None
                        rec['wind_schedule_mu']  = n[4]
                        rec['wind_actual_mu']    = n[5]
                        rec['wind_deviation_mu'] = n[6] if len(n) > 6 else None
                        rec['wind_cuf_pct']      = n[7] if len(n) > 7 else None
                    pending_wind = None

            if current_region:
                n = _nums(line); t = _times(line)
                if len(n) >= 4:
                    rec['solar_installed_mw'] = n[0]
                    rec['solar_available_mw'] = n[1]
                    rec['solar_day_max_mw']   = n[2]
                    rec['solar_day_max_time'] = _t(t[0]) if t else None
                    rec['solar_schedule_mu']  = n[3]
                    rec['solar_actual_mu']    = n[4] if len(n) > 4 else None
                    rec['solar_deviation_mu'] = n[5] if len(n) > 5 else None
                    rec['solar_cuf_pct']      = n[6] if len(n) > 6 else None

        elif is_total and current_region:
            n = _nums(line); t = _times(line)
            if len(n) >= 6:
                rec['total_installed_mw'] = n[0]
                rec['total_available_mw'] = n[1]
                rec['total_day_max_mw']   = n[2]
                rec['total_day_max_time'] = _t(t[0]) if t else None
                rec['total_day_min_mw']   = n[3]
                rec['total_day_min_time'] = _t(t[1]) if len(t) > 1 else None
                rec['total_schedule_mu']  = n[4]
                rec['total_actual_mu']    = n[5]
                rec['total_deviation_mu'] = n[6] if len(n) > 6 else None
                rec['total_cuf_pct']      = n[7] if len(n) > 7 else None

    if rec and current_region:
        results.append(rec)

    return results


# ── Section 4 & 5: State profiles ────────────────────────────────────────────

STATE_MAP = {
    'Rajasthan':      ('WR', 'remc_intrastate'),
    'Tamil Nadu':     ('SR', 'remc_intrastate'),
    'Madhya Pradesh': ('WR', 'remc_intrastate'),
    'Andhra Pradesh': ('SR', 'remc_intrastate'),
    'Telangana':      ('SR', 'remc_intrastate'),
    'Maharashtra':    ('WR', 'non_remc_regional'),
    'Karnataka':      ('SR', 'non_remc_regional'),
    'Gujarat':        ('WR', 'non_remc_regional'),
}

STATE_HINDI = {
    'राजस्थान': 'Rajasthan', 'र र्स्थ': 'Rajasthan', 'र र्स्थान': 'Rajasthan',
    'तमिलनाडु': 'Tamil Nadu', 'तधमलन': 'Tamil Nadu', 'तममलन': 'Tamil Nadu',
    'मध्य प्रदेश': 'Madhya Pradesh', 'मध्य': 'Madhya Pradesh',
    'आांध्र': 'Andhra Pradesh', 'आध्रां': 'Andhra Pradesh',
    'तेलगां': 'Telangana', 'तले गां': 'Telangana', 'तेलंग': 'Telangana',
    'मह र ष्ट्': 'Maharashtra', 'महाराष्ट्': 'Maharashtra',
    'कन िटक': 'Karnataka', 'कर्नाटक': 'Karnataka',
    'गर्ु र त': 'Gujarat', 'गुर्र त': 'Gujarat', 'गुजरात': 'Gujarat',
}

def _detect_state(line: str) -> str | None:
    for eng in STATE_MAP:
        if eng in line:
            return eng
    for hin, eng in STATE_HINDI.items():
        if hin in line:
            return eng
    return None

def _parse_state_profiles(full_text: str, report_date: date) -> list[dict]:
    sec4_start = full_text.find('REMC Monitored Intra')
    if sec4_start == -1:
        sec4_start = full_text.find('Intra State Profile')
    sec6_start = full_text.find('Non REMC ISTS')
    if sec6_start == -1:
        sec6_start = len(full_text)

    text = full_text[sec4_start:sec6_start] if sec4_start != -1 else ''
    lines = text.split('\n')

    results = []
    current_state = None
    rec = {}
    pending_wind = None

    for line in lines:
        state = _detect_state(line)
        is_wind  = ('Wind' in line or 'पवन' in line) and 'Total' not in line and 'कुल' not in line
        is_solar = ('Solar' in line or 'सौर' in line) and 'Total' not in line and 'कुल' not in line
        is_total = 'Total' in line or ('कुल' in line and ('Wind' in line or 'Solar' in line or 'पवन' in line or 'सौर' in line))

        if is_wind and not is_solar:
            pending_wind = line

        elif is_solar:
            if state and state != current_state:
                if rec and current_state:
                    results.append(rec)
                current_state = state
                region, section = STATE_MAP.get(state, (None, 'remc_intrastate'))
                rec = {
                    'report_date': str(report_date),
                    'state':   current_state,
                    'region':  region,
                    'section': section,
                }
                if pending_wind:
                    n = _nums(pending_wind); t = _times(pending_wind)
                    if len(n) >= 2:
                        rec['wind_installed_mw'] = n[0]
                        rec['wind_available_mw'] = n[1]
                        rec['wind_day_max_mw']   = n[2] if len(n) > 2 else None
                        rec['wind_day_max_time'] = _t(t[0]) if t else None
                        rec['wind_schedule_mu']  = n[3] if len(n) > 3 else None
                        rec['wind_actual_mu']    = n[4] if len(n) > 4 else None
                        rec['wind_deviation_mu'] = n[5] if len(n) > 5 else None
                        rec['wind_cuf_pct']      = n[6] if len(n) > 6 else None
                    pending_wind = None

            if current_state:
                n = _nums(line); t = _times(line)
                if len(n) >= 2:
                    rec['solar_installed_mw'] = n[0]
                    rec['solar_available_mw'] = n[1]
                    rec['solar_day_max_mw']   = n[2] if len(n) > 2 else None
                    rec['solar_day_max_time'] = _t(t[0]) if t else None
                    rec['solar_schedule_mu']  = n[3] if len(n) > 3 else None
                    rec['solar_actual_mu']    = n[4] if len(n) > 4 else None
                    rec['solar_deviation_mu'] = n[5] if len(n) > 5 else None
                    rec['solar_cuf_pct']      = n[6] if len(n) > 6 else None

        elif is_total and current_state:
            n = _nums(line); t = _times(line)
            if len(n) >= 4:
                rec['total_installed_mw'] = n[0]
                rec['total_available_mw'] = n[1]
                rec['total_day_max_mw']   = n[2]
                rec['total_day_max_time'] = _t(t[0]) if t else None
                rec['total_schedule_mu']  = n[3] if len(n) > 3 else None
                rec['total_actual_mu']    = n[4] if len(n) > 4 else None
                rec['total_deviation_mu'] = n[5] if len(n) > 5 else None
                rec['total_cuf_pct']      = n[6] if len(n) > 6 else None

    if rec and current_state:
        results.append(rec)

    # Deduplicate — keep first occurrence of each state
    seen = set()
    unique = []
    for r in results:
        key = (r['report_date'], r['state'], r.get('section'))
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


# ── Main parse function ───────────────────────────────────────────────────────

def parse_vre_report(pdf_path: str | Path) -> dict:
    """
    Parse a single NLDC VRE/REMC PDF report.

    Returns:
        {
            'report_date': 'YYYY-MM-DD',
            'daily_summary': {...},
            'region_profile': [...],
            'state_profile': [...]
        }
    """
    pdf_path = Path(pdf_path)
    pages = _extract_pages(pdf_path)
    full_text = '\n'.join(pages)

    # Always prefer "Report for" date from inside PDF (actual data date)
    # Filename date is the download/publish date, not the data date
    report_date = _date_from_text(full_text) or _date_from_filename(pdf_path)

    # Section 1
    daily = _parse_daily_summary(pages[0], report_date)

    # Split text into sections
    sec2_start = full_text.find('REMC Monitored Profile')
    sec3_start = full_text.find('REMC Monitored ISTS')
    sec4_start = full_text.find('REMC Monitored Intra')
    if sec4_start == -1:
        sec4_start = full_text.find('Intra State Profile')

    sec2_text = full_text[sec2_start:sec3_start] if sec2_start != -1 and sec3_start != -1 else ''
    sec3_text = full_text[sec3_start:sec4_start] if sec3_start != -1 and sec4_start != -1 else ''

    region_remc = _parse_region_section(sec2_text, report_date, 'remc')
    region_ists = _parse_region_section(sec3_text, report_date, 'ists')
    state_profiles = _parse_state_profiles(full_text, report_date)

    return {
        'report_date':    str(report_date),
        'daily_summary':  daily,
        'region_profile': region_remc + region_ists,
        'state_profile':  state_profiles,
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python nldc_vre_parser.py <pdf_path> [--json]")
        sys.exit(1)

    result = parse_vre_report(sys.argv[1])

    if '--json' in sys.argv:
        print(json.dumps(result, indent=2, default=str))
        sys.exit(0)

    ds = result['daily_summary']
    print(f"\n{'='*62}")
    print(f"  NLDC VRE Report  |  {result['report_date']}")
    print(f"{'='*62}")

    print(f"\n── Section 1: All India VRE ──")
    print(f"  Solar hrs demand   : {ds.get('solar_hrs_max_demand_mw'):>9,.0f} MW  @ {ds.get('solar_hrs_max_demand_time')}")
    print(f"  Solar hrs VRE      : {ds.get('solar_hrs_vre_pct'):>7.2f}%  (Wind {ds.get('solar_hrs_wind_pct')}% + Solar {ds.get('solar_hrs_solar_pct')}%)")
    print(f"  Daily max VRE MW   : {ds.get('daily_max_vre_mw'):>9,.0f} MW  @ {ds.get('daily_max_vre_time')}")
    print(f"  Daily max VRE %    : {ds.get('daily_max_vre_pct'):>7.2f}%  @ {ds.get('daily_max_vre_pct_time')}")
    print(f"  All-time max VRE   : {ds.get('alltime_max_vre_mw'):>9,.0f} MW  |  {ds.get('alltime_max_vre_pct')}%  on {ds.get('alltime_max_vre_date')}")

    print(f"\n── Section 2: Region Profile (REMC) ──")
    print(f"  {'Region':<8} {'Wind MU':>9} {'Solar MU':>10} {'Total MU':>10} {'CUF%':>7}")
    print(f"  {'-'*46}")
    for r in result['region_profile']:
        if r['source'] == 'remc':
            print(f"  {r['region']:<8} {r.get('wind_actual_mu') or 0:>9.2f} "
                  f"{r.get('solar_actual_mu') or 0:>10.2f} "
                  f"{r.get('total_actual_mu') or 0:>10.2f} "
                  f"{r.get('total_cuf_pct') or 0:>7.2f}%")

    print(f"\n── Section 4: State Profile ──")
    print(f"  {'State':<22} {'Solar MU':>10} {'Wind MU':>9} {'Solar CUF':>10}")
    print(f"  {'-'*53}")
    for s in result['state_profile']:
        print(f"  {s['state']:<22} {s.get('solar_actual_mu') or 0:>10.2f} "
              f"{s.get('wind_actual_mu') or 0:>9.2f} "
              f"{s.get('solar_cuf_pct') or 0:>9.2f}%")

    print(f"\n  Region rows : {len(result['region_profile'])}")
    print(f"  State rows  : {len(result['state_profile'])}")
