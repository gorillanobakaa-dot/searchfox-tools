# sfconsumers — CONSUMER ANALYSIS (axis 2: is the pref actually READ?)

The #1 layer missing from every "the string exists, therefore it's real" check. A searchfox hit
proves a *string* is in Firefox source; it does **not** prove Firefox *reads* the pref. This
classifies **where** the references live.

**LAYMAN.** The switch-is-actually-wired check. If a setting's name only shows up in the master
list of defaults, or only in test files, then nothing in the real browser reads it — the switch
isn't connected to anything.

**DEVELOPER.** Buckets every reference:
- **DEF** (definition site — not consumption): `StaticPrefList`, `all.js`, `firefox.js`,
  `__generated__`, `greprefs`, `featuremanifest`, `/profile/`.
- **TEST** (not production reachability): `/test/`, `/tests/`, `test_`, mochitest, xpcshell,
  gtest, wpt, reftest.
- **CONSUMER** (real code that reads it): `.cpp` `.cc` `.h` `.mjs` `.jsm` `.js` `.rs` `.webidl`
  outside the above.

```bash
python3 sfconsumers.py <pref>...
#   DEFINED_AND_CONSUMED  -> production code reads it   (CONSUMER > 0)
#   TEST_ONLY             -> only defined + tested, no consumer
#   DEFINED_UNUSED        -> defined, never read        -> drop
#   NOT_FOUND             -> no references at all        -> likely fabricated / removed
```

## Honest limit
The verdict is a **floor, not a ceiling.** `DEFINED_AND_CONSUMED` means "code reads it" — it does
**not** mean "changing it does what a hardening list claims." That is a separate axis (runtime
effect). Proven 2026-08-01 on knowns (`widevinecdm`, `cache.disk`, `https_only_mode`,
`cookieBehavior` all correctly `DEFINED_AND_CONSUMED` with real consumer counts).

## Where it fits
Axis 2 of the five-axis method. See `PREF_VALIDATION.md` for the full pipeline and the cheap-first
walk. Companion tools: `sfpref.py` (axis 1, EXISTS), `sfstandards.py` (CURRENT / standards).
Politeness inherited from `searchfox_tools.py` (1 s throttle, 24 h cache); CLI adds a 1.2 s
per-pref pause.
