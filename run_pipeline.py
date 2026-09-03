"""
run_pipeline.py
NLDC Daily PSP Pipeline — bulk historical + daily automation

Usage:
  # Process all PDFs in a folder (historical bulk load)
  python run_pipeline.py --folder ./pdfs/raw

  # Process a single PDF
  python run_pipeline.py --file ./pdfs/raw/2026-08-21_NLDC_PSP.pdf

  # Run as daily job (processes yesterday's PDF)
  python run_pipeline.py --daily

  # Dry run (parse only, no Supabase load)
  python run_pipeline.py --folder ./pdfs/raw --dry-run

Naming convention for PDFs:
  YYYY-MM-DD_NLDC_PSP.pdf   where date = DATA date (not report date)
  e.g. 2026-08-21_NLDC_PSP.pdf  contains 21-Aug data
"""

import argparse
import json
import sys
import logging
from datetime import date, timedelta
from pathlib import Path

from nldc_parser import parse_nldc_pdf
from nldc_loader import load_parsed

# ── logging ───────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler('pipeline.log'),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger(__name__)


# ── helpers ───────────────────────────────────────────────────

def get_processed_dates(log_file='processed.json'):
    """Track which dates have already been loaded."""
    p = Path(log_file)
    if p.exists():
        return set(json.loads(p.read_text()))
    return set()

def mark_processed(data_date, log_file='processed.json'):
    dates = get_processed_dates(log_file)
    dates.add(str(data_date))
    Path(log_file).write_text(json.dumps(sorted(dates), indent=2))


def process_one(pdf_path, data_date=None, dry_run=False, skip_existing=True):
    """Parse + load one PDF. Returns True on success."""
    pdf_path = Path(pdf_path)

    try:
        parsed = parse_nldc_pdf(pdf_path, data_date)
        d = parsed['meta']['data_date']

        if skip_existing and d in get_processed_dates():
            log.info(f"  SKIP {d} (already processed)")
            return True

        log.info(f"  PARSED {d}: {parsed['meta']['scada_rows']} SCADA rows, "
                 f"{parsed['meta']['state_rows']} states, "
                 f"{parsed['meta']['summary_fields']} summary fields")

        if not dry_run:
            load_parsed(parsed, verbose=False)
            mark_processed(d)
            log.info(f"  LOADED {d} ✅")
        else:
            log.info(f"  DRY RUN — not loading to Supabase")

        return True

    except Exception as e:
        log.error(f"  FAILED {pdf_path.name}: {e}")
        return False


def process_folder(folder, dry_run=False, skip_existing=True):
    """Process all PDFs in a folder, sorted by filename (= date order)."""
    folder = Path(folder)
    pdfs = sorted(folder.glob('*.pdf'))

    if not pdfs:
        log.warning(f"No PDFs found in {folder}")
        return

    log.info(f"Found {len(pdfs)} PDFs in {folder}")
    ok = fail = skip = 0

    for pdf in pdfs:
        result = process_one(pdf, dry_run=dry_run, skip_existing=skip_existing)
        if result:
            ok += 1
        else:
            fail += 1

    log.info(f"\nDone: {ok} OK, {fail} failed, {skip} skipped")
    return ok, fail


def process_daily(pdf_folder, dry_run=False):
    """
    Process yesterday's PDF.
    For use as a daily cron job.
    PDF should be named: YYYY-MM-DD_NLDC_PSP.pdf
    NLDC publishes each day's data on the following morning.
    """
    yesterday = date.today() - timedelta(days=1)
    pdf_path  = Path(pdf_folder) / f"{yesterday.isoformat()}_NLDC_PSP.pdf"

    if not pdf_path.exists():
        log.error(f"Daily PDF not found: {pdf_path}")
        log.error("Download yesterday's NLDC PSP report and rename it.")
        return False

    log.info(f"Daily run: processing {yesterday}")
    return process_one(pdf_path, data_date=yesterday, dry_run=dry_run)


# ── CLI ───────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='NLDC PSP Pipeline')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--folder', help='Folder containing dated PDFs')
    group.add_argument('--file',   help='Single PDF to process')
    group.add_argument('--daily',  action='store_true', help='Process yesterday PDF')

    parser.add_argument('--pdf-folder', default='./pdfs/raw',
                        help='PDF folder for --daily mode')
    parser.add_argument('--dry-run', action='store_true',
                        help='Parse only, do not load to Supabase')
    parser.add_argument('--force', action='store_true',
                        help='Reprocess even if date already in processed.json')
    parser.add_argument('--date', help='Override data date (YYYY-MM-DD) for --file mode')

    args = parser.parse_args()

    skip_existing = not args.force

    if args.folder:
        process_folder(args.folder, dry_run=args.dry_run, skip_existing=skip_existing)

    elif args.file:
        data_date = date.fromisoformat(args.date) if args.date else None
        process_one(args.file, data_date=data_date,
                    dry_run=args.dry_run, skip_existing=skip_existing)

    elif args.daily:
        process_daily(args.pdf_folder, dry_run=args.dry_run)


if __name__ == '__main__':
    main()
