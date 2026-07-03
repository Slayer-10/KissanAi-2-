import sys
sys.path.insert(0, ".")
from services.mandi_service import is_mandi_rate_query

tests = [
    "mere qareeb gandum ka mandi rate batao",
    "nearby wheat mandi rates",
    "\u06af\u0646\u062f\u0645 \u06a9\u0627 \u0645\u0646\u0688\u06cc \u0631\u06cc\u0679 \u0628\u062a\u0627\u0626\u06cc\u06ba",
    "Multan mein cotton ka rate kya hai?",
    "mandi rate batao",
    "gandum ka rate batao",
    "aaj aam ka mandi rate kya chal raha hai?",
    "nearby wheat mandi rates",
    "wheat price today",
    "gandum bhao batao",
]
print()
for t in tests:
    result = is_mandi_rate_query(t)
    status = "MATCH" if result else "MISS "
    print(f"  [{status}] {t}")
print()
