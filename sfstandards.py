#!/usr/bin/env python3
"""sfstandards — the STANDARDS axis (layer 1) for pref validation.
Maps a pref to its governing standard and reports: concept real? current or legacy?
Complements sfpref (implementation/searchfox) + arkenfox (curation). GitHub crowd = discarded.

  standards <pref>...   -> per-pref: standard, status (current/obsoleted/legacy-feature)

SEED map (extend freely). Authority: rfc-editor.org (IETF) + known W3C/WHATWG specs +
a hand-curated legacy-feature set (things technically in a current spec but abandoned)."""
import sys, re, json, urllib.request, time

# keyword (matched against pref name) -> (standard-id, kind)
KW = [
    ("http.http3","RFC9000 QUIC","ietf"), ("http.http2","RFC9113 HTTP/2","ietf"),
    ("http.pipelining","RFC9112 HTTP/1.1 sec9.3.2","legacy"),  # spec-permitted but browser-abandoned
    ("spdy","SPDY","legacy"), ("trr","RFC8484 DoH","ietf"), ("dns.","RFC1035 DNS","ietf"),
    ("websocket","RFC6455 WebSocket","ietf"), ("tls.version.1.","RFC8996 (TLS1.0/1.1 deprecated)","legacy"),
    ("vp8","RFC6386 VP8","ietf"), ("vp9","VP9 (VPx, no core RFC)","codec"), ("av1","AV1 (AOMedia)","codec"),
    ("h264","H.264 ITU-T H.264","codec"), ("opus","RFC6716 Opus","ietf"),
    ("peerconnection","W3C WebRTC","w3c"), ("getusermedia","W3C Media Capture","w3c"),
    ("wakelock","W3C Screen Wake Lock","w3c"), ("asyncclipboard","W3C Async Clipboard","w3c"),
    ("indexeddb","W3C IndexedDB","w3c"), ("webauth","W3C WebAuthn / FIDO2 CTAP","w3c"),
    ("page_visibility","W3C Page Visibility","w3c"),
    # extended families (2026-08-01) — status alone is often NOT enough; note the caveat kind
    ("javascript.options","ECMA-262 / TC39 (check proposal stage; withdrawn?)","tc39"),
    ("intl.","Unicode CLDR + ECMA-402 Intl","unicode"),
    ("network.idn","Unicode IDNA (UTS-46) + IANA","unicode"),
    ("webgl","Khronos WebGL/GLSL (+ OpenGL ES)","khronos"),
    ("webgpu","W3C WebGPU + WGSL (experimental ecosystem)","webgpu"), ("dom.webgpu","W3C WebGPU + WGSL","webgpu"),
    ("security.cert","CA/Browser Forum BR + Mozilla Root Store Policy","pki"),
    ("security.pki","Mozilla Root Store Policy + CA/B Forum","pki"),
    ("security.ssl","CA/B Forum + IETF TLS","pki"),
    ("media.mp4","ISO/IEC 14496 (MP4/MPEG) — patents+OS-decoder+build gate shipping","iso"),
    ("media.av1","AOMedia AV1 — royalty-free but build/dav1d gated","codec"),
    ("gfx.font","OpenType spec (font shaping/variable fonts)","opentype"),
    # IANA registry note: an RFC can DEFINE a thing the IANA registry marks deprecated/provisional/reserved
    ("network.http.accept","IANA HTTP field/content-coding registries","iana"),
    ("network.security","IANA TLS parameters registry + IETF","iana"),
]
LEGACY_NOTE = {"legacy":"LEGACY — spec-permitted/obsoleted but abandoned in browsers; drop"}
_cache={}
def rfc_status(num):
    if num in _cache: return _cache[num]
    try:
        d=json.load(urllib.request.urlopen(urllib.request.Request(
            f"https://www.rfc-editor.org/rfc/rfc{num}.json",
            headers={"User-Agent":"gorilla-standards/1.0 (research)"}),timeout=15))
        ob=d.get("obsoleted_by") or []
        _cache[num]=("OBSOLETED_BY "+str(ob)) if ob else "current"
    except Exception: _cache[num]="?"
    time.sleep(0.6); return _cache[num]
def check(pref):
    p=pref.lower()
    for kw,std,kind in KW:
        if kw in p:
            extra=""
            m=re.match(r"RFC(\d+)",std)
            if kind=="ietf" and m: extra=" ["+rfc_status(m.group(1))+"]"
            if kind=="legacy": extra=" [LEGACY — abandoned in browsers]"
            return f"{std}{extra} ({kind})"
    return "no standard mapped (seed map — extend, or likely Firefox-internal/vendor pref)"
if __name__=="__main__":
    for pref in sys.argv[1:]:
        print(f"  {pref:52} {check(pref)}")
