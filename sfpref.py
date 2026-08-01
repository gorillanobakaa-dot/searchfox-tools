#!/usr/bin/env python3
"""sfpref — searchfox-backed Firefox pref tool. Tames the searchfox firehose by
querying REGEXP definition-patterns only, so you get real prefs, not media.play().

  enumerate <namespace>   authoritative list of real prefs under a namespace
  validate  <pref>...     REAL / FAKE(+nearest real name) per pref, from the source

Authority = searchfox (mozilla-central), the index real Mozilla engineers use.
Politeness inherited from searchfox_tools (1s throttle, 24h cache)."""
import sys, re, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import searchfox_tools as sf

def _hits(regex):
    # search() returns [(path,lno,line)]; we pass a raw regexp
    try: return sf.search(regex, regexp=True, use_cache=True, limit=4000)
    except Exception: return []

def enumerate_ns(ns):
    nse = re.escape(ns)
    defs = {}          # key -> (value, site)
    static = {}        # key -> site  (StaticPrefList, value lives on following lines)
    # 1) pref("ns...", value)  — all.js / firefox.js / generated defaults
    for p,l,line in _hits(rf'pref\("{nse}'):
        m = re.search(r'pref\("([^"]+)"\s*,\s*(.+?)\)\s*;', line)
        if m and m.group(1).startswith(ns): defs.setdefault(m.group(1), (m.group(2).strip(), f"{p}:{l}"))
    # 2) - name: ns...  — StaticPrefList.yaml
    for p,l,line in _hits(rf'- name: {nse}'):
        m = re.search(r'- name:\s*(\S+)', line)
        if m and m.group(1).startswith(ns): static.setdefault(m.group(1), f"{p}:{l}")
    allkeys = sorted(set(defs) | set(static))
    return defs, static, allkeys

def cmd_enumerate(ns):
    defs, static, allkeys = enumerate_ns(ns)
    print(f"# authoritative real prefs under '{ns}*' (searchfox mozilla-central): {len(allkeys)}\n")
    for k in allkeys:
        if k in defs: v,site = defs[k]; print(f"  {k} = {v:<28} [{site}]")
        else:         print(f"  {k}   (StaticPrefList) [{static[k]}]")

def cmd_validate(prefs):
    # group by namespace prefix (first 2 dotted segments) to reuse enumerations
    print(f"{'pref':52} verdict")
    cache={}
    for pref in prefs:
        ns = ".".join(pref.split(".")[:2])
        if ns not in cache: cache[ns]=enumerate_ns(ns)[2]
        real = cache[ns]
        if pref in real: print(f"{pref:52} REAL")
        else:
            near=[k for k in real if k.split('.')[-1]==pref.split('.')[-1] or pref.rsplit('.',1)[0]==k.rsplit('.',1)[0]]
            print(f"{pref:52} FAKE" + (f"  -> nearest real: {near[:3]}" if near else "  (no near name — likely invented)"))

if __name__=="__main__":
    if len(sys.argv)<3: print(__doc__); sys.exit(1)
    if sys.argv[1]=="enumerate": cmd_enumerate(sys.argv[2])
    elif sys.argv[1]=="validate": cmd_validate(sys.argv[2:])
    else: print(__doc__)
