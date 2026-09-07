"""
nldc_vre_loader.py — NLDC VRE / REMC Report Supabase Loader
CarobInsights Power Sector Analytics

Parses NLDC VRE/REMC daily PDF reports and upserts into Supabase:
  nldc_vre.daily_summary   — All India VRE metrics
  nldc_vre.region_profile  — Region-wise REMC + ISTS profiles
  nldc_vre.state_profile   — State-wise intra-state profiles

Usage:
  # Single file
  python nldc_vre_loader.py raw/vre/13_07_2026_NLDC_REMC_REPORT_582.pdf

  # Bulk folder
  python nldc_vre_loader.py --folder raw/vre/

  # Dry run (parse only, no DB write)
  python nldc_vre_loader.py --folder raw/vre/ --dry-run

  # Force reprocess already-loaded dates
  python nldc_vre_loader.py --folder raw/vre/ --force
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
from supabase import create_client, Client

from nldc_vre_parser import parse_vre_report

def _load_env():
    try:
        for fname in [".env", ".env.local"]:
            for base in [Path(__file__).parent, Path.cwd()]:
                f = base / fname
                if f.exists():
                    load_dotenv(f); return
    except ImportError:
        pass
_load_env()

SCHEMA          = 'nldc_vre'
PROCESSED_FILE  = Path('processed_vre.json')


# ── Supabase client ──────────────────────────────────────────────────

def get_client() -> Client:
    url = os.environ.get('SUPABASE_URL', '').strip().strip('"').strip("'")
    key = os.environ.get('SUPABASE_SERVICE_KEY', '').strip().strip('"').strip("'")
    if not url or not key:
        raise EnvironmentError('SUPABASE_URL or SUPABASE_SERVICE_KEY not set in .env')
    return create_client(url, key)


# ── Processed tracking ────────────────────────────────────────────────────────

def load_processed() -> set:
    if PROCESSED_FILE.exists():
        return set(json.loads(PROCESSED_FILE.read_text()))
    return set()

def save_processed(dates: set):
    PROCESSED_FILE.write_text(json.dumps(sorted(dates), indent=2))


# ── Upsert helpers ────────────────────────────────────────────────────────────

def _clean(rec: dict) -> dict:
    """Remove None values and ensure JSON-serialisable types."""
    return {k: v for k, v in rec.items() if v is not None}

def upsert_daily_summary(client: Client, data: dict, dry_run: bool) -> bool:
    rec = _clean(data)
    if not rec.get('report_date'):
        print("  ✗ daily_summary: no report_date — skipping")
        return False
    if dry_run:
        print(f"  [DRY] daily_summary: {rec.get('report_date')}  "
              f"VRE% {rec.get('daily_max_vre_pct')}  "
              f"VRE MW {rec.get('daily_max_vre_mw')}")
        return True
    try:
        client.schema(SCHEMA).table('daily_summary').upsert(
            rec, on_conflict='report_date'
        ).execute()
        print(f"  ✓ daily_summary: {rec['report_date']}  "
              f"VRE {rec.get('daily_max_vre_pct')}%  "
              f"{rec.get('daily_max_vre_mw'):,.0f} MW")
        return True
    except Exception as e:
        print(f"  ✗ daily_summary error: {e}")
        return False

def upsert_region_profile(client: Client, rows: list[dict], dry_run: bool) -> bool:
    if not rows:
        print("  ✗ region_profile: no rows")
        return False
    clean_rows = [_clean(r) for r in rows]
    if dry_run:
        for r in clean_rows:
            print(f"  [DRY] region_profile: {r.get('report_date')}  "
                  f"{r.get('region'):5s}  {r.get('source'):5s}  "
                  f"Solar {r.get('solar_actual_mu')} MU  "
                  f"Wind {r.get('wind_actual_mu')} MU  "
                  f"CUF {r.get('total_cuf_pct')}%")
        return True
    try:
        client.schema(SCHEMA).table('region_profile').upsert(
            clean_rows, on_conflict='report_date,region,source'
        ).execute()
        print(f"  ✓ region_profile: {len(clean_rows)} rows upserted")
        return True
    except Exception as e:
        print(f"  ✗ region_profile error: {e}")
        return False

def upsert_state_profile(client: Client, rows: list[dict], dry_run: bool) -> bool:
    if not rows:
        print("  ✗ state_profile: no rows")
        return False
    clean_rows = [_clean(r) for r in rows]
    if dry_run:
        for r in clean_rows:
            print(f"  [DRY] state_profile: {r.get('report_date')}  "
                  f"{r.get('state'):22s}  "
                  f"Solar {r.get('solar_actual_mu')} MU  "
                  f"CUF {r.get('solar_cuf_pct')}%")
        return True
    try:
        client.schema(SCHEMA).table('state_profile').upsert(
            clean_rows, on_conflict='report_date,state,section'
        ).execute()
        print(f"  ✓ state_profile: {len(clean_rows)} rows upserted")
        return True
    except Exception as e:
        print(f"  ✗ state_profile error: {e}")
        return False


# ── Process single file ───────────────────────────────────────────────────────

def process_file(
    pdf_path: Path,
    client: Client,
    processed: set,
    dry_run: bool = False,
    force: bool = False,
    override_date: str = None,
) -> bool:
    print(f"\n{'─'*60}")
    print(f"File : {pdf_path.name}")

    # Parse
    try:
        result = parse_vre_report(pdf_path)
    except Exception as e:
        print(f"  ✗ Parse error: {e}")
        return False

    report_date = result.get('report_date')
    if not report_date or report_date == 'None':
        print(f"  ✗ Could not determine report date — skipping")
        return False

    # Override date if specified (for NLDC typos in Report for field)
    if override_date:
        print(f"Date : {report_date} → overridden to {override_date}")
        report_date = override_date
        result['daily_summary']['report_date'] = override_date
        for r in result['region_profile']: r['report_date'] = override_date
        for r in result['state_profile']:  r['report_date'] = override_date
    else:
        print(f"Date : {report_date}")

    # Skip if already processed
    if report_date in processed and not force:
        print(f"  ↷  Already loaded — use --force to reprocess")
        return True

    # Upsert all three tables
    ok1 = upsert_daily_summary(client, result['daily_summary'], dry_run)
    ok2 = upsert_region_profile(client, result['region_profile'], dry_run)
    ok3 = upsert_state_profile(client, result['state_profile'], dry_run)

    if ok1 and not dry_run:
        processed.add(report_date)

    return ok1


# ── Bulk folder mode ──────────────────────────────────────────────────────────

def process_folder(
    folder: Path,
    client: Client,
    dry_run: bool = False,
    force: bool = False,
):
    pdfs = sorted(folder.glob('*.pdf'))
    # Filter VRE files only (in case PSP files are in same folder)
    vre_pdfs = [p for p in pdfs if 'REMC' in p.name.upper() or 'VRE' in p.name.upper()]

    if not vre_pdfs:
        print(f"No VRE PDF files found in {folder}")
        return

    print(f"Found {len(vre_pdfs)} VRE PDF files in {folder}")
    processed = load_processed()

    success = 0
    skipped = 0
    failed  = 0

    for pdf in vre_pdfs:
        result = process_file(pdf, client, processed, dry_run, force)
        if result:
            success += 1
        else:
            failed += 1

    if not dry_run:
        save_processed(processed)

    print(f"\n{'='*60}")
    print(f"Done  |  Success: {success}  Skipped: {skipped}  Failed: {failed}")
    print(f"Processed dates tracked: {len(processed)}")

    # Prompt to delete loaded PDFs
    if not dry_run and success > 0:
        ans = input("\nDelete loaded PDF files? (Y/N): ").strip().upper()
        if ans == 'Y':
            deleted = 0
            for pdf in vre_pdfs:
                try:
                    pdf.unlink()
                    print(f"  🗑 Deleted: {pdf.name}")
                    deleted += 1
                except Exception as e:
                    print(f"  ✗ Could not delete {pdf.name}: {e}")
            print(f"  {deleted} file(s) deleted.")
        else:
            print("  PDF files kept.")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='NLDC VRE/REMC Report Loader — parse PDFs and load into Supabase'
    )
    parser.add_argument('path', nargs='?', help='Single PDF file path')
    parser.add_argument('--folder', '-f', help='Folder of VRE PDFs to bulk load')
    parser.add_argument('--dry-run', action='store_true',
                        help='Parse and print without writing to Supabase')
    parser.add_argument('--force', action='store_true',
                        help='Reprocess dates already in processed_vre.json')
    parser.add_argument('--override-date', metavar='YYYY-MM-DD',
                        help='Override the report date (for NLDC typos in PDF)')
    parser.add_argument('--status', action='store_true',
                        help='Show processed dates and exit')

    args = parser.parse_args()

    if args.status:
        processed = load_processed()
        print(f"Processed VRE dates ({len(processed)}):")
        for d in sorted(processed):
            print(f"  {d}")
        return

    # Skip Supabase connection entirely for dry-run
    client = None if args.dry_run else get_client()
    processed = load_processed()

    if args.folder:
        process_folder(Path(args.folder), client, args.dry_run, args.force)

    elif args.path:
        pdf_path = Path(args.path)
        ok = process_file(pdf_path, client, processed, args.dry_run, args.force,
                          override_date=args.override_date)
        if ok and not args.dry_run:
            save_processed(processed)
            ans = input(f"\nDelete {pdf_path.name}? (Y/N): ").strip().upper()
            if ans == 'Y':
                try:
                    pdf_path.unlink()
                    print(f"  🗑 Deleted: {pdf_path.name}")
                except Exception as e:
                    print(f"  ✗ Could not delete: {e}")
            else:
                print("  PDF file kept.")

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
