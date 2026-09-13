"""
nldc_viewer.py  v2
NLDC Power Grid Data Viewer — Streamlit App
Run: streamlit run nldc_viewer.py

Pages:
  1. Trend Dashboard    — All India daily trend
  2. Regional Trendlines — Region-wise energy/demand/shortage over time
  3. Duck Curve          — 15-min SCADA for selected date
  4. State Analysis      — State-level demand and grid discipline
"""

import os, colorsys
from pathlib import Path
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

st.set_page_config(page_title="NLDC Grid Analytics", page_icon="⚡",
                   layout="wide", initial_sidebar_state="expanded")

# ── env ───────────────────────────────────────────────────────
def _load_env():
    try:
        from dotenv import load_dotenv
        for fname in ['.env', '.env.local']:
            for base in [Path(__file__).parent, Path.cwd()]:
                f = base / fname
                if f.exists():
                    load_dotenv(f); return
    except ImportError: pass
_load_env()

# ── supabase ──────────────────────────────────────────────────
@st.cache_resource
def get_client():
    from supabase import create_client
    # Streamlit Cloud — read from [supabase] secrets section
    try:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
    except Exception:
        # Local — fall back to .env
        url = os.environ.get('SUPABASE_URL', '').strip().strip('"')
        key = os.environ.get('SUPABASE_SERVICE_KEY', '').strip().strip('"')
    if not url or not key:
        st.error("❌ Supabase credentials not found in secrets or .env"); st.stop()
    return create_client(url, key)

S = 'nldc'

@st.cache_data(ttl=300)
def load_summary():
    df = pd.DataFrame(get_client().schema(S).table('daily_summary')
                      .select('*').order('report_date').execute().data)
    if not df.empty: df['report_date'] = pd.to_datetime(df['report_date'])
    return df

@st.cache_data(ttl=300)
def load_scada(d):
    df = pd.DataFrame(get_client().schema(S).table('scada_15min')
                      .select('*').eq('report_date',d).order('time_block').execute().data)
    if not df.empty: df['time_label'] = df['time_block'].str[:5]
    return df

@st.cache_data(ttl=300)
def load_states(d):
    df = pd.DataFrame(get_client().schema(S).table('state_daily')
                      .select('*').eq('report_date',d).order('region,state').execute().data)
    if not df.empty:
        df = df[~df['state'].isin(NON_STATES)].reset_index(drop=True)
    return df

@st.cache_data(ttl=300)
def load_state_trend(state):
    df = pd.DataFrame(get_client().schema(S).table('state_daily')
                      .select('report_date,state,region,peak_demand_mw,energy_met_mu,od_ud_mu')
                      .eq('state',state).order('report_date').execute().data)
    if not df.empty: df['report_date'] = pd.to_datetime(df['report_date'])
    return df

@st.cache_data(ttl=300)
def load_all_states():
    df = pd.DataFrame(get_client().schema(S).table('state_daily')
                      .select('report_date,state,region,peak_demand_mw,energy_met_mu,od_ud_mu,energy_shortage_mu')
                      .order('report_date').execute().data)
    if not df.empty:
        df['report_date'] = pd.to_datetime(df['report_date'])
        # Exclude non-geographic rows (bulk industrials, railways, utility corps)
        df = df[~df['state'].isin(NON_STATES)].reset_index(drop=True)
    return df

VS = 'nldc_vre'

@st.cache_data(ttl=300)
def load_vre_summary():
    df = pd.DataFrame(get_client().schema(VS).table('daily_summary')
                      .select('*').order('report_date').execute().data)
    if not df.empty: df['report_date'] = pd.to_datetime(df['report_date'])
    return df

@st.cache_data(ttl=300)
def load_vre_regions():
    df = pd.DataFrame(get_client().schema(VS).table('region_profile')
                      .select('*').eq('source','remc').order('report_date,region').execute().data)
    if not df.empty: df['report_date'] = pd.to_datetime(df['report_date'])
    return df

@st.cache_data(ttl=300)
def load_vre_states():
    df = pd.DataFrame(get_client().schema(VS).table('state_profile')
                      .select('*').order('report_date,state').execute().data)
    if not df.empty: df['report_date'] = pd.to_datetime(df['report_date'])
    return df

# ── constants ─────────────────────────────────────────────────
RC = {'NR':'#3b82f6','WR':'#f97316','SR':'#22c55e','ER':'#a855f7','NER':'#06b6d4'}
REGIONS = ['NR','WR','SR','ER','NER']
# Non-geographic rows in nldc.state_daily — bulk industrials, railways traction, utility corporations
NON_STATES = {'Bulk NR','Railways NR','Railways ER','AMNSIL','BALCO','DVC','RIL Jamnagar'}

def dl(h=300):
    return dict(height=h, margin=dict(l=0,r=0,t=20,b=0),
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                font=dict(color='#94a3b8'),
                xaxis=dict(gridcolor='#1e293b',color='#94a3b8'),
                yaxis=dict(gridcolor='#1e293b',color='#94a3b8'),
                legend=dict(bgcolor='rgba(0,0,0,0)',font=dict(color='#94a3b8')))

# ── sidebar ───────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚡ NLDC Grid Analytics")
    st.markdown("**CarobInsights** · Power Sector")
    st.divider()
    summary_df = load_summary()
    if summary_df.empty:
        st.error("No data yet. Run pipeline first."); st.stop()
    dates = summary_df['report_date'].dt.date.tolist()
    st.metric("Days Loaded", len(dates))
    st.metric("From", str(dates[0]))
    st.metric("To",   str(dates[-1]))
    st.divider()
    sel_date = st.date_input("Date for Detail View",
                              value=dates[-1], min_value=dates[0], max_value=dates[-1])
    page = st.radio("View",[
        "📈 Trend Dashboard",
        "🌏 Regional Trendlines",
        "🦆 Duck Curve",
        "🗺 State Analysis",
        "☀️ Renewable Energy",
        "⚡ Grid Real-time",
    ], label_visibility="collapsed")

# ══════════════════════════════════════════════════════════════
# P1 — TREND DASHBOARD
# ══════════════════════════════════════════════════════════════
if page == "📈 Trend Dashboard":
    st.title("📈 All India Grid — Daily Trend")
    st.caption(f"{dates[0]} → {dates[-1]}  ·  {len(dates)} days  ·  NLDC Daily PSP Reports")
    df = summary_df.copy()
    la = df.iloc[-1]

    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("Latest Peak",   f"{la.get('max_demand_mw',0)/1000:.1f} GW", delta=la['report_date'].strftime('%d %b'))
    c2.metric("Energy",        f"{la.get('all_energy_mu',0):,.0f} MU/day")
    c3.metric("Solar",         f"{la.get('solar_mu',0):.0f} MU", delta=f"{la.get('res_share_pct',0):.1f}% RES")
    c4.metric("Freq in Band",  f"{la.get('freq_band_pct',0):.1f}%")
    c5.metric("Outage",        f"{la.get('total_outage_mw',0)/1000:.1f} GW", delta_color="inverse", delta="offline")
    st.divider()

    # Daily Energy Met + Peak Demand combined
    st.subheader("Daily Energy Met (MU) with Peak Demand (GW)")
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df['report_date'], y=df['max_demand_mw']/1000,
        name='Peak Demand (GW)', mode='lines+markers',
        line=dict(color='#f97316', width=2), marker=dict(size=4),
        visible='legendonly',
        yaxis='y2',
        hovertemplate='%{x|%d %b}<br>Peak: %{y:.2f} GW<extra></extra>'))
    fig.add_trace(go.Scatter(
        x=df['report_date'], y=df['all_energy_mu'],
        name='Energy Met (MU)', mode='lines+markers',
        line=dict(color='#3b82f6', width=2), marker=dict(size=4),
        hovertemplate='%{x|%d %b}<br>Energy: %{y:,.0f} MU<extra></extra>'))
    if 'non_solar_shortage_mw' in df.columns:
        sh = df[df['non_solar_shortage_mw'].fillna(0) > 0]
        if not sh.empty:
            fig.add_trace(go.Scatter(
                x=sh['report_date'], y=sh['max_demand_mw']/1000,
                mode='markers', name='Shortage Day',
                marker=dict(color='#ef4444', size=9, symbol='x'),
                visible='legendonly',
                yaxis='y2'))
    lyt = dl(320)
    lyt['yaxis']['title'] = 'MU'
    lyt['yaxis2'] = dict(title='GW', side='right', overlaying='y',
                         gridcolor='rgba(0,0,0,0)', color='#f97316')
    lyt['legend']['orientation'] = 'h'
    fig.update_layout(**lyt)
    st.plotly_chart(fig, use_container_width=True)

    # ── Generation mix constants (shared by both charts) ────────
    gen_mix = [
        ('coal_mu',    '#78350f', 'Coal'),
        ('lignite_mu', '#92400e', 'Lignite'),
        ('nuclear_mu', '#a855f7', 'Nuclear'),
        ('gas_mu',     '#06b6d4', 'Gas'),
        ('hydro_mu',   '#22c55e', 'Hydro'),
        ('wind_mu',    '#5BA4CF', 'Wind'),
        ('solar_mu',   '#F5A623', 'Solar'),
    ]
    mix_cols = [c for c, _, _ in gen_mix if c in df.columns]

    # ── MU chart ──────────────────────────────────────────────
    st.subheader("Daily Generation Mix (MU)")
    mu_mode = st.radio("View", ["Stacked", "Unstacked"],
                        horizontal=True, key='mu_mode')
    f3 = go.Figure()
    for col, color, label in gen_mix:
        if col in df.columns:
            f3.add_trace(go.Scatter(
                x=df['report_date'], y=df[col],
                mode='lines', name=label,
                line=dict(color=color, width=1.5 if mu_mode=='Unstacked' else 0.5),
                stackgroup='one' if mu_mode=='Stacked' else None,
                hovertemplate=f'{label}: %{{y:,.0f}} MU<br>%{{x|%d %b}}<extra></extra>'))
    lf3 = dl(300); lf3['yaxis']['title'] = 'MU'; lf3['legend']['orientation'] = 'h'
    f3.update_layout(**lf3); st.plotly_chart(f3, use_container_width=True)

    # ── % Share chart ─────────────────────────────────────────
    st.subheader("Daily Generation Mix — % Share")
    pct_mode = st.radio("View", ["Stacked", "Unstacked"],
                         horizontal=True, key='pct_mode')
    df_mix = df[['report_date'] + mix_cols].copy()
    df_mix['total'] = df_mix[mix_cols].sum(axis=1)
    for col in mix_cols:
        df_mix[col + '_pct'] = (df_mix[col] / df_mix['total'] * 100).round(2)

    f4 = go.Figure()
    for col, color, label in gen_mix:
        if col in df.columns:
            f4.add_trace(go.Scatter(
                x=df_mix['report_date'], y=df_mix[col + '_pct'],
                mode='lines', name=label,
                line=dict(color=color, width=1.5 if pct_mode=='Unstacked' else 0.5),
                stackgroup='one' if pct_mode=='Stacked' else None,
                hovertemplate=f'{label}: %{{y:.1f}}%<br>%{{x|%d %b}}<extra></extra>'))
    lf4 = dl(300); lf4['yaxis']['title'] = '% Share'; lf4['legend']['orientation'] = 'h'
    if pct_mode == 'Stacked':
        lf4['yaxis']['range'] = [0, 100]
    f4.update_layout(**lf4); st.plotly_chart(f4, use_container_width=True)


    with st.expander("📋 Raw data table"):
        cols = [c for c in ['report_date','max_demand_mw','all_energy_mu','solar_mu',
                'wind_mu','hydro_mu','coal_mu','freq_band_pct',
                'total_outage_mw','non_solar_shortage_mw'] if c in df.columns]
        st.dataframe(df[cols].sort_values('report_date',ascending=False),
                     use_container_width=True,height=300)

# ══════════════════════════════════════════════════════════════
# P2 — REGIONAL TRENDLINES
# ══════════════════════════════════════════════════════════════
elif page == "🌏 Regional Trendlines":
    st.title("🌏 Region-wise Trendlines")
    st.caption(f"{dates[0]} → {dates[-1]}  ·  {len(dates)} days  ·  NR / WR / SR / ER / NER  ·  From nldc.state_daily")

    all_st = load_all_states()
    if all_st.empty:
        st.warning("No state data loaded yet."); st.stop()

    # Aggregate state → region × date
    reg_day = (all_st.groupby(['report_date','region'])
               .agg(total_energy_mu=('energy_met_mu','sum'),
                    peak_demand_mw=('peak_demand_mw','max'),
                    total_shortage_mu=('energy_shortage_mu','sum'),
                    od_ud_net_mu=('od_ud_mu','sum'))
               .reset_index())

    # Metric selector
    metric_map = {
        'Daily Energy Met (MU)':  'total_energy_mu',
        'Peak Demand Met (MW)':   'peak_demand_mw',
        'Energy Shortage (MU)':   'total_shortage_mu',
        'Net OD/UD (MU)':         'od_ud_net_mu',
    }
    c1,c2 = st.columns([2,3])
    with c1:
        sel_metric = st.selectbox("Metric", list(metric_map.keys()))
    with c2:
        sel_regions = st.multiselect("Regions", REGIONS, default=REGIONS)
    metric_col = metric_map[sel_metric]

    st.divider()

    # ── All regions overlaid ──────────────────────────────────
    st.subheader(f"{sel_metric} — All Regions Overlaid")
    fig_all = go.Figure()
    for region in sel_regions:
        rdf = reg_day[reg_day['region']==region].sort_values('report_date')
        if rdf.empty: continue
        fig_all.add_trace(go.Scatter(
            x=rdf['report_date'], y=rdf[metric_col],
            mode='lines+markers', name=region,
            line=dict(color=RC[region],width=2.5), marker=dict(size=5),
            hovertemplate=f'{region}  %{{x|%d %b}}<br>%{{y:,.1f}}<extra></extra>'))
    lyt = dl(380); lyt['yaxis']['title']=sel_metric
    lyt['legend']['orientation']='h'; lyt['legend']['yanchor']='bottom'; lyt['legend']['y']=1.02
    fig_all.update_layout(**lyt); st.plotly_chart(fig_all, use_container_width=True)

    # ── Small multiples ───────────────────────────────────────
    st.subheader(f"{sel_metric} — Region by Region")
    n = len(sel_regions)
    cols = st.columns(min(n,3))

    # Shared y-axis: compute max across all selected regions so charts are comparable
    shared_y_max = 0
    for region in sel_regions:
        rdf_tmp = reg_day[reg_day['region']==region]
        if not rdf_tmp.empty:
            shared_y_max = max(shared_y_max, rdf_tmp[metric_col].max())
    shared_y_max = shared_y_max * 1.08  # 8% headroom

    def _hex_to_rgba(hx: str, alpha: float = 0.13) -> str:
        h = hx.lstrip('#')
        r2,g2,b2 = int(h[0:2],16),int(h[2:4],16),int(h[4:6],16)
        return f'rgba({r2},{g2},{b2},{alpha})'

    for idx, region in enumerate(sel_regions):
        rdf = reg_day[reg_day['region']==region].sort_values('report_date')
        if rdf.empty: continue
        with cols[idx % min(n,3)]:
            latest = rdf[metric_col].iloc[-1]
            delta = ""
            if len(rdf)>=2:
                prev = rdf[metric_col].iloc[-2]
                if prev: delta = f"{(latest-prev)/prev*100:+.1f}% DoD"
            st.metric(f"{region} — {sel_metric.split('(')[0].strip()}", f"{latest:,.0f}", delta=delta)
            fr = go.Figure(go.Scatter(
                x=rdf['report_date'], y=rdf[metric_col],
                mode='lines', fill='tozeroy',
                fillcolor=_hex_to_rgba(RC[region]),
                line=dict(color=RC[region],width=2), showlegend=False,
                hovertemplate=f'%{{x|%d %b}}<br>%{{y:,.0f}}<extra></extra>'))
            lr = dl(180); lr['margin']=dict(l=0,r=0,t=5,b=0)
            lr['xaxis']['tickangle']=45; lr['xaxis']['nticks']=6; lr['showlegend']=False
            lr['yaxis']['range'] = [0, shared_y_max]
            fr.update_layout(**lr); st.plotly_chart(fr, use_container_width=True)

    # ── State breakdown ───────────────────────────────────────
    # metric_col uses aggregated names (total_energy_mu etc); map back to raw state_daily cols
    state_col_map = {
        'total_energy_mu':   'energy_met_mu',
        'peak_demand_mw':    'peak_demand_mw',
        'total_shortage_mu': 'energy_shortage_mu',
        'od_ud_net_mu':      'od_ud_mu',
    }
    state_col = state_col_map.get(metric_col, metric_col)

    st.divider()
    st.subheader("State Breakdown Within a Region")
    c1,c2 = st.columns([1,3])
    with c1:
        sel_region_detail = st.selectbox("Region", REGIONS)
    state_filt = all_st[all_st['region']==sel_region_detail].copy()

    if not state_filt.empty:
        # State trendlines
        fig_s = go.Figure()
        base_hue = {'NR':0.60,'WR':0.08,'SR':0.35,'ER':0.75,'NER':0.50}.get(sel_region_detail,0.5)
        for i,state in enumerate(sorted(state_filt['state'].unique())):
            sdf = state_filt[state_filt['state']==state].sort_values('report_date')
            r,g,b = colorsys.hsv_to_rgb((base_hue+i*0.09)%1.0, 0.55+i%3*0.12, 0.75+i%2*0.18)
            color = f'rgb({int(r*255)},{int(g*255)},{int(b*255)})'
            fig_s.add_trace(go.Scatter(
                x=sdf['report_date'], y=sdf[state_col],
                mode='lines', name=state, line=dict(color=color,width=1.8),
                hovertemplate=f'{state}  %{{x|%d %b}}<br>%{{y:,.1f}}<extra></extra>'))
        lyt_s = dl(380); lyt_s['yaxis']['title']=sel_metric
        lyt_s['legend']['orientation']='h'; lyt_s['legend']['yanchor']='bottom'
        lyt_s['legend']['y']=1.02; lyt_s['legend']['font']['size']=10
        fig_s.update_layout(**lyt_s); st.plotly_chart(fig_s, use_container_width=True)

        # Day table
        st.subheader(f"State Summary — {sel_date.strftime('%d %b %Y')}")
        day_st = state_filt[state_filt['report_date'].dt.date==sel_date][
            ['state','peak_demand_mw','energy_met_mu','od_ud_mu','energy_shortage_mu']].copy()
        if not day_st.empty:
            day_st.columns = ['State','Peak MW','Energy MU','OD/UD MU','Shortage MU']
            st.dataframe(day_st.sort_values('Energy MU',ascending=False),
                         use_container_width=True, hide_index=True)
        else:
            st.info(f"Select a loaded date for state detail.")

    with st.expander("📋 Regional aggregates table"):
        pivot = reg_day.pivot(index='report_date',columns='region',values=metric_col).reset_index()
        pivot['report_date'] = pivot['report_date'].dt.strftime('%Y-%m-%d')
        st.dataframe(pivot.sort_values('report_date',ascending=False),
                     use_container_width=True, height=300)

# ══════════════════════════════════════════════════════════════
# P3 — DUCK CURVE
# ══════════════════════════════════════════════════════════════
elif page == "🦆 Duck Curve":
    st.title(f"🦆 Duck Curve — {sel_date.strftime('%d %b %Y')}")
    scada = load_scada(str(sel_date))
    if scada.empty:
        st.warning(f"No SCADA data for {sel_date}."); st.stop()
    scada['net_demand'] = (scada['demand_mw']-scada['solar_mw'].fillna(0)).astype(int)

    day_row = summary_df[summary_df['report_date'].dt.date==sel_date]
    if not day_row.empty:
        ds = day_row.iloc[0]
        c1,c2,c3,c4,c5 = st.columns(5)
        c1.metric("Peak Demand",   f"{ds.get('max_demand_mw',0)/1000:.1f} GW")
        c2.metric("Solar Peak",    f"{scada['solar_mw'].max()/1000:.1f} GW")
        c3.metric("Net Demand Min",f"{scada['net_demand'].min()/1000:.1f} GW")
        c4.metric("Freq Low",      f"{scada['frequency_hz'].min():.2f} Hz" if 'frequency_hz' in scada.columns else "—")
        shortage = int(ds.get('non_solar_shortage_mw') or 0)
        c5.metric("Non-Solar Shortage", f"{shortage:,} MW", delta_color="inverse" if shortage>0 else "off")
    st.divider()

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=scada['time_label'],y=scada['demand_mw']/1000,
        mode='lines',name='Gross Demand',line=dict(color='#94a3b8',width=1.5,dash='dot')))
    fig.add_trace(go.Scatter(x=scada['time_label'],y=scada['solar_mw']/1000,
        mode='lines',name='Solar',line=dict(color='#F5A623',width=2),
        fill='tozeroy',fillcolor='rgba(245,166,35,0.15)'))
    fig.add_trace(go.Scatter(x=scada['time_label'],y=scada['net_demand']/1000,
        mode='lines',name='Net Demand (Duck)',line=dict(color='#ef4444',width=2.5)))
    if 'frequency_hz' in scada.columns:
        low = scada.loc[scada['frequency_hz'].idxmin()]
        low_idx = scada.reset_index(drop=True).index[scada['frequency_hz'] == scada['frequency_hz'].min()][0]
        fig.add_vline(x=low_idx, line_dash='dash', line_color='#ef4444', opacity=0.5,
                      annotation_text=f"Freq low {low['frequency_hz']:.2f} Hz  ({low['time_label']})",
                      annotation_font_color='#ef4444')
    lyt = dl(380); lyt['yaxis']['title']='GW'; lyt['xaxis']['tickangle']=45; lyt['xaxis']['nticks']=25
    fig.update_layout(**lyt); st.plotly_chart(fig,use_container_width=True)

    st.subheader("Generation Mix — Stacked (GW)")
    f2 = go.Figure()
    for col,color,label in [('thermal_mw','#ef4444','Thermal'),('hydro_mw','#22c55e','Hydro'),
                              ('solar_mw','#F5A623','Solar'),('wind_mw','#5BA4CF','Wind'),
                              ('nuclear_mw','#1ABC9C','Nuclear'),('gas_mw','#9B59B6','Gas')]:
        if col in scada.columns and scada[col].notna().any():
            f2.add_trace(go.Scatter(x=scada['time_label'],y=scada[col].fillna(0)/1000,
                mode='lines',name=label,line=dict(color=color,width=0.5),stackgroup='gen'))
    lyt2 = dl(300); lyt2['yaxis']['title']='GW'; lyt2['xaxis']['tickangle']=45
    lyt2['xaxis']['nticks']=25; lyt2['legend']['orientation']='h'
    f2.update_layout(**lyt2); st.plotly_chart(f2,use_container_width=True)

    if 'frequency_hz' in scada.columns:
        st.subheader("Grid Frequency (Hz)")
        f3 = go.Figure(go.Scatter(x=scada['time_label'],y=scada['frequency_hz'],
            mode='lines',line=dict(color='#3b82f6',width=1.5)))
        f3.add_hline(y=49.9,line_dash='dash',line_color='#f59e0b')
        f3.add_hline(y=50.05,line_dash='dash',line_color='#f59e0b')
        lyt3 = dl(220); lyt3['yaxis']['range']=[49.5,50.3]; lyt3['yaxis']['title']='Hz'
        lyt3['showlegend']=False; lyt3['xaxis']['tickangle']=45
        f3.update_layout(**lyt3); st.plotly_chart(f3,use_container_width=True)

    with st.expander("📋 Raw SCADA data"):
        st.dataframe(scada,use_container_width=True,height=300)

# ══════════════════════════════════════════════════════════════
# P4 — STATE ANALYSIS
# ══════════════════════════════════════════════════════════════
elif page == "🗺 State Analysis":
    st.title(f"🗺 State Analysis — {sel_date.strftime('%d %b %Y')}")
    states = load_states(str(sel_date))
    if states.empty:
        st.warning(f"No state data for {sel_date}."); st.stop()

    rdf = states.groupby('region').agg(
        total_energy=('energy_met_mu','sum'),peak=('peak_demand_mw','max')
    ).reset_index().sort_values('total_energy',ascending=False)

    st.subheader("Regional Summary (MU)")
    rcols = st.columns(len(rdf))
    for i,(_,row) in enumerate(rdf.iterrows()):
        c = RC.get(row['region'],'#64748b')
        rcols[i].markdown(
            f"<div style='background:#0f172a;border-left:4px solid {c};"
            f"padding:12px;border-radius:8px;text-align:center'>"
            f"<div style='color:{c};font-weight:700;font-size:15px'>{row['region']}</div>"
            f"<div style='color:#e2e8f0;font-size:18px;font-weight:700'>{row['total_energy']:,.0f} MU</div>"
            f"<div style='color:#64748b;font-size:10px'>Peak {row['peak']:,} MW</div>"
            f"</div>", unsafe_allow_html=True)

    st.divider()
    c1,c2 = st.columns(2)
    with c1:
        st.subheader("Peak Demand by State (MW)")
        top = states.sort_values('peak_demand_mw',ascending=True).tail(20)
        fig = go.Figure(go.Bar(x=top['peak_demand_mw'],y=top['state'],orientation='h',
            marker_color=[RC.get(r,'#64748b') for r in top['region']],
            hovertemplate='%{y}<br>%{x:,} MW<extra></extra>'))
        lyt = dl(480); lyt['yaxis']['tickfont']=dict(size=10); lyt['showlegend']=False
        fig.update_layout(**lyt); st.plotly_chart(fig,use_container_width=True)

    with c2:
        st.subheader("Grid Discipline — OD/UD (MU)")
        od = states.sort_values('od_ud_mu',ascending=True)
        f2 = go.Figure(go.Bar(x=od['od_ud_mu'],y=od['state'],orientation='h',
            marker_color=od['od_ud_mu'].apply(
                lambda x:'#22c55e' if x<-50 else '#86efac' if x<0 else '#f59e0b' if x<50 else '#ef4444'),
            hovertemplate='%{y}<br>%{x:+.1f} MU<extra></extra>'))
        f2.add_vline(x=0,line_color='#475569')
        lyt2 = dl(480); lyt2['yaxis']['tickfont']=dict(size=10)
        lyt2['xaxis']['title']='← Underdrawal | Overdrawal →'; lyt2['showlegend']=False
        f2.update_layout(**lyt2); st.plotly_chart(f2,use_container_width=True)

    st.divider()
    st.subheader("State Trend Over Time")
    all_states_list = sorted(states['state'].tolist())
    idx = all_states_list.index('Maharashtra') if 'Maharashtra' in all_states_list else 0
    sel_state = st.selectbox("Select State",all_states_list,index=idx)
    trend = load_state_trend(sel_state)
    if not trend.empty:
        f3 = go.Figure()
        f3.add_trace(go.Scatter(x=trend['report_date'],y=trend['peak_demand_mw'],
            mode='lines+markers',name='Peak MW',line=dict(color='#3b82f6',width=2),yaxis='y1'))
        f3.add_trace(go.Bar(x=trend['report_date'],y=trend['energy_met_mu'],
            name='Energy MU',marker_color='rgba(245,166,35,0.4)',yaxis='y2'))
        lyt3 = dl(300)
        lyt3['yaxis']  = dict(gridcolor='#1e293b',color='#3b82f6',title='Peak MW',side='left')
        lyt3['yaxis2'] = dict(color='#F5A623',title='Energy MU',side='right',overlaying='y')
        f3.update_layout(**lyt3); st.plotly_chart(f3,use_container_width=True)

    with st.expander("📋 Full state table"):
        cols = [c for c in ['state','region','peak_demand_mw','energy_met_mu',
                             'energy_shortage_mu','drawal_schedule_mu','od_ud_mu'] if c in states.columns]
        st.dataframe(states[cols].sort_values('energy_met_mu',ascending=False),
                     use_container_width=True,height=400)

# ══════════════════════════════════════════════════════════════
# P5 — RENEWABLE ENERGY (VRE)
# ══════════════════════════════════════════════════════════════
elif page == "☀️ Renewable Energy":
    st.title("☀️ Renewable Energy — VRE Analytics")
    st.caption("Source: NLDC REMC Daily VRE Reports · Grid Controller of India Ltd")

    vre_sum = load_vre_summary()
    vre_reg = load_vre_regions()
    vre_st  = load_vre_states()

    if vre_sum.empty:
        st.warning("No VRE data loaded yet. Run nldc_vre_loader.py first."); st.stop()

    latest = vre_sum.iloc[-1]

    # ── KPI row ───────────────────────────────────────────────
    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("Days Loaded",      f"{len(vre_sum)}")
    c2.metric("Latest VRE %",     f"{latest.get('daily_max_vre_pct',0):.2f}%",
              delta=f"{latest.get('solar_hrs_vre_pct',0):.1f}% solar-hrs avg")
    c3.metric("Solar Peak",       f"{latest.get('daily_max_solar_mw',0)/1000:.1f} GW",
              delta=latest.get('daily_max_solar_time',''))
    c4.metric("Wind Peak",        f"{latest.get('daily_max_wind_mw',0)/1000:.1f} GW",
              delta=latest.get('daily_max_wind_time',''))
    c5.metric("All-time VRE%",    f"{latest.get('alltime_max_vre_pct',0):.2f}%",
              delta=str(latest.get('alltime_max_vre_date','')))
    st.divider()

    # ── VRE % trend ───────────────────────────────────────────
    st.subheader("Daily Max VRE Penetration % (Wind + Solar)")
    fig1 = go.Figure()
    fig1.add_trace(go.Scatter(
        x=vre_sum['report_date'], y=vre_sum['daily_max_vre_pct'],
        mode='lines+markers', name='VRE %',
        line=dict(color='#22c55e', width=2), marker=dict(size=4),
        hovertemplate='%{x|%d %b}<br>%{y:.2f}%<extra></extra>'))
    fig1.add_trace(go.Scatter(
        x=vre_sum['report_date'], y=vre_sum['solar_hrs_vre_pct'],
        mode='lines', name='Solar-hrs Avg VRE %',
        line=dict(color='#F5A623', width=1.5, dash='dot'),
        hovertemplate='%{x|%d %b}<br>%{y:.2f}%<extra></extra>'))
    # All-time record line
    if latest.get('alltime_max_vre_pct'):
        fig1.add_hline(y=latest['alltime_max_vre_pct'],
                       line_dash='dash', line_color='#ef4444', opacity=0.6,
                       annotation_text=f"All-time record: {latest['alltime_max_vre_pct']}%",
                       annotation_font_color='#ef4444')
    lyt1 = dl(300); lyt1['yaxis']['title'] = 'VRE %'
    fig1.update_layout(**lyt1); st.plotly_chart(fig1, use_container_width=True)

    # ── Solar vs Wind MU trend ────────────────────────────────
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Daily Max Solar Generation (GW)")
        fs = go.Figure(go.Scatter(
            x=vre_sum['report_date'], y=vre_sum['daily_max_solar_mw']/1000,
            mode='lines', fill='tozeroy',
            fillcolor='rgba(245,166,35,0.15)', line=dict(color='#F5A623', width=2),
            hovertemplate='%{x|%d %b}<br>%{y:.1f} GW<extra></extra>'))
        lys = dl(250); lys['yaxis']['title'] = 'GW'; lys['showlegend'] = False
        fs.update_layout(**lys); st.plotly_chart(fs, use_container_width=True)

    with c2:
        st.subheader("Daily Max Wind Generation (GW)")
        fw = go.Figure(go.Scatter(
            x=vre_sum['report_date'], y=vre_sum['daily_max_wind_mw']/1000,
            mode='lines', fill='tozeroy',
            fillcolor='rgba(91,164,207,0.15)', line=dict(color='#5BA4CF', width=2),
            hovertemplate='%{x|%d %b}<br>%{y:.1f} GW<extra></extra>'))
        lyw = dl(250); lyw['yaxis']['title'] = 'GW'; lyw['showlegend'] = False
        fw.update_layout(**lyw); st.plotly_chart(fw, use_container_width=True)

    st.divider()

    # ── Region-wise solar + wind MU ───────────────────────────
    if not vre_reg.empty:
        st.subheader("Region-wise Solar & Wind Generation (MU)")
        metric_vre = st.selectbox("Metric", ["Solar MU", "Wind MU", "Total MU", "CUF %"],
                                   key='vre_metric')
        col_map = {
            "Solar MU": "solar_actual_mu",
            "Wind MU":  "wind_actual_mu",
            "Total MU": "total_actual_mu",
            "CUF %":    "total_cuf_pct",
        }
        vcol = col_map[metric_vre]

        fig_r = go.Figure()
        for region in REGIONS:
            rdf2 = vre_reg[vre_reg['region'] == region].sort_values('report_date')
            if rdf2.empty or vcol not in rdf2.columns: continue
            fig_r.add_trace(go.Scatter(
                x=rdf2['report_date'], y=rdf2[vcol],
                mode='lines', name=region,
                line=dict(color=RC.get(region,'#64748b'), width=2),
                hovertemplate=f'{region}  %{{x|%d %b}}<br>%{{y:,.1f}}<extra></extra>'))
        lyr = dl(320); lyr['yaxis']['title'] = metric_vre
        lyr['legend']['orientation'] = 'h'
        fig_r.update_layout(**lyr); st.plotly_chart(fig_r, use_container_width=True)

        # Small multiples per region
        st.subheader(f"{metric_vre} — Region by Region")
        n = len(REGIONS)
        rcols = st.columns(min(n, 3))

        # Shared y max
        y_max = 0
        for region in REGIONS:
            rdf2 = vre_reg[vre_reg['region'] == region]
            if not rdf2.empty and vcol in rdf2.columns:
                y_max = max(y_max, rdf2[vcol].max())
        y_max *= 1.08

        def _hex_rgba(hx, alpha=0.13):
            h = hx.lstrip('#')
            r2,g2,b2 = int(h[0:2],16),int(h[2:4],16),int(h[4:6],16)
            return f'rgba({r2},{g2},{b2},{alpha})'

        for idx2, region in enumerate(REGIONS):
            rdf2 = vre_reg[vre_reg['region']==region].sort_values('report_date')
            if rdf2.empty or vcol not in rdf2.columns: continue
            with rcols[idx2 % min(n,3)]:
                latest_v = rdf2[vcol].iloc[-1]
                delta2 = ""
                if len(rdf2) >= 2:
                    prev2 = rdf2[vcol].iloc[-2]
                    if prev2: delta2 = f"{(latest_v-prev2)/prev2*100:+.1f}% DoD"
                st.metric(f"{region} — {metric_vre}", f"{latest_v:,.1f}", delta=delta2)
                fr2 = go.Figure(go.Scatter(
                    x=rdf2['report_date'], y=rdf2[vcol],
                    mode='lines', fill='tozeroy',
                    fillcolor=_hex_rgba(RC.get(region,'#64748b')),
                    line=dict(color=RC.get(region,'#64748b'), width=2), showlegend=False,
                    hovertemplate=f'%{{x|%d %b}}<br>%{{y:,.1f}}<extra></extra>'))
                lr2 = dl(180); lr2['margin'] = dict(l=0,r=0,t=5,b=0)
                lr2['xaxis']['tickangle'] = 45; lr2['xaxis']['nticks'] = 6
                lr2['yaxis']['range'] = [0, y_max]; lr2['showlegend'] = False
                fr2.update_layout(**lr2); st.plotly_chart(fr2, use_container_width=True)

    st.divider()

    # ── State-wise solar CUF ranking ──────────────────────────
    if not vre_st.empty:
        st.subheader("State-wise Solar CUF % Ranking")
        latest_date = vre_st['report_date'].max()
        day_states = vre_st[vre_st['report_date'] == latest_date].copy()
        day_states = day_states[day_states['solar_cuf_pct'].notna()].sort_values(
            'solar_cuf_pct', ascending=True)

        if not day_states.empty:
            fig_cuf = go.Figure(go.Bar(
                x=day_states['solar_cuf_pct'],
                y=day_states['state'],
                orientation='h',
                marker_color='#F5A623',
                hovertemplate='%{y}<br>CUF: %{x:.1f}%<extra></extra>'))
            lc = dl(320); lc['xaxis']['title'] = 'Solar CUF %'
            lc['showlegend'] = False
            fig_cuf.update_layout(**lc)
            st.plotly_chart(fig_cuf, use_container_width=True)

        # State trend over time
        st.subheader("State Solar Generation Trend")
        state_list = sorted(vre_st['state'].dropna().unique().tolist())
        sel_vre_state = st.selectbox("Select State", state_list, key='vre_state')
        st_trend = vre_st[vre_st['state'] == sel_vre_state].sort_values('report_date')
        if not st_trend.empty:
            f_st = go.Figure()
            f_st.add_trace(go.Scatter(
                x=st_trend['report_date'], y=st_trend['solar_actual_mu'],
                mode='lines+markers', name='Solar MU',
                line=dict(color='#F5A623', width=2), marker=dict(size=4),
                hovertemplate='%{x|%d %b}<br>%{y:.1f} MU<extra></extra>'))
            if 'solar_cuf_pct' in st_trend.columns:
                f_st.add_trace(go.Scatter(
                    x=st_trend['report_date'], y=st_trend['solar_cuf_pct'],
                    mode='lines', name='CUF %',
                    line=dict(color='#94a3b8', width=1.5, dash='dot'),
                    yaxis='y2',
                    hovertemplate='%{x|%d %b}<br>%{y:.1f}%<extra></extra>'))
            lst = dl(280)
            lst['yaxis']  = dict(gridcolor='#1e293b', color='#F5A623', title='Solar MU')
            lst['yaxis2'] = dict(color='#94a3b8', title='CUF %', side='right', overlaying='y')
            lst['legend']['orientation'] = 'h'
            f_st.update_layout(**lst); st.plotly_chart(f_st, use_container_width=True)

    with st.expander("📋 VRE Daily Summary Table"):
        show_cols = ['report_date','daily_max_vre_pct','daily_max_solar_mw',
                     'daily_max_wind_mw','solar_hrs_vre_pct','alltime_max_vre_pct']
        show_cols = [c for c in show_cols if c in vre_sum.columns]
        disp = vre_sum[show_cols].copy()
        disp['report_date'] = disp['report_date'].dt.strftime('%Y-%m-%d')
        st.dataframe(disp.sort_values('report_date', ascending=False),
                     use_container_width=True, height=300)

# ══════════════════════════════════════════════════════════════
# P6 — GRID REAL-TIME (15-MIN SCADA)
# ══════════════════════════════════════════════════════════════
elif page == "⚡ Grid Real-time":
    st.title("⚡ Grid Real-time — 15-Min SCADA Profile")
    st.caption("Source: NLDC Daily PSP Reports · 96 blocks/day · Grid Controller of India Ltd")

    # Date selector
    c1, c2 = st.columns([1, 3])
    with c1:
        scada_date = st.date_input("Select Date",
                                    value=dates[-1],
                                    min_value=dates[0],
                                    max_value=dates[-1],
                                    key="scada_date")

    # Load SCADA for selected date
    @st.cache_data(ttl=300)
    def load_scada_date(d):
        df = pd.DataFrame(get_client().schema(S).table('scada_15min')
                          .select('*').eq('report_date', str(d))
                          .order('time_block').execute().data)
        return df

    scada = load_scada_date(scada_date)

    if scada.empty:
        st.warning(f"No SCADA data for {scada_date}")
        st.stop()

    # Convert MW to GW for readability
    mw_cols = ['demand_mw','net_demand_mw','thermal_mw','hydro_mw',
               'solar_mw','wind_mw','nuclear_mw','gas_mw','others_mw',
               'storage_demand_mw','storage_discharge_mw','total_gen_mw']
    for col in mw_cols:
        if col in scada.columns:
            scada[col + '_gw'] = scada[col] / 1000

    x = scada['time_block'].astype(str)

    # ── KPI row ───────────────────────────────────────────────
    peak_idx = scada['demand_mw'].idxmax() if 'demand_mw' in scada.columns else 0
    peak_mw  = scada.loc[peak_idx, 'demand_mw'] if 'demand_mw' in scada.columns else 0
    peak_t   = scada.loc[peak_idx, 'time_block']
    min_freq = scada['frequency_hz'].min() if 'frequency_hz' in scada.columns else 0
    max_freq = scada['frequency_hz'].max() if 'frequency_hz' in scada.columns else 0
    sol_peak = scada['solar_mw'].max() / 1000 if 'solar_mw' in scada.columns else 0
    win_peak = scada['wind_mw'].max() / 1000 if 'wind_mw' in scada.columns else 0

    k1,k2,k3,k4,k5 = st.columns(5)
    k1.metric("Peak Demand",   f"{peak_mw/1000:.1f} GW", delta=str(peak_t))
    k2.metric("Solar Peak",    f"{sol_peak:.1f} GW")
    k3.metric("Wind Peak",     f"{win_peak:.1f} GW")
    k4.metric("Min Frequency", f"{min_freq:.3f} Hz")
    k5.metric("Max Frequency", f"{max_freq:.3f} Hz")
    st.divider()

    # ── Chart 1: Demand ───────────────────────────────────────
    st.subheader(f"Demand Profile — {scada_date}")
    fig_d = go.Figure()
    if 'demand_mw' in scada.columns:
        fig_d.add_trace(go.Scatter(
            x=x, y=scada['demand_mw']/1000,
            mode='lines', name='Total Demand',
            line=dict(color='#f97316', width=2.5),
            hovertemplate='%{x}<br>Demand: %{y:.2f} GW<extra></extra>'))
    lyd = dl(320)
    lyd['yaxis']['title'] = 'GW'
    lyd['xaxis']['tickangle'] = 45; lyd['xaxis']['nticks'] = 24
    lyd['legend']['orientation'] = 'h'
    fig_d.update_layout(**lyd)
    st.plotly_chart(fig_d, use_container_width=True)

    st.divider()

    # ── Chart 2: Generation mix ───────────────────────────────
    st.subheader(f"Generation Mix — {scada_date}")

    gen_sources = [
        ('thermal_mw',  'Thermal',   '#ef4444'),
        ('hydro_mw',    'Hydro',     '#3b82f6'),
        ('solar_mw',    'Solar',     '#F5A623'),
        ('wind_mw',     'Wind',      '#22c55e'),
        ('nuclear_mw',  'Nuclear',   '#a855f7'),
        ('gas_mw',      'Gas',       '#06b6d4'),
        ('others_mw',   'Others',    '#64748b'),
    ]

    chart_type = st.radio("Chart type",
                          ["Stacked Area", "Line", "Stacked Bar"],
                          horizontal=True, key='gen_chart_type')

    fig_g = go.Figure()

    if chart_type == "Stacked Area":
        for col, label, color in gen_sources:
            if col in scada.columns:
                fig_g.add_trace(go.Scatter(
                    x=x, y=scada[col]/1000,
                    mode='lines', name=label,
                    stackgroup='one',
                    line=dict(color=color, width=0.5),
                    fillcolor=color.replace('#','rgba(') if False else color,
                    hovertemplate=f'{label}: %{{y:.2f}} GW<br>%{{x}}<extra></extra>'))

    elif chart_type == "Line":
        for col, label, color in gen_sources:
            if col in scada.columns:
                fig_g.add_trace(go.Scatter(
                    x=x, y=scada[col]/1000,
                    mode='lines', name=label,
                    line=dict(color=color, width=2),
                    hovertemplate=f'{label}: %{{y:.2f}} GW<br>%{{x}}<extra></extra>'))

    else:  # Stacked Bar
        for col, label, color in gen_sources:
            if col in scada.columns:
                fig_g.add_trace(go.Bar(
                    x=x, y=scada[col]/1000,
                    name=label,
                    marker_color=color,
                    hovertemplate=f'{label}: %{{y:.2f}} GW<br>%{{x}}<extra></extra>'))
        fig_g.update_layout(barmode='stack')

    lyg = dl(360)
    lyg['yaxis']['title'] = 'GW'
    lyg['xaxis']['tickangle'] = 45; lyg['xaxis']['nticks'] = 24
    lyg['legend']['orientation'] = 'h'
    fig_g.update_layout(**lyg)
    st.plotly_chart(fig_g, use_container_width=True)

    st.divider()

    # ── Storage ───────────────────────────────────────────────
    if 'storage_demand_mw' in scada.columns or 'storage_discharge_mw' in scada.columns:
        st.subheader("Battery Storage Profile")
        fig_bat = go.Figure()
        if 'storage_demand_mw' in scada.columns:
            fig_bat.add_trace(go.Scatter(
                x=x, y=scada['storage_demand_mw']/1000,
                mode='lines', name='Charging (demand)',
                line=dict(color='#ef4444', width=2),
                fill='tozeroy', fillcolor='rgba(239,68,68,0.1)',
                hovertemplate='Charging: %{y:.2f} GW<br>%{x}<extra></extra>'))
        if 'storage_discharge_mw' in scada.columns:
            fig_bat.add_trace(go.Scatter(
                x=x, y=scada['storage_discharge_mw']/1000,
                mode='lines', name='Discharging (generation)',
                line=dict(color='#22c55e', width=2),
                fill='tozeroy', fillcolor='rgba(34,197,94,0.1)',
                hovertemplate='Discharging: %{y:.2f} GW<br>%{x}<extra></extra>'))
        lyb = dl(220); lyb['yaxis']['title'] = 'GW'
        lyb['xaxis']['tickangle'] = 45; lyb['xaxis']['nticks'] = 24
        lyb['legend']['orientation'] = 'h'
        fig_bat.update_layout(**lyb)
        st.plotly_chart(fig_bat, use_container_width=True)

    st.divider()

    # ── Monthly average SCADA ─────────────────────────────────
    st.subheader("Monthly Average — Generation Mix by Time Block")
    st.caption("Average GW per 15-min block across all days in each month")

    @st.cache_data(ttl=300)
    def load_scada_all():
        df = pd.DataFrame(get_client().schema(S).table('scada_15min')
                          .select('report_date,time_block,demand_mw,thermal_mw,hydro_mw,'
                                  'solar_mw,wind_mw,nuclear_mw,gas_mw,others_mw,'
                                  'storage_demand_mw,storage_discharge_mw')
                          .order('report_date,time_block').execute().data)
        if not df.empty:
            df['report_date'] = pd.to_datetime(df['report_date'])
            df['month'] = df['report_date'].dt.to_period('M').astype(str)
        return df

    all_scada = load_scada_all()

    if not all_scada.empty:
        months = sorted(all_scada['month'].unique())
        month_options = months + ['YTD Average']
        sel_months = st.multiselect("Select Months", month_options,
                                     default=months[-2:] if len(months) >= 2 else months,
                                     key='scada_months')
        sel_metric = st.selectbox("Metric",
                                   ["Generation Mix", "Demand", "Storage"],
                                   key='scada_monthly_metric')

        if sel_months:
            fig_m = go.Figure()
            colors_m = ['#3b82f6','#f97316','#22c55e','#a855f7','#ef4444','#fbbf24']

            if sel_metric == "Demand":
                real_months = [m for m in sel_months if m != 'YTD Average']
                show_ytd    = 'YTD Average' in sel_months
                color_idx   = 0
                for month in real_months:
                    mdf = all_scada[all_scada['month'] == month]
                    avg = mdf.groupby('time_block')['demand_mw'].mean().reset_index()
                    fig_m.add_trace(go.Scatter(
                        x=avg['time_block'].astype(str), y=avg['demand_mw']/1000,
                        mode='lines', name=month,
                        line=dict(color=colors_m[color_idx % len(colors_m)], width=2),
                        hovertemplate=f'{month}  %{{x}}<br>%{{y:.2f}} GW<extra></extra>'))
                    color_idx += 1
                if show_ytd:
                    base = real_months if real_months else months
                    ytd_avg = (all_scada[all_scada['month'].isin(base)]
                               .groupby('time_block')['demand_mw'].mean().reset_index())
                    fig_m.add_trace(go.Scatter(
                        x=ytd_avg['time_block'].astype(str), y=ytd_avg['demand_mw']/1000,
                        mode='lines', name='YTD Average',
                        line=dict(color='#ffffff', width=2.5, dash='dash'),
                        hovertemplate='YTD Avg  %{x}<br>%{y:.2f} GW<extra></extra>'))
                lym = dl(340); lym['yaxis']['title'] = 'GW (avg)'

            elif sel_metric == "Storage":
                for i, month in enumerate(sel_months):
                    mdf = all_scada[all_scada['month'] == month]
                    avg_ch  = mdf.groupby('time_block')['storage_demand_mw'].mean().reset_index()
                    avg_dis = mdf.groupby('time_block')['storage_discharge_mw'].mean().reset_index()
                    fig_m.add_trace(go.Scatter(
                        x=avg_ch['time_block'].astype(str), y=avg_ch['storage_demand_mw']/1000,
                        mode='lines', name=f'{month} Charging',
                        line=dict(color=colors_m[i % len(colors_m)], width=2, dash='dot'),
                        hovertemplate=f'{month} Charging  %{{x}}<br>%{{y:.2f}} GW<extra></extra>'))
                    fig_m.add_trace(go.Scatter(
                        x=avg_dis['time_block'].astype(str), y=avg_dis['storage_discharge_mw']/1000,
                        mode='lines', name=f'{month} Discharging',
                        line=dict(color=colors_m[i % len(colors_m)], width=2),
                        hovertemplate=f'{month} Discharging  %{{x}}<br>%{{y:.2f}} GW<extra></extra>'))
                lym = dl(340); lym['yaxis']['title'] = 'GW (avg)'

            else:  # Generation Mix — two sub-charts side by side per month + overall
                # Overall average across all selected months
                overall_df = all_scada[all_scada['month'].isin(sel_months)]

                # Tab layout: one tab per month + one Overall tab
                tab_labels = ['📊 Overall'] + sel_months
                tabs = st.tabs(tab_labels)

                def _gen_mix_fig(data_df, title):
                    f = go.Figure()
                    for col, label, color in gen_sources:
                        if col in data_df.columns:
                            avg = data_df.groupby('time_block')[col].mean().reset_index()
                            f.add_trace(go.Scatter(
                                x=avg['time_block'].astype(str), y=avg[col]/1000,
                                mode='lines', name=label,
                                stackgroup='one',
                                line=dict(color=color, width=0.5),
                                hovertemplate=f'{label}  %{{x}}<br>%{{y:.2f}} GW<extra></extra>'))
                    ly = dl(340); ly['yaxis']['title'] = 'GW (avg)'
                    ly['xaxis']['tickangle'] = 45; ly['xaxis']['nticks'] = 24
                    ly['legend']['orientation'] = 'h'
                    f.update_layout(**ly)
                    return f

                with tabs[0]:
                    st.caption(f"Average across all selected months: {', '.join(sel_months)}")
                    st.plotly_chart(_gen_mix_fig(overall_df, 'Overall'), use_container_width=True)

                for i, month in enumerate(sel_months):
                    with tabs[i+1]:
                        mdf = all_scada[all_scada['month'] == month]
                        st.caption(f"Average generation mix for {month}")
                        st.plotly_chart(_gen_mix_fig(mdf, month), use_container_width=True)

                lym = dl(340); lym['yaxis']['title'] = 'GW (avg)'  # used below

            lym['xaxis']['tickangle'] = 45; lym['xaxis']['nticks'] = 24
            lym['legend']['orientation'] = 'h'
            fig_m.update_layout(**lym)
            st.plotly_chart(fig_m, use_container_width=True)

    st.divider()

    # ── Raw data table ────────────────────────────────────────
    with st.expander("📋 Raw SCADA Data (96 blocks)"):
        show = [c for c in ['time_block','demand_mw','net_demand_mw',
                             'thermal_mw','hydro_mw','solar_mw','wind_mw',
                             'nuclear_mw','gas_mw','frequency_hz','total_gen_mw']
                if c in scada.columns]
        st.dataframe(scada[show].rename(columns={c: c.replace('_mw',' MW').replace('_hz',' Hz').replace('_',' ').title()
                                                  for c in show}),
                     use_container_width=True, height=300)

st.divider()
st.caption("NLDC Daily PSP Reports · Grid Controller of India Ltd · CarobInsights Power Sector Analytics")