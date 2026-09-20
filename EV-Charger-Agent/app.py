"""
Automated EV Charging Station Finder - Gradio prototype (agentic version)
===========================================================================
Pipeline:
    User text --> Intent Agent (LLM) --> Orchestrator
        --> Search Agent --> Availability Agent --> Route Agent
        --> Decision Agent (scoring)
        --> Booking Agent (may fail --> Orchestrator retries next candidate)
        --> Notification Agent

WHY YOUR PREVIOUS RUN ALWAYS SAID "no candidates"
---------------------------------------------------
Two real bugs, now fixed:
  1. Open Charge Map now requires a (free) API key for reliable access -
     without one, requests can be silently throttled, so the Search Agent
     was often getting zero stations back no matter what you typed.
  2. The search radius didn't scale with your stated remaining range, and
     Open Charge Map's crowdsourced coverage is genuinely sparse in many
     Indian cities (Nagpur included) - so even a successful call could
     legitimately return zero stations nearby.
This file fixes #1 (real API key support) and #2 (adaptive radius + a
clearly-labelled DEMO fallback so the pipeline always has something to show
you, instead of just failing silently). See SearchAgent below.

ZERO-COST SETUP
----------------
1. Open Charge Map key (free, takes 1 minute, fixes the bug above):
   - Sign up at https://openchargemap.org/site/profile/applications
   - Create an API key
   - export OCM_API_KEY=your_key_here
   (The app still runs without this, but real station data becomes
   unreliable - see the banner it prints if you skip this.)

2. LLM backend for the Intent Agent (pick ONE, all free):
   - Groq      (fast, ~30 req/min free)   -> export GROQ_API_KEY=gsk_...
   - Cerebras  (higher daily quota, ~1M tokens/day free)
                                            -> export CEREBRAS_API_KEY=csk_...
   - Ollama    (fully local, zero signup, zero rate limit)
                                            -> install ollama.com, `ollama pull llama3.2:1b`
   By default (LLM_BACKEND=auto) this file tries them in that order and
   uses whichever is actually configured/reachable - you don't have to
   pick, just set ONE key and it's used automatically. Force a specific
   one with LLM_BACKEND=groq|cerebras|ollama|anthropic|rules.

3. pip install gradio requests
   python app.py --check-llm     # verify before a demo
   python app.py                 # launch
"""

import os
import re
import sys
import json
import math
import random
import requests
import gradio as gr

OCM_API = "https://api.openchargemap.io/v3/poi/"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "openai/gpt-oss-20b"
CEREBRAS_URL = "https://api.cerebras.ai/v1/chat/completions"
CEREBRAS_MODEL = "llama3.1-8b"
OLLAMA_MODEL_DEFAULT = "llama3.2:1b"

# Default demo location: Bengaluru, which has denser Open Charge Map
# coverage than many other Indian cities. You can still search anywhere;
# sparse-coverage areas just lean on the labelled DEMO fallback more often.
DEFAULT_LAT, DEFAULT_LON = 21.1263, 79.1600


# --------------------------------------------------------------------------
# 1. Intent Agent - the actual "AI" reasoning step
# --------------------------------------------------------------------------
class IntentAgent:
    """Turns free-text into structured intent using a real LLM. Backends,
    selected via LLM_BACKEND (default "auto" = try each in this order and
    use whichever is configured/reachable):
        "groq"      - free-tier cloud API, ~30 req/min, very fast
        "cerebras"  - free-tier cloud API, much higher daily token quota
        "ollama"    - fully local, no account, no API key, no cost at all
        "anthropic" - paid, for anyone who already has API credits
    If nothing is configured/reachable, falls back to keyword rules so the
    pipeline still runs - but this fallback is NOT genuine reasoning and
    is called out as such, loudly, rather than hidden."""

    SYSTEM_PROMPT = (
    "You extract structured intent from a message to an EV-charging-finder "
    "assistant. Reply with ONLY a JSON object, no other text, with keys:\n"
    '  "intent": "find_charger" or "chitchat"\n'
    '  "priority": one of "nearest", "fastest", "cheapest", "available"\n'
    '  "connector_type": a string like "CCS", "CHAdeMO", "Type 2", or null\n'
    '  "min_power_kw": a number if the user mentions a minimum charging '
    "speed, else null\n"
    '  "search_radius_km": a number if the user specifies a distance/radius '
    'such as "within 75 km", otherwise null\n'
    'If the message is not about finding/booking a charger, set intent to "chitchat".'
    )

    _BACKEND_LABELS = {
        "groq": "Groq (GPT-OSS-20B, free tier)",
        "cerebras": "Cerebras (Llama-3.1-8B, free tier, high quota)",
        "ollama": "Ollama (local Llama, free/offline)",
    }

    def __init__(self):
        self.groq_key = os.environ.get("GROQ_API_KEY")
        self.cerebras_key = os.environ.get("CEREBRAS_API_KEY")
        self.ollama_url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
        self.ollama_model = os.environ.get("OLLAMA_MODEL", OLLAMA_MODEL_DEFAULT)
        self.using_llm = False
        self.llm_error = None
        self.backend = None

        requested = os.environ.get("LLM_BACKEND", "auto").lower()
        order = [requested] if requested != "auto" else ["groq", "cerebras", "ollama"]

        errors = []
        for candidate in order:
            ok, err = self._try_backend(candidate)
            if ok:
                self.backend = candidate
                self.using_llm = True
                label = self._BACKEND_LABELS.get(candidate, candidate)
                print(f"[IntentAgent] Using LIVE backend: {label}.")
                break
            errors.append(f"{candidate}: {err}")

        if not self.using_llm:
            self.backend = requested if requested != "auto" else "rules"
            self.llm_error = "; ".join(errors) if errors else "no backend configured"
            print(f"[IntentAgent] No usable LLM backend ({self.llm_error}) -> "
                   "using rule-based fallback (NOT genuine LLM reasoning).")

    def _try_backend(self, name):
        if name == "groq":
            if not self.groq_key:
                return False, "GROQ_API_KEY not set (free at console.groq.com)"
            return True, None
        if name == "cerebras":
            if not self.cerebras_key:
                return False, "CEREBRAS_API_KEY not set (free at cloud.cerebras.ai)"
            return True, None
        if name == "ollama":
            try:
                r = requests.get(f"{self.ollama_url}/api/tags", timeout=2)
                if r.ok:
                    return True, None
                return False, f"HTTP {r.status_code}"
            except requests.RequestException as e:
                return False, f"not reachable at {self.ollama_url} ({e})"
        return False, f"unknown backend '{name}'"

    def run(self, text):
        if self.using_llm:
            try:
                result = self._llm_parse(text)
                print(f"[IntentAgent] {self.backend} call succeeded for {text!r} -> {result}")
                return result
            except Exception as e:
                print(f"[IntentAgent] LLM call failed ({e}); falling back to rules for this message.")
        return self._rule_based_parse(text)

    def self_test(self):
        """Makes one real, minimal API call to confirm the backend actually
        works. Run this BEFORE walking into a demo or viva:
            python app.py --check-llm
        """
        if not self.using_llm:
            return False, self.llm_error or "No LLM backend configured."
        try:
            if self.backend == "groq":
                r = requests.post(GROQ_URL, headers={"Authorization": f"Bearer {self.groq_key}"},
                                    json={"model": GROQ_MODEL, "max_tokens": 20,
                                           "messages": [{"role": "user", "content": "Reply with exactly: OK"}]},
                                     timeout=15)
                r.raise_for_status()
                return True, r.json()["choices"][0]["message"]["content"].strip()
            if self.backend == "cerebras":
                r = requests.post(CEREBRAS_URL, headers={"Authorization": f"Bearer {self.cerebras_key}"},
                                    json={"model": CEREBRAS_MODEL, "max_tokens": 20,
                                           "messages": [{"role": "user", "content": "Reply with exactly: OK"}]},
                                     timeout=15)
                r.raise_for_status()
                return True, r.json()["choices"][0]["message"]["content"].strip()
            if self.backend == "ollama":
                r = requests.post(f"{self.ollama_url}/api/chat",
                                    json={"model": self.ollama_model, "stream": False,
                                           "messages": [{"role": "user", "content": "Reply with exactly: OK"}]},
                                     timeout=30)
                r.raise_for_status()
                return True, r.json()["message"]["content"].strip()
        except Exception as e:
            return False, str(e)
        return False, "Unrecognised backend."

    def _llm_parse(self, text):
        if self.backend == "groq":
            r = requests.post(
                GROQ_URL, headers={"Authorization": f"Bearer {self.groq_key}"},
                json={ "model": GROQ_MODEL,
                      "max_completion_tokens": 2048,
                      "temperature": 0,
                      "reasoning_effort": "low",
                      "include_reasoning": False,
                      "response_format": {"type": "json_object"},
                      "messages": [
                            {"role": "system", "content": self.SYSTEM_PROMPT},
                            {"role": "user", "content": text}]
                },timeout=15)
            r.raise_for_status()
            raw = r.json()["choices"][0]["message"]["content"].strip()

        elif self.backend == "cerebras":
            r = requests.post(
                CEREBRAS_URL, headers={"Authorization": f"Bearer {self.cerebras_key}"},
                json={"model": CEREBRAS_MODEL, "max_completion_tokens": 1024,"temperature": 0,
                       "response_format": {"type": "json_object"},
                       "messages": [{"role": "system", "content": self.SYSTEM_PROMPT},
                                     {"role": "user", "content": text}]},
                timeout=15)
            r.raise_for_status()
            raw = r.json()["choices"][0]["message"]["content"].strip()

        elif self.backend == "ollama":
            r = requests.post(
                f"{self.ollama_url}/api/chat",
                json={"model": self.ollama_model, "stream": False, "format": "json",
                       "messages": [{"role": "system", "content": self.SYSTEM_PROMPT},
                                     {"role": "user", "content": text}]},
                timeout=30)
            r.raise_for_status()
            raw = r.json()["message"]["content"].strip()

        else:
            raise RuntimeError(f"Unrecognised backend '{self.backend}'.")

        raw = re.sub(r"^```json|```$", "", raw, flags=re.MULTILINE).strip()
        data = json.loads(raw)
        data.setdefault("priority", "nearest")
        data["_source"] = "llm"
        data["_backend"] = self.backend
        return data

    def _rule_based_parse(self, text):
        t = text.lower()
        charger_kw = ["charg", "ev", "station", "plug", "battery", "range", "socket"]
        if not any(k in t for k in charger_kw):
            return {"intent": "chitchat", "priority": None, "connector_type": None,
                     "min_power_kw": None, "_source": "rules", "_backend": "rules"}

        if any(k in t for k in ["fast", "quick", "rapid", "speed"]):
            priority = "fastest"
        elif any(k in t for k in ["cheap", "low cost", "budget"]):
            priority = "cheapest"
        elif any(k in t for k in ["available", "free now", "open now"]):
            priority = "available"
        else:
            priority = "nearest"

        connector = None
        for c in ["ccs", "chademo", "type 2", "type2", "type 1"]:
            if c in t:
                connector = c.upper()
                break

        power_match = re.search(r"(\d+)\s*kw", t)
        min_power = float(power_match.group(1)) if power_match else None

        return {"intent": "find_charger", "priority": priority, "connector_type": connector,
                 "min_power_kw": min_power, "_source": "rules", "_backend": "rules"}


# --------------------------------------------------------------------------
# 2. Task agents
# --------------------------------------------------------------------------
def _haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class SearchAgent:
    """Queries Open Charge Map for real stations. Two things that broke the
    previous version, fixed here:
      - Sends an OCM_API_KEY (if set) via the X-API-Key header and a proper
        User-Agent, since OCM now throttles/bans anonymous callers making
        repeated calls (see community.openchargemap.org).
      - Records exactly what happened (HTTP error vs. zero results) so the
        Orchestrator can tell the user the real reason instead of a generic
        "no candidates" message every time.
    """

    _COST_NUMBER_RE = re.compile(r"(\d+(?:\.\d+)?)")

    def __init__(self):
        self.api_key = os.environ.get("OCM_API_KEY")
        self.last_error = None
        self.last_raw_count = None
        if not self.api_key:
            print("[SearchAgent] No OCM_API_KEY set - Open Charge Map now requires a free "
                   "key for reliable access (https://openchargemap.org/site/profile/applications). "
                   "Requests will still be attempted, but may be throttled or return incomplete data.")

    def run(self, lat, lon, max_results=25, radius_km=40):
        headers = {"User-Agent": "AgenticEVChargingFinder-CollegeProject/1.0"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        params = {
            "output": "json", "latitude": lat, "longitude": lon,
            "distance": radius_km, "distanceunit": "KM", "maxresults": max_results,
            "compact": True, "verbose": False,
        }
        try:
            resp = requests.get(OCM_API, params=params, headers=headers, timeout=15)
            resp.raise_for_status()
            stations = resp.json()
            self.last_error = None
        except requests.RequestException as e:
            self.last_error = str(e)
            print(f"[SearchAgent] Open Charge Map request failed: {e}")
            stations = []

        self.last_raw_count = len(stations)
        for s in stations:
            conns = s.get("Connections") or [{}]
            powers = [c.get("PowerKW") for c in conns if c.get("PowerKW")]
            s["_max_power_kw"] = max(powers) if powers else 0
            s["_connectors"] = [c.get("ConnectionType", {}).get("Title", "") for c in conns]
            s["_cost_value"], s["_cost_display"] = self._parse_cost(s.get("UsageCost"))
            s["_is_demo"] = False
        return stations

    def _parse_cost(self, usage_cost_text):
        if not usage_cost_text:
            return None, "price unknown"
        text = usage_cost_text.strip()
        if not text:
            return None, "price unknown"
        if re.search(r"\bfree\b", text, re.IGNORECASE) and not self._COST_NUMBER_RE.search(text):
            return 0.0, "Free"
        match = self._COST_NUMBER_RE.search(text)
        if match:
            return float(match.group(1)), text
        return None, text

    def fallback_demo_stations(self, lat, lon, remaining_range_km):
        """Used ONLY when a real Open Charge Map search returns zero
        results, so the pipeline can still demonstrate the full agent flow.
        Clearly labelled [DEMO] end-to-end - never presented as real data."""
        random.seed(f"{round(lat, 3)}:{round(lon, 3)}")  # deterministic per location
        templates = [
            ("City Center Fast Charger", 60, "CCS", "0.22 USD/kWh"),
            ("Mall Parking EV Point", 22, "Type 2", "Free"),
            ("Highway Rest Stop DC Fast", 120, "CCS", "0.30 USD/kWh"),
            ("Residential Society Charger", 7, "Type 2", "0.10 USD/kWh"),
            ("Tech Park Charging Hub", 50, "CHAdeMO", None),
        ]
        max_offset_km = max(min(remaining_range_km * 0.8, 15), 2)
        stations = []
        for i, (name, power, connector, cost_text) in enumerate(templates, start=1):
            bearing = random.uniform(0, 360)
            dist_km = round(random.uniform(1.5, max_offset_km), 1)
            dlat = (dist_km / 111.0) * math.cos(math.radians(bearing))
            dlon = (dist_km / (111.0 * math.cos(math.radians(lat)))) * math.sin(math.radians(bearing))
            cost_value, cost_display = self._parse_cost(cost_text)
            stations.append({
                "ID": -i,  # negative IDs so they can never collide with real OCM IDs
                "AddressInfo": {"Title": f"[DEMO] {name}", "Distance": dist_km,
                                  "Town": "Demo data - no real station found nearby"},
                "_max_power_kw": power,
                "_connectors": [connector],
                "_cost_value": cost_value,
                "_cost_display": cost_display,
                "_is_demo": True,
                "UsageCost": cost_text,
            })
        return stations


class AvailabilityAgent:
    def run(self, stations, live_status: dict):
        return [s for s in stations if live_status.get(s.get("ID"), "available") == "available"]


class RouteAgent:
    def run(self, stations, remaining_range_km, avg_speed_kmh=40):
        feasible = []
        for s in stations:
            dist_km = s.get("AddressInfo", {}).get("Distance") or 0
            if dist_km <= remaining_range_km:
                s["_eta_min"] = round(dist_km / avg_speed_kmh * 60, 1)
                s["_dist_km"] = round(dist_km, 1)
                feasible.append(s)
        return feasible


class DecisionAgent:
    """Scores every feasible, available station instead of just taking the
    first result. Price ("cheapest") is a REAL value parsed from Open
    Charge Map's cost field, not a placeholder - a station with no
    parseable price is penalised, never assumed to be cheap."""

    WEIGHT_PROFILES = {
        "nearest":   {"dist": 0.50, "eta": 0.20, "power": 0.10, "connector": 0.10, "cost": 0.10},
        "fastest":   {"dist": 0.10, "eta": 0.10, "power": 0.55, "connector": 0.10, "cost": 0.15},
        "available": {"dist": 0.30, "eta": 0.20, "power": 0.10, "connector": 0.20, "cost": 0.20},
        "cheapest":  {"dist": 0.15, "eta": 0.10, "power": 0.05, "connector": 0.10, "cost": 0.60},
    }

    def run(self, stations, priority="nearest", connector_type=None, min_power_kw=None):
        if not stations:
            return []
        weights = self.WEIGHT_PROFILES.get(priority, self.WEIGHT_PROFILES["nearest"])
        max_dist = max(s["_dist_km"] for s in stations) or 1
        max_eta = max(s["_eta_min"] for s in stations) or 1
        max_power = max(s["_max_power_kw"] for s in stations) or 1
        known_costs = [s["_cost_value"] for s in stations if s.get("_cost_value") is not None]
        max_known_cost = max(known_costs) if known_costs else 1.0
        unknown_cost_score = 1.15  # penalised, never assumed cheap

        scored = []
        for s in stations:
            dist_score = s["_dist_km"] / max_dist
            eta_score = s["_eta_min"] / max_eta
            power_score = 1 - (s["_max_power_kw"] / max_power)
            connector_score = 0.0
            if connector_type:
                match = any(connector_type.lower() in c.lower() for c in s.get("_connectors", []))
                connector_score = 0.0 if match else 1.0
            if min_power_kw and s["_max_power_kw"] < min_power_kw:
                continue
            cost_score = (s["_cost_value"] / max_known_cost) if s.get("_cost_value") is not None \
                else unknown_cost_score
            s["_cost_data_available"] = bool(known_costs)
            score = (weights["dist"] * dist_score + weights["eta"] * eta_score +
                      weights["power"] * power_score + weights["connector"] * connector_score +
                      weights["cost"] * cost_score)
            s["_score"] = round(score, 3)
            scored.append(s)

        scored.sort(key=lambda s: s["_score"])
        return scored


class BookingAgent:
    """Simulates a real-world booking call that can fail (station taken in
    the seconds since the availability check, network error, etc.)."""

    def run(self, station, user_id="demo-user", fail_prob=0.35):
        success = random.random() > fail_prob
        return {
            "station_name": station.get("AddressInfo", {}).get("Title", "Unknown station"),
            "station_id": station.get("ID"),
            "user_id": user_id,
            "distance_km": station.get("_dist_km"),
            "eta_min": station.get("_eta_min"),
            "cost_display": station.get("_cost_display"),
            "score": station.get("_score"),
            "is_demo": station.get("_is_demo", False),
            "status": "confirmed" if success else "failed",
        }


class NotificationAgent:
    def run(self, booking, attempts_log, priority=None, cost_data_available=True,
            pipeline_stats=None, used_fallback=False, ocm_error=None):
        lines = []

        if pipeline_stats:
            lines.append(
                f"_Search: {pipeline_stats['raw_found']} stations found near this location "
                f"({pipeline_stats['radius_km']} km radius) -> {pipeline_stats['after_availability']} "
                f"available -> {pipeline_stats['after_range']} reachable on your remaining range._"
            )

        if used_fallback:
            reason = f" (Open Charge Map error: {ocm_error})" if ocm_error else \
                " (Open Charge Map returned zero real stations near this location)"
            lines.append(
                f"\u26a0\ufe0f **No real stations found{reason}.** Showing labelled DEMO stations "
                "instead so you can see the full pipeline. Try a well-covered city, a larger "
                "search radius, or add a free `OCM_API_KEY` for more reliable real results.\n"
            )

        if priority == "cheapest" and not cost_data_available and not used_fallback:
            lines.append(
                "_Note: none of the nearby stations had a parseable price from Open Charge Map, "
                "so \u201ccheapest\u201d fell back to distance/ETA/power instead of real pricing._\n"
            )

        if len(attempts_log) > 1:
            lines.append("**Booking attempts:**")
            for name, status in attempts_log:
                icon = "OK" if status == "confirmed" else "FAILED"
                lines.append(f"- [{icon}] {name}")
            lines.append("")

        if booking is None:
            lines.append(
                "Could not confirm a booking after trying all feasible candidates. "
                "Try a larger search radius or a higher remaining range."
            )
        else:
            demo_tag = " _(demo station)_" if booking.get("is_demo") else ""
            lines.append(
                f"**Booked: {booking['station_name']}**{demo_tag}  \n"
                f"{booking['distance_km']} km away, ~{booking['eta_min']} min ETA, "
                f"price: {booking['cost_display']}, decision score {booking['score']}  \n"
                f"Status: {booking['status']} | Reference: {booking['station_id']}"
            )
        return "\n".join(lines)


# --------------------------------------------------------------------------
# 3. Orchestrator - plans the pipeline, adapts search radius, and retries
# --------------------------------------------------------------------------
class OrchestratorAgent:
    def __init__(self):
        self.intent_agent = IntentAgent()
        self.search = SearchAgent()
        self.availability = AvailabilityAgent()
        self.route = RouteAgent()
        self.decision = DecisionAgent()
        self.booking = BookingAgent()
        self.notify = NotificationAgent()

    def handle_request(self, user_text, lat, lon, remaining_range_km, search_radius_km=None, max_retries=3):
        intent = self.intent_agent.run(user_text)

        if intent["intent"] == "chitchat":
            return ("Hi! Tell me you need a charger, your remaining range, and "
                     "what matters most (nearest / fastest / cheapest / available) "
                     "and I'll find and book one for you."), [], intent

        priority = intent.get("priority") or "nearest"
        requested_radius = intent.get("search_radius_km")
        # Search at least as far as the driver can actually drive, with headroom
        # for road distance vs. straight-line distance - this was the other bug.
        radius_km = requested_radius or search_radius_km or max(remaining_range_km * 1.5, 40)

        stations = self.search.run(lat, lon, radius_km=radius_km)
        raw_found = self.search.last_raw_count or 0
        ocm_error = self.search.last_error
        used_fallback = False

        if not stations:
            stations = self.search.fallback_demo_stations(lat, lon, remaining_range_km)
            used_fallback = True

        live_status = fake_live_status(stations)
        available = self.availability.run(stations, live_status)
        feasible = self.route.run(available, remaining_range_km)

        pipeline_stats = {
            "raw_found": raw_found if not used_fallback else len(stations),
            "radius_km": round(radius_km, 1),
            "after_availability": len(available),
            "after_range": len(feasible),
        }

        if not feasible:
            # widen once automatically before giving up, in case the range
            # filter (not availability) was the actual blocker
            feasible = self.route.run(available, remaining_range_km * 2)
            pipeline_stats["after_range"] = len(feasible)
            if not feasible:
                msg = self.notify.run(None, [], priority, True, pipeline_stats, used_fallback, ocm_error)
                return msg, [], intent

        ranked = self.decision.run(feasible, priority, intent.get("connector_type"), intent.get("min_power_kw"))
        if not ranked:
            msg = self.notify.run(None, [], priority, True, pipeline_stats, used_fallback, ocm_error)
            return msg, [], intent

        candidates = list(ranked)
        attempts_log = []
        booking = None
        attempts_left = max_retries
        while candidates and attempts_left > 0:
            candidate = candidates.pop(0)
            result = self.booking.run(candidate)
            attempts_log.append((result["station_name"], result["status"]))
            attempts_left -= 1
            if result["status"] == "confirmed":
                booking = result
                break

        message = self.notify.run(booking, attempts_log, priority,
                                    ranked[0].get("_cost_data_available", True),
                                    pipeline_stats, used_fallback, ocm_error)
        table_rows = [
            [s.get("AddressInfo", {}).get("Title", "Unknown"), s["_dist_km"],
             s["_eta_min"], s["_max_power_kw"], s.get("_cost_display", "price unknown"), s["_score"]]
            for s in ranked[:5]
        ]
        return message, table_rows, intent


def fake_live_status(stations, occupied_fraction=0.20):
    """Stands in for a real telemetry/booking-partner feed until one is
    integrated - swap this for a live API call in production. Demo stations
    are never marked occupied, so the fallback path always succeeds."""
    return {s.get("ID"): ("available" if s.get("_is_demo") else
                            ("occupied" if random.random() < occupied_fraction else "available"))
            for s in stations}


orchestrator = OrchestratorAgent()

_BACKEND_LABELS = IntentAgent._BACKEND_LABELS

if orchestrator.intent_agent.using_llm:
    label = _BACKEND_LABELS.get(orchestrator.intent_agent.backend, orchestrator.intent_agent.backend)
    print("=" * 60)
    print(f" LIVE MODE: Intent Agent is calling {label}.")
    print("=" * 60)
else:
    print("=" * 60)
    print(f" FALLBACK MODE: {orchestrator.intent_agent.llm_error}")
    print(" Intent Agent is using keyword rules only, NOT an LLM.")
    print("=" * 60)


# --------------------------------------------------------------------------
# Gradio UI
# --------------------------------------------------------------------------
def chat_respond(message, history, lat, lon, remaining_range_km, search_radius_km, show_debug):
    try:
        lat, lon, remaining_range_km = float(lat), float(lon), float(remaining_range_km)
        search_radius_km = float(search_radius_km) if search_radius_km else None
    except (TypeError, ValueError):
        return "Please enter valid numbers for latitude, longitude and range."

    reply, rows, intent = orchestrator.handle_request(
        message, lat, lon, remaining_range_km, search_radius_km)

    if rows:
        table_lines = ["| Station | Dist (km) | ETA (min) | Power (kW) | Price | Score |",
                        "|---|---|---|---|---|---|"]
        for name, dist, eta, power, cost, score in rows:
            table_lines.append(f"| {name} | {dist} | {eta} | {power:.0f} | {cost} | {score} |")
        reply = f"{reply}\n\n**Ranked candidates:**\n" + "\n".join(table_lines)

    if show_debug:
        if intent.get("_source") == "llm":
            backend_label = _BACKEND_LABELS.get(intent.get("_backend"), intent.get("_backend"))
            source_note = f"LIVE LLM call ({backend_label})"
        else:
            source_note = "rule-based fallback - no LLM backend configured/reachable"
        reply += f"\n\n<sub>Intent parsed via **{source_note}** · `{intent}`</sub>"

    return reply



# --------------------------------------------------------------------------
# UI Styling & Layout (Light Pastel Theme matching Reference Design)
# --------------------------------------------------------------------------
CUSTOM_CSS = """
/* Google Font & Design Tokens */
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

:root {
    --bg-page: #EEF2FB;
    --card-bg: #FFFFFF;
    --text-navy: #0F172A;
    --text-muted: #475569;
    --purple-primary: #5B48E0;
    --purple-light: #EDE9FE;
    --purple-hover: #4A38C8;
    --mint-primary: #059669;
    --mint-light: #D1FAE5;
    --border-light: #94A3B8;
    --shadow-card: 0 2px 12px rgba(0,0,0,0.08), 0 1px 4px rgba(0,0,0,0.05);
}

body, .gradio-container {
    background-color: var(--bg-page) !important;
    font-family: 'Plus Jakarta Sans', system-ui, -apple-system, sans-serif !important;
    color: var(--text-navy) !important;
    max-width: 1440px !important;
    margin: 0 auto !important;
    padding: 10px 16px !important;
}

/* Top Navbar */
.top-navbar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 24px;
    background: var(--card-bg);
    border-radius: 20px;
    border: 1px solid var(--border-light);
    box-shadow: var(--shadow-card);
    margin-bottom: 18px;
}

.brand-section {
    display: flex;
    align-items: center;
    gap: 12px;
}

.brand-logo-badge {
    width: 42px;
    height: 42px;
    border-radius: 50%;
    background: linear-gradient(135deg, #10B981 0%, #059669 100%);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 22px;
    color: white;
    box-shadow: 0 4px 12px rgba(16, 185, 129, 0.25);
}

.brand-info h2 {
    margin: 0;
    font-size: 20px;
    font-weight: 800;
    color: var(--text-navy);
    letter-spacing: -0.5px;
    display: flex;
    align-items: center;
    gap: 6px;
}

.brand-info p {
    margin: 0;
    font-size: 12px;
    font-weight: 600;
    color: var(--purple-primary);
}

.nav-pills {
    display: flex;
    gap: 8px;
    background: #F8FAFC;
    padding: 4px 6px;
    border-radius: 9999px;
    border: 1px solid #EEF2F6;
}

.nav-pill {
    padding: 6px 18px;
    border-radius: 9999px;
    font-size: 13px;
    font-weight: 600;
    color: #334155;
    text-decoration: none;
    transition: all 0.15s ease;
    cursor: pointer;
}

.nav-pill.active {
    background: var(--purple-light);
    color: var(--purple-primary);
}

.eco-badge {
    display: flex;
    align-items: center;
    gap: 10px;
}

.eco-icon {
    width: 36px;
    height: 36px;
    border-radius: 50%;
    background: var(--mint-light);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 18px;
}

.eco-text h4 {
    margin: 0;
    font-size: 12px;
    font-weight: 700;
    color: var(--text-navy);
}

.eco-text p {
    margin: 0;
    font-size: 11px;
    color: var(--mint-primary);
    font-weight: 600;
}

/* 3-Column Responsive Grid Layout */
.dashboard-grid {
    display: flex !important;
    flex-direction: row !important;
    gap: 16px !important;
    align-items: stretch !important;
}

.left-sidebar-col {
    order: 1 !important;
    flex: 1.1 !important;
    min-width: 190px !important;
}

.center-main-col {
    order: 2 !important;
    flex: 3.6 !important;
    min-width: 520px !important;
}

.right-sidebar-col {
    order: 3 !important;
    flex: 1.6 !important;
    min-width: 260px !important;
}

@media (max-width: 1080px) {
    .dashboard-grid {
        flex-direction: column !important;
    }
    .left-sidebar-col, .center-main-col, .right-sidebar-col {
        order: unset !important;
        min-width: 100% !important;
    }
}

/* Left Sidebar */
.sidebar-nav {
    background: var(--card-bg);
    border-radius: 20px;
    padding: 14px;
    border: 1px solid var(--border-light);
    box-shadow: var(--shadow-card);
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin-bottom: 16px;
}

.sidebar-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 14px;
    border-radius: 12px;
    font-size: 13px;
    font-weight: 600;
    color: #334155;
    transition: all 0.15s ease;
    cursor: pointer;
}

.sidebar-item.active {
    background: var(--purple-light);
    color: var(--purple-primary);
}

.sidebar-item:hover:not(.active) {
    background: #F8FAFC;
    color: var(--text-navy);
}

.sidebar-eco-card {
    background: linear-gradient(180deg, #FFFFFF 0%, #F0FDF4 100%);
    border-radius: 20px;
    padding: 18px 14px;
    border: 1px solid #DCFCE7;
    box-shadow: var(--shadow-card);
    text-align: center;
}

.sidebar-eco-art {
    margin-bottom: 10px;
    display: flex;
    justify-content: center;
}

.sidebar-eco-card h3 {
    margin: 0 0 4px 0;
    font-size: 14px;
    font-weight: 800;
    color: var(--text-navy);
}

.sidebar-eco-card p {
    margin: 0;
    font-size: 11px;
    font-style: italic;
    color: #374151;
    font-weight: 500;
}

/* Center Hero */
.hero-banner {
    background: linear-gradient(135deg, #EFF6FF 0%, #EDE9FE 45%, #ECFDF5 100%);
    border-radius: 22px;
    padding: 22px 28px;
    border: 1px solid rgba(226, 232, 240, 0.8);
    box-shadow: var(--shadow-card);
    position: relative;
    overflow: hidden;
    margin-bottom: 16px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.hero-content {
    max-width: 62%;
    z-index: 2;
}

.hero-content h1 {
    font-size: 26px;
    font-weight: 800;
    color: #0F172A;
    line-height: 1.25;
    margin: 0 0 10px 0;
    letter-spacing: -0.5px;
}

.hero-content h1 span {
    color: var(--purple-primary);
}

.hero-content p {
    font-size: 14px;
    color: #334155;
    line-height: 1.5;
    margin: 0;
    font-weight: 500;
}

.hero-art-side {
    text-align: right;
    z-index: 1;
}

.hero-slogan {
    font-size: 13px;
    font-weight: 700;
    color: #059669;
    background: rgba(255, 255, 255, 0.7);
    padding: 4px 10px;
    border-radius: 9999px;
    border: 1px solid #A7F3D0;
    display: inline-block;
    margin-bottom: 6px;
}

/* Agentic Pipeline */
.pipeline-container {
    background: var(--card-bg);
    border-radius: 18px;
    padding: 14px 16px;
    border: 1px solid var(--border-light);
    box-shadow: var(--shadow-card);
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 6px;
    margin-bottom: 16px;
    overflow-x: auto;
}

.pipeline-step {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 6px;
    padding: 10px 10px;
    border-radius: 14px;
    background: #F8FAFC;
    border: 1px solid #CBD5E1;
    min-width: 88px;
    text-align: center;
    transition: transform 0.15s ease;
}

.pipeline-step:hover {
    transform: translateY(-2px);
}

.pipeline-icon {
    width: 28px;
    height: 28px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 13px;
}

.pipeline-step:nth-child(1) .pipeline-icon { background: #EDE9FE; color: #6C5CE7; }
.pipeline-step:nth-child(3) .pipeline-icon { background: #E0F2FE; color: #0284C7; }
.pipeline-step:nth-child(5) .pipeline-icon { background: #DCFCE7; color: #16A34A; }
.pipeline-step:nth-child(7) .pipeline-icon { background: #FEF3C7; color: #D97706; }
.pipeline-step:nth-child(9) .pipeline-icon { background: #FCE7F3; color: #DB2777; }
.pipeline-step:nth-child(11) .pipeline-icon { background: #F3E8FF; color: #9333EA; }

.pipeline-step span {
    font-size: 11px;
    font-weight: 700;
    color: #1E293B;
    line-height: 1.25;
}

.pipeline-arrow {
    color: #94A3B8;
    font-size: 16px;
    font-weight: 700;
    flex-shrink: 0;
}

/* Chat Card Header */
.chat-card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: var(--card-bg);
    border-radius: 18px 18px 0 0;
    padding: 14px 20px;
    border: 1px solid var(--border-light);
    border-bottom: none;
    box-shadow: var(--shadow-card);
}

.chat-header-title {
    display: flex;
    align-items: center;
    gap: 10px;
}

.chat-header-icon {
    width: 32px;
    height: 32px;
    border-radius: 8px;
    background: #EDE9FE;
    color: var(--purple-primary);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 16px;
}

.chat-header-title h3 {
    margin: 0;
    font-size: 15px;
    font-weight: 700;
    color: var(--text-navy);
}

.chat-header-title p {
    margin: 0;
    font-size: 12px;
    color: #475569;
    font-weight: 500;
}

.live-indicator {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 5px 12px;
    border-radius: 9999px;
    background: #ECFDF5;
    color: #065F46;
    font-size: 11px;
    font-weight: 700;
    border: 1px solid #6EE7B7;
}

.live-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: #10B981;
    box-shadow: 0 0 0 2px rgba(16, 185, 129, 0.3);
}

/* Right Sidebar Cards */
.right-card {
    background: var(--card-bg);
    border-radius: 18px;
    padding: 16px;
    border: 1px solid var(--border-light);
    box-shadow: var(--shadow-card);
    margin-bottom: 14px;
}
/* ---- Right Settings Gradio Group readability fix ---- */

.right-sidebar-col .right-card {
    background: #FFFFFF !important;
    color: #0F172A !important;
    opacity: 1 !important;
}

.right-sidebar-col .right-card > div,
.right-sidebar-col .right-card .block,
.right-sidebar-col .right-card .form,
.right-sidebar-col .right-card .row {
    background: #FFFFFF !important;
    color: #0F172A !important;
    opacity: 1 !important;
}

/* Settings labels */
.right-sidebar-col .right-card label,
.right-sidebar-col .right-card label span,
.right-sidebar-col .right-card span[data-testid="block-info"] {
    color: #1E293B !important;
    opacity: 1 !important;
    font-weight: 600 !important;
}

/* Settings input boxes */
.right-sidebar-col .right-card input,
.right-sidebar-col .right-card textarea {
    color: #0F172A !important;
    background: #F8FAFC !important;
    border: 1px solid #94A3B8 !important;
    opacity: 1 !important;
}

/* Placeholder / helper text */
.right-sidebar-col .right-card input::placeholder,
.right-sidebar-col .right-card textarea::placeholder {
    color: #64748B !important;
    opacity: 1 !important;
}

/* ---- Left sustainability card readability ---- */

.sidebar-eco-card {
    background: #FFFFFF !important;
    color: #0F172A !important;
    opacity: 1 !important;
}

.sidebar-eco-card h3 {
    color: #0F172A !important;
    opacity: 1 !important;
}

.sidebar-eco-card p {
    color: #374151 !important;
    opacity: 1 !important;
}

.right-card-title {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 12px;
    font-size: 14px;
    font-weight: 700;
    color: var(--text-navy);
}

.impact-card {
    background: linear-gradient(135deg, #ECFDF5 0%, #D1FAE5 100%);
    border: 1px solid #A7F3D0;
    border-radius: 18px;
    padding: 14px;
    margin-bottom: 14px;
}

.impact-header {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    font-weight: 700;
    color: #064E3B;
    margin-bottom: 6px;
}

.impact-card p {
    margin: 0;
    font-size: 12px;
    color: #065F46;
    line-height: 1.45;
    font-weight: 500;
}

.demo-specs-card {
    background: #F8FAFC;
    border-radius: 14px;
    padding: 12px;
    border: 1px solid #CBD5E1;
    font-size: 12px;
}

.demo-specs-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 5px 0;
    border-bottom: 1px solid #E2E8F0;
}

.demo-specs-row:last-child {
    border-bottom: none;
}

.demo-specs-label {
    color: #475569;
    font-weight: 600;
}

.demo-specs-val {
    color: #0F172A;
    font-weight: 700;
    font-size: 11px;
}

/* Map Preview Graphic */
.map-preview-box {
    background: #F8FAFC;
    border: 1px solid #EEF2F6;
    border-radius: 14px;
    padding: 12px;
    text-align: center;
    margin-bottom: 10px;
}

.map-legend {
    display: flex;
    justify-content: space-around;
    font-size: 11px;
    font-weight: 600;
    color: #334155;
    margin-top: 8px;
}

/* Footer */
.footer-bar {
    text-align: center;
    font-size: 12px;
    color: #64748B;
    margin-top: 20px;
    padding: 14px 0;
    border-top: 1px solid #CBD5E1;
    font-weight: 500;
}

/* Gradio Component Styling */
.gradio-chatbot {
    border-radius: 0 0 18px 18px !important;
    border: 1px solid var(--border-light) !important;
    border-top: none !important;
    background: #FFFFFF !important;
    box-shadow: var(--shadow-card) !important;
}

.gradio-container button.primary, .gradio-container .primary-btn {
    background: linear-gradient(135deg, #5B48E0 0%, #4A38C8 100%) !important;
    color: white !important;
    border-radius: 12px !important;
    font-weight: 700 !important;
}

/* Input / label overrides */
.gradio-container label,
.gradio-container .label-wrap span {
    color: #1E293B !important;
    font-weight: 600 !important;
    font-size: 13px !important;
}

.gradio-container input[type=number],
.gradio-container input[type=text],
.gradio-container textarea {
    color: #0F172A !important;
    background: #F8FAFC !important;
    border: 1px solid #94A3B8 !important;
    border-radius: 10px !important;
}

.gradio-container .examples button {
    color: #334155 !important;
    font-weight: 600 !important;
    background: #F8FAFC !important;
    border: 1px solid #CBD5E1 !important;
    border-radius: 8px !important;
}

.gradio-container button[type=submit],
.gradio-container .send-btn {
    background: linear-gradient(135deg, #5B48E0 0%, #4A38C8 100%) !important;
    color: white !important;
    font-weight: 700 !important;
    border-radius: 12px !important;
}

/* ---- Targeted fix: real Gradio 6.x label/helper text contrast ----
   Gradio renders each component's visible label text inside
   <span data-testid="block-info">, NOT inside the <label> tag itself,
   and the Soft(primary_hue="purple") theme colors that span a light
   purple (#A855F7) that is nearly invisible on our light card
   backgrounds. This is the actual element behind "Latitude", "Longitude",
   "Remaining Range (km)" and "Search Radius (km, optional override)"
   being unreadable - confirmed by inspecting the live rendered DOM. */
.gradio-container span[data-testid="block-info"] {
    color: #1E293B !important;
    font-weight: 600 !important;
    opacity: 1 !important;
}

/* Gradio's own built-in footer ("Use via API", "Built with Gradio",
   "Settings") renders at very low contrast against our light page
   background - covered by "any other secondary/helper text" above. */
.gradio-container .show-api,
.gradio-container .built-with,
.gradio-container .settings {
    color: #475569 !important;
}
/* ---- Section-specific text color overrides ---- */
/* Navbar and brand */
.top-navbar, .top-navbar * {
    color: var(--text-navy) !important;
    opacity: 1 !important;
}

/* Sidebar navigation items */
.sidebar-nav, .sidebar-nav * {
    color: var(--text-navy) !important;
    opacity: 1 !important;
}

/* Hero banner */
.hero-banner, .hero-banner * {
    color: var(--text-navy) !important;
    opacity: 1 !important;
}

/* Agent pipeline */
.pipeline-container, .pipeline-container * {
    color: var(--text-navy) !important;
    opacity: 1 !important;
}

/* Chat header */
.chat-card-header, .chat-card-header * {
    color: var(--text-navy) !important;
    opacity: 1 !important;
}

/* Right side cards */
.right-card, .right-card * {
    color: var(--text-navy) !important;
    opacity: 1 !important;
}

/* Ensure headings stay dark */
.gradio-container .gr-markdown h1,
.gradio-container .gr-markdown h2,
.gradio-container .gr-markdown h3,
.gradio-container .gr-markdown h4,
.gradio-container .gr-markdown h5,
.gradio-container .gr-markdown h6 {
    color: var(--text-navy) !important;
}
"
/* ---- Additional text color overrides for Gradio components ---- */
/* Primary text inside cards */
.gradio-container .gr-text,
.gradio-container .gr-markdown,
.gradio-container .gr-html,
.gradio-container .gr-update-area,
.gradio-container .gr-chatbot *,
.gradio-container .gr-chatbot .message,
.gradio-container .gr-tooltip,
.gradio-container .gr-accordion,
.gradio-container .gr-block,
.gradio-container .gr-section {
    color: #0F172A !important;
}
/* Headings inside markdown */
.gradio-container .gr-markdown h1,
.gradio-container .gr-markdown h2,
.gradio-container .gr-markdown h3,
.gradio-container .gr-markdown h4,
.gradio-container .gr-markdown h5,
.gradio-container .gr-markdown h6 {
    color: #0F172A !important;
}
/* Secondary/helper text */
.gradio-container .gr-help,
.gradio-container .gr-info,
.gradio-container .gr-tip,
.gradio-container .gr-markdown p,
.gradio-container .gr-markdown li {
    color: #475569 !important;
}

/* =========================================================
   TRIP & SEARCH SETTINGS - FINAL INPUT VISIBILITY FIX
   ========================================================= */

.right-sidebar-col .right-card .gr-input,
.right-sidebar-col .right-card .gr-input-container,
.right-sidebar-col .right-card .input-container,
.right-sidebar-col .right-card .wrap {
    background: #F8FAFC !important;
    border: 1px solid #CBD5E1 !important;
    border-radius: 10px !important;
    opacity: 1 !important;
    visibility: visible !important;
}

/* Actual number input */
.right-sidebar-col .right-card input[type="number"] {
    display: block !important;
    visibility: visible !important;
    opacity: 1 !important;

    width: 100% !important;
    height: 42px !important;
    min-height: 42px !important;

    padding: 8px 12px !important;

    background: #F8FAFC !important;
    color: #0F172A !important;
    -webkit-text-fill-color: #0F172A !important;

    border: 1px solid #CBD5E1 !important;
    border-radius: 10px !important;

    font-size: 15px !important;
    font-weight: 500 !important;
}

/* Number input when focused */
.right-sidebar-col .right-card input[type="number"]:focus {
    background: #FFFFFF !important;
    color: #0F172A !important;
    -webkit-text-fill-color: #0F172A !important;
    border-color: #94A3B8 !important;
    outline: none !important;
}

/* Settings labels */
.right-sidebar-col .right-card label {
    color: #1E293B !important;
    opacity: 1 !important;
    font-weight: 600 !important;
}

/* Label text generated by Gradio */
.right-sidebar-col .right-card label span {
    color: #1E293B !important;
    opacity: 1 !important;
}

/* Make sure the whole Number component remains visible */
.right-sidebar-col .right-card .gradio-number,
.right-sidebar-col .right-card [data-testid="number"] {
    display: block !important;
    visibility: visible !important;
    opacity: 1 !important;
}

"""

with gr.Blocks(title="⚡ ChargeMate — EV Charging Assistant") as demo:
    # Inject Custom CSS
    gr.HTML(f"<style>{CUSTOM_CSS}</style>")

    # 1. Top Navigation Bar
    gr.HTML(
        """
        <div class="top-navbar">
            <div class="brand-section">
                <div class="brand-logo-badge">⚡</div>
                <div class="brand-info">
                    <h2>ChargeMate</h2>
                    <p>Plan. Charge. Go Further.</p>
                </div>
            </div>
            <div class="nav-pills">
                <span class="nav-pill active">Home</span>
                <span class="nav-pill">How It Works</span>
                <span class="nav-pill">About</span>
                <span class="nav-pill">Demo</span>
            </div>
            <div class="eco-badge">
                <div class="eco-icon">🍃</div>
                <div class="eco-text">
                    <h4>Sustainable Travel</h4>
                    <p>Brighter Tomorrow</p>
                </div>
            </div>
        </div>
        """
    )

    # 2. Main 3-Column Layout
    with gr.Row(elem_classes=["dashboard-grid"]):
        # Left Sidebar (scale 1.1)
        with gr.Column(elem_classes=["left-sidebar-col"]):
            gr.HTML(
                """
                <div class="sidebar-nav">
                    <div class="sidebar-item active">
                        <span>💬</span> AI Assistant
                    </div>
                    <div class="sidebar-item">
                        <span>📍</span> Find Chargers
                    </div>
                    <div class="sidebar-item">
                        <span>🗺️</span> Plan Route
                    </div>
                    <div class="sidebar-item">
                        <span>📅</span> My Bookings
                    </div>
                    <div class="sidebar-item">
                        <span>ℹ️</span> Learn & Help
                    </div>
                </div>

                <div class="sidebar-eco-card">
                    <div class="sidebar-eco-art">
                        <svg width="100%" height="80" viewBox="0 0 160 80" fill="none" xmlns="http://www.w3.org/2000/svg">
                            <rect width="160" height="80" rx="12" fill="#E6F4EA"/>
                            <path d="M0 65 Q 40 45, 80 55 T 160 50 L 160 80 L 0 80 Z" fill="#CEEAD6"/>
                            <circle cx="25" cy="40" r="10" fill="#34A853" opacity="0.8"/>
                            <circle cx="35" cy="42" r="8" fill="#1E8E3E" opacity="0.8"/>
                            <!-- EV Car -->
                            <rect x="75" y="48" width="55" height="18" rx="5" fill="#6C5CE7"/>
                            <path d="M85 48 L93 38 L117 38 L125 48 Z" fill="#8C7AE6"/>
                            <circle cx="88" cy="66" r="6" fill="#2D3748"/>
                            <circle cx="118" cy="66" r="6" fill="#2D3748"/>
                            <!-- Charger Post -->
                            <rect x="52" y="32" width="10" height="34" rx="2" fill="#10B981"/>
                            <circle cx="57" cy="40" r="3" fill="#FFFFFF"/>
                            <path d="M57 48 L65 54 L75 54" stroke="#10B981" stroke-width="2" stroke-linecap="round"/>
                        </svg>
                    </div>
                    <h3>Drive Electric<br/>Drive Change 🍃</h3>
                    <p>"A cleaner planet is a brighter future."</p>
                </div>
                """
            )

        # Right Sidebar (instantiated first in Python so lat_in/lon_in exist for ChatInterface, displayed on right via flex order)
        with gr.Column(elem_classes=["right-sidebar-col"]):
            # Trip & Search Settings
            with gr.Group(elem_classes=["right-card"]):
                gr.HTML("<div class='right-card-title'>⚙️ Trip & Search Settings</div>")
                with gr.Row():
                    lat_in = gr.Number(label="Latitude", value=DEFAULT_LAT, precision=4)
                    lon_in = gr.Number(label="Longitude", value=DEFAULT_LON, precision=4)
                range_in = gr.Number(label="Remaining Range (km)", value=40)
                radius_in = gr.Number(label="Search Radius (km, optional override)", value=None)
                debug_in = gr.Checkbox(label="Show technical debug info", value=False)

            # Live Map Preview Card
            gr.HTML(
                """
                <div class="right-card">
                    <div class="right-card-title">🗺️ Live Map Preview</div>
                    <div class="map-preview-box">
                        <svg width="100%" height="110" viewBox="0 0 200 110" fill="none" xmlns="http://www.w3.org/2000/svg">
                            <rect width="200" height="110" rx="8" fill="#F1F5F9"/>
                            <!-- Radar concentric circles -->
                            <circle cx="100" cy="55" r="45" stroke="#CBD5E1" stroke-width="1" stroke-dasharray="3 3"/>
                            <circle cx="100" cy="55" r="28" stroke="#E2E8F0" stroke-width="1"/>
                            <!-- Center vehicle pin -->
                            <circle cx="100" cy="55" r="7" fill="#6C5CE7"/>
                            <circle cx="100" cy="55" r="14" fill="#6C5CE7" fill-opacity="0.2"/>
                            <!-- Charger Pins -->
                            <circle cx="80" cy="35" r="5" fill="#10B981"/>
                            <circle cx="130" cy="45" r="5" fill="#10B981"/>
                            <circle cx="115" cy="80" r="5" fill="#F59E0B"/>
                            <circle cx="65" cy="70" r="5" fill="#EF4444"/>
                        </svg>
                        <div class="map-legend">
                            <span>🟢 Available</span>
                            <span>🟡 Limited</span>
                            <span>🔴 Occupied</span>
                        </div>
                    </div>
                </div>
                """
            )

            # Small Steps Impact Card
            gr.HTML(
                """
                <div class="impact-card">
                    <div class="impact-header">
                        <span>🌱</span> Small Steps. Big Impact.
                    </div>
                    <p>Every electric mile counts towards a cleaner, greener tomorrow. →</p>
                </div>
                """
            )

            # Demo Status Card
            gr.HTML(
                """
                <div class="right-card">
                    <div class="right-card-title">📊 Demo Status</div>
                    <div class="demo-specs-card">
                        <div class="demo-specs-row">
                            <span class="demo-specs-label">AI Reasoning</span>
                            <span class="demo-specs-val">Groq GPT-OSS-20B</span>
                        </div>
                        <div class="demo-specs-row">
                            <span class="demo-specs-label">Station Data</span>
                            <span class="demo-specs-val">Open Charge Map</span>
                        </div>
                        <div class="demo-specs-row">
                            <span class="demo-specs-label">Booking</span>
                            <span class="demo-specs-val">Simulated Demo</span>
                        </div>
                    </div>
                </div>
                """
            )

        # Center Main Content Column (scale 3.6)
        with gr.Column(elem_classes=["center-main-col"]):
            # Hero Card
            gr.HTML(
                """
                <div class="hero-banner">
                    <div class="hero-content">
                        <h1>Your AI-Powered<br/><span>EV Charging</span> Assistant</h1>
                        <p>Find the nearest chargers, check availability, plan your route, and even book — all in one place.</p>
                    </div>
                    <div class="hero-art-side">
                        <div class="hero-slogan">Charge Today for a Greener Tomorrow 💚</div>
                        <svg width="120" height="55" viewBox="0 0 120 55" fill="none" xmlns="http://www.w3.org/2000/svg">
                            <path d="M10 45 Q 60 20, 110 45" stroke="#10B981" stroke-width="3" stroke-linecap="round"/>
                            <circle cx="60" cy="30" r="16" fill="#EDE9FE"/>
                            <text x="60" y="35" text-anchor="middle" font-size="14" fill="#6C5CE7">⚡</text>
                        </svg>
                    </div>
                </div>
                """
            )

            # Agentic AI Pipeline
            gr.HTML(
                """
                <div class="pipeline-container">
                    <div class="pipeline-step">
                        <div class="pipeline-icon">💬</div>
                        <span>Understand<br/>Request</span>
                    </div>
                    <div class="pipeline-arrow">›</div>
                    <div class="pipeline-step">
                        <div class="pipeline-icon">🔍</div>
                        <span>Search<br/>Chargers</span>
                    </div>
                    <div class="pipeline-arrow">›</div>
                    <div class="pipeline-step">
                        <div class="pipeline-icon">📅</div>
                        <span>Check<br/>Availability</span>
                    </div>
                    <div class="pipeline-arrow">›</div>
                    <div class="pipeline-step">
                        <div class="pipeline-icon">🗺️</div>
                        <span>Plan<br/>Route</span>
                    </div>
                    <div class="pipeline-arrow">›</div>
                    <div class="pipeline-step">
                        <div class="pipeline-icon">⭐</div>
                        <span>Give<br/>Decision</span>
                    </div>
                    <div class="pipeline-arrow">›</div>
                    <div class="pipeline-step">
                        <div class="pipeline-icon">🎫</div>
                        <span>Simulate<br/>Booking</span>
                    </div>
                </div>
                """
            )

            # Chat Card Header
            gr.HTML(
                """
                <div class="chat-card-header">
                    <div class="chat-header-title">
                        <div class="chat-header-icon">💬</div>
                        <div>
                            <h3>Chat with ChargeMate</h3>
                            <p>Ask anything about EV chargers, routes, or bookings.</p>
                        </div>
                    </div>
                    <div class="live-indicator">
                        <span class="live-dot"></span>
                        <span>Powered by Groq + Open Charge Map</span>
                    </div>
                </div>
                """
            )

            # Main Gradio ChatInterface
            gr.ChatInterface(
                fn=chat_respond,
                additional_inputs=[lat_in, lon_in, range_in, radius_in, debug_in],
                examples=[
                    ["Find me the nearest available charger"],
                    ["I need a charger within 75 km"],
                    ["What's the cheapest charger nearby?"],
                    ["I need the fastest charger"],
                ],
                title=None,
            )

    # 3. Footer
    gr.HTML(
        """
        <div class="footer-bar">
            Built with Python • Gradio • Groq • Open Charge Map &nbsp;|&nbsp; <strong>ChargeMate Agentic AI EV Assistant</strong>
        </div>
        """
    )

if __name__ == "__main__":
    if "--check-llm" in sys.argv:
        print("Running Intent Agent self-test (one real API call)...")
        ok, detail = orchestrator.intent_agent.self_test()
        if ok:
            print(f"PASS - LLM reachable, model replied: {detail!r}")
            print("You are good to demo with live LLM reasoning.")
            sys.exit(0)
        else:
            print(f"FAIL - {detail}")
            print("Fix this before your demo,")
            print("run on the rule-based fallback instead of the LLM.")
            sys.exit(1)
    demo.launch(server_name="0.0.0.0",server_port=int(os.environ.get("PORT", 10000)),share=False)
