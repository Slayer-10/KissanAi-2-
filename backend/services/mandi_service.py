"""
FarmAI — Mandi Rates Service
Detects mandi-rate queries, fetches live rates from AMIS Punjab,
falls back to mock data if live fetch fails, and formats responses
in Urdu, Roman Urdu, or English depending on query language.
"""

import re
import math
import logging
import requests
from datetime import date
from typing import Optional

try:
    from bs4 import BeautifulSoup
    _BS4_AVAILABLE = True
except ImportError:
    _BS4_AVAILABLE = False

logger = logging.getLogger(__name__)

# ─── AMIS Commodity IDs (discovered from live site) ────────────────────────────
_AMIS_COMMODITY_IDS = {
    "wheat":     1,
    "rice":      4,
    "maize":     17,
    "sugarcane": 125,
    "cotton":    49,   # Seed Cotton (Phutti)
    "mango":     48,   # Mango Chounsa
    "potato":    21,   # Potato Fresh
    "onion":     23,
    "tomato":    26,
}

_AMIS_BASE_URL = "http://www.amis.pk/ViewPrices.aspx"
_AMIS_TIMEOUT  = 7  # seconds — short so app never hangs

# ─── Commodity Keyword Mapping (EN / RU / UR) ──────────────────────────────────
_COMMODITY_KEYWORDS = {
    "wheat":     ["wheat", "gandum", "گندم"],
    "cotton":    ["cotton", "kapas", "kapaas", "کپاس"],
    "mango":     ["mango", "aam", "آم"],
    "rice":      ["rice", "chawal", "چاول"],
    "maize":     ["maize", "makai", "makki", "مکئی"],
    "sugarcane": ["sugarcane", "ganna", "گنا"],
    "potato":    ["potato", "aloo", "آلو"],
    "onion":     ["onion", "piyaz", "pyaz", "پیاز"],
    "tomato":    ["tomato", "tamatar", "ٹماٹر"],
}

# All commodity keywords flattened (for commodity+price-word detection)
_ALL_COMMODITY_WORDS = [kw for kws in _COMMODITY_KEYWORDS.values() for kw in kws]

# ─── Pakistani City → (lat, lon) ────────────────────────────────────────────────
_MANDI_LOCATIONS = {
    "Multan":         (30.1575, 71.5249),
    "Khanewal":       (30.3006, 71.9322),
    "Lodhran":        (29.5340, 71.6327),
    "Bahawalpur":     (29.3956, 71.6836),
    "Vehari":         (30.0450, 72.3484),
    "Sahiwal":        (30.6706, 73.1062),
    "Faisalabad":     (31.4504, 73.1350),
    "Lahore":         (31.5204, 74.3587),
    "Gujranwala":     (32.1877, 74.1945),
    "Rawalpindi":     (33.5651, 73.0169),
    "Islamabad":      (33.7294, 73.0931),
    "DG Khan":        (30.0577, 70.6352),
    "Muzaffargarh":   (30.0728, 71.1928),
    "Rahim Yar Khan": (28.4202, 70.2952),
    "Sukkur":         (27.7052, 68.8574),
    "Hyderabad":      (25.3960, 68.3578),
    "Karachi":        (24.8607, 67.0011),
}

# ─── City Name Aliases ──────────────────────────────────────────────────────────
_CITY_ALIASES = {
    "multan": "Multan",
    "ملتان": "Multan",
    "khanewal": "Khanewal",
    "خانیوال": "Khanewal",
    "lodhran": "Lodhran",
    "bahawalpur": "Bahawalpur",
    "بہاولپور": "Bahawalpur",
    "vehari": "Vehari",
    "وہاری": "Vehari",
    "sahiwal": "Sahiwal",
    "ساہیوال": "Sahiwal",
    "faisalabad": "Faisalabad",
    "فیصل آباد": "Faisalabad",
    "fsd": "Faisalabad",
    "lahore": "Lahore",
    "لاہور": "Lahore",
    "gujranwala": "Gujranwala",
    "گوجرانوالہ": "Gujranwala",
    "rawalpindi": "Rawalpindi",
    "راولپنڈی": "Rawalpindi",
    "pindi": "Rawalpindi",
    "islamabad": "Islamabad",
    "اسلام آباد": "Islamabad",
    "dg khan": "DG Khan",
    "dera ghazi khan": "DG Khan",
    "ڈیرہ غازی خان": "DG Khan",
    "muzaffargarh": "Muzaffargarh",
    "مظفرگڑھ": "Muzaffargarh",
    "rahim yar khan": "Rahim Yar Khan",
    "رحیم یار خان": "Rahim Yar Khan",
    "ryk": "Rahim Yar Khan",
    "sukkur": "Sukkur",
    "سکھر": "Sukkur",
    "hyderabad": "Hyderabad",
    "حیدرآباد": "Hyderabad",
    "karachi": "Karachi",
    "کراچی": "Karachi",
}

# ─── Fallback Mock Rates (Rs/maund unless noted) ────────────────────────────────
_FALLBACK_RATES = {
    "wheat": {
        "unit": "Rs/maund",
        "mandis": [
            {"name": "Multan",         "min": 3600, "max": 3760, "avg": 3680},
            {"name": "Khanewal",       "min": 3560, "max": 3720, "avg": 3640},
            {"name": "Lodhran",        "min": 3550, "max": 3690, "avg": 3620},
            {"name": "Bahawalpur",     "min": 3540, "max": 3680, "avg": 3610},
            {"name": "Vehari",         "min": 3550, "max": 3700, "avg": 3625},
            {"name": "Sahiwal",        "min": 3570, "max": 3730, "avg": 3650},
            {"name": "Faisalabad",     "min": 3600, "max": 3750, "avg": 3675},
            {"name": "Lahore",         "min": 3610, "max": 3760, "avg": 3685},
            {"name": "Gujranwala",     "min": 3590, "max": 3740, "avg": 3665},
            {"name": "Rawalpindi",     "min": 3620, "max": 3780, "avg": 3700},
            {"name": "DG Khan",        "min": 3530, "max": 3680, "avg": 3605},
            {"name": "Muzaffargarh",   "min": 3540, "max": 3690, "avg": 3615},
            {"name": "Rahim Yar Khan", "min": 3520, "max": 3670, "avg": 3595},
        ]
    },
    "cotton": {
        "unit": "Rs/maund",
        "mandis": [
            {"name": "Multan",         "min": 18000, "max": 19500, "avg": 18750},
            {"name": "Khanewal",       "min": 17800, "max": 19200, "avg": 18500},
            {"name": "Lodhran",        "min": 17600, "max": 19000, "avg": 18300},
            {"name": "Bahawalpur",     "min": 17900, "max": 19400, "avg": 18650},
            {"name": "Rahim Yar Khan", "min": 17700, "max": 19100, "avg": 18400},
            {"name": "Vehari",         "min": 17850, "max": 19300, "avg": 18575},
            {"name": "Faisalabad",     "min": 18100, "max": 19600, "avg": 18850},
        ]
    },
    "mango": {
        "unit": "Rs/maund",
        "mandis": [
            {"name": "Multan",         "min": 2500,  "max": 5000,  "avg": 3750},
            {"name": "Rahim Yar Khan", "min": 2400,  "max": 4800,  "avg": 3600},
            {"name": "Bahawalpur",     "min": 2600,  "max": 5200,  "avg": 3900},
            {"name": "Lahore",         "min": 3000,  "max": 6000,  "avg": 4500},
            {"name": "Karachi",        "min": 3500,  "max": 7000,  "avg": 5250},
        ]
    },
    "rice": {
        "unit": "Rs/maund",
        "mandis": [
            {"name": "Lahore",         "min": 4500, "max": 5500, "avg": 5000},
            {"name": "Gujranwala",     "min": 4400, "max": 5400, "avg": 4900},
            {"name": "Faisalabad",     "min": 4350, "max": 5300, "avg": 4825},
            {"name": "Rawalpindi",     "min": 4600, "max": 5600, "avg": 5100},
            {"name": "Sahiwal",        "min": 4300, "max": 5200, "avg": 4750},
        ]
    },
    "maize": {
        "unit": "Rs/maund",
        "mandis": [
            {"name": "Faisalabad",     "min": 1400, "max": 1700, "avg": 1550},
            {"name": "Sahiwal",        "min": 1380, "max": 1680, "avg": 1530},
            {"name": "Lahore",         "min": 1450, "max": 1750, "avg": 1600},
            {"name": "Gujranwala",     "min": 1420, "max": 1720, "avg": 1570},
            {"name": "Rawalpindi",     "min": 1480, "max": 1780, "avg": 1630},
        ]
    },
    "sugarcane": {
        "unit": "Rs/maund",
        "mandis": [
            {"name": "Faisalabad",     "min": 380, "max": 420, "avg": 400},
            {"name": "Lahore",         "min": 375, "max": 415, "avg": 395},
            {"name": "Sahiwal",        "min": 370, "max": 410, "avg": 390},
            {"name": "Gujranwala",     "min": 380, "max": 420, "avg": 400},
            {"name": "Multan",         "min": 365, "max": 405, "avg": 385},
        ]
    },
    "potato": {
        "unit": "Rs/100kg",
        "mandis": [
            {"name": "Lahore",         "min": 3500, "max": 5000, "avg": 4250},
            {"name": "Faisalabad",     "min": 3400, "max": 4800, "avg": 4100},
            {"name": "Sahiwal",        "min": 3300, "max": 4700, "avg": 4000},
            {"name": "Rawalpindi",     "min": 3600, "max": 5200, "avg": 4400},
            {"name": "Multan",         "min": 3800, "max": 5400, "avg": 4600},
        ]
    },
    "onion": {
        "unit": "Rs/100kg",
        "mandis": [
            {"name": "Lahore",         "min": 4000, "max": 7000, "avg": 5500},
            {"name": "Faisalabad",     "min": 3800, "max": 6800, "avg": 5300},
            {"name": "Multan",         "min": 3600, "max": 6500, "avg": 5050},
            {"name": "Karachi",        "min": 4500, "max": 8000, "avg": 6250},
            {"name": "Hyderabad",      "min": 4200, "max": 7500, "avg": 5850},
        ]
    },
    "tomato": {
        "unit": "Rs/100kg",
        "mandis": [
            {"name": "Lahore",         "min": 5000, "max": 12000, "avg": 8500},
            {"name": "Faisalabad",     "min": 4800, "max": 11500, "avg": 8150},
            {"name": "Rawalpindi",     "min": 5200, "max": 12500, "avg": 8850},
            {"name": "Multan",         "min": 6000, "max": 14000, "avg": 10000},
            {"name": "Karachi",        "min": 5500, "max": 13000, "avg": 9250},
        ]
    },
}

# ─── Intent Detection ─────────────────────────────────────────────────────────────
# Strategy: match any mandi/market keyword phrase, OR a commodity word + price word combo.
#
# Tier-1: explicit mandi/rate phrases (very high precision)
_TIER1_PHRASES = [
    # Roman Urdu phrases
    "mandi rate", "mandi rates", "mandi rete", "mandi ka rate", "mandi ka rete",
    "mandi price", "mandi prices", "mandi mein rate", "mandi mein price",
    "ka mandi rate", "ka rate kya hai", "ka rate batao", "ka rate bata",
    "ka bhav", "ka bhaav", "ka bhao", "mandi bhav", "mandi bhaav", "mandi bhao",
    "nearby mandi", "qareeb mandi", "qareeb ki mandi",
    "aaj ka rate", "aaj ka mandi", "aaj ka bhav", "aaj ka bhao",
    "today rate", "today mandi", "today price",
    "market rate", "market price", "market rates", "market prices",
    "fasal ka rate", "fasal ka bhav", "crop rate", "crop price", "crop rates",
    "near me rate", "near me mandi", "nearby rate",
    # Urdu script
    "منڈی ریٹ", "منڈی ریٹس", "منڈی قیمت", "منڈی ریٹ بتائیں",
    "منڈی بھاؤ", "منڈی نرخ", "منڈی میں ریٹ",
    "ریٹ بتائیں", "ریٹ کیا ہے", "قیمت بتائیں",
    "آج کا ریٹ", "آج کا بھاؤ", "آج کی قیمت",
    "نرخ بتائیں",
]

# Tier-2: standalone mandi/price words that alone signal mandi intent
_TIER2_MANDI_WORDS = [
    "mandi",      # Roman Urdu standalone
    "منڈی",       # Urdu standalone
]

# Price/rate signal words (used with commodity check in tier-3)
_PRICE_WORDS = [
    "rate", "rates", "rete", "price", "prices", "bhav", "bhaav", "bhao",
    "qeemat", "keemat", "qimat", "narakh", "nrakh",
    "ریٹ", "قیمت", "بھاؤ", "نرخ",
]


def is_mandi_rate_query(text: str) -> bool:
    """
    Return True if the user text is asking about mandi/market rates.

    Detection tiers:
      Tier-1: explicit mandi/rate phrase match (e.g. "mandi rate", "منڈی ریٹ")
      Tier-2: standalone "mandi" or "منڈی" word in text
      Tier-3: commodity word + price word in same text (e.g. "gandum rate batao")
    """
    if not text:
        return False

    logger.info("[MANDI] raw_text=%s", text[:120])
    text_lower = text.lower()

    # Tier-1: explicit phrase match
    for phrase in _TIER1_PHRASES:
        if phrase.lower() in text_lower or phrase in text:
            logger.info("[MANDI] intent_detected=true (tier1_phrase=%s)", phrase)
            return True

    # Tier-2: standalone mandi word
    for mw in _TIER2_MANDI_WORDS:
        if mw.lower() in text_lower or mw in text:
            logger.info("[MANDI] intent_detected=true (tier2_mandi_word=%s)", mw)
            return True

    # Tier-3: commodity word + price word
    has_commodity = any(kw.lower() in text_lower or kw in text for kw in _ALL_COMMODITY_WORDS)
    has_price_word = any(pw.lower() in text_lower or pw in text for pw in _PRICE_WORDS)
    if has_commodity and has_price_word:
        logger.info("[MANDI] intent_detected=true (tier3: commodity+price_word)")
        return True

    logger.info("[MANDI] intent_detected=false")
    return False


def extract_commodity(text: str) -> Optional[str]:
    """Extract commodity name from user text. Returns normalized key like 'wheat'."""
    if not text:
        return None
    text_lower = text.lower()
    for commodity, keywords in _COMMODITY_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in text_lower or kw in text:
                logger.info("[MANDI] commodity=%s", commodity)
                return commodity
    return None


def extract_city(text: str) -> Optional[str]:
    """Extract city name from user text. Returns canonical city name or None."""
    if not text:
        return None
    text_lower = text.lower()
    for alias, canonical in _CITY_ALIASES.items():
        if alias.lower() in text_lower or alias in text:
            logger.info("[MANDI] city=%s", canonical)
            return canonical
    return None


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the great-circle distance in km between two lat/lon points."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def get_nearby_mandis(
    latitude: Optional[float],
    longitude: Optional[float],
    city: Optional[str] = None,
    top_n: int = 5,
) -> list:
    """
    Return list of mandis sorted by distance.
    Each item: {'name': ..., 'lat': ..., 'lon': ..., 'distance_km': ...}
    """
    mandis = []
    for mandi_name, (mlat, mlon) in _MANDI_LOCATIONS.items():
        if latitude is not None and longitude is not None:
            dist = _haversine_km(latitude, longitude, mlat, mlon)
        elif city and city.lower() == mandi_name.lower():
            dist = 0.0
        else:
            dist = None
        mandis.append({"name": mandi_name, "lat": mlat, "lon": mlon, "distance_km": dist})

    # City mentioned → put that city first, sort rest by distance if GPS available
    if city:
        mandis = sorted(
            mandis,
            key=lambda m: (0 if m["name"] == city else 1, m["distance_km"] if m["distance_km"] is not None else 99999)
        )
    elif latitude is not None and longitude is not None:
        mandis = sorted(mandis, key=lambda m: m["distance_km"] if m["distance_km"] is not None else 99999)

    return mandis[:top_n]


# ─── Live AMIS Fetch ────────────────────────────────────────────────────────────
_AMIS_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Connection": "keep-alive",
}


def _parse_amis_price_table(html: str, mandi_list: list) -> list:
    """
    Parse the AMIS ViewPrices.aspx HTML.
    Tries multiple parsing strategies to handle different AMIS page layouts.
    Returns list of {name, min, max, avg, unit, distance_km, source}.
    """
    if not _BS4_AVAILABLE:
        logger.warning("[MANDI] BeautifulSoup not installed — cannot parse AMIS HTML")
        return []

    soup = BeautifulSoup(html, "html.parser")
    results = []
    mandi_names_lower = {m["name"].lower(): m for m in mandi_list}

    # Detect unit from page heading or title
    unit = "Rs/maund"
    for tag in soup.find_all(["h1", "h2", "h3", "p", "span"]):
        tag_text = tag.get_text(" ", strip=True)
        if "100Kg" in tag_text or "100kg" in tag_text or "100 kg" in tag_text.lower():
            unit = "Rs/100kg"
            break
        if "quintal" in tag_text.lower():
            unit = "Rs/quintal"
            break

    tables = soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        if len(rows) < 3:
            continue

        # Build header index
        header_row = rows[0]
        headers = [c.get_text(" ", strip=True).replace("\xa0", " ").lower()
                   for c in header_row.find_all(["td", "th"])]

        # Flexible header detection
        min_idx = max_idx = name_idx = None
        for i, h in enumerate(headers):
            if h in ("min", "minimum", "min price", "min."):
                min_idx = i
            elif h in ("max", "maximum", "max price", "max."):
                max_idx = i
            elif i == 0:
                name_idx = 0  # first column is usually the mandi/location name

        if min_idx is None or max_idx is None:
            # Try to find numeric columns by scanning a few data rows
            for row in rows[1:4]:
                cols = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
                numeric_cols = [i for i, c in enumerate(cols) if re.search(r"\d{3,}", c)]
                if len(numeric_cols) >= 2:
                    min_idx = numeric_cols[0]
                    max_idx = numeric_cols[1]
                    break

        if min_idx is None or max_idx is None:
            continue

        for row in rows[1:]:
            cols = [c.get_text(" ", strip=True).replace("\xa0", " ") for c in row.find_all(["td", "th"])]
            if not cols or len(cols) <= max(min_idx, max_idx):
                continue

            row_text = cols[0].lower() if cols else ""

            for mandi_key, mandi_info in mandi_names_lower.items():
                # Partial match — e.g. "multan" in "Multan Grain Market"
                if mandi_key in row_text:
                    try:
                        mn_str = re.sub(r"[^\d]", "", cols[min_idx])
                        mx_str = re.sub(r"[^\d]", "", cols[max_idx])
                        if mn_str and mx_str:
                            mn = int(mn_str)
                            mx = int(mx_str)
                            if mn > 0 and mx > 0 and mx >= mn:
                                avg = (mn + mx) // 2
                                # Avoid duplicates
                                already = any(r["name"] == mandi_info["name"] for r in results)
                                if not already:
                                    results.append({
                                        "name": mandi_info["name"],
                                        "min": mn,
                                        "max": mx,
                                        "avg": avg,
                                        "unit": unit,
                                        "distance_km": mandi_info.get("distance_km"),
                                        "source": "AMIS / live source",
                                    })
                    except Exception:
                        pass

    return results


def fetch_live_amis_rates(commodity: str, mandi_list: list) -> list:
    """
    Try to fetch live rates from AMIS Punjab.
    Returns parsed results or empty list on any failure.
    Never raises — safe to call from the main handler.
    """
    cid = _AMIS_COMMODITY_IDS.get(commodity)
    if not cid:
        logger.info("[MANDI] live_fetch_attempt=false (no_commodity_id)")
        return []

    url = f"{_AMIS_BASE_URL}?searchType=0&commodityId={cid}"
    logger.info("[MANDI] live_fetch_attempt=true url=%s", url)

    try:
        res = requests.get(url, timeout=_AMIS_TIMEOUT, headers=_AMIS_HEADERS)
        if res.status_code == 200 and len(res.text) > 3000:
            parsed = _parse_amis_price_table(res.text, mandi_list)
            if parsed:
                logger.info("[MANDI] live_fetch_success=true results=%d", len(parsed))
                return parsed
            else:
                logger.info("[MANDI] live_fetch_success=false (html_ok_but_no_parseable_rows)")
        else:
            logger.info("[MANDI] live_fetch_success=false (status=%d body_len=%d)",
                        res.status_code, len(res.text))
    except requests.exceptions.Timeout:
        logger.info("[MANDI] live_fetch_success=false (timeout)")
    except Exception as exc:
        logger.info("[MANDI] live_fetch_success=false (exception=%s)", type(exc).__name__)

    return []


def get_fallback_mandi_rates(commodity: str, mandi_list: list) -> list:
    """Return fallback mock rates for mandis in the nearby list."""
    data = _FALLBACK_RATES.get(commodity)
    if not data:
        return []
    unit = data["unit"]
    fallback_by_name = {m["name"]: m for m in data["mandis"]}
    results = []
    for mandi_info in mandi_list:
        name = mandi_info["name"]
        if name in fallback_by_name:
            fb = fallback_by_name[name]
            results.append({
                "name": name,
                "min": fb["min"],
                "max": fb["max"],
                "avg": fb["avg"],
                "unit": unit,
                "distance_km": mandi_info.get("distance_km"),
                "source": "local mock data",
            })
    return results


# ─── Language Detection ─────────────────────────────────────────────────────────
def _detect_query_language(text: str) -> str:
    """Return 'urdu', 'roman_urdu', or 'english'."""
    if not text:
        return "urdu"
    urdu_count = len(re.findall(r"[\u0600-\u06FF]", text))
    latin_count = len(re.findall(r"[a-zA-Z]", text))
    if urdu_count > 3:
        return "urdu"
    if latin_count > urdu_count:
        roman_signals = [
            "mandi", "rate", "rete", "gandum", "kapas", "aam", "chawal", "aloo",
            "piyaz", "tamatar", "ganna", "makai", "batao", "kya", "mere", "qareeb",
            "bhav", "bhaav", "bhao", "keemat", "qeemat", "narakh",
        ]
        roman_hits = sum(1 for w in roman_signals if w in text.lower())
        if roman_hits >= 1:
            return "roman_urdu"
        return "english"
    return "roman_urdu"


# ─── Response Formatter ─────────────────────────────────────────────────────────
_COMMODITY_URDU = {
    "wheat": "گندم", "cotton": "کپاس", "mango": "آم",
    "rice": "چاول", "maize": "مکئی", "sugarcane": "گنا",
    "potato": "آلو", "onion": "پیاز", "tomato": "ٹماٹر",
}

_COMMODITY_ROMAN = {
    "wheat": "gandum", "cotton": "kapas", "mango": "aam",
    "rice": "chawal", "maize": "makai", "sugarcane": "ganna",
    "potato": "aloo", "onion": "piyaz", "tomato": "tamatar",
}


def format_mandi_response(
    results: list,
    language: str,
    commodity: str,
    fallback_used: bool,
    has_location: bool,
) -> str:
    """Build the final text response for the farmer."""
    today = date.today().strftime("%d-%m-%Y")
    c_ur = _COMMODITY_URDU.get(commodity, commodity)
    c_ro = _COMMODITY_ROMAN.get(commodity, commodity)
    c_en = commodity.title()
    unit = results[0]["unit"] if results else "Rs/maund"

    lines = []
    if language == "urdu":
        lines.append(f"آپ کے قریب {c_ur} کے منڈی ریٹس ({today}):\n")
        for i, r in enumerate(results, 1):
            dist = f" ({r['distance_km']:.1f} کلومیٹر)" if r.get("distance_km") is not None else ""
            lines.append(
                f"{i}. {r['name']} منڈی{dist}: اوسط ریٹ {r['avg']:,} روپے ({unit}) "
                f"(رینج: {r['min']:,} - {r['max']:,} روپے)"
            )
        best = results[0]
        best_dist = f"قریب ({best['distance_km']:.1f} کلومیٹر) " if best.get("distance_km") is not None else ""
        lines.append(
            f"\nبہتر آپشن: {best['name']} منڈی {best_dist}ہے اور ریٹ بھی مناسب لگ رہا ہے۔ "
            "فروخت سے پہلے مقامی منڈی یا آڑھتی سے آخری ریٹ ضرور confirm کر لیں۔"
        )
    elif language == "roman_urdu":
        lines.append(f"Aap ke qareeb {c_ro} ke mandi rates ({today}):\n")
        for i, r in enumerate(results, 1):
            dist = f" ({r['distance_km']:.1f} km)" if r.get("distance_km") is not None else ""
            lines.append(
                f"{i}. {r['name']} Mandi{dist}: Avg rate Rs {r['avg']:,}/{unit.split('/')[-1]} "
                f"(Range: {r['min']:,} - {r['max']:,} Rs)"
            )
        best = results[0]
        best_dist = f"qareeb ({best['distance_km']:.1f} km) bhi " if best.get("distance_km") is not None else ""
        lines.append(
            f"\nBehtar option: {best['name']} Mandi {best_dist}hai aur rate bhi acha lag raha hai. "
            "Bechnay se pehle local mandi ya arhti se final rate confirm kar lein."
        )
    else:  # english
        loc_phrase = "near you" if has_location else "available"
        lines.append(f"Available mandi rates {loc_phrase} for {c_en} ({today}):\n")
        for i, r in enumerate(results, 1):
            dist = f" ({r['distance_km']:.1f} km)" if r.get("distance_km") is not None else ""
            lines.append(
                f"{i}. {r['name']} Mandi{dist}: Avg rate Rs {r['avg']:,}/{unit.split('/')[-1]} "
                f"(Range: {r['min']:,} - {r['max']:,} Rs)"
            )
        best = results[0]
        best_dist = f"closest ({best['distance_km']:.1f} km) and " if best.get("distance_km") is not None else ""
        lines.append(
            f"\nBest nearby option: {best['name']} Mandi is {best_dist}"
            "has a good rate. Please confirm the final price from your local mandi or arhti before selling."
        )

    response = "\n".join(lines)

    # Append fallback note ONLY when mock/local data is used
    if fallback_used:
        note = (
            "\n\nNote: These rates are for reference only (local mock data). "
            "Please confirm final rates from your local mandi or arhti. "
            "Future prices cannot be guaranteed."
        )
        if language == "urdu":
            note = (
                "\n\nنوٹ: یہ ریٹس صرف حوالے کے لیے ہیں (مقامی mock data)۔ "
                "حتمی ریٹس اپنی مقامی منڈی یا آڑھتی سے confirm کریں۔ "
                "مستقبل کے ریٹس کی ضمانت نہیں۔"
            )
        elif language == "roman_urdu":
            note = (
                "\n\nNote: Ye rates sirf reference ke liye hain (local mock data). "
                "Final rates apni local mandi ya arhti se confirm karen. "
                "Future prices cannot be guaranteed."
            )
        response += note

    return response


def _ask_for_commodity(language: str) -> str:
    if language == "urdu":
        return "براہ کرم بتائیں کہ آپ کس فصل یا چیز کا منڈی ریٹ جاننا چاہتے ہیں؟ مثلاً: گندم، کپاس، آم، چاول، پیاز وغیرہ۔"
    if language == "roman_urdu":
        return "Kaunsi fasal ya cheez ka mandi rate chahiye? Maslan: gandum, kapas, aam, chawal, piyaz, etc."
    return "Which crop or commodity are you asking about? E.g.: wheat, cotton, mango, rice, onion, etc."


def _ask_for_location(language: str) -> str:
    if language == "urdu":
        return "براہ کرم اپنی لوکیشن شیئر کریں یا شہر کا نام بتائیں تاکہ آپ کے قریب کی منڈیوں کے ریٹس مل سکیں۔"
    if language == "roman_urdu":
        return "Apni location share karein ya shehar ka naam batain taake aapke qareeb ki mandion ke rates mill sakein."
    return "Please share your location or mention your city so I can show nearby mandi rates."


def _no_data_response(language: str) -> str:
    if language == "urdu":
        return "معذرت، اس وقت اس فصل یا شہر کے منڈی ریٹس دستیاب نہیں ہیں۔ براہ کرم کوئی دوسری فصل یا شہر آزمائیں۔"
    if language == "roman_urdu":
        return "Maafi chahta hun, is waqt is fasal ya shehar ke mandi rates available nahi hain. Koi aur fasal ya shehar try karein."
    return "Sorry, mandi rates for this crop or city are not available right now. Please try another crop or city."


# ─── Main Handler ────────────────────────────────────────────────────────────────
def handle_mandi_query(
    text: str,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
) -> dict:
    """
    Main entry point called when mandi intent is detected.
    Returns a dict with: farmer_response, tts_summary, mandi_status.
    """
    language = _detect_query_language(text)
    commodity = extract_commodity(text)
    city = extract_city(text)
    has_location = (latitude is not None and longitude is not None)

    logger.info(
        "[MANDI] commodity=%s city=%s has_location=%s language=%s",
        commodity, city, has_location, language
    )

    # Ask for commodity if missing
    if not commodity:
        msg = _ask_for_commodity(language)
        return {
            "farmer_response": msg,
            "tts_summary": msg,
            "mandi_status": {
                "intent": True, "commodity": None,
                "fallback_used": False, "results_count": 0,
            }
        }

    # Ask for location/city if both missing
    if not has_location and not city:
        msg = _ask_for_location(language)
        return {
            "farmer_response": msg,
            "tts_summary": msg,
            "mandi_status": {
                "intent": True, "commodity": commodity,
                "fallback_used": False, "results_count": 0,
            }
        }

    # Get nearby mandis (sorted by distance)
    nearby = get_nearby_mandis(latitude, longitude, city, top_n=5)

    # Try live AMIS fetch first
    results = fetch_live_amis_rates(commodity, nearby)
    fallback_used = False

    if not results:
        logger.info("[MANDI] fallback_used=true")
        results = get_fallback_mandi_rates(commodity, nearby)
        fallback_used = True
    else:
        logger.info("[MANDI] fallback_used=false")

    logger.info("[MANDI] results_count=%d", len(results))

    if not results:
        msg = _no_data_response(language)
        return {
            "farmer_response": msg,
            "tts_summary": msg,
            "mandi_status": {
                "intent": True, "commodity": commodity,
                "fallback_used": True, "results_count": 0,
            }
        }

    # Format the full response
    response = format_mandi_response(results, language, commodity, fallback_used, has_location)

    # TTS summary: first header + first 2 mandi lines (concise for speech)
    tts_lines = [l for l in response.split("\n") if l.strip()]
    tts_summary = "\n".join(tts_lines[:4])

    logger.info("[MANDI] intercept_returned=true")

    return {
        "farmer_response": response,
        "tts_summary": tts_summary,
        "mandi_status": {
            "intent": True,
            "commodity": commodity,
            "fallback_used": fallback_used,
            "results_count": len(results),
            "source": "local mock data" if fallback_used else "AMIS / live source",
        }
    }
