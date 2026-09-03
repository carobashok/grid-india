"""
nldc_parser.py
NLDC Daily PSP Report — PDF Parser
Python 3.12 · pdfplumber

Handles two known layouts:
  Apr 2026 format  — demand/max-demand values on next line, 12-col SCADA
  Aug 2026 format  — demand/max-demand values on same line, 15-col SCADA
"""

import re
import pdfplumber
from datetime import date, datetime
from pathlib import Path


# ── type helpers ──────────────────────────────────────────────

def sf(v, d=None):
    try: return float(str(v).strip().replace(',', ''))
    except: return d

def si(v, d=None):
    try: return int(str(v).strip().replace(',', ''))
    except: return d

def st(v):
    try:
        v = str(v).strip()
        if ':' in v:
            h, m = v.split(':')[:2]
            return f"{int(h):02d}:{int(m):02d}:00"
    except: pass
    return None


# ── summary parser ────────────────────────────────────────────

def parse_summary(text, report_date):
    s = {'report_date': report_date.isoformat()}
    lines = text.split('\n')

    def nums_in(ln):
        return re.findall(r'[\d.]+', ln)

    def ints_in(ln):
        return re.findall(r'\d+', ln)

    for i, ln in enumerate(lines):

        # ── Section A ────────────────────────────────────────

        # Evening peak demand — may be on same line (Aug) or next line (Apr)
        if 'Demand Met during Evening Peak' in ln or \
           'Demand Met (MW) during Evening Peak' in ln:
            n = ints_in(ln)
            if len(n) >= 6:
                # Same-line format (Aug)
                s['nr_peak_mw']=int(n[-6]); s['wr_peak_mw']=int(n[-5])
                s['sr_peak_mw']=int(n[-4]); s['er_peak_mw']=int(n[-3])
                s['ner_peak_mw']=int(n[-2]); s['all_peak_mw']=int(n[-1])
            else:
                # Next-line format (Apr) — look ahead up to 3 lines
                for j in range(i+1, min(i+4, len(lines))):
                    n2 = ints_in(lines[j])
                    if len(n2) >= 6:
                        s['nr_peak_mw']=int(n2[-6]); s['wr_peak_mw']=int(n2[-5])
                        s['sr_peak_mw']=int(n2[-4]); s['er_peak_mw']=int(n2[-3])
                        s['ner_peak_mw']=int(n2[-2]); s['all_peak_mw']=int(n2[-1])
                        break

        # Peak / Evening shortage
        if 'Peak Shortage' in ln or \
           ('Shoratge' in ln and 'Evening Peak' in ln) or \
           ('Shortage' in ln and 'Evening Peak' in ln):
            n = ints_in(ln)
            if len(n) >= 6:
                s['nr_shortage_mw']=int(n[-6]); s['wr_shortage_mw']=int(n[-5])
                s['sr_shortage_mw']=int(n[-4]); s['er_shortage_mw']=int(n[-3])
                s['ner_shortage_mw']=int(n[-2]); s['all_shortage_mw']=int(n[-1])

        if ln.strip().startswith('Energy Met (MU)'):
            n = nums_in(ln)
            if len(n) >= 6:
                s['nr_energy_mu']=float(n[-6]); s['wr_energy_mu']=float(n[-5])
                s['sr_energy_mu']=float(n[-4]); s['er_energy_mu']=float(n[-3])
                s['ner_energy_mu']=float(n[-2]); s['all_energy_mu']=float(n[-1])

        if ln.strip().startswith('Hydro Gen (MU)'):
            n = nums_in(ln)
            if len(n) >= 6:
                s['hydro_nr_mu']=float(n[-6]); s['hydro_wr_mu']=float(n[-5])
                s['hydro_sr_mu']=float(n[-4]); s['hydro_er_mu']=float(n[-3])
                s['hydro_ner_mu']=float(n[-2]); s['hydro_mu']=float(n[-1])

        if ln.strip().startswith('Wind Gen (MU)'):
            n = nums_in(ln)
            if n: s['wind_mu'] = float(n[-1])

        if ln.strip().startswith('Solar Gen (MU)'):
            n = nums_in(ln)
            if len(n) >= 6:
                s['solar_nr_mu']=float(n[-6]); s['solar_wr_mu']=float(n[-5])
                s['solar_sr_mu']=float(n[-4]); s['solar_er_mu']=float(n[-3])
                s['solar_ner_mu']=float(n[-2]); s['solar_mu']=float(n[-1])

        if ln.strip().startswith('Energy Shortage (MU)'):
            n = nums_in(ln)
            if n: s['all_energy_shortage_mu'] = float(n[-1])

        # Max demand during day — same line (Aug) or next line (Apr)
        if 'Maximum Demand Met During the Day' in ln:
            n = re.findall(r'\d{4,6}', ln)
            if len(n) >= 6:
                s['nr_max_mw']=int(n[-6]); s['wr_max_mw']=int(n[-5])
                s['sr_max_mw']=int(n[-4]); s['er_max_mw']=int(n[-3])
                s['ner_max_mw']=int(n[-2]); s['max_demand_mw']=int(n[-1])
            else:
                for j in range(i+1, min(i+4, len(lines))):
                    n2 = re.findall(r'\d{4,6}', lines[j])
                    if len(n2) >= 6:
                        s['nr_max_mw']=int(n2[-6]); s['wr_max_mw']=int(n2[-5])
                        s['sr_max_mw']=int(n2[-4]); s['er_max_mw']=int(n2[-3])
                        s['ner_max_mw']=int(n2[-2]); s['max_demand_mw']=int(n2[-1])
                        break

        if ln.strip().startswith('Time Of Maximum Demand Met'):
            t = re.findall(r'\d{1,2}:\d{2}', ln)
            if t: s['max_demand_time'] = st(t[-1])

        # ── Section B: Frequency ─────────────────────────────
        if ln.strip().startswith('All India'):
            n = nums_in(ln)
            if len(n) >= 7:
                s['freq_fvi']        = float(n[0])
                s['freq_below_497']  = float(n[1])
                s['freq_497_498']    = float(n[2])
                s['freq_498_499']    = float(n[3])
                s['freq_band_pct']   = float(n[5])
                s['freq_above_5005'] = float(n[6])

        # ── Section F: Outage ────────────────────────────────
        if ln.strip().startswith('Central Sector'):
            n = ints_in(ln)
            if len(n) >= 7: s['central_outage_mw'] = int(n[6])
        if ln.strip().startswith('State Sector'):
            n = ints_in(ln)
            if len(n) >= 7: s['state_outage_mw'] = int(n[6])
        if ln.strip().startswith('Total') and re.search(r'\d{4,}', ln):
            n = ints_in(ln)
            if len(n) >= 7: s['total_outage_mw'] = int(n[6])

        # ── Section G: Sourcewise generation ─────────────────
        if re.match(r'^Coal\b', ln.strip()):
            n = nums_in(ln)
            if len(n) >= 7: s['coal_mu'] = float(n[5])
        if ln.strip().startswith('Lignite'):
            n = nums_in(ln)
            if len(n) >= 7: s['lignite_mu'] = float(n[5])
        if re.match(r'^Hydro\b', ln.strip()) and 'Gen' not in ln:
            n = nums_in(ln)
            if len(n) >= 7: s['hydro_gen_mu'] = float(n[5])
        if ln.strip().startswith('Nuclear'):
            n = nums_in(ln)
            if len(n) >= 7: s['nuclear_mu'] = float(n[5])
        if ln.strip().startswith('Gas'):
            n = nums_in(ln)
            if len(n) >= 7: s['gas_mu'] = float(n[5])
        if ln.strip().startswith('RES (Wind'):
            n = nums_in(ln)
            if len(n) >= 7: s['res_mu'] = float(n[5])
        if re.match(r'^Total\b', ln.strip()) and 'generation' not in ln.lower():
            n = nums_in(ln)
            if len(n) >= 7: s['total_gen_mu'] = float(n[5])

        if 'Share of RES in total generation' in ln:
            n = nums_in(ln)
            if n: s['res_share_pct'] = float(n[-1])
        if 'Share of Non-fossil' in ln:
            # May continue on next line in some formats
            full = ln
            if not any(c.isdigit() for c in ln) and i+1 < len(lines):
                full = ln + ' ' + lines[i+1]
            n = nums_in(full)
            if n: s['non_fossil_share_pct'] = float(n[-1])

        # ── Section H + I ─────────────────────────────────────
        if 'Based on Regional Max Demands' in ln:
            n = nums_in(ln)
            if n: s['diversity_factor_regional'] = float(n[0])

        if 'Based on State Max Demands' in ln:
            n = nums_in(ln)
            t = re.findall(r'\d{1,2}:\d{2}', ln)
            if n:
                s['diversity_factor_state'] = float(n[0])
                # Aug format: solar hr on same line
                if len(n) >= 3:
                    s['solar_hr_peak_mw']     = si(n[1])
                    s['solar_hr_shortage_mw']  = si(n[3]) if len(n) >= 4 else 0
            if t: s['solar_hr_peak_time'] = st(t[0])

        # Solar hr — Apr format: separate line
        if re.match(r'^\s*Solar hr\b', ln) and 'Based' not in ln:
            n = nums_in(ln)
            t = re.findall(r'\d{1,2}:\d{2}', ln)
            if n:
                s['solar_hr_peak_mw']    = si(n[0])
                s['solar_hr_shortage_mw'] = si(n[2]) if len(n) >= 3 else 0
            if t: s['solar_hr_peak_time'] = st(t[0])

        # Non-Solar hr — both formats
        if re.match(r'^\s*Non-Solar hr|^\s*Non Solar hr', ln):
            n = nums_in(ln)
            t = re.findall(r'\d{1,2}:\d{2}', ln)
            if n:
                s['non_solar_peak_mw']     = si(n[0])
                s['non_solar_shortage_mw']  = si(n[2]) if len(n) >= 3 else 0
            if t: s['non_solar_peak_time'] = st(t[0])

    return s


# ── SCADA parser — handles 12-col (Apr) and 15-col (Aug) ─────

def parse_scada(text, report_date):
    """
    Returns list of dicts. Handles two column formats:

    Apr 2026 — 12 cols:
      TIME FREQ DEMAND NUCLEAR WIND SOLAR HYDRO GAS THERMAL NET_DEMAND TOTAL TRANSNATIONAL

    Aug 2026 — 15 cols:
      TIME FREQ DEMAND STORAGE_D NUCLEAR WIND SOLAR HYDRO GAS THERMAL STORAGE_DIS OTHERS NET_DEMAND TOTAL TRANSNATIONAL
    """
    rows = []

    # Try 15-column pattern first (Aug format)
    p15 = re.compile(
        r'(\d{1,2}:\d{2})\s+'
        r'([\d.]+)\s+'       # freq
        r'(\d{5,6})\s+'      # demand
        r'(\d+)\s+'          # storage_demand (B)
        r'(\d+)\s+'          # nuclear (C)
        r'(\d+)\s+'          # wind (D)
        r'(\d+)\s+'          # solar (E)
        r'(\d+)\s+'          # hydro (F)
        r'(\d+)\s+'          # gas (G)
        r'(\d+)\s+'          # thermal (H)
        r'(\d+)\s+'          # storage_discharge (I)
        r'(\d+)\s+'          # others (J)
        r'(\d+)\s+'          # net_demand (K)
        r'(\d+)\s+'          # total_gen (L)
        r'(-?\d+)'           # transnational (M)
    )

    # 12-column pattern (Apr format)
    p12 = re.compile(
        r'(\d{1,2}:\d{2})\s+'
        r'([\d.]+)\s+'       # freq
        r'(\d{5,6})\s+'      # demand
        r'(\d+)\s+'          # nuclear
        r'(\d+)\s+'          # wind
        r'(\d+)\s+'          # solar
        r'(\d+)\s+'          # hydro
        r'(\d+)\s+'          # gas
        r'(\d+)\s+'          # thermal
        r'(\d+)\s+'          # net_demand
        r'(\d+)\s+'          # total_gen
        r'(-?\d+)'           # transnational
    )

    # Try 15-col first
    matches15 = list(p15.finditer(text))
    if len(matches15) >= 90:
        for m in matches15:
            rows.append({
                'report_date':          report_date.isoformat(),
                'time_block':           st(m.group(1)),
                'frequency_hz':         float(m.group(2)),
                'demand_mw':            int(m.group(3)),
                'storage_demand_mw':    int(m.group(4)),
                'nuclear_mw':           int(m.group(5)),
                'wind_mw':              int(m.group(6)),
                'solar_mw':             int(m.group(7)),
                'hydro_mw':             int(m.group(8)),
                'gas_mw':               int(m.group(9)),
                'thermal_mw':           int(m.group(10)),
                'storage_discharge_mw': int(m.group(11)),
                'others_mw':            int(m.group(12)),
                'net_demand_mw':        int(m.group(13)),
                'total_gen_mw':         int(m.group(14)),
                'transnational_mw':     int(m.group(15)),
            })
        return rows

    # Fall back to 12-col
    matches12 = list(p12.finditer(text))
    for m in matches12:
        rows.append({
            'report_date':          report_date.isoformat(),
            'time_block':           st(m.group(1)),
            'frequency_hz':         float(m.group(2)),
            'demand_mw':            int(m.group(3)),
            'storage_demand_mw':    None,          # not in Apr format
            'nuclear_mw':           int(m.group(4)),
            'wind_mw':              int(m.group(5)),
            'solar_mw':             int(m.group(6)),
            'hydro_mw':             int(m.group(7)),
            'gas_mw':               int(m.group(8)),
            'thermal_mw':           int(m.group(9)),
            'storage_discharge_mw': None,          # not in Apr format
            'others_mw':            None,
            'net_demand_mw':        int(m.group(10)),
            'total_gen_mw':         int(m.group(11)),
            'transnational_mw':     int(m.group(12)),
        })
    return rows


# ── state parser ──────────────────────────────────────────────

REGION_MAP = {
    'Punjab':'NR','Haryana':'NR','Rajasthan':'NR','Delhi':'NR',
    'Uttar Pradesh':'NR','Uttarakhand':'NR','Himachal Pradesh':'NR',
    'J&K+Ladakh':'NR','Chandigarh':'NR','Railways NR':'NR','Bulk NR':'NR',
    'Chhattisgarh':'WR','Gujarat':'WR','Madhya Pradesh':'WR',
    'Maharashtra':'WR','Goa':'WR','DNHDDPDCL':'WR',
    'AMNSIL':'WR','BALCO':'WR','RIL Jamnagar':'WR',
    'Andhra Pradesh':'SR','Telangana':'SR','Karnataka':'SR',
    'Kerala':'SR','Tamil Nadu':'SR','Puducherry':'SR',
    'Bihar':'ER','DVC':'ER','Jharkhand':'ER','Odisha':'ER',
    'West Bengal':'ER','Sikkim':'ER','Railways ER':'ER',
    'Arunachal Pradesh':'NER','Assam':'NER','Manipur':'NER',
    'Meghalaya':'NER','Mizoram':'NER','Nagaland':'NER','Tripura':'NER',
}

RAW_TO_CLEAN = {
    'Punjab':'Punjab','Haryana':'Haryana','Rajasthan':'Rajasthan',
    'Delhi':'Delhi','UP':'Uttar Pradesh','Uttarakhand':'Uttarakhand',
    'HP':'Himachal Pradesh','J&K(UT) & Ladakh(UT)':'J&K+Ladakh',
    'Chandigarh':'Chandigarh','Railways_NR ISTS':'Railways NR',
    'Bulk Consumer_NR ISTS':'Bulk NR','Chhattisgarh':'Chhattisgarh',
    'Gujarat':'Gujarat','MP':'Madhya Pradesh','Maharashtra':'Maharashtra',
    'Goa':'Goa','DNHDDPDCL':'DNHDDPDCL','AMNSIL':'AMNSIL',
    'BALCO':'BALCO','RIL JAMNAGAR':'RIL Jamnagar',
    'Andhra Pradesh':'Andhra Pradesh','Telangana':'Telangana',
    'Karnataka':'Karnataka','Kerala':'Kerala','Tamil Nadu':'Tamil Nadu',
    'Puducherry':'Puducherry','Bihar':'Bihar','DVC':'DVC',
    'Jharkhand':'Jharkhand','Odisha':'Odisha','West Bengal':'West Bengal',
    'Sikkim':'Sikkim','Railways_ER ISTS':'Railways ER',
    'Arunachal Pradesh':'Arunachal Pradesh','Assam':'Assam',
    'Manipur':'Manipur','Meghalaya':'Meghalaya','Mizoram':'Mizoram',
    'Nagaland':'Nagaland','Tripura':'Tripura',
}

def parse_states(text, report_date):
    m = re.search(
        r'C\. Power Supply Position in States(.*?)D\. Transnational',
        text, re.DOTALL
    )
    if not m:
        return []
    block = m.group(1)

    states = []
    seen = set()
    pattern = re.compile(
        r'(?:NR|WR|SR|ER|NER)?\s*'
        r'(' + '|'.join(re.escape(k) for k in sorted(RAW_TO_CLEAN, key=len, reverse=True)) + r')'
        r'\s+(\d+)\s+(\d+)\s+([\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?\d+)/\s*(-?\d+)\s+([\d.]+)'
    )
    for m in pattern.finditer(block):
        raw   = m.group(1).strip()
        clean = RAW_TO_CLEAN.get(raw, raw)
        if clean in seen:
            continue
        seen.add(clean)
        states.append({
            'report_date':        report_date.isoformat(),
            'state':              clean,
            'region':             REGION_MAP.get(clean, 'Unknown'),
            'peak_demand_mw':     si(m.group(2)),
            'shortage_peak_mw':   si(m.group(3)),
            'energy_met_mu':      sf(m.group(4)),
            'drawal_schedule_mu': sf(m.group(5)),
            'od_ud_mu':           sf(m.group(6)),
            'max_od_mw':          si(m.group(7)),
            'max_ud_mw':          si(m.group(8)),
            'energy_shortage_mu': sf(m.group(9)),
        })
    return states


# ── master parser ─────────────────────────────────────────────

def parse_nldc_pdf(pdf_path, report_date=None):
    """
    Parse a single NLDC Daily PSP PDF.
    Handles Apr 2026 and Aug 2026 formats automatically.

    Args:
        pdf_path:     str or Path
        report_date:  date for the DATA date (day before report date)
                      If None, inferred from filename YYYY-MM-DD_NLDC_PSP.pdf

    Returns:
        { summary, scada, states, meta }
    """
    pdf_path = Path(pdf_path)

    if report_date is None:
        stem = pdf_path.stem

        # Format 1: YYYY-MM-DD  e.g. 2026-04-01_NLDC_PSP
        m = re.search(r'(\d{4})-(\d{2})-(\d{2})', stem)
        if m:
            report_date = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))

        # Format 2: DD.MM.YY  e.g. 09.04.26_NLDC_PSP_754
        if report_date is None:
            m = re.search(r'(\d{2})\.(\d{2})\.(\d{2})', stem)
            if m:
                dd, mm, yy = int(m.group(1)), int(m.group(2)), int(m.group(3))
                report_date = date(2000 + yy, mm, dd)

        # Format 3: DD_MM_YY  e.g. 21_08_26_NLDC_PSP_736
        if report_date is None:
            m = re.match(r'(\d{2})_(\d{2})_(\d{2})', stem)
            if m:
                dd, mm, yy = int(m.group(1)), int(m.group(2)), int(m.group(3))
                report_date = date(2000 + yy, mm, dd)

        if report_date is None:
            raise ValueError(
                f"Cannot infer date from: {pdf_path.name}\n"
                "Supported formats: YYYY-MM-DD_..., DD.MM.YY_..., DD_MM_YY_..."
            )

    with pdfplumber.open(pdf_path) as pdf:
        n_pages = len(pdf.pages)
        pages   = {i+1: (p.extract_text() or '') for i, p in enumerate(pdf.pages)}

    summary_pnum = scada_pnum = None
    for pnum, text in pages.items():
        if 'Power Supply Position at All India' in text:
            summary_pnum = pnum
        if '15 Min (INSTANTANEOUS)' in text and 'SCADA' in text:
            scada_pnum = pnum

    if summary_pnum is None:
        raise ValueError(f"Summary page not found in {pdf_path.name}")
    if scada_pnum is None:
        raise ValueError(f"SCADA page not found in {pdf_path.name}")

    summary = parse_summary(pages[summary_pnum], report_date)
    scada   = parse_scada(pages[scada_pnum], report_date)
    states  = parse_states(pages[summary_pnum], report_date)

    return {
        'summary': summary,
        'scada':   scada,
        'states':  states,
        'meta': {
            'source_file':    pdf_path.name,
            'pages':          n_pages,
            'parse_date':     datetime.now().isoformat(),
            'data_date':      report_date.isoformat(),
            'scada_rows':     len(scada),
            'state_rows':     len(states),
            'summary_fields': len(summary),
            'scada_format':   '15col' if any(
                r.get('storage_demand_mw') is not None for r in scada
            ) else '12col',
        }
    }
