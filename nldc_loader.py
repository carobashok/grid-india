"""
nldc_loader.py
Load parsed NLDC data into Supabase (existing project, nldc schema)

Schema: nldc.daily_summary, nldc.scada_15min, nldc.state_daily
"""

import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SCHEMA = 'nldc'   # separate schema in your existing Supabase project


def get_client() -> Client:
    url = os.environ['SUPABASE_URL']
    key = os.environ['SUPABASE_SERVICE_KEY']   # use service role key for inserts
    return create_client(url, key)


def upsert_summary(client: Client, summary: dict) -> dict:
    """Upsert one row into nldc.daily_summary. Returns Supabase response."""
    res = (
        client
        .schema(SCHEMA)
        .table('daily_summary')
        .upsert(summary, on_conflict='report_date')
        .execute()
    )
    return res


def upsert_scada(client: Client, scada_rows: list) -> dict:
    """
    Upsert 96 SCADA rows into nldc.scada_15min.
    Batches in groups of 50 to stay within Supabase limits.
    """
    results = []
    batch_size = 50
    for i in range(0, len(scada_rows), batch_size):
        batch = scada_rows[i:i+batch_size]
        res = (
            client
            .schema(SCHEMA)
            .table('scada_15min')
            .upsert(batch, on_conflict='report_date,time_block')
            .execute()
        )
        results.append(res)
    return results


def upsert_states(client: Client, state_rows: list) -> dict:
    """Upsert state daily rows into nldc.state_daily."""
    if not state_rows:
        return []
    res = (
        client
        .schema(SCHEMA)
        .table('state_daily')
        .upsert(state_rows, on_conflict='report_date,state')
        .execute()
    )
    return res


def load_parsed(parsed: dict, verbose: bool = True) -> dict:
    """
    Load a fully parsed result dict (output of parse_nldc_pdf) into Supabase.

    Args:
        parsed:  dict with keys summary, scada, states, meta
        verbose: print progress

    Returns:
        dict with status and row counts
    """
    client = get_client()
    meta   = parsed['meta']
    date   = meta['data_date']

    if verbose:
        print(f"  Loading {date} → summary({meta['summary_fields']} fields) "
              f"scada({meta['scada_rows']}) states({meta['state_rows']})")

    # Summary
    upsert_summary(client, parsed['summary'])
    if verbose: print(f"    ✅ summary")

    # SCADA
    if parsed['scada']:
        upsert_scada(client, parsed['scada'])
        if verbose: print(f"    ✅ scada  ({len(parsed['scada'])} rows)")

    # States
    if parsed['states']:
        upsert_states(client, parsed['states'])
        if verbose: print(f"    ✅ states ({len(parsed['states'])} rows)")

    return {
        'date':        date,
        'summary_ok':  True,
        'scada_rows':  len(parsed['scada']),
        'state_rows':  len(parsed['states']),
    }
