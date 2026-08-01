#!/usr/bin/env python3
"""sfconsumers — CONSUMER ANALYSIS (the '#1 missing layer').
A searchfox hit proves a STRING is in source. It does NOT prove Firefox READS the pref.
This classifies WHERE the references live: real production consumer vs test vs definition-only.

  consumers <pref>...  -> DEFINED_AND_CONSUMED | TEST_ONLY | DEFINED_UNUSED | NOT_FOUND

Verdict is a floor, not a ceiling: DEFINED_AND_CONSUMED means 'code reads it', NOT
'changing it does what a recommendation claims' (that needs the runtime layer). Proven
2026-08-01 on knowns: widevinecdm/cache.disk/https_only/cookieBehavior all correctly CONSUMED."""
import sys, re, time
sys.path.insert(0, "/home/gorilla/Documents/Scripts.For.Work/searchfox-tools")
import searchfox_tools as sf

def classify_path(p):
    pl = p.lower()
    # definition sites: not evidence of consumption
    if re.search(r'staticpreflist|/all\.js|firefox\.js|__generated__|greprefs|featuremanifest|/profile/', pl):
        return 'DEF'
    # test harnesses: not production reachability
    if re.search(r'/test/|/tests/|test_|browser_[a-z].*\.js|mochitest|xpcshell|/gtest/|/wpt|reftest|\.test\.', pl):
        return 'TEST'
    # real code that references the pref = a consumer
    if re.search(r'\.(cpp|cc|h|mjs|jsm|js|rs|webidl)$', pl):
        return 'CONSUMER'
    return 'OTHER'

def consumers(pref):
    try:
        hits = sf.search(f'text:{pref}', use_cache=True, limit=400)
    except Exception as e:
        return ("QUERY_FAILED", {}, [])
    cats = {}
    examples = []
    for p, l, line in hits:
        c = classify_path(p)
        cats[c] = cats.get(c, 0) + 1
        if c == 'CONSUMER' and len(examples) < 3:
            examples.append(f"{p}:{l}")
    if not hits:
        return ("NOT_FOUND", cats, [])
    cons, test, dfn = cats.get('CONSUMER', 0), cats.get('TEST', 0), cats.get('DEF', 0)
    if cons > 0:   v = "DEFINED_AND_CONSUMED"
    elif dfn > 0 and test > 0: v = "TEST_ONLY"
    elif dfn > 0:  v = "DEFINED_UNUSED"
    elif test > 0: v = "TEST_ONLY"
    else:          v = "REFERENCED_ELSEWHERE (inspect manually)"
    return (v, cats, examples)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: sfconsumers.py <pref>..."); sys.exit(1)
    for pref in sys.argv[1:]:
        v, cats, ex = consumers(pref)
        print(f"  {pref:48} {v}")
        print(f"    breakdown={cats}" + (f"  e.g. {ex[0]}" if ex else ""))
        time.sleep(1.2)
