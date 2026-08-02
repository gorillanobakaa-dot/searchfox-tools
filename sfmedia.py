#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026  gorillanobakaa
# Part of searchfox-tools: https://github.com/gorillanobakaa-dot/searchfox-tools
"""sfmedia — media/gfx source-identifier & standards validator.

The pref suite (sfpref/sfconsumers/sfstandards) answers "is this PREF real?".
sfmedia answers the same question one level down, for the C++ patch layer:
"is this codec string / MIME type / vendor ID / feature constant REAL —
 who invented it, who governs it, and does the patch use it correctly?"

An invented identifier at this layer compiles fine and silently does the wrong
thing (a misspelled codec string simply never matches). So every token is
checked on these axes:

  GOVERNED   embedded standards registry: authority, inventor, status, citation.
             The authority list is COMPLETE and CLOSED — no "and others". Every
             body is defined in AUTHORITIES below (`registry` prints them):
             IETF, IANA, ISO/IEC JTC 1/SC 29 (MPEG), ITU-T, ITU-R, MP4RA (run
             by Apple for ISO), AOM, WebM Project, Matroska/IETF-CELLAR,
             Xiph.Org, WHATWG, PCI-SIG, freedesktop.org, Linux kernel, Mozilla.
  VANILLA    token exists in an UNTOUCHED Firefox tree (offline grep = ground
             truth; searchfox not required)
  OURS       token absent from vanilla -> must carry GORILLA provenance in the
             same patch, else INVENTED
  SEMANTICS  pair rules (hev1<->hvc1: blocking only one leaves a HEVC hole;
             vp09 <-> vp8/vp9: ISOBMFF vs WebM in-container names both needed)
  DOC-ONLY   token appears only in comments -> validated as documentation
             (a wrong pref name in a comment is doc-poison, not code-poison)

Pref-shaped tokens are additionally validated against StaticPrefList.yaml /
all.js, and against C++ Preferences::Get callsites (dynamic prefs like
media.hardware-video-decoding.failed are real but never declared).

Usage:
  sfmedia.py scan <patch-dir>...        extract + validate every token in *.patch
  sfmedia.py validate <token>...        validate individual tokens
  sfmedia.py registry                   dump the standards registry (who governs what)

Env (defaults are this project's layout; override for other checkouts):
  SFMEDIA_VANILLA  untouched Firefox tree   SFMEDIA_LIVE  patched Firefox tree
"""
import os, re, sys, glob, subprocess, collections

VANILLA = os.environ.get("SFMEDIA_VANILLA",
    "/home/gorilla/Documents/FIREFOX.WORK/Firefox.Scripts.Vault.Docs/SafetyVault.Firefox/firefox-main")
LIVE = os.environ.get("SFMEDIA_LIVE", "/home/gorilla/firefox-main")
# dirs that hold media/gfx truth; keeps the offline grep fast
GREP_DIRS = ["dom/media", "dom/html", "gfx", "widget", "media", "modules/libpref/init"]
PCI_IDS = "/usr/share/misc/pci.ids"

# ---------------------------------------------------------------- registry ---
# WHO THE AUTHORITIES ARE — complete, closed list. Anyone auditing this file can
# ask "who the hell is that?" about every name below and get an answer here.
# acronym -> (full name, who they actually are, what they govern in this build, url)
AUTHORITIES = {
 "IETF": ("Internet Engineering Task Force",
    "the internet's open standards body; publishes RFCs by rough consensus",
    "codecs= parameter (RFC 6381), Ogg (5334/7845), video/mp4 (4337), VP8 "
    "bitstream (6386), Matroska (9559), the x- prefix ban (6648)",
    "rfc-editor.org"),
 "IANA": ("Internet Assigned Numbers Authority",
    "the internet's registrar of protocol names/numbers (ICANN-operated, IETF policy)",
    "the MIME media-types registry (video/ogg IS in it; video/webm is NOT)",
    "iana.org/assignments/media-types"),
 "ISO/IEC JTC 1/SC 29": ("Joint ISO/IEC subcommittee 29 — the MPEG committee",
    "treaty-level international standards machinery; 'the MPEG people'",
    "ISOBMFF (14496-12), hev1/hvc1/avc1 carriage (14496-15), H.264 (14496-10), "
    "HEVC (23008-2)", "iso.org"),
 "ITU-T": ("International Telecommunication Union — Telecom Standardization Sector",
    "UN agency; co-signs H.264/H.265 with MPEG (identical twin text, two logos)",
    "H.264, H.265", "itu.int"),
 "ITU-R": ("ITU — Radiocommunication Sector",
    "same UN agency, broadcast side", "Rec. BT.709 colorimetry (our BT709 enums)",
    "itu.int"),
 "MP4RA": ("MP4 Registration Authority",
    "operated by APPLE INC. 'for the benefit of the standards community', on "
    "behalf of ISO/MPEG (verified mp4ra.org 2026-08-02)",
    "the FourCC code-point registry: av01, vp09, vp08, hev1, hvc1, avc1",
    "mp4ra.org"),
 "AOM": ("Alliance for Open Media",
    "industry consortium: Google, Mozilla, Netflix, Amazon, Cisco, Intel, "
    "Microsoft, Apple, et al. (founded 2015)",
    "AV1 and the 'av01' ISOBMFF binding", "aomedia.org"),
 "WebM Project": ("The WebM Project",
    "Google-stewarded open project born of the 2010 On2 acquisition",
    "WebM container profile, vp8/vp9 codecs= names, vp08/vp09 ISOBMFF binding, "
    "the de-facto (unregistered) video/webm MIME type", "webmproject.org"),
 "Matroska/CELLAR": ("Matroska.org + IETF CELLAR working group",
    "the container WebM is a profile of; standardized as RFC 9559 (Proposed "
    "Standard, Oct 2024)", "V_VP8/V_VP9 codec IDs, EBML structure",
    "matroska.org; rfc-editor.org/rfc/rfc9559"),
 "Xiph.Org": ("Xiph.Org Foundation",
    "non-profit for royalty-free media formats (Ogg, Vorbis, Opus, FLAC)",
    "the Ogg container; video/ogg (with IETF)", "xiph.org"),
 "WHATWG": ("Web Hypertext Application Technology Working Group",
    "the browser vendors themselves (Apple, Google, Mozilla, Microsoft) "
    "maintaining the HTML Living Standard",
    "canPlayType() return values: '' / 'maybe' / 'probably'",
    "html.spec.whatwg.org"),
 "PCI-SIG": ("PCI Special Interest Group",
    "the hardware consortium that assigns PCI vendor IDs; we check offline "
    "against Debian's pci.ids (community mirror pci-ids.ucw.cz of PCI-SIG data)",
    "vendor IDs 0x8086 Intel / 0x1002 AMD / 0x10de NVIDIA", "pcisig.com"),
 "freedesktop.org": ("freedesktop.org",
    "shared-infrastructure org of the Linux desktop", "hosts libva — VA-API "
    "(Intel-born, 2007)", "freedesktop.org"),
 "Linux kernel": ("The Linux kernel", "kernel.org",
    "dma-buf — the zero-copy buffer sharing the DMABUF path rides", "kernel.org"),
 "Mozilla": ("Mozilla",
    "Firefox's own project; ground truth = the vanilla tree + searchfox",
    "every MOZ-VANILLA identifier (nsIGfxInfo features, CANPLAY enums, StaticPrefs)",
    "searchfox.org"),
}
# token (lowercased key) -> (authority, inventor/origin, status, citation)
# Every entry was verified against the named source on the date in the citation.
REG = {
 # -- codec strings (the RFC 6381 codecs= parameter; FourCCs registered at MP4RA,
 #    the registration authority ISO appoints for ISOBMFF code-points) --
 "av01": ("AOM 'AV1 Codec ISO Media File Format Binding' + MP4RA",
          "Alliance for Open Media (2018)", "current",
          "MP4RA codecs registry (checked 2026-08-02): registered, AV1-ISOBMFF"),
 "vp09": ("WebM Project 'VP Codec ISO Media File Format Binding' + MP4RA",
          "Google / WebM Project", "current",
          "MP4RA: ObjectType 0xB1; string vp09.PP.LL.DD[+5 optional], first 4 mandatory"),
 "vp08": ("WebM Project VP-ISOBMFF binding + MP4RA", "Google / WebM Project",
          "current", "MP4RA (2026-08-02); altref caveat in binding spec"),
 "vp8":  ("WebM/Matroska codec ID V_VP8 (RFC 9559); bitstream RFC 6386",
          "Google (On2 lineage)", "current",
          "canPlayType 'video/webm; codecs=vp8'; RFC 9559 = Matroska (IETF CELLAR, Oct 2024)"),
 "vp9":  ("WebM/Matroska codec ID V_VP9 (RFC 9559); bitstream = Google spec, no RFC",
          "Google", "current", "RFC 9559 Matroska + WebM Project container guidelines"),
 "hev1": ("ISO/IEC 14496-15 (NALu structured video in ISOBMFF) + MP4RA",
          "MPEG (ISO/IEC JTC1/SC29); codec = ITU-T H.265 | ISO/IEC 23008-2",
          "current", "MP4RA: NALu Video, ObjectType 0x23; param sets MAY be in-band"),
 "hvc1": ("ISO/IEC 14496-15 + MP4RA",
          "MPEG; codec = ITU-T H.265 | ISO/IEC 23008-2", "current",
          "MP4RA: NALu Video, ObjectType 0x23; param sets ONLY in sample entry"),
 "avc1": ("ISO/IEC 14496-15 + MP4RA",
          "MPEG; codec = ITU-T H.264 | ISO/IEC 14496-10", "current",
          "MP4RA: ObjectType 0x21 — the ALLOWED codec in this build"),
 # -- MIME types (IANA media-types registry is the governing registry) --
 "video/ogg":  ("IANA media-types registry", "Xiph.Org / IETF", "REGISTERED",
                "IANA video.csv (checked 2026-08-02): RFC 5334 + RFC 7845"),
 "video/mp4":  ("IANA media-types registry", "MPEG / IETF", "REGISTERED",
                "IANA video.csv (2026-08-02): RFC 4337 + RFC 6381"),
 "video/webm": ("NONE — de-facto convention", "Google / WebM Project (2010)",
                "UNREGISTERED (de-facto, universally shipped)",
                "IANA video.csv (2026-08-02): absent from registry"),
 "video/x-webm": ("NONE — unregistered x- alias (RFC 6648 deprecates x- prefix)",
                "legacy server convention", "UNREGISTERED; absent from vanilla Firefox",
                "vault grep 2026-08-02: 0 hits in vanilla; OURS-DEFENSIVE dead-belt"),
 "video/vp8":  ("IANA (RTP payload format — NOT a container type)", "IETF payload WG",
                "REGISTERED for RTP only", "RFC 7741; do not confuse with video/webm"),
 # -- PCI vendor IDs (PCI-SIG assigns; verify offline against pci.ids) --
 "0x8086": ("PCI-SIG vendor ID", "PCI-SIG assignment", "current",
            "pci.ids (offline, 2026-08-02): 8086 = Intel Corporation"),
 "0x10de": ("PCI-SIG vendor ID", "PCI-SIG assignment", "current",
            "pci.ids: 10de = NVIDIA Corporation"),
 "0x1002": ("PCI-SIG vendor ID", "PCI-SIG assignment", "current",
            "pci.ids: 1002 = Advanced Micro Devices [AMD/ATI]"),
 # -- color / platform --
 "bt709": ("ITU-R Recommendation BT.709", "ITU-R (HDTV colorimetry)", "current",
           "Mozilla enums ColorSpace2/YUVColorSpace::BT709 encode the ITU standard"),
 "dmabuf": ("Linux kernel dma-buf subsystem", "Linux kernel (Sumit Semwal, 2012)",
            "current", "Feature::DMABUF = Mozilla gfxConfig wrapper of kernel facility"),
 "va-api": ("freedesktop libva", "Intel (2007), now freedesktop", "current",
            "runs in RDD process in this build (NOT the GPU process)"),
 # -- WHATWG-governed semantics --
 "canplay_no":    ("WHATWG HTML: canPlayType() -> ''", "WHATWG", "current",
                   "vanilla HTMLMediaElement.cpp maps CANPLAY_NO -> empty string"),
 "canplay_maybe": ("WHATWG HTML: canPlayType() -> 'maybe'", "WHATWG", "current",
                   "dom/media/mediaelement/HTMLMediaElement.cpp"),
}
# pair rules: (set-of-tokens, message) — all-or-none within one patch file
PAIRS = [
 ({"hev1","hvc1"}, "HEVC has TWO sample-entry FourCCs (14496-15); gating only one leaves the other playable"),
 ({"vp09"}, None),  # placeholder: vp09 handled with vp8/vp9 below
]

# ---------------------------------------------------------------- helpers ---
def _grep(token, root, dirs=GREP_DIRS, fixed=True):
    """offline ground-truth grep; returns first hit 'path:line' or None"""
    paths = [os.path.join(root, d) for d in dirs if os.path.isdir(os.path.join(root, d))]
    if not paths: return None
    cmd = ["grep", "-rn", "-m1", "-F" if fixed else "-E", token] + paths
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=300).stdout
        if out:
            line = out.split("\n", 1)[0]
            return line.replace(root + "/", "")[:160]
    except Exception:
        pass
    return None

def _pref_real(name, root):
    """a pref is real if declared (StaticPrefList/all.js) OR consumed dynamically
    (a C++ Preferences::Get* callsite names it — e.g. media.hardware-video-decoding.failed)"""
    init = os.path.join(root, "modules/libpref/init")
    hit = _grep(f'name: {name}', root, ["modules/libpref/init"]) \
       or _grep(f'"{name}"', root, ["modules/libpref/init"])
    if hit: return ("DECLARED", hit)
    hit = _grep(f'"{name}"', root, ["dom", "gfx", "widget", "media", "toolkit", "browser"])
    if hit: return ("DYNAMIC (C++ callsite)", hit)
    return (None, None)

PREF_RE = re.compile(r'^(?:media|gfx|layers|webgl|dom|widget|apz|image|browser|network|security)\.[a-z0-9_.-]{3,60}$')

def classify(token, ctx=None):
    """ctx: dict with 'comment_only': bool, 'patchfiles': set — from scan"""
    t = token.strip(); key = t.lower()
    rows = []
    # 1) standards registry
    if key in REG:
        auth, inv, status, cite = REG[key]
        v = "STANDARD" if "UNREGISTERED" not in status else "STANDARD*"
        rows.append((v, f"{auth} | {inv} | {status} | {cite}"))
    # 2) pref-shaped -> pref reality check against VANILLA
    if PREF_RE.match(t):
        kind, site = _pref_real(t, VANILLA)
        if kind: rows.append(("PREF-REAL", f"{kind} [{site}]"))
        else:
            kind2, site2 = _pref_real(t, LIVE)
            if kind2: rows.append(("PREF-OURS", f"{kind2} in LIVE only [{site2}]"))
            else:     rows.append(("PREF-INVENTED", "not declared, not consumed, in either tree"))
    # 3) vanilla existence (identifiers, strings)
    if not rows or rows[-1][0].startswith("PREF") is False:
        pass
    if not any(r[0].startswith(("STANDARD","PREF")) for r in rows):
        hit = _grep(t, VANILLA)
        if hit: rows.append(("MOZ-VANILLA", f"[{hit}]"))
        else:
            lh = _grep(t, LIVE)
            if lh:
                # ours -> provenance: GORILLA marker in the same live file?
                f = os.path.join(LIVE, lh.split(":", 1)[0])
                prov = False
                try: prov = "GORILLA" in open(f, encoding="utf-8", errors="replace").read()
                except Exception: pass
                rows.append(("OURS" if prov else "OURS-NO-PROVENANCE", f"[{lh}]"))
            else:
                rows.append(("INVENTED", "absent from vanilla AND live trees"))
    if ctx and ctx.get("comment_only"):
        rows.append(("DOC-ONLY", "appears only in comments — verify as documentation"))
    return rows

# ------------------------------------------------------------------- scan ---
STR_RE   = re.compile(r'"([^"\\]{2,80})"')
STATIC_RE= re.compile(r'StaticPrefs::([A-Za-z0-9_]+)\(\)')
SCOPED_RE= re.compile(r'\b([A-Z][A-Za-z0-9]+::[A-Za-z0-9_]+)')
CAPS_RE  = re.compile(r'\b(CANPLAY_[A-Z_]+|FEATURE_[A-Z0-9_]+|MOZ_[A-Z0-9_]+)\b')
PREFTOK_RE=re.compile(r'\b((?:media|gfx|layers|webgl|dom|widget|apz|image|browser|network|security)\.[a-z0-9_.-]{3,60})\b')

def extract(patch_dirs):
    inv = collections.defaultdict(lambda: {"files": set(), "n": 0, "code": 0, "comment": 0})
    for d in patch_dirs:
        for pf in sorted(glob.glob(os.path.join(d, "**", "*.patch"), recursive=True)):
            rel = os.path.basename(pf)
            for line in open(pf, encoding="utf-8", errors="replace"):
                if not line.startswith("+") or line.startswith("+++"): continue
                body = line[1:]
                stripped = body.lstrip()
                in_comment = stripped.startswith(("//", "/*", "*", "#"))
                toks = set()
                for m in STR_RE.finditer(body):
                    s = m.group(1)
                    if re.match(r'^[A-Za-z0-9!#$&^_.+/*-]+$', s) or "/" in s: toks.add(s)
                for rx in (STATIC_RE, SCOPED_RE, CAPS_RE, PREFTOK_RE):
                    for m in rx.finditer(body):
                        toks.add(m.group(1) if rx is not STATIC_RE else "StaticPrefs::" + m.group(1))
                for t in toks:
                    e = inv[t]; e["files"].add(rel); e["n"] += 1
                    e["comment" if in_comment else "code"] += 1
    return inv

def cmd_scan(dirs):
    inv = extract(dirs)
    print(f"# sfmedia scan — {len(inv)} distinct tokens from {dirs}\n")
    counts = collections.Counter(); flagged = []
    for t in sorted(inv):
        e = inv[t]
        ctx = {"comment_only": e["code"] == 0, "patchfiles": e["files"]}
        rows = classify(t, ctx)
        verdicts = "+".join(r[0] for r in rows)
        counts[rows[0][0]] += 1
        bad = any(r[0] in ("INVENTED", "PREF-INVENTED", "OURS-NO-PROVENANCE") for r in rows) \
              or (ctx["comment_only"] and any("PREF" in r[0] and "REAL" not in r[0] for r in rows))
        mark = "!!" if bad else "  "
        print(f"{mark} {t:52} {verdicts}")
        for v, why in rows: print(f"       {v}: {why}")
        if bad: flagged.append((t, rows, sorted(e['files'])))
    # pair rules per patch file
    print("\n# SEMANTIC PAIR RULES")
    byfile = collections.defaultdict(set)
    for t, e in inv.items():
        for f in e["files"]: byfile[f].add(t.lower())
    for f, toks in sorted(byfile.items()):
        if "hev1" in toks or "hvc1" in toks:
            ok = {"hev1", "hvc1"} <= toks
            print(f"  [{'PAIR-OK' if ok else 'PAIR-BROKEN'}] {f}: hev1/hvc1 "
                  f"{'both gated' if ok else 'ONLY ONE gated — HEVC hole'}")
        if ("vp09" in toks) or ("vp9" in toks):
            ok = {"vp09", "vp9"} <= toks
            print(f"  [{'PAIR-OK' if ok else 'PAIR-BROKEN'}] {f}: vp09(ISOBMFF)/vp9(WebM) "
                  f"{'both gated' if ok else 'one naming system missed'}")
    print(f"\n# verdict summary: {dict(counts)}")
    if flagged:
        print(f"\n# {len(flagged)} FLAGGED token(s):")
        for t, rows, files in flagged: print(f"  !! {t}  ({', '.join(files)})")
    else:
        print("\n# no invented/unprovenanced tokens — patch layer is clean")

def cmd_registry():
    print("# THE AUTHORITIES — complete and closed; there are no 'others'\n")
    for k, (full, who, governs, url) in AUTHORITIES.items():
        print(f"{k:20} {full}\n{'':20}   who:     {who}\n{'':20}   governs: {governs}\n{'':20}   where:   {url}")
    print("\n# TOKEN REGISTRY — who invented it, who governs it\n")
    for k, (auth, inv, status, cite) in REG.items():
        print(f"{k:16} governs: {auth}\n{'':16} origin:  {inv}\n{'':16} status:  {status}\n{'':16} proof:   {cite}\n")

if __name__ == "__main__":
    if len(sys.argv) < 2: print(__doc__); sys.exit(1)
    if sys.argv[1] == "scan" and len(sys.argv) > 2: cmd_scan(sys.argv[2:])
    elif sys.argv[1] == "validate" and len(sys.argv) > 2:
        for t in sys.argv[2:]:
            for v, why in classify(t): print(f"  {t:52} {v}: {why}")
    elif sys.argv[1] == "registry": cmd_registry()
    else: print(__doc__)
