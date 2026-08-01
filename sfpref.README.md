# sfpref — searchfox-backed Firefox pref enumerator/validator

Solves "is this a REAL pref or Gemini slop?" and "what ARE the real prefs under X?"
using searchfox (mozilla-central) — the index real Mozilla engineers use — with its
REGEXP query mode to filter to pref DEFINITIONS at the source, so you never sift the
firehose (a plain `media.` search = 1108 noisy lines; `pref\("media\.` regexp = ~100
clean definitions).

## Why this beats the alternatives (learned 2026-08-01)
- Local greps: FAILED ~9 ways (scattered pref files, version skew, mangled accessors).
- GitHub code-search count: gameable by AI-slop flooding + polluted by cargo-culted
  DEAD prefs (e.g. media.getusermedia.aec_enabled shows 149 GitHub hits but searchfox
  says 0 — the real name is media.getusermedia.audio.processing.aec.enabled).
- searchfox regexp: authoritative, structured (Core/Generated/Test), shows the built
  output, not floodable. THE primary authority.

## Usage
  python3 sfpref.py enumerate <namespace>   # e.g. "media.gmp" -> 35 real prefs + values + citations
  python3 sfpref.py validate  <pref>...      # REAL / FAKE(+nearest real name)

## The key technique
searchfox `regexp=true` with definition patterns:
  pref\("<ns>          -> all.js/firefox.js/generated defaults (with values)
  - name: <ns>         -> StaticPrefList.yaml entries
Politeness: inherits searchfox_tools 1s throttle + 24h cache. For version skew
(nightly vs release) query --repo mozilla-release.

## Honest limits
- searchfox = nightly by default; a pref real-in-154-removed-in-nightly reads as gone
  (use mozilla-release channel).
- Single trust root (Mozilla) — but the realistic threat (GitHub slop) favors it.
- nearest-real-name heuristic is basic; REAL/FAKE verdict is solid, use enumerate for
  the exact rename.
