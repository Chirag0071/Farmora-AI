import hashlib
import math
import os
import re
import threading
import time
 
import requests
 
 
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
 
HEADERS = {
    "User-Agent": "Farmora/1.0 (agriculture price project)"
}
 
# Optional: Nominatim's policy likes a contact address. Set it in .env if you wish.
CONTACT_EMAIL = os.getenv("NOMINATIM_EMAIL")
 
# Optional, most accurate: Google Places (New) text search. Needs a key with billing enabled.
GOOGLE_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
GOOGLE_URL = "https://places.googleapis.com/v1/places:searchText"
 
MAX_DISTANCE_KM = float(os.getenv("FARMORA_MAX_MARKET_KM", "120"))
MAP_TIME_BUDGET_SECONDS = int(os.getenv("FARMORA_MAP_BUDGET", "25"))    # map answers within ~25 s; the rest finishes in the background
MISS_RETRY_SECONDS = 7 * 24 * 3600
MIN_INTERVAL_SECONDS = 1.0                                              # Nominatim: max 1 request/second
 
# lat_min, lon_min, lat_max, lon_max
INDIA_BBOX = (6.0, 68.0, 37.5, 98.0)
 
_cache_lock = threading.RLock()
_rate_lock = threading.Lock()
_last_request_at = 0.0
_cache = None
_background_jobs = set()
 
 
# ============================================================
# IN-MEMORY CACHE (cleared when the backend restarts)
# ============================================================
 
def _load_cache():
    global _cache
    with _cache_lock:
        if _cache is None:
            _cache = {}
        return _cache
 
 
def _key(kind, state, district, name=""):
    return "|".join([kind, state.strip().lower(), district.strip().lower(), name.strip().lower()])
 
 
def _cache_get(key):
    with _cache_lock:
        return _load_cache().get(key)
 
 
def _cache_set(key, value):
    with _cache_lock:
        _load_cache()[key] = value
 
 
# ============================================================
# NOMINATIM
# ============================================================
 
def _nominatim(query, limit=5, extra=None):
    """Rate-limited search. Returns a list (possibly empty) or None if the service failed."""
    global _last_request_at
 
    params = {
        "q": query,
        "format": "json",
        "limit": limit,
        "countrycodes": "in",
    }
 
    if extra:
        params.update(extra)
 
    if CONTACT_EMAIL:
        params["email"] = CONTACT_EMAIL
 
    for attempt in range(3):
 
        with _rate_lock:
            wait = MIN_INTERVAL_SECONDS - (time.monotonic() - _last_request_at)
            if wait > 0:
                time.sleep(wait)
            _last_request_at = time.monotonic()
 
        try:
            response = requests.get(NOMINATIM_URL, params=params, headers=HEADERS, timeout=15)
 
            if response.status_code in (429, 502, 503, 504):
                time.sleep(2 * (attempt + 1))
                continue
 
            response.raise_for_status()
            return response.json()
 
        except Exception as exc:
            print(f"Nominatim error for '{query}': {exc}")
            time.sleep(1)
 
    return None
 
 
def _haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
 
 
def _in_india(lat, lon):
    return INDIA_BBOX[0] <= lat <= INDIA_BBOX[2] and INDIA_BBOX[1] <= lon <= INDIA_BBOX[3]
 
 
_MARKET_TYPES = {
    ("amenity", "marketplace"), ("shop", "wholesale"),
    ("landuse", "retail"), ("landuse", "commercial"),
}
_MARKET_WORDS = ("mandi", "apmc", "krishi", "market yard", "sabzi", "anaj", "wholesale")
 
 
def _is_marketplace(item):
    if (item.get("class"), item.get("type")) in _MARKET_TYPES:
        return True
    name = str(item.get("name") or item.get("display_name", "").split(",")[0]).lower()
    return any(word in name for word in _MARKET_WORDS)
 
 
def _best_hit(results, centroid, allow_admin=False):
    """Best valid result as (lat, lon, precision), or None.
 
    precision = "marketplace" when the result is a real market/mandi place, else "locality".
    Real market places win over town/locality hits; among equals the closest to the district
    centre wins. Hits outside India or farther than MAX_DISTANCE_KM from the centre are rejected."""
    best, best_score = None, None
 
    for item in results or []:
        try:
            lat, lon = float(item["lat"]), float(item["lon"])
        except (KeyError, TypeError, ValueError):
            continue
 
        if not _in_india(lat, lon):
            continue
 
        if not allow_admin and item.get("class") == "boundary" and item.get("type") == "administrative":
            continue
 
        market = _is_marketplace(item)
        distance = 0.0
 
        if centroid is not None:
            distance = _haversine_km(lat, lon, centroid[0], centroid[1])
            if distance > MAX_DISTANCE_KM:
                continue
 
        score = distance - (40 if market else 0)
 
        if best is None or score < best_score:
            best, best_score = (lat, lon, "marketplace" if market else "locality"), score
 
    return best
 
 
# ============================================================
# DISTRICT CENTRE
# ============================================================
 
def get_district_centroid(district, state):
    key = _key("district", state, district)
    cached = _cache_get(key)
 
    if cached and "lat" in cached:
        return cached["lat"], cached["lon"]
 
    if cached and time.time() - cached.get("miss", 0) < MISS_RETRY_SECONDS:
        return None
 
    failed = False
 
    for query in (
        f"{district}, {state}, India",
        f"{district} district, {state}, India",
        f"{district}, India",
    ):
        results = _nominatim(query)
 
        if results is None:
            failed = True
            continue
 
        hit = _best_hit(results, None, allow_admin=True)
 
        if hit:
            _cache_set(key, {"lat": hit[0], "lon": hit[1]})
            return hit[0], hit[1]
 
    if not failed:
        _cache_set(key, {"miss": time.time()})
 
    return None
 
 
# ============================================================
# MARKET LOOKUP
# ============================================================
 
_NOISE_WORDS = re.compile(
    r"\b(apmc|a\.p\.m\.c\.?|mandi|market|krishi|utpadan|upaj|samiti|anaj|sabzi|grain|f&v|"
    r"fruits?|vegetables?|veg|yard|rmc|aprc)\b",
    flags=re.I,
)
 
 
def _clean_market_name(name):
    text = re.sub(r"\(.*?\)", " ", name)
    text = _NOISE_WORDS.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip(" -,.")
 
 
def _google_lookup(market, district, state, centroid):
    """Google Places text search. Returns (lat, lon, 'marketplace'), 'miss', or None on failure."""
    body = {
        "textQuery": f"{market} mandi, {district}, {state}, India",
        "regionCode": "IN",
        "maxResultCount": 5,
    }
 
    if centroid:
        body["locationBias"] = {"circle": {
            "center": {"latitude": centroid[0], "longitude": centroid[1]},
            "radius": 50000.0,
        }}
 
    try:
        response = requests.post(
            GOOGLE_URL,
            json=body,
            headers={
                "X-Goog-Api-Key": GOOGLE_KEY,
                "X-Goog-FieldMask": "places.displayName,places.location,places.formattedAddress",
            },
            timeout=15,
        )
        if response.status_code != 200:
            print(f"Google Places HTTP {response.status_code}: {response.text[:200]}")
            return None
        places = response.json().get("places", [])
    except Exception as exc:
        print(f"Google Places error: {exc}")
        return None
 
    best, best_distance = None, None
    for place in places:
        try:
            lat, lon = float(place["location"]["latitude"]), float(place["location"]["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        if not _in_india(lat, lon):
            continue
        distance = _haversine_km(lat, lon, centroid[0], centroid[1]) if centroid else 0.0
        if distance <= MAX_DISTANCE_KM and (best is None or distance < best_distance):
            best, best_distance = (lat, lon, "marketplace"), distance
 
    return best or "miss"
 
 
def _lookup_market(market, district, state, centroid):
    """Returns (lat, lon, precision), or 'miss' when searched fine but not found, or None on service failure.
 
    1) Google Places (only if GOOGLE_MAPS_API_KEY is set).
    2) OpenStreetMap, at most 2 requests: the short name + "mandi" inside a box around the district
       (usually hits at once), then the full name. A real marketplace hit is returned immediately;
       otherwise the first town/locality hit is used."""
 
    if GOOGLE_KEY:
        outcome = _google_lookup(market, district, state, centroid)
        if isinstance(outcome, tuple):
            return outcome
 
    clean = _clean_market_name(market) or market
 
    attempts = []
 
    if centroid:
        lat, lon = centroid
        box = {"viewbox": f"{lon - 0.8},{lat + 0.8},{lon + 0.8},{lat - 0.8}", "bounded": 1}
        attempts.append((f"{clean} mandi", box))
 
    attempts.append((f"{market}, {district}, {state}, India", None))
 
    service_failed = False
    fallback = None
 
    for query, extra in attempts:
 
        results = _nominatim(query, extra=extra)
 
        if results is None:
            service_failed = True
            continue
 
        hit = _best_hit(results, centroid)
 
        if hit and hit[2] == "marketplace":
            return hit
 
        if hit and fallback is None:
            fallback = hit
 
    if fallback:
        return fallback
 
    return None if service_failed else "miss"
 
 
def _resolve_market(market, district, state, centroid):
    """Cached lookup. Returns (lat, lon, precision) or None (not found / not yet known)."""
    key = _key("market", state, district, market)
    cached = _cache_get(key)
 
    if cached and "lat" in cached:
        return cached["lat"], cached["lon"], cached.get("precision", "locality")
 
    if cached and time.time() - cached.get("miss", 0) < MISS_RETRY_SECONDS:
        return None
 
    outcome = _lookup_market(market, district, state, centroid)
 
    if isinstance(outcome, tuple):
        _cache_set(key, {"lat": outcome[0], "lon": outcome[1], "precision": outcome[2]})
        return outcome
 
    if outcome == "miss":
        _cache_set(key, {"miss": time.time()})
 
    return None
 
 
def _is_known(market, district, state):
    cached = _cache_get(_key("market", state, district, market))
    return bool(cached) and ("lat" in cached or time.time() - cached.get("miss", 0) < MISS_RETRY_SECONDS)
 
 
def _approximate_point(centroid, market):
    """Deterministic spot 2-8 km from the district centre so approximate dots don't stack."""
    digest = hashlib.md5(market.encode("utf-8")).digest()
    angle = digest[0] / 255 * 2 * math.pi
    radius_km = 2 + digest[1] / 255 * 6
    dlat = radius_km * math.cos(angle) / 111.0
    dlon = radius_km * math.sin(angle) / (111.0 * max(math.cos(math.radians(centroid[0])), 0.2))
    return centroid[0] + dlat, centroid[1] + dlon
 
 
def _background_lookup(markets, district, state, centroid):
    job = (state.lower(), district.lower())
    try:
        for market in markets:
            _resolve_market(market, district, state, centroid)
    finally:
        _background_jobs.discard(job)
 
 
def warm_market_locations(state, district, markets):
    """Start locating markets in the background (called as soon as prices are requested, so the
    map is mostly ready by the time the result page asks for it)."""
    job = (state.lower(), district.lower())
 
    unique = list(dict.fromkeys(str(m).strip() for m in markets if str(m).strip()))
 
    if not unique or job in _background_jobs:
        return
 
    _background_jobs.add(job)
 
    def run():
        try:
            centroid = get_district_centroid(district, state)
            if centroid:
                for market in unique:
                    _resolve_market(market, district, state, centroid)
        finally:
            _background_jobs.discard(job)
 
    threading.Thread(target=run, daemon=True).start()
 
 
# ============================================================
# PUBLIC API  (same signature as before)
# ============================================================
 
def get_market_locations(
    state,
    district,
    crop
):
    from backend.services.agmarknet import (
        AGMARKNETError,
        get_price_history,
        get_district_markets,
    )
 
    markets = []
 
    # Markets that trade the selected crop first ...
    try:
        df = get_price_history(state=state, district=district, crop=crop)
        markets += [str(m).strip() for m in df["market"].dropna().unique()]
    except AGMARKNETError as exc:
        print(f"Map: no price history for the crop ({exc}); using district markets only.")
 
    # ... then every other mandi in the district.
    try:
        markets += get_district_markets(state, district)
    except AGMARKNETError as exc:
        if not markets:
            raise exc
 
    unique, seen = [], set()
    for market in markets:
        if market and market.lower() not in seen:
            seen.add(market.lower())
            unique.append(market)
 
    if not unique:
        return []
 
    centroid = get_district_centroid(district, state)
 
    deadline = time.monotonic() + MAP_TIME_BUDGET_SECONDS
 
    # If a background warm-up is already locating this district's markets, let it finish
    # (instead of doing the same lookups twice).
    job = (state.lower(), district.lower())
    while job in _background_jobs and time.monotonic() < deadline:
        time.sleep(0.5)
    locations, pending = [], []
 
    # Cached markets cost nothing, so resolve those first; then look up new ones.
    ordered = sorted(unique, key=lambda m: not _is_known(m, district, state))
 
    resolved = {}
    for market in ordered:
        if _is_known(market, district, state) or time.monotonic() < deadline:
            resolved[market] = _resolve_market(market, district, state, centroid)
        else:
            resolved[market] = None
            pending.append(market)
 
    for market in unique:
        point = resolved.get(market)
 
        if point and point[2] == "marketplace":
            locations.append({"market": market, "lat": point[0], "lon": point[1],
                              "approximate": False, "precision": "marketplace"})
        elif point:
            locations.append({"market": f"{market} (town area)", "lat": point[0], "lon": point[1],
                              "approximate": True, "precision": "locality"})
        elif centroid:
            lat, lon = _approximate_point(centroid, market)
            locations.append({"market": f"{market} (approx.)", "lat": lat, "lon": lon,
                              "approximate": True, "precision": "district"})
 
    if pending:
        if job not in _background_jobs:
            _background_jobs.add(job)
            threading.Thread(
                target=_background_lookup,
                args=(pending, district, state, centroid),
                daemon=True,
            ).start()
 
    exact = sum(1 for item in locations if item["precision"] == "marketplace")
    print(f"Map: {len(locations)} markets in {district}, {state} ({exact} exact market places, "
          f"{len(locations) - exact} town-area/approximate, {len(pending)} still locating)")
 
    return locations