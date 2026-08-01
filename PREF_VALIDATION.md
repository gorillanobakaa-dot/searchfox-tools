# Firefox pref validation — the five-axis method

**Is this `about:config` preference real, and does it belong in a hardened build?**
That is not one question. It is *five*, and the whole point of this suite is that they must be
answered separately. Answering only the first one — the mistake almost every tool and every
AI-generated "hardening list" makes — is how dead, useless, and actively harmful prefs end up
shipped as "verified."

This document is written in two tracks: a **LAYMAN** track (plain English, no jargon) and a
**DEVELOPER** track (the mechanics). Read whichever you need; they say the same thing at
different depths.

---

## The core mistake this fixes

**LAYMAN.** Finding a setting's name inside Firefox's code is like finding a light switch on a
wall. It tells you the switch *exists*. It does **not** tell you whether the switch is wired to
anything, whether the bulb it controls is already on, whether flipping it actually changes the
room, or whether it is a builder's test switch left in the wall that does nothing at all. Each of
those is a separate thing you have to check. Someone who says "I found the switch, therefore the
setting is real and worth flipping" has checked exactly one of five things — and it's the one
that proves the least.

**DEVELOPER.** A searchfox text hit proves **EXISTS** and nothing else. The old pipeline
collapsed five orthogonal questions into a single "REAL / keep" verdict. They are independent and
must be decided independently:

| # | Axis | The question | Answered by |
|---|------|--------------|-------------|
| 1 | **EXISTS** | Is the string in Firefox source at all? | `sfpref.py` (searchfox `text:` / `regexp`) |
| 2 | **CONSUMED** | Does *production code* actually read it, or is it only defined / test-only? | `sfconsumers.py` |
| 3 | **ALIVE** | Is Mozilla's intent that this is a permanent control — or a killswitch / experiment / migration pref that's on its way out? | *(designed, human-in-the-loop — Bugzilla)* |
| 4 | **EFFECTIVE** | When you actually change it, does the claimed effect measurably happen? | *(designed — runtime harness, per-category assertions)* |
| 5 | **SAFE** | Is the effect useful, non-redundant, non-conflicting, and backed by a real threat model? | *(human — threat model + dependency graph)* |
| — | **CURRENT** | Is the underlying *concept / standard* real and current, or a legacy feature browsers abandoned? | `sfstandards.py` |

Only a pref that clears every axis that *applies to it* is a genuine KEEP. Axes 1, 2 and the
standards check are built and cheap. Axes 3–5 are progressively more expensive and the last is
irreducibly human — this document is honest about that (see [Honest status](#honest-status)).

---

## Who do you trust? (the trust hierarchy)

**LAYMAN.** At the end of the day you have to trust *someone*, so trust the right someone for the
right question. The people who **invented** the thing (standards bodies) tell you whether it's a
real idea and whether it's current or dead. The people who **built Firefox** (searchfox, the
index Mozilla's own engineers use) tell you whether Firefox actually has that setting and reads
it. Respected hardening curators (arkenfox, Betterfox) tell you whether a setting is worth
changing. And the random crowd on GitHub tells you **nothing but noise** — the same 1999-era
setting copied into a thousand config files, plus AI-generated lists inventing settings that were
never real.

**DEVELOPER.** Four layers, each competent for a *different* question. They are not sequential
gates; they are families you consult by pref type.

1. **STANDARDS** — IETF RFCs (via `rfc-editor.org` JSON: `status` / `obsoleted_by`), W3C/WHATWG
   specs, and the wider normative families (see `sfstandards.py`). *Is the concept real, and is
   it current or legacy?* Applies to protocol and web-platform prefs. **Skip it for vendor
   prefs** (`browser.ml.*`, `smartwindow`, activity-stream) — they have no external standard.
2. **SEARCHFOX** — mozilla-central, the real engineers' index. *Does Firefox implement it, and
   does production code consume it?* The sole authority for vendor prefs.
3. **CURATORS** — arkenfox/user.js, Betterfox. *Is it a reputable hardening recommendation?*
   **Positive signal only:** present = meaningful; absent = inconclusive (they curate a subset).
4. **GITHUB CROWD** — **DISCARDED.** Code-search *count* is an anti-signal.

### Why GitHub count is discarded (proven, not asserted)

**LAYMAN.** A setting being copied into thousands of files online does not make it real. Dead
settings get copied *more*, because nobody prunes them.

**DEVELOPER.** Measured 2026-08-01:

| Pref | GitHub refs | searchfox `text:` | Reality |
|------|-------------|-------------------|---------|
| `network.predictor.enabled` | 1436 | 0 | **removed** from Firefox |
| `dom.events.asyncClipboard.clipboardItem` | 2136 | 0 | **removed** from Firefox |

GitHub count **certifies dead and fabricated prefs as real.** It is gameable by AI-slop flooding
and polluted by cargo-culted stale `user.js` files. This is why `pref_provenance.py` — which was
built on that signal — is **SUPERSEDED** (see below), and why its verdicts must not be used.

---

## The tools

All four are zero-dependency Python 3, sit on top of `searchfox_tools.py`, and inherit its
politeness (≥1 s throttle, 24 h cache). They talk only to `searchfox.org` (and, for the standards
axis, `rfc-editor.org`).

### `sfpref.py` — axis 1, EXISTS

**LAYMAN.** Answers "is this a real Firefox setting, or invented?" and "what *are* all the real
settings under this family?" — straight from Firefox's own source.

**DEVELOPER.** Tames the searchfox firehose by querying *definition patterns* via regexp, so you
get real prefs instead of every incidental mention. A plain `media.` search returns ~1108 noisy
lines; `pref\("media\.` regexp returns ~100 clean definitions with values and citations.

```bash
python3 sfpref.py enumerate media.gmp      # authoritative list under a namespace, with values
python3 sfpref.py validate  <pref>...       # REAL / FAKE(+nearest real name) per pref
```

### `sfconsumers.py` — axis 2, CONSUMED (the #1 missing layer)

**LAYMAN.** This is the switch-is-actually-wired check. It looks at *where* in the code the
setting's name appears. If it only appears in the list of default settings, or only in test
files, then nothing in the real browser reads it — the switch isn't wired to anything.

**DEVELOPER.** Classifies where every reference lives: **definition sites** (`StaticPrefList`,
`all.js`, `firefox.js`, generated files) and **test dirs** are *not* evidence of consumption; a
reference in real component code (`.cpp`/`.cc`/`.h`/`.mjs`/`.jsm`/`.js`/`.rs`/`.webidl`) is.

```bash
python3 sfconsumers.py <pref>...
#   -> DEFINED_AND_CONSUMED | TEST_ONLY | DEFINED_UNUSED | NOT_FOUND  (+ breakdown, example sites)
```

Verdict is a **floor, not a ceiling**: `DEFINED_AND_CONSUMED` means "code reads it," not "changing
it does what a recommendation claims" — that needs axis 4. Proven 2026-08-01 on knowns
(`widevinecdm`, `cache.disk`, `https_only_mode`, `cookieBehavior` all correctly consumed).

### `sfstandards.py` — the CURRENT axis (standards / normative status)

**LAYMAN.** Checks whether the *idea* behind a setting is a real, current web standard — or a
dead one that browsers ripped out years ago. Some settings look modern but control 20-year-old
technology.

**DEVELOPER.** Maps a pref (by keyword) to its governing standard and reports current vs legacy.
For IETF prefs it fetches the live `rfc-editor.org` status (`obsoleted_by` catches whole-protocol
death: SPDY → HTTP/2, TLS 1.0/1.1 → RFC 8996). Feature-level abandonment *inside* a current RFC
(e.g. HTTP pipelining in RFC 9112 §9.3.2) needs the spec **text**, not the status field. The seed
map covers the extended normative families beyond IETF/W3C — TC39/ECMA-262, Unicode + CLDR, IANA
registries, Khronos, WebGPU/WGSL, CA/Browser Forum + Mozilla Root Store, ISO/MPEG/AOM, OpenType —
because for several of these, status alone is insufficient (codecs ship or don't based on patents
+ OS decoder + build config, not spec maturity). Extend the `KW` map freely.

```bash
python3 sfstandards.py "network.http.http3.enable" "network.http.pipelining"
```

#### The behavior-not-technology correction (important)

**LAYMAN.** "This setting is about old technology, so drop it" is wrong. A setting about an
obsolete feature can be *valuable* precisely because it **turns that feature off**. Judge what the
setting's *value* does, not the age of the thing it names.

**DEVELOPER.** Do **not** use the old absolute "obsoleted-standard → drop" rule. Classify the
behaviour the pref *value* produces:

| The pref value... | Verdict |
|---|---|
| `enable obsolete protocol = true` | DROP / REJECT |
| `disable obsolete-protocol fallback = true` | **KEEP** — this *is* the hardening |
| `control migration from an obsolete mechanism` | TEMPORARY / lifecycle-dependent |
| no-op compatibility pref | DROP |

### `pref_provenance.py` — ⚠️ SUPERSEDED, kept for the record

**LAYMAN.** An earlier attempt that trusted "how many times is this copied on GitHub" as proof a
setting is real. That turned out to be exactly backwards (see the table above). It is kept here,
clearly marked, so the mistake and its correction stay on the record — not because you should use
it.

**DEVELOPER.** Built on GitHub code-search count, which is an anti-signal. Its build-detection
plumbing (checking the objdir `greprefs.js` and generated `StaticPrefs_*.h`) is sound; its
count-threshold *verdicts* are wrong. Use `sfpref.py` + `sfconsumers.py` instead. Retained under
the project's append-only / radical-transparency convention.

---

## How to actually use them (cheap-first walk)

**LAYMAN.** Check the cheap things first and throw out the obvious junk before spending effort on
the hard checks.

**DEVELOPER.** Per pref, walk the axes cheapest-first and stop as soon as a disqualifier fires:

1. `sfpref validate` → **EXISTS?** FAKE → drop (record nearest real name for a possible rename).
2. `sfconsumers` → **CONSUMED?** `DEFINED_UNUSED` / `TEST_ONLY` → drop.
3. Local default compare (objdir `dist/bin/greprefs.js`) → **REDUNDANT_DEFAULT?** → drop unless
   you specifically want policy-pinning. *(This is the highest-noise-reduction cheap check and is
   the recommended next build — see status below.)*
4. Type / range / gating from `StaticPrefList.yaml` → `WRONG_TYPE` / `INVALID_VALUE` /
   `NIGHTLY_ONLY` / `BUILD_GATED` / `PLATFORM_GATED`.
5. `sfstandards` → **CURRENT?** (concept real; apply behaviour-not-technology; skip for vendor prefs).
6. Lifecycle (Bugzilla) → **ALIVE?** killswitch / rollback / experiment vs permanent control.
7. Runtime assert (per category) → **EFFECTIVE?** `SILENTLY_IGNORED` / `MISSING_DEPENDENCY` / `SHADOWED`.
8. Threat model + conflict graph → **SAFE?** (human).

Only a pref that clears every applicable step is KEEP.

---

## Honest status

**LAYMAN.** Not all five checks are automated. The first two and the standards check are built and
proven. The last three are harder — one of them (is it genuinely more secure?) can't be fully
automated at all and needs a human. This document does not pretend otherwise.

**DEVELOPER.**

| Axis / check | Status |
|---|---|
| 1. EXISTS (`sfpref.py`) | **BUILT**, proven |
| 2. CONSUMED (`sfconsumers.py`) | **BUILT**, proven on knowns |
| CURRENT / standards (`sfstandards.py`) | **BUILT** (seed map; extend families) |
| default-compare `REDUNDANT_DEFAULT` (local, objdir) | **BUILDABLE** — recommended next |
| type / value / gating (local, `StaticPrefList.yaml`) | **BUILDABLE** |
| 3. ALIVE / lifecycle (Bugzilla) | **DESIGNED** — semi-automatable, interpretive |
| 4. EFFECTIVE / runtime | **DESIGNED** — scaffold; assertions are human-authored per category |
| 5. SAFE / threat model + dependency graph | **HUMAN** — cannot be fully automated |

"More restrictive" ≠ "more secure." A restriction with no threat, no protected asset, and no
measured effect is security theatre, not hardening.

---

## Provenance

Author: the project owner with Fable5 / Claude. Method verified 2026-08-01. Part of the
`searchfox-tools` suite (AGPL-3.0). The private design-of-record with the full decision tree and
the complete union of output states lives in the project's patch tree; this file is the public,
self-contained version. Tools live beside this doc; each also carries a `# CHANGELOG` /
`.README.md`. Do not fork tools into `_v2` files — edit in place and bump the header.
