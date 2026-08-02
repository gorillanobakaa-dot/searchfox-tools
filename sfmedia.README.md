# sfmedia — media/gfx source-identifier & standards validator

## LAYMAN track

The pref tools answer "is this *setting* real, or did an AI invent it?".
`sfmedia` asks the same question about the deeper layer — the C++ patches
themselves. When a patch says *"refuse to play `vp09`"*, that string `vp09` is
not Firefox's invention: it is a **registered code-point in a public standard**,
governed by a real organization. If an AI had quietly written `vp90` instead,
the compiler would not complain — the string would simply never match, and the
protection would silently not exist. That is the failure class this tool hunts.

So for every name a patch uses, sfmedia asks three questions a human auditor
would ask:

1. **Who invented this, and who governs it today?** — `av01` belongs to the
   Alliance for Open Media; `hev1`/`hvc1` to MPEG's ISO/IEC 14496-15; `video/ogg`
   is registered at IANA; PCI vendor ID `0x8086` is Intel, assigned by PCI-SIG.
   The tool carries a registry of these facts, each with the source it was
   checked against and the date.
2. **Does vanilla Firefox actually contain this identifier?** — checked by
   searching an untouched copy of the Firefox source kept offline. No trust in
   memory, no trust in search-engine popularity.
3. **If it's OUR addition — does it say so?** — anything absent from vanilla
   must carry a `GORILLA` provenance comment, or it is flagged.

Plus two subtleties that caught real bugs:

- **Pair rules**: HEVC has *two* names (`hev1` and `hvc1`). Block only one and
  the other still plays — a hole. The tool verifies pairs travel together.
- **Comment poison**: a wrong name in a *comment* compiles fine and misleads
  every future auditor. First real catch: a comment cited the pref
  `media.rdd-ffmpeg.vaapi` — which does not exist (real name:
  `media.rdd-ffmpeg.enabled`). Found in two files, fixed in three places.

### Who exactly are the authorities (there are no "others")

Every standards body this tool cites, by full name. If a name is not in this
table, the tool does not lean on it. `sfmedia.py registry` prints the same list.

| Acronym | Full name | Who they actually are | Governs here |
|---|---|---|---|
| IETF | Internet Engineering Task Force | the internet's open standards body; publishes RFCs by rough consensus | `codecs=` parameter (RFC 6381), Ogg (5334/7845), video/mp4 (4337), VP8 bitstream (6386), Matroska (9559), x- prefix ban (6648) |
| IANA | Internet Assigned Numbers Authority | the internet's registrar of names and numbers (ICANN-operated, IETF policy) | the MIME registry — `video/ogg` is in it, `video/webm` is not |
| ISO/IEC JTC 1/SC 29 | Joint ISO/IEC subcommittee 29 | treaty-level standards machinery — "the MPEG people" | ISOBMFF (14496-12), `hev1`/`hvc1`/`avc1` (14496-15), H.264 (14496-10), HEVC (23008-2) |
| ITU-T | Int'l Telecommunication Union, Telecom Standardization | UN agency; co-signs H.264/H.265 with MPEG — identical twin text, two logos | H.264, H.265 |
| ITU-R | ITU, Radiocommunication Sector | same UN agency, broadcast side | BT.709 colorimetry (our `BT709` enums) |
| MP4RA | MP4 Registration Authority | operated by **Apple Inc.** "for the benefit of the standards community", on behalf of ISO/MPEG (verified mp4ra.org, 2026-08-02) | the FourCC registry: `av01` `vp09` `hev1` `hvc1` `avc1` |
| AOM | Alliance for Open Media | consortium: Google, Mozilla, Netflix, Amazon, Cisco, Intel, Microsoft, Apple… (2015) | AV1 + the `av01` binding |
| WebM Project | The WebM Project | Google-stewarded open project from the 2010 On2 acquisition | WebM container, `vp8`/`vp9` names, `vp08`/`vp09` binding, de-facto `video/webm` |
| Matroska/CELLAR | Matroska.org + IETF CELLAR WG | the container WebM is a profile of; RFC 9559 (Proposed Standard, Oct 2024) | `V_VP8`/`V_VP9` codec IDs, EBML |
| Xiph.Org | Xiph.Org Foundation | non-profit for royalty-free media (Ogg, Vorbis, Opus, FLAC) | Ogg; `video/ogg` |
| WHATWG | Web Hypertext Application Technology Working Group | the browser vendors themselves (Apple, Google, Mozilla, Microsoft), HTML Living Standard | `canPlayType()` → `""`/`"maybe"`/`"probably"` |
| PCI-SIG | PCI Special Interest Group | the hardware consortium that assigns PCI vendor IDs; checked offline against Debian's `pci.ids` (community mirror of PCI-SIG data) | `0x8086` Intel, `0x1002` AMD, `0x10de` NVIDIA |
| freedesktop.org | — | shared-infrastructure org of the Linux desktop | hosts libva — VA-API (Intel-born, 2007) |
| Linux kernel | — | kernel.org | dma-buf (the zero-copy path DMABUF rides) |
| Mozilla | — | Firefox's own project; ground truth = vanilla tree + searchfox | every MOZ-VANILLA identifier |

## DEVELOPER track

```
sfmedia.py scan <patch-dir>...    # extract + validate every token in *.patch files
sfmedia.py validate <token>...    # validate individual tokens
sfmedia.py registry               # dump the standards registry with citations
```

Token extraction (added `+` lines only): string literals, `StaticPrefs::x()`,
`Scope::Identifier`, `CANPLAY_*/FEATURE_*/MOZ_*` constants, pref-shaped names.

Verdicts, in evaluation order:

| verdict | meaning |
|---|---|
| `STANDARD` | in the embedded registry — governed by MP4RA / IANA / IETF / ISO / ITU-R / AOM / WebM / PCI-SIG / WHATWG, citation included |
| `STANDARD*` | documented but **unregistered** (e.g. `video/webm` is absent from IANA — de-facto only) |
| `PREF-REAL` | pref-shaped token declared in StaticPrefList/all.js **or** consumed by a C++ `Preferences::Get*` callsite (dynamic prefs like `media.hardware-video-decoding.failed` are real but never declared) |
| `PREF-INVENTED` | pref-shaped token with neither declaration nor callsite in either tree |
| `MOZ-VANILLA` | identifier found in the untouched vault tree (offline ground truth) |
| `OURS` | absent from vanilla, present in live, `GORILLA` provenance in the file |
| `OURS-NO-PROVENANCE` | ours but unmarked — violates the project's transparency rule |
| `INVENTED` | in neither tree — red flag |
| `+DOC-ONLY` | token appears only in comment lines — judged as documentation |

Environment: `SFMEDIA_VANILLA` (untouched tree), `SFMEDIA_LIVE` (patched tree).
Offline-first: existence checks grep local trees; nothing requires searchfox.
The registry facts were each verified against the named authority
(MP4RA codecs registry, IANA `video.csv`, rfc-editor JSON, `pci.ids`) — dates
in the entries.

### Grep traps encoded (learned the hard way)

- **X-macro constants are invisible to naive greps**: `FEATURE_H264_HW_DECODE`
  is *not* declared in `nsIGfxInfo.idl` — it is generated by
  `GFXINFO_FEATURE(H264_HW_DECODE, ...)` in `widget/GfxInfoFeatureDefs.inc`
  (statuses in `GfxInfoFeatureStatusDefs.inc`). Grep the `.inc` list files.
- **Dynamic prefs**: runtime-written prefs never appear in StaticPrefList; the
  proof of life is the C++ callsite.
- **`media.ffmpeg.vaapi.enabled` no longer exists in Firefox 154** — the only
  surviving `vaapi` pref is `media.ffmpeg.vaapi.force-surface-zero-copy`;
  RDD/VA-API enablement rides `media.rdd-ffmpeg.enabled`.

First production run (2026-08-02, 01.MEDIA + 02.GPU, 62 tokens): 12 STANDARD,
2 STANDARD*, 40 MOZ-VANILLA, 6 OURS (all provenanced), 1 PREF-REAL(dynamic),
1 PREF-INVENTED (comment-only — fixed). Both pair rules PAIR-OK.
