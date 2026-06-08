"""
AEO Citation Tracker — which answer engines cite your URLs.

Answer engines (ChatGPT, Claude, Perplexity, Gemini) increasingly replace search.
The new question is not "do I rank" but "do the models cite me." This tool asks a
set of real questions across every configured engine and records whether a target
domain appears in the citations, over time.

Read-only: it sends queries and reads the answers. Bring your own API keys; only
engines with a key configured run. Claude (Anthropic web search) works out of the
box if .anthropic-api-key is present.

Run:
    python3 aeo.py --domain majorlabs.co --queries queries.txt
    python3 aeo.py --domain example.com --report      # summarise stored runs
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from engines import all_engines

DB = Path(__file__).parent / "aeo.db"
DEFAULT_QUERIES = Path(__file__).parent / "queries.example.txt"


def host(url: str) -> str:
    try:
        h = (urlparse(url).hostname or "").lower()
        return h[4:] if h.startswith("www.") else h
    except Exception:
        return ""


def cites(url: str, domain: str) -> bool:
    d = domain.lower()
    d = d[4:] if d.startswith("www.") else d
    h = host(url)
    return h == d or h.endswith("." + d)


def init_db(conn):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS citations (
            run_at TEXT, engine TEXT, query TEXT, domain TEXT,
            cited INTEGER, matched_urls TEXT, total_cited INTEGER, error TEXT
        )"""
    )


def load_queries(path: Path):
    if not path.exists():
        return []
    return [ln.strip() for ln in path.read_text().splitlines() if ln.strip() and not ln.startswith("#")]


def run(domain: str, queries, only, run_at: str):
    conn = sqlite3.connect(DB)
    init_db(conn)
    engines = [e for e in all_engines() if e.available and (not only or e.name in only)]
    skipped = [e.name for e in all_engines() if not e.available]
    if not engines:
        print("No engines available. Configure at least one API key (see README).")
        return
    print(f"domain: {domain}")
    print(f"engines: {', '.join(e.name for e in engines)}"
          + (f"   (no key: {', '.join(skipped)})" if skipped else ""))
    print(f"queries: {len(queries)}\n")

    for e in engines:
        for q in queries:
            res = e.query(q)
            matched = [u for u in res.cited_urls if cites(u, domain)]
            conn.execute(
                "INSERT INTO citations VALUES (?,?,?,?,?,?,?,?)",
                (run_at, e.name, q, domain, 1 if matched else 0,
                 json.dumps(matched), len(res.cited_urls), res.error),
            )
            conn.commit()
            mark = "CITED" if matched else ("err" if res.error else "—")
            print(f"  [{e.name:<10}] {mark:<6} {q[:58]}")
            if matched:
                for u in matched[:2]:
                    print(f"               -> {u}")
            time.sleep(1)
    conn.close()
    report(domain)


def report(domain: str):
    conn = sqlite3.connect(DB)
    init_db(conn)
    rows = conn.execute(
        "SELECT engine, COUNT(*) , SUM(cited) FROM citations WHERE domain=? "
        "AND run_at=(SELECT MAX(run_at) FROM citations WHERE domain=?) GROUP BY engine",
        (domain, domain),
    ).fetchall()
    print(f"\n=== citation rate for {domain} (latest run) ===")
    if not rows:
        print("  no runs recorded yet")
        return
    for engine, total, cited in rows:
        cited = cited or 0
        pct = round(100 * cited / total) if total else 0
        bar = "#" * (pct // 5)
        print(f"  {engine:<11} {cited}/{total} cited  {pct:>3}%  {bar}")
    runs = conn.execute("SELECT COUNT(DISTINCT run_at) FROM citations WHERE domain=?", (domain,)).fetchone()[0]
    print(f"\n  {runs} run(s) recorded. The series compounds; re-run to track movement over time.")
    conn.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", required=True, help="target domain, e.g. majorlabs.co")
    ap.add_argument("--queries", default=str(DEFAULT_QUERIES), help="file of queries, one per line")
    ap.add_argument("--engines", nargs="*", help="restrict to these engines (claude perplexity openai gemini)")
    ap.add_argument("--report", action="store_true", help="just summarise stored runs, do not query")
    args = ap.parse_args()

    if args.report:
        report(args.domain)
        return
    queries = load_queries(Path(args.queries))
    if not queries:
        print(f"No queries found in {args.queries}", file=sys.stderr)
        sys.exit(1)
    # Caller stamps the run time; the module stays clock-free for reproducibility.
    run_at = time.strftime("%Y-%m-%dT%H:%M:%S")
    run(args.domain, queries, args.engines, run_at)


if __name__ == "__main__":
    main()
