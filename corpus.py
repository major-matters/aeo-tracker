"""
State of AEO — citation corpus.

Runs a query set across every configured answer engine and stores EVERY URL each
one cites (not just a target-domain match). The corpus is then analysed for the
report: who gets cited, how much the engines agree with each other, how
concentrated citations are, and what kinds of sources win.

Read-only. Bring your own keys (see engines.py). Reuses the same adapters.

    python3 corpus.py --queries queries-state-of-aeo.txt [--limit N]
    python3 corpus.py --report
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from urllib.parse import urlparse

from engines import all_engines

DB = Path(__file__).parent / "aeo.db"
DEFAULT_QUERIES = Path(__file__).parent / "queries-state-of-aeo.txt"


def host(url: str) -> str:
    try:
        h = (urlparse(url).hostname or "").lower()
        return h[4:] if h.startswith("www.") else h
    except Exception:
        return ""


def source_type(h: str) -> str:
    if h.endswith("wikipedia.org"):
        return "wikipedia"
    if h in ("reddit.com", "quora.com") or "stackexchange.com" in h or h == "stackoverflow.com":
        return "forum"
    if h in ("youtube.com", "youtu.be", "x.com", "twitter.com", "linkedin.com", "facebook.com", "instagram.com", "tiktok.com", "medium.com"):
        return "social_ugc"
    if h.endswith(".gov") or h.endswith(".edu"):
        return "gov_edu"
    return "site"  # vendor/brand/news/blog/other


def init_db(conn):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS corpus (run_at TEXT, engine TEXT, query TEXT, url TEXT, host TEXT)"
    )


def load_queries(path: Path):
    if not path.exists():
        return []
    return [ln.strip() for ln in path.read_text().splitlines() if ln.strip() and not ln.startswith("#")]


def run(queries, run_at):
    conn = sqlite3.connect(DB)
    init_db(conn)
    engines = [e for e in all_engines() if e.available]
    skipped = [e.name for e in all_engines() if not e.available]
    print(f"engines: {', '.join(e.name for e in engines)}" + (f"  (no key: {', '.join(skipped)})" if skipped else ""))
    print(f"queries: {len(queries)}\n")
    for e in engines:
        cited = 0
        for q in queries:
            res = e.query(q)
            for u in res.cited_urls:
                h = host(u)
                if h:
                    conn.execute("INSERT INTO corpus VALUES (?,?,?,?,?)", (run_at, e.name, q, u, h))
                    cited += 1
            conn.commit()
            time.sleep(1)
        print(f"  [{e.name:<10}] {cited} citations across {len(queries)} queries")
    conn.close()


def report():
    conn = sqlite3.connect(DB)
    init_db(conn)
    run_at = conn.execute("SELECT MAX(run_at) FROM corpus").fetchone()[0]
    if not run_at:
        print("no corpus yet")
        return
    rows = conn.execute("SELECT engine, query, host FROM corpus WHERE run_at=?", (run_at,)).fetchall()
    engines = sorted({r[0] for r in rows})
    queries = sorted({r[1] for r in rows})

    # domains cited per (engine, query)
    by_eq = defaultdict(set)
    host_counts = Counter()
    host_queries = defaultdict(set)
    by_engine_hosts = defaultdict(Counter)
    type_counts = Counter()
    for engine, query, h in rows:
        by_eq[(engine, query)].add(h)
        host_counts[h] += 1
        host_queries[h].add(query)
        by_engine_hosts[engine][h] += 1
        type_counts[source_type(h)] += 1

    print(f"=== State of AEO corpus ({len(queries)} queries, {len(engines)} engines, {len(rows)} citations) ===\n")

    print("Top cited domains (by # of queries they appear in):")
    for h, qs in sorted(host_queries.items(), key=lambda kv: (-len(kv[1]), -host_counts[kv[0]]))[:15]:
        print(f"  {len(qs):>2}/{len(queries)} queries  {host_counts[h]:>3} cites   {h}")

    print("\nCross-engine agreement (do the engines cite the same domains for a query?):")
    overlaps = []
    for q in queries:
        present = [e for e in engines if by_eq.get((e, q))]
        for a, b in combinations(present, 2):
            sa, sb = by_eq[(a, q)], by_eq[(b, q)]
            j = len(sa & sb) / len(sa | sb) if (sa | sb) else 0
            overlaps.append(j)
    avg = sum(overlaps) / len(overlaps) if overlaps else 0
    print(f"  mean pairwise domain overlap (Jaccard): {avg:.2f}   ({len(overlaps)} engine-pairs over {len(queries)} queries)")
    print("  (0 = the engines never cite the same source; 1 = identical)")

    print("\nConcentration:")
    total = sum(host_counts.values())
    top10 = sum(c for _, c in host_counts.most_common(10))
    print(f"  {len(host_counts)} distinct domains across all answers")
    print(f"  top 10 domains = {round(100*top10/total,1)}% of all citations")

    print("\nSource type mix:")
    for t, c in type_counts.most_common():
        print(f"  {t:<11} {round(100*c/total,1)}%")

    print("\nPer-engine character (top 3 domains each):")
    for e in engines:
        top = ", ".join(f"{h}({c})" for h, c in by_engine_hosts[e].most_common(3))
        n = sum(by_engine_hosts[e].values())
        print(f"  {e:<11} {n} cites, {len(by_engine_hosts[e])} domains  ::  {top}")
    conn.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--queries", default=str(DEFAULT_QUERIES))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()
    if args.report:
        report()
        return
    queries = load_queries(Path(args.queries))
    if args.limit:
        queries = queries[: args.limit]
    if not queries:
        print("no queries", file=sys.stderr)
        sys.exit(1)
    run(queries, time.strftime("%Y-%m-%dT%H:%M:%S"))
    print()
    report()


if __name__ == "__main__":
    main()
