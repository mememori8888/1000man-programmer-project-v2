"""Deterministic personal-finance simulation rules.

This module intentionally accepts only events with the ``財務:`` prefix.  It
never treats ordinary calendar text as financial data.
"""
from __future__ import annotations

import hashlib
import html
import re
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


FINANCE_APP = "finance-simulator-v1"
FINANCE_PREFIX = "財務:"
TYPES = {"残高", "借入", "収入", "支出", "返済", "支払予定", "訂正"}
ACTUAL = "実績"
PLANNED = "予定"
VALUE_LABELS = {"生き金", "必要支出", "任意支出", "未判定"}


def finance_defaults(config):
    return {
        "enabled": True,
        "lookback_days": 365,
        "calendar_future_days": 365,
        "forecast_days": 30,
        "payoff_horizon_days": 3650,
        "safety_reserve_yen": 0,
        "ml_min_history_days": 60,
        "ml_horizon_days": 30,
    } | config.get("finance_simulation", {})


def event_id(kind, key):
    return hashlib.sha256(f"{FINANCE_APP}:{kind}:{key}".encode()).hexdigest()


def _text(value):
    value = html.unescape(value or "")
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    return re.sub(r"<[^>]+>", "", value).strip()


def _fields(description):
    result = {}
    for line in _text(description).splitlines():
        if "：" in line:
            key, value = line.split("：", 1)
        elif ":" in line:
            key, value = line.split(":", 1)
        else:
            continue
        result[key.strip()] = value.strip()
    return result


def _amount(value):
    try:
        value = re.sub(r"[￥¥円,\s]", "", str(value))
        amount = Decimal(value)
        if not amount.is_finite() or amount < 0:
            raise InvalidOperation
        return amount
    except (InvalidOperation, ValueError):
        return None


def _day(event, fields):
    value = fields.get("日付") or event.get("start", {}).get("date") or event.get("start", {}).get("dateTime", "")[:10]
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def parse_finance_event(event):
    """Return a normalized record for one manually entered finance event."""
    summary = (event.get("summary") or "").strip()
    if not summary.startswith(FINANCE_PREFIX) or event.get("app") == FINANCE_APP:
        return None
    kind = summary[len(FINANCE_PREFIX):].strip()
    if kind not in TYPES:
        return None
    fields = _fields(event.get("description"))
    amount_supplied = "金額" in fields
    amount = _amount(fields.get("金額", "")) if amount_supplied else None
    currency = fields.get("通貨", "JPY").upper()
    when = _day(event, fields)
    # Older manually entered records used 口座 for a loan as well.  Keep them
    # readable, while new repayment records use 借入名 and 支払口座 separately.
    account = (fields.get("借入名") or fields.get("口座", "")) if kind == "返済" else fields.get("口座", "")
    cash_account = fields.get("支払口座") or fields.get("口座", "")
    status = fields.get("状態")
    if kind != "訂正":
        status = status or ACTUAL
    if kind == "訂正":
        if not fields.get("訂正対象") or currency != "JPY" or (amount_supplied and amount is None):
            return None
    elif (amount is None or not account or not when or currency != "JPY" or status not in {ACTUAL, PLANNED}):
        return None
    rate_known = "年利" in fields
    rate = _amount(fields.get("年利", "0"))
    record = {
        "id": f"calendar:{event.get('calendar')}:{event.get('id')}", "source": "calendar", "source_event_id": event.get("id"),
        # A correction is timestamped by its Calendar event for audit ordering, but it
        # changes the original transaction date only when 日付 is explicitly supplied.
        "kind": kind, "date": when.isoformat() if when else "", "amount": str(amount) if amount is not None else None,
        "currency": currency, "account": account, "status": status,
        "value_label": fields.get("区分") if fields.get("区分") in VALUE_LABELS else None if kind == "訂正" else "未判定",
        "annual_rate_percent": str(rate or Decimal(0)), "note": fields.get("内容", "")[:300],
        "replaces": fields.get("訂正対象", ""),
        "cash_account": cash_account,
        "rate_known": rate_known,
        "corrected_date": when.isoformat() if kind == "訂正" and "日付" in fields and when else None,
    }
    return record


def normalize_voice_transactions(source_id, recorded_day, transactions, source_text=""):
    """Validate Gemini extraction without accepting arbitrary text as a transaction."""
    result = []
    for index, item in enumerate(transactions or []):
        if not isinstance(item, dict) or item.get("currency") != "JPY":
            continue
        kind = item.get("kind")
        if kind not in {"収入", "支出", "返済", "支払予定", "訂正"}:
            continue
        amount_supplied = item.get("amount") not in (None, "")
        amount = _amount(item.get("amount")) if amount_supplied else None
        account = str(item.get("account", "")).strip()[:100]
        status = item.get("status")
        if kind != "訂正":
            status = status or ACTUAL
        if kind == "訂正" and (not item.get("replaces") or (amount_supplied and amount is None)):
            continue
        if kind != "訂正" and (amount is None or not account or status not in {ACTUAL, PLANNED}):
            continue
        declared_date = str(item.get("date") or "").strip()
        try:
            when = date.fromisoformat(declared_date or recorded_day)
        except ValueError:
            continue
        label = item.get("value_label")
        evidence = str(item.get("evidence", ""))[:500]
        normalized_evidence = re.sub(r"[￥¥円,\s]", "", evidence)
        if kind != "訂正" and (str(amount) not in normalized_evidence or account not in evidence):
            continue
        if when != date.fromisoformat(recorded_day):
            date_mentions = {when.isoformat(), f"{when.month}月{when.day}日"}
            if not any(value in evidence for value in date_mentions):
                continue
        result.append({
            "id": f"voice:{source_id}:{index}", "source": "voice", "source_id": source_id,
            "kind": kind, "date": when.isoformat(), "amount": str(amount) if amount is not None else None, "currency": "JPY",
            "account": account, "status": status, "value_label": label if label in VALUE_LABELS else "未判定",
            "annual_rate_percent": "0", "note": str(item.get("note", ""))[:300],
            "replaces": str(item.get("replaces", ""))[:160], "evidence": evidence,
            "cash_account": str(item.get("cash_account") or account).strip()[:100],
            "corrected_date": when.isoformat() if kind == "訂正" and declared_date else None,
        })
    return result


def _money(value):
    return Decimal(str(value or "0"))


def _latest_balance(records, kind):
    latest = {}
    for record in sorted(records, key=lambda r: (r.get("date", ""), r.get("id", ""))):
        if record.get("kind") != kind or record.get("currency") != "JPY" or record.get("status") != ACTUAL:
            continue
        latest[record.get("account")] = record
    return latest


def effective_records(records):
    """Preserve source records while applying an explicit correction to its target."""
    active = {record["id"]: dict(record) for record in records if record.get("kind") != "訂正"}
    aliases = {record_id: record_id for record_id in active}
    for correction in sorted((r for r in records if r.get("kind") == "訂正"), key=lambda r: (r.get("date", ""), r.get("id", ""))):
        target_id = aliases.get(correction.get("replaces"), correction.get("replaces"))
        target = active.get(target_id)
        if not target:
            continue
        updated = dict(target)
        for field in ("amount", "account", "cash_account", "status", "value_label"):
            value = correction.get(field)
            if value not in (None, ""):
                updated[field] = value
        if correction.get("corrected_date"):
            updated["date"] = correction["corrected_date"]
        updated["id"] = correction["id"]
        del active[target_id]
        active[updated["id"]] = updated
        aliases[correction["replaces"]] = updated["id"]
        aliases[updated["id"]] = updated["id"]
    return list(active.values())


def financial_state(records, as_of):
    """Build cash and debt state. Explicit balances override earlier transaction history."""
    as_of = date.fromisoformat(as_of) if isinstance(as_of, str) else as_of
    records = [r for r in effective_records(records) if r.get("currency") == "JPY" and r.get("date", "") <= as_of.isoformat()]
    cash = {name: _money(r["amount"]) for name, r in _latest_balance(records, "残高").items()}
    debts = {name: {"principal": _money(r["amount"]), "annual_rate_percent": _money(r.get("annual_rate_percent")),
                    "rate_known": bool(r.get("rate_known", False))}
             for name, r in _latest_balance(records, "借入").items()}
    if not cash:
        cash = {"未指定": Decimal(0)}
    balance_anchor = {name: item.get("date", "") for name, item in _latest_balance(records, "残高").items()}
    debt_anchor = {name: item.get("date", "") for name, item in _latest_balance(records, "借入").items()}
    for record in sorted(records, key=lambda r: (r.get("date", ""), r.get("id", ""))):
        amount = _money(record.get("amount"))
        cash_account = record.get("cash_account") or record["account"]
        after_cash_anchor = record["date"] > balance_anchor.get(cash_account, "")
        if record["kind"] == "収入" and record["status"] == ACTUAL and after_cash_anchor:
            cash[cash_account] = cash.get(cash_account, Decimal(0)) + amount
        elif record["kind"] in {"支出", "支払予定"} and record["status"] == ACTUAL and after_cash_anchor:
            cash[cash_account] = cash.get(cash_account, Decimal(0)) - amount
        elif record["kind"] == "返済" and record["status"] == ACTUAL:
            if after_cash_anchor:
                cash[cash_account] = cash.get(cash_account, Decimal(0)) - amount
            if record["date"] > debt_anchor.get(record["account"], "") and record["account"] in debts:
                debts[record["account"]]["principal"] = max(Decimal(0), debts[record["account"]]["principal"] - amount)
    return cash, debts


def _future_records(records, start, include_planned_purchases):
    result = defaultdict(list)
    for r in effective_records(records):
        if r.get("currency") != "JPY" or r.get("status") != PLANNED or r.get("date", "") < start.isoformat():
            continue
        if r["kind"] not in {"収入", "支出", "返済", "支払予定"}:
            continue
        if r["kind"] == "支出" and not include_planned_purchases:
            continue
        result[r["date"]].append(r)
    return result


def simulate(records, today, forecast_days=30, payoff_horizon_days=3650, safety_reserve_yen=0, include_planned_purchases=False):
    """Project cash and debt using explicit scheduled transactions and daily interest."""
    today = date.fromisoformat(today) if isinstance(today, str) else today
    cash, debts = financial_state(records, today)
    scheduled = _future_records(records, today, include_planned_purchases)
    current_cash = sum(cash.values(), Decimal(0))
    daily = []
    min_cash = current_cash
    projected = current_cash
    missing = [name for name, debt in debts.items() if not debt["rate_known"]]
    has_planned_repayment = any(r.get("kind") == "返済" and r.get("status") == PLANNED for r in effective_records(records))
    payoff_day = None
    for offset in range(payoff_horizon_days + 1):
        day = today + timedelta(days=offset)
        for debt in debts.values():
            if debt["principal"] > 0:
                debt["principal"] += (debt["principal"] * debt["annual_rate_percent"] / Decimal("100") / Decimal("365"))
        for record in scheduled.get(day.isoformat(), []):
            amount = _money(record["amount"])
            if record["kind"] == "収入":
                projected += amount
            elif record["kind"] in {"支出", "支払予定"}:
                projected -= amount
            elif record["kind"] == "返済":
                projected -= amount
                debt = debts.get(record["account"])
                if debt:
                    debt["principal"] = max(Decimal(0), debt["principal"] - amount)
        if offset <= forecast_days:
            daily.append({"date": day.isoformat(), "cash": projected})
            min_cash = min(min_cash, projected)
        if debts and all(debt["principal"] <= Decimal("1") for debt in debts.values()):
            payoff_day = day
            break
    if missing:
        payoff_day = None
    return {
        "cash_now": current_cash, "cash_minimum_30d": min_cash,
        "safe_spend": max(Decimal(0), min_cash - _money(safety_reserve_yen)),
        "debt_now": sum((debt["principal"] for debt in debts.values()), Decimal(0)),
        "payoff_date": payoff_day.isoformat() if payoff_day else None,
        "payoff_reason": ("利率未登録" if missing else ("返済予定なし" if debts and not has_planned_repayment else
                          "予測期間内に完済しない" if debts and not payoff_day else "")),
        "missing_interest_accounts": missing,
        "daily": daily,
    }


def ml_forecast(records, today, minimum_days=60, horizon_days=30):
    """Educational Ridge baseline with walk-forward holdout MAE."""
    days = sorted({r.get("date") for r in records if r.get("status") == ACTUAL and r.get("currency") == "JPY" and r.get("date")})
    if len(days) < minimum_days:
        return {"available": False, "reason": f"実績日数が{minimum_days}日に不足"}
    try:
        import numpy as np
        from sklearn.linear_model import Ridge
        from sklearn.metrics import mean_absolute_error
    except ImportError:
        return {"available": False, "reason": "scikit-learn未導入"}
    today = date.fromisoformat(today) if isinstance(today, str) else today
    first = date.fromisoformat(days[0])
    actual = defaultdict(lambda: {"income": Decimal(0), "expense": Decimal(0), "repay": Decimal(0), "living": Decimal(0)})
    for r in records:
        if r.get("status") != ACTUAL or r.get("currency") != "JPY":
            continue
        amount = _money(r.get("amount"))
        if r.get("kind") == "収入": actual[r["date"]]["income"] += amount
        if r.get("kind") in {"支出", "支払予定"}: actual[r["date"]]["expense"] += amount
        if r.get("kind") == "返済": actual[r["date"]]["repay"] += amount
        if r.get("value_label") == "生き金": actual[r["date"]]["living"] += amount
    series, cash = [], Decimal(0)
    for offset in range((today - first).days + 1):
        day = first + timedelta(days=offset)
        row = actual[day.isoformat()]
        cash += row["income"] - row["expense"] - row["repay"]
        series.append((day, row, cash))
    X, y = [], []
    for i in range(7, len(series) - horizon_days):
        trailing = series[max(0, i - 7):i]
        income7 = sum((x[1]["income"] for x in trailing), Decimal(0))
        expense7 = sum((x[1]["expense"] for x in trailing), Decimal(0))
        repay7 = sum((x[1]["repay"] for x in trailing), Decimal(0))
        living7 = sum((x[1]["living"] for x in trailing), Decimal(0))
        target = series[i + horizon_days][2]
        X.append([float(series[i][2]), float(income7), float(expense7), float(repay7), float(living7)])
        y.append(float(target))
    if len(X) < 12:
        return {"available": False, "reason": "評価可能な履歴が不足"}
    first_test = max(8, int(len(X) * 0.6))
    errors = []
    for cutoff in range(first_test, len(X)):
        model_at_cutoff = Ridge(alpha=1.0).fit(X[:cutoff], y[:cutoff])
        errors.append(abs(y[cutoff] - float(model_at_cutoff.predict([X[cutoff]])[0])))
    model = Ridge(alpha=1.0).fit(X, y)
    latest_trailing = series[-7:]
    latest = [float(series[-1][2]),
              float(sum((x[1]["income"] for x in latest_trailing), Decimal(0))),
              float(sum((x[1]["expense"] for x in latest_trailing), Decimal(0))),
              float(sum((x[1]["repay"] for x in latest_trailing), Decimal(0))),
              float(sum((x[1]["living"] for x in latest_trailing), Decimal(0)))]
    mae = float(mean_absolute_error([0] * len(errors), errors)) if errors else None
    return {"available": True, "model": "Ridge", "horizon_days": horizon_days,
            "predicted_cash": Decimal(str(model.predict([latest])[0])), "mae": Decimal(str(mae)) if mae is not None else None,
            "samples": len(X)}


def yen(value):
    return f"{_money(value).quantize(Decimal('1'), rounding=ROUND_HALF_UP):,}円"


def render_summary(today, baseline, scenario, model):
    lines = ["財務エージェント『キャッシュナビ』", "財務シミュレーション", f"判定日: {today}", "", f"現在の手元残高: {yen(baseline['cash_now'])}",
             f"円建て借入残高: {yen(baseline['debt_now'])}", f"30日間の最低予測残高: {yen(baseline['cash_minimum_30d'])}",
             f"今日の安全支出上限: {yen(baseline['safe_spend'])}"]
    lines.append("推定完済日: " + (baseline["payoff_date"] or baseline.get("payoff_reason", "予測不能")))
    if baseline["missing_interest_accounts"]:
        lines.append("利率未登録の借入: " + "、".join(baseline["missing_interest_accounts"]))
    impact = scenario["cash_minimum_30d"] - baseline["cash_minimum_30d"]
    lines.extend(["", "■ 買い物予定を含めた試算", f"30日間の最低残高への影響: {yen(impact)}"])
    lines.extend(["", "■ 機械学習（学習実験）"])
    if model.get("available"):
        lines.append(f"{model['model']}による{model['horizon_days']}日後の手元残高: {yen(model['predicted_cash'])}")
        lines.append(f"時系列評価の平均絶対誤差: {yen(model['mae']) if model['mae'] is not None else '評価不足'}")
    else:
        lines.append("未表示: " + model.get("reason", "履歴不足"))
    lines.append("注記: 残高と完済予測は実額で計算し、生き金の判定は行動傾向の分析だけに使用します。")
    return "\n".join(lines)


def summary_event(today, text, limit=7000):
    description = html.escape(text).replace("\n", "<br>")
    if len(description.encode("utf-8")) > limit:
        description = "財務シミュレーション本文が長すぎるため、GCSの保存結果を確認してください。"
    return {"id": event_id("summary", today), "summary": f"財務シミュレーション {today}", "description": description,
            "start": {"date": today}, "end": {"date": (date.fromisoformat(today) + timedelta(days=1)).isoformat()},
            "transparency": "transparent", "visibility": "private", "reminders": {"useDefault": False},
            "extendedProperties": {"private": {"app": FINANCE_APP, "kind": "summary", "date": today}}}


def transaction_event(record):
    def line(label, value):
        return f"{label}: {value}" if value not in (None, "") else None

    description = "\n".join([
        item for item in [
            line("金額", record.get("amount")), "通貨: JPY", line("借入名" if record.get("kind") == "返済" else "口座", record.get("account")),
            f"日付: {record['date']}", line("状態", record.get("status")), line("区分", record.get("value_label")),
            line("支払口座", record.get("cash_account")), line("内容", record.get("note")),
            line("訂正対象", record.get("replaces")), f"取引ID: {record['id']}",
        ] if item
    ])
    return {"id": event_id("transaction", record["id"]), "summary": f"財務: {record['kind']}",
            "description": html.escape(description).replace("\n", "<br>"),
            "start": {"date": record["date"]}, "end": {"date": (date.fromisoformat(record["date"]) + timedelta(days=1)).isoformat()},
            "transparency": "transparent", "visibility": "private", "reminders": {"useDefault": False},
            "extendedProperties": {"private": {"app": FINANCE_APP, "kind": "transaction", "source_id": record["id"]}}}
