# AEO Citation Tracker

[![MCP Surface Check: low surface](https://img.shields.io/badge/MCP_Surface_Check-low-4FA86A)](https://majorlabs.co/security)

**Which answer engines cite your URLs.** Read-only, bring-your-own-keys, built to compound over time.

Answer engines (ChatGPT, Claude, Perplexity, Gemini) are replacing search for a growing share of questions. The optimisation target moves with them: not "do I rank" but "do the models cite me." This tool asks a set of real questions across every configured engine and records whether a target domain shows up in the citations, run after run, so you can watch the number move.

It is a [Major Labs](https://majorlabs.co) measurement tool, in the same family as the MCP scanner: a small read-only instrument that produces an open, longitudinal dataset.

---

## What it does

```bash
python3 aeo.py --domain majorlabs.co --queries queries.txt
python3 aeo.py --domain majorlabs.co --report     # summarise stored runs
```

For each query, against each engine that has a key, it asks the question, reads the answer's citations, and records whether the target domain was cited. Results go to a local SQLite database so the series compounds.

```
=== citation rate for majorlabs.co (latest run) ===
  claude      2/6 cited   33%  ######
```

---

## Engines

| Engine | How citations come back | Status |
|---|---|---|
| **Claude** (Anthropic) | web-search tool, cited URLs | **works out of the box** |
| **Perplexity** | native `citations` in the response | wired; needs a key |
| **OpenAI** (ChatGPT) | web-search tool, `url_citation` annotations | wired; needs a key |
| **Gemini** (Google) | Google Search grounding metadata | wired; needs a key |

Only engines with a key configured run; the rest are skipped and reported. Add keys as files in the Major Labs root or as environment variables:

| Engine | File | Env |
|---|---|---|
| Claude | `.anthropic-api-key` | `ANTHROPIC_API_KEY` |
| Perplexity | `.perplexity-api-key` | `PERPLEXITY_API_KEY` |
| OpenAI | `.openai-api-key` | `OPENAI_API_KEY` |
| Gemini | `.gemini-api-key` | `GEMINI_API_KEY` |

---

## Honest limitations (v0)

- **Coverage depends on your keys.** With one engine you get one column; the value is in the cross-engine comparison, which needs all four.
- **Citations are not rankings.** Being cited once for one phrasing is weak signal; the tool is built to run many queries, many times, and read the trend.
- **Engines are non-deterministic.** The same query can cite different sources run to run. That is why this stores a series rather than a single verdict.
- **Read-only and rate-limited.** It only sends queries and reads answers, with a pause between calls.

---

## The research angle

Run across a fixed query set on a schedule and the database becomes a *State of AEO* dataset: how AI answer engines rewrite discovery, who they cite for a topic, and how fast that changes. The first reading for any new site is honest and useful on its own: today, almost nobody is cited yet.

MIT. Built by [Major Labs](https://majorlabs.co).
