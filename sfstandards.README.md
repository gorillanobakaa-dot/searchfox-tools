# sfstandards — the STANDARDS axis (layer 1 of the 4-layer pref trust hierarchy)

Maps a pref to its governing standard (IETF RFC / W3C / WHATWG) and reports whether the
CONCEPT is real and CURRENT vs LEGACY. Complements sfpref (searchfox = implementation).

Trust hierarchy (see DB atom Four_Layer_Pref_Trust_Hierarchy):
1. STANDARDS (this tool) — concept real? current or legacy?   [protocol + web-platform prefs]
2. searchfox (sfpref)    — does Firefox implement it?           [all prefs; sole authority for vendor prefs]
3. arkenfox/Betterfox    — reputable curation?                  [positive signal only]
4. GitHub crowd          — DISCARDED (cargo-cult + AI slop)

Legacy detection is the unique value: rfc-editor.org obsoleted_by catches whole-protocol
death (SPDY, TLS1.0/1.1); spec TEXT catches feature-level abandonment inside a current RFC
(HTTP pipelining in RFC9112). Vendor prefs (browser.ml.*, smartwindow) have NO standard —
use sfpref for those.

Usage: python3 sfstandards.py "pref.name"...
Seed keyword->RFC map; extend it. Verdict rules in the DB atom.
