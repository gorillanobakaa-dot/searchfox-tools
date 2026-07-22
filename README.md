# searchfox_tools — Firefox source intelligence on someone else's compute

**`fx searchfox <cmd>`** — query [searchfox.org](https://searchfox.org), Mozilla's semantic
index of Firefox's ~30 million lines of source, and get structured answers back. The heavy
lifting — cross-references, symbol graphs, "who uses this" — runs on **Mozilla's servers, not
your machine.** That's the entire point.

> Built for a Sony VAIO with an Ivy Bridge i7 and 16 GB of DDR3L. Grepping 30M LOC locally is
> a coffee-break; Searchfox already has it indexed. So we let *them* do the compute and just
> ask questions. Zero dependencies, caches its answers, and it's polite about it.

---

## Table of contents
1. [30-second version](#30-second-version)
2. [The story — why this exists (and why it almost didn't)](#the-story)
3. [Install](#install)
4. [The commands](#the-commands)
5. [The killer app: safe asset shimming](#the-killer-app-safe-asset-shimming)
6. [Searchfox query reference (the operators)](#searchfox-query-reference)
7. [How it works under the hood](#how-it-works-under-the-hood)
8. [For AI agents landing cold](#for-ai-agents-landing-cold)
9. [Adapting it](#adapting-it)
10. [Triple redundancy — where this lives](#triple-redundancy)
11. [Provenance & versioning](#provenance--versioning)

---

## 30-second version
```bash
fx searchfox search "AudioStream" --path dom/media   # find it
fx searchfox symbol AudioStream                      # definitions + usages (semantic)
fx searchfox blast-radius AudioStream                # every file that touches it, ranked
fx searchfox svg-keeplist arrow-down.svg             # is this asset used? KEEP vs SAFE-TO-SHIM
```
No alias needed — it's part of `fx`. (Standalone: `python3 modules/searchfox_tools.py …`.)

---

## The story
Someone had a genuinely smart idea: instead of burning the VAIO's CPU mapping Firefox source,
**hijack Mozilla's own infrastructure** — Searchfox indexes all 30M LOC with full semantic
understanding, for free, on their servers. A tool was built around it (`searchfox_tools.py`,
7 functions including `blast_radius`), and it worked.

Then an agent deleted the tree it lived in (`FIrefox.153.Work`). The file was gone.

**But it came back** — because the *method* had been documented in the brain: a 1,057-line API
reference, the function inventory, and a sample of its output. It was reconstructed from those
records in an afternoon. The file was disposable; the knowledge wasn't.

**That is why this README exists in three places** (see [below](#triple-redundancy)). A tool
this useful should never again live somewhere a single `rm -rf` can end it.

---

## Install
Nothing to install. Requirements:
- **Python 3** (stdlib only — no `pip install` anything; deliberately dependency-free).
- **Network** — it talks to `searchfox.org`. First query is live; repeats are cached.

```bash
fx searchfox --help
# or standalone:
python3 ~/Documents/FIREFOX.WORK/gorilla-firefox-toolkit/modules/searchfox_tools.py --help
```

---

## The commands
| Command | What it does |
|---|---|
| `search "<q>" --path dom/media` | raw search; add `--regexp` / `--case` |
| `symbol AudioStream` | semantic definitions + usages of a symbol |
| `includers AudioStream.h` | files that `#include` a header |
| `deps <path>` | a file's own `#include` dependencies |
| `blast-radius AudioStream` | **impact map** — every file referencing a name, ranked by hits |
| `map <symbol>` | class/relationship + context view |
| `svg-keeplist arrow-down.svg` | **is this SVG referenced? KEEP vs SAFE-TO-SHIM** |
| `file dom/media/AudioStream.cpp` | raw source URL |

**Global flags:** `--repo` (default `firefox-main`), `--all-platforms` (disable the Linux-only
noise filter), `--no-cache`. Results are Linux/GTK-filtered by default (drops
android/windows/cocoa/ios/bsd) — because this project targets Linux and the rest is noise.

---

## The killer app: safe asset shimming
The "ghost shim" technique — replacing decorative PNG/SVG assets with 0-byte or 63-byte stubs —
saved *tens of MB*. It worked. But run blind, it also shimmed the tiny SVGs that Firefox's ~46
`about:` pages use for their **controls** (checkboxes, chevrons, arrows), breaking them. The
missing piece was never the ablator — it was a **keep-list**: which assets are functionally used.

Now that exists, and it's built on Mozilla's index instead of local grep:
```bash
fx searchfox svg-keeplist arrow-down.svg
#   VERDICT: KEEP (referenced — do NOT shim)
#     · browser/components/preferences/dialogs/sitePermissions.css
#     · browser/components/sidebar/sidebar-history.css   ... (39 files)

fx searchfox blast-radius warning.svg     # decorative? few/no refs → safe to shim
```
**Workflow:** run `svg-keeplist` over the asset set → build the KEEP list → feed it to
`fx brand shim` as an exclusion → shim only what's decorative. The good technique, now guided.

---

## Searchfox query reference
The power is in the operators. **All `term:value` operators must come BEFORE free text.**

| Operator | Meaning | Example |
|---|---|---|
| `symbol:NAME` | semantic symbol (prefix) — defs + xrefs, no comments/strings | `symbol:AudioStream` |
| `id:NAME` | exact identifier (no prefix bleed) | `id:createGain` |
| `text:STRING` | literal full-text (comments, strings, macros, `#ifdef`) | `text:MOZ_PULSEAUDIO` |
| `re:REGEX` | full-text regex (RE2 — no lookaheads) | `re:promote_current_thread\(` |
| `path:GLOB [term]` | inline path filter (positive-include only) | `path:dom/media audio` |
| `pathre:REGEX [term]` | regex path filter (supports negative lookahead) | `pathre:^(?!.*(android\|windows)).*$ AudioStream` |
| `context:N …` | N context lines (only with `text:`/`re:`) | `context:5 re:lto` |

**Path globs:** `*` = one segment, `**` = crosses `/`, `^`/`$` = anchors, `{a,b}` = alternation.
E.g. `^dom/media/**.{cpp,h,rs}$` = C++/Rust anywhere under dom/media.

**Linux guards** (for `#ifdef` searches): `XP_LINUX`, `XP_UNIX`, `MOZ_WIDGET_GTK`, `MOZ_PULSEAUDIO`,
`MOZ_ALSA`. Platform dirs: `widget/gtk/` (Linux), `widget/windows/`, `widget/cocoa/`, `mobile/android/`.

*(The complete 1,057-line reference — every operator, the full source-tree map, URL-encoding
table, and per-subsystem examples — lives in the brain as `searchfox_agent_reference.xml`.)*

---

## How it works under the hood
- Hits `https://searchfox.org/{repo}/search?q=…` with `Accept: application/json`, parses the JSON
  defensively (Searchfox nests results by kind; the tool flattens to `(path, line, text)`).
- **Cache:** every response is stored in `~/.cache/searchfox_tools/` (1-day TTL). Repeat queries
  are instant and don't touch the network.
- **Polite:** ≥1s between live requests, a real User-Agent, retry-with-backoff on 429/5xx. We're
  borrowing Mozilla's compute — we don't hammer it.
- **Linux filter:** `is_linux_path()` drops other-platform paths by default.

---

## For AI agents landing cold
If you're an agent working on Firefox source: **use Searchfox before opening files.** Random
file-browsing wastes turns; Searchfox gives you the exact cross-references. Decision tree:
- Known symbol (class/fn/var)? → `fx searchfox symbol NAME`
- "What breaks if I change X?" → `fx searchfox blast-radius X` (the impact map — check this
  BEFORE any excision/shim/refactor; it's the guard against the "correct locally, catastrophic
  globally" failure mode).
- Comment/string/macro/`#ifdef`? → `search "text:…"` or `--regexp`.
- Is an asset safe to remove? → `fx searchfox svg-keeplist asset.svg`.

**Never mass-modify or ablate assets without running `blast-radius`/`svg-keeplist` first.** That
omission is exactly what broke the 46 about: pages.

---

## Adapting it
Edit the constants at the top of `searchfox_tools.py`:
- `DEFAULT_REPO` — `firefox-main` (also `firefox-beta`, `firefox-esr140`, `glean`, `nss`, …).
- `CACHE_TTL` / `SEARCHFOX_CACHE` env — cache lifetime / location.
- `MIN_INTERVAL` — request throttle (be polite).
- `_OTHER_PLATFORM` — the noise-filter regex, if you target a different platform.

---

## Triple redundancy
This tool died once from living in one place. It now exists in **three**, on purpose:
1. **Canonical / live** — `gorilla-firefox-toolkit/modules/searchfox_tools.py` (run via `fx searchfox`).
2. **Brain backup** — copied into `SECOND.BRAIN/` alongside the `searchfox_agent_reference.xml`
   that saved it, so the tool AND its method sit together.
3. **GitHub** — pushed to a remote, so an `rm -rf` of the laptop can't end it.

If you're reading this after a loss: the method to rebuild from scratch is the brain's
`searchfox_agent_reference.xml` (1057 lines) + `SearchFox_Agent.xml` (function inventory).

---

## Provenance & versioning
`searchfox_tools.py` carries a `# VERSION | UPDATED | STATUS` header + `# CHANGELOG`. To change
it: **edit the file, bump the version, add a changelog line** — never fork into `_v2`. Current:
**v2.0.0** — resurrected + zero-dep + cache + politeness + Linux filter + CLI + `fx searchfox`.

*Local, private, dependency-free. Talks only to searchfox.org (Mozilla's public index).*
