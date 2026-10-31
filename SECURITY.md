# Security

The AEO Citation Tracker is read-only and bring-your-own-keys. Its threat surface is small by design.

- **No live probing.** It sends queries to four fixed, hardcoded provider endpoints (Anthropic, Perplexity, OpenAI, Google) and reads the answers. It does not fetch the cited URLs or connect to anything else.
- **Keys stay local.** API keys are read from files (`.anthropic-api-key`, `.perplexity-api-key`, ...) or environment variables and are never written to the database, logs, or output. Every provider key travels in a request header (Gemini's in `x-goog-api-key`, never in the URL), and error strings are redacted as a second guard.
- **Bounded responses.** A provider response body over 5 MB is refused before it is parsed.
- **No injection surface.** All SQL uses parameterized queries; queries you supply are sent only as prompt text to the LLM APIs.
- **Nothing secret is committed.** Key files and the local `aeo.db` are gitignored.

This is a v0 research tool. Report anything that looks like a key leak or an SSRF path privately through GitHub's private vulnerability reporting on this repository (Security tab -> Report a vulnerability); it is enabled and monitored. Acknowledgment within 7 days, a fix or a plan within 45, credit to reporters who want it. Please do not open public issues for security reports.
