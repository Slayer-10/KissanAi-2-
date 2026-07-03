"""
Smoke-test for mandi_service.py — no server needed, runs offline.
"""
import sys
sys.path.insert(0, ".")

from services.mandi_service import (
    is_mandi_rate_query,
    extract_commodity,
    extract_city,
    handle_mandi_query,
)

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
errors = 0

def check(label, got, expected=True):
    global errors
    ok = got == expected
    mark = PASS if ok else FAIL
    print(f"  {mark}  {label}: got={got!r}")
    if not ok:
        errors += 1

print("\n── Intent Detection ─────────────────────────────")
check("RU: gandum ka mandi rate",   is_mandi_rate_query("mere qareeb gandum ka mandi rate batao"), True)
check("UR: منڈی ریٹ",               is_mandi_rate_query("گندم کا منڈی ریٹ بتائیں"), True)
check("EN: nearby wheat mandi",     is_mandi_rate_query("nearby wheat mandi rates"), True)
check("EN: market rate",            is_mandi_rate_query("Multan mein cotton ka market rate kya hai"), True)
check("Non-mandi: weather query",   is_mandi_rate_query("kal baarish hogi kya"), False)
check("Non-mandi: disease query",   is_mandi_rate_query("fazl par keeda lag raha hai"), False)

print("\n── Commodity Extraction ──────────────────────────")
check("wheat",  extract_commodity("gandum ka mandi rate"), "wheat")
check("cotton", extract_commodity("Multan mein cotton ka rate kya hai?"), "cotton")
check("mango",  extract_commodity("aaj aam ka mandi rate kya chal raha hai?"), "mango")
check("UR wheat", extract_commodity("گندم کا منڈی ریٹ بتائیں"), "wheat")
check("None",   extract_commodity("mujhe paani chahiye"), None)

print("\n── City Extraction ───────────────────────────────")
check("Multan",     extract_city("Multan mein gandum ka rate"), "Multan")
check("UR Multan",  extract_city("ملتان میں گندم کا ریٹ"), "Multan")
check("Lahore",     extract_city("Lahore mandi me chawal ka rate"), "Lahore")
check("RYK alias",  extract_city("rahim yar khan mandi"), "Rahim Yar Khan")
check("None",       extract_city("mere qareeb"), None)

print("\n── handle_mandi_query: city + commodity ──────────")
res = handle_mandi_query("Multan mein gandum ka mandi rate batao", None, None)
print(f"  farmer_response[:80] = {res['farmer_response'][:80]!r}")
print(f"  tts_summary[:80]     = {res['tts_summary'][:80]!r}")
print(f"  mandi_status         = {res['mandi_status']}")
check("has farmer_response", bool(res["farmer_response"]))
check("has tts_summary",     bool(res["tts_summary"]))
check("commodity=wheat",     res["mandi_status"]["commodity"], "wheat")
check("fallback_used=True",  res["mandi_status"]["fallback_used"], True)
check("results>0",           res["mandi_status"]["results_count"] > 0)

print("\n── handle_mandi_query: location + commodity ──────")
res2 = handle_mandi_query("mere qareeb gandum ka mandi rate batao", 30.1575, 71.5249)
print(f"  farmer_response[:80] = {res2['farmer_response'][:80]!r}")
check("has farmer_response", bool(res2["farmer_response"]))
check("results>0",           res2["mandi_status"]["results_count"] > 0)

print("\n── handle_mandi_query: Urdu ──────────────────────")
res3 = handle_mandi_query("گندم کا منڈی ریٹ بتائیں", None, None)
print(f"  farmer_response[:80] = {res3['farmer_response'][:80]!r}")
# Should ask for city/location since no city detected and no GPS
check("asks for location",   "لوکیشن" in res3["farmer_response"] or "شہر" in res3["farmer_response"] or "location" in res3["farmer_response"].lower() or "shehar" in res3["farmer_response"].lower())

print("\n── handle_mandi_query: no commodity ─────────────")
res4 = handle_mandi_query("mandi rate batao", 30.15, 71.52)
print(f"  farmer_response[:80] = {res4['farmer_response'][:80]!r}")
check("asks for commodity",  res4["mandi_status"]["commodity"] is None)

print(f"\n{'─'*50}")
if errors == 0:
    print(f"\033[92m All {6+5+5+5+2+1+1} checks passed.\033[0m\n")
else:
    print(f"\033[91m {errors} check(s) FAILED.\033[0m\n")
    sys.exit(1)
