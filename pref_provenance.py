import sys, subprocess, json, os
SD=os.path.dirname(os.path.abspath(__file__))
FF="/home/gorilla/firefox-main"
GREP=f"{FF}/obj-x86_64-pc-linux-gnu/dist/bin/greprefs.js"
SPGLOB=f"{FF}/obj-x86_64-pc-linux-gnu/dist/include/mozilla/StaticPrefs_*.h"
def in_file(k,p):
    try:return k in open(p,encoding='utf-8',errors='ignore').read()
    except:return False
def built(k):
    if in_file(k,GREP): return True
    # StaticPrefList accessor (mangled dots/hyphens -> underscores) — use proven grep
    mang=k.replace('.','_').replace('-','_')
    r=subprocess.run(f'grep -rlq "{mang}" {SPGLOB}',shell=True)
    return r.returncode==0
def gh(k):
    try:
        r=subprocess.run(["gh","api","-X","GET","search/code","-f",f'q="{k}"'],capture_output=True,text=True,timeout=45)
        if r.returncode==0:return json.loads(r.stdout).get("total_count",-1)
    except:pass
    return -1
def verdict(k,b,a,bt,g):
    indep=(a or bt or g>50)
    cust='gorilla' in k.lower()
    if b and cust: return "OUR CUSTOM (built + intentional)"
    if b and g>=800: return "REAL upstream (built + widely corroborated)"
    if b and indep: return "REAL (built + corroborated)"
    if b and not indep: return "SUSPECT INJECTED (built, ~nobody upstream)"
    if not b and g>50: return "STALE/CARGO-CULT (not in this build = INERT here)"
    return "HALLUCINATION (not built + ~nobody uses it)"
print(f"{'pref':52} built ark bet github   verdict")
for k in sys.argv[1:]:
    b=built(k);a=in_file(k,f"{SD}/arkenfox.user.js");bt=in_file(k,f"{SD}/betterfox.user.js");g=gh(k)
    print(f"{k:52}{'Y' if b else '.':^6}{'Y' if a else '.':^4}{'Y' if bt else '.':^4}{g:>6}  {verdict(k,b,a,bt,g)}")
