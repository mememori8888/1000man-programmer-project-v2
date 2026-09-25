"""Pure date, calendar and asset rules; no API calls."""
import hashlib
import html
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo


def recording_time(name):
    match = re.match(r"^(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})\.", name)
    if not match:
        raise ValueError("Recording filename must be YYYY-MM-DD_HH-MM-SS.ext")
    return datetime.strptime("_".join(match.groups()), "%Y-%m-%d_%H-%M-%S")


def upload_window_time(uploaded_at, timezone="Asia/Tokyo", cutoff_hour=5):
    """Return local upload time and the date on which its 05:00 window closes."""
    if not isinstance(cutoff_hour, int) or not 0 <= cutoff_hour <= 23:
        raise ValueError("cutoff_hour must be an integer from 0 through 23")
    value = str(uploaded_at or "").strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    stamp = datetime.fromisoformat(value)
    if stamp.tzinfo is None:
        raise ValueError("Drive upload timestamp must include a timezone")
    local = stamp.astimezone(ZoneInfo(timezone))
    return local, (local - timedelta(hours=cutoff_hour) + timedelta(days=1)).date()


def event_id(kind, day):
    return hashlib.sha256(f"voice-coach-v1:{kind}:{day}".encode()).hexdigest()


def daily_text(records):
    return "\n\n".join(f"■ {r['name']}\n{r['text']}" for r in
                       sorted(records, key=lambda r: (r['recorded_at'], r['id'])))


def event_body(kind, day, text, source_url, limit=7000):
    # Calendar descriptions interpret HTML. Escape transcript to retain literal text.
    description = html.escape(text).replace("\n", "<br>")
    if len(description.encode("utf-8")) > limit:
        # Never silently summarize, truncate or split the user's single daily event.
        label = "文字起こし全文" if kind == "transcript" else "一問一答・コーチの全文"
        description = ('全文がカレンダーの安全な保存サイズを超えました。要約・省略した本文は登録していません。'
                       f'<br><a href="{html.escape(source_url, quote=True)}">{label}を開く</a>')
    return {
        "id": event_id(kind, day),
        "summary": ("音声メモ " if kind == "transcript" else "今日のコーチ ") + day,
        "description": description,
        "start": {"date": day},
        "end": {"date": (date.fromisoformat(day) + timedelta(days=1)).isoformat()},
        "transparency": "transparent", "visibility": "private",
        "reminders": {"useDefault": False},
        "extendedProperties": {"private": {"app": "voice-coach-v1", "kind": kind}},
    }


def asset_snapshot(observations):
    """Latest explicit balance for each account; currencies never implicitly converted."""
    latest = {}
    unresolved = []
    for o in sorted(observations, key=lambda x: (x.get("as_of", ""), x.get("recorded_at", ""))):
        try:
            if o.get("kind") not in ("cash", "investment", "debt"):
                raise ValueError()
            if not o.get("account") or not re.fullmatch(r"[A-Z]{3}", o.get("currency", "")):
                raise ValueError()
            date.fromisoformat(o["as_of"])
            amount = Decimal(str(o["amount"]))
            if not amount.is_finite() or amount < 0:
                raise ValueError()
            if not o.get("evidence"):
                raise ValueError()
            latest[(o["kind"], o["account"], o["currency"])] = {**o, "amount": str(amount)}
        except (KeyError, ValueError, InvalidOperation):
            unresolved.append(o)
    totals = {}
    for o in latest.values():
        c = o["currency"]
        totals[c] = totals.get(c, Decimal(0)) + Decimal(o["amount"]) * (-1 if o["kind"] == "debt" else 1)
    return {"accounts": list(latest.values()), "reported_net_assets": {k: str(v) for k, v in totals.items()},
            "unresolved": unresolved,
            "note": "自己申告の最新値の合算。日付が異なる場合があり、未申告口座を含む総資産や本日の確定値ではない。"}
