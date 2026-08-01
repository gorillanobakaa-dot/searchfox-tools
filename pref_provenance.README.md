# ⚠️ SUPERSEDED by sfpref.py — read this first

**2026-08-01: GitHub code-search count is NOT a reliable pref-validity signal.**
Proven that day: `network.predictor.enabled` has 1436 GitHub refs and
`dom.events.asyncClipboard.clipboardItem` has 2136 — yet BOTH are REMOVED from current
Firefox (searchfox text: = 0). GitHub count is polluted by cargo-culted DEAD prefs in
thousands of stale user.js files; it certifies dead/fake prefs as "real." Do NOT use the
count as a validity verdict.

**Use `sfpref.py` instead** (searchfox `text:` per-pref = the real source, the authority).
This tool is kept only for its multi-source *plumbing*; its count-threshold verdicts are wrong.

---

# pref_provenance.py — independent pref truth-triangulator

Answers "is this a REAL Firefox pref or a Gemini/corruption hallucination?" using
trust roots NOT controlled by Mozilla (so it survives the "Mozilla-is-compromised"
threat model that defeats searchfox alone).

Two orthogonal axes (need BOTH):
1. INDEPENDENT CORROBORATION (catches hallucinations): GitHub code search count
   (via authenticated `gh api search/code`), arkenfox/user.js, Betterfox. A real
   pref has thousands of independent witnesses; an invented one has ~1 (only the
   corrupted fork that spawned it). Threshold rules-of-thumb: >=300 real upstream;
   10-300 real-but-uncommon/renamed; <10 fork-only (custom or fabricated); 0 pure invention.
2. CONSUMING-CODE (catches cargo-culted typos): local greprefs.js (default branch)
   + generated StaticPrefs_*.h accessors = what THIS build actually compiles. A pref
   with crowd-corroboration but no consumer is a propagated typo (inert here).

POLITENESS: GitHub code search is ~10/min authenticated — throttle 7s between queries.
Wayback CDX + Bugzilla REST are additional dated/provenance roots (wire in as needed).

Usage: python3 pref_provenance.py "pref.one" "pref.two" ...
Proven 2026-08-01: caught 8/21 fabricated prefs in config/firefox.js that searchfox
(Mozilla-controlled) + local grep had missed/mislabelled.
