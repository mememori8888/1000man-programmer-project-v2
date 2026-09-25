import unittest
from datetime import date, timedelta
from decimal import Decimal

from finance import (ACTUAL, PLANNED, effective_records, ml_forecast, normalize_voice_transactions,
                     parse_finance_event, simulate, summary_event, transaction_event)


def record(record_id, kind, day, amount, account, status=ACTUAL, rate="0", label="未判定"):
    return {"id": record_id, "kind": kind, "date": day, "amount": str(amount), "currency": "JPY",
            "account": account, "status": status, "annual_rate_percent": str(rate), "value_label": label}


class FinanceRulesTest(unittest.TestCase):
    def test_only_prefixed_structured_calendar_events_are_parsed(self):
        self.assertIsNone(parse_finance_event({"summary": "今日のタスク", "description": "金額: 1000"}))
        parsed = parse_finance_event({"id": "event-1", "summary": "財務: 支出", "description": "金額: 1,200円\n通貨: JPY\n口座: 現金\n日付: 2026-09-14\n状態: 実績\n区分: 必要支出", "start": {"date": "2026-09-14"}})
        self.assertEqual(parsed["amount"], "1200")
        self.assertEqual(parsed["value_label"], "必要支出")
        self.assertIsNone(parse_finance_event({"id": "event-2", "summary": "財務: 支出", "description": "金額: 1\n通貨: USD\n口座: 現金", "start": {"date": "2026-09-14"}}))

    def test_html_calendar_description_and_separate_repayment_accounts_are_parsed(self):
        event = {"id": "repay-1", "summary": "財務: 返済", "description": (
            "金額: 1,200円<br>通貨: JPY<br>借入名: ローンA<br>支払口座: 普通預金<br>"
            "日付: 2026-09-14<br>状態: 実績"), "start": {"date": "2026-09-14"}}
        parsed = parse_finance_event(event)
        self.assertEqual(parsed["account"], "ローンA")
        self.assertEqual(parsed["cash_account"], "普通預金")
        copied = parse_finance_event({"id": "copy", "summary": "財務: 返済",
                                      "description": transaction_event(parsed)["description"], "start": {"date": "2026-09-14"}})
        self.assertEqual(copied["amount"], "1200")

    def test_voice_normalization_separates_actual_and_planned(self):
        records = normalize_voice_transactions("audio", "2026-09-14", [
            {"kind": "支出", "amount": "500", "currency": "JPY", "account": "現金", "date": "2026-09-14", "status": ACTUAL, "value_label": "必要支出", "note": "昼食", "replaces": "", "evidence": "現金で500円払った"},
            {"kind": "支出", "amount": "3000", "currency": "JPY", "account": "現金", "date": "2026-09-15", "status": PLANNED, "value_label": "生き金", "note": "書籍", "replaces": "", "evidence": "9月15日に現金で3000円の本を買う予定"},
        ], "現金で500円払った。9月15日に現金で3000円の本を買う予定")
        self.assertEqual([item["status"] for item in records], [ACTUAL, PLANNED])
        self.assertEqual(records[1]["value_label"], "生き金")

    def test_projection_uses_actual_amounts_and_keeps_value_label_out_of_cash(self):
        records = [
            record("cash", "残高", "2026-09-14", 10000, "現金"),
            record("debt", "借入", "2026-09-14", 5000, "ローン", rate="36.5"),
            record("income", "収入", "2026-09-15", 2000, "現金", PLANNED),
            record("repay", "返済", "2026-09-15", 1000, "ローン", PLANNED),
            record("purchase", "支出", "2026-09-15", 3000, "現金", PLANNED, label="生き金"),
        ]
        baseline = simulate(records, date(2026, 9, 14), forecast_days=2, payoff_horizon_days=2)
        scenario = simulate(records, date(2026, 9, 14), forecast_days=2, payoff_horizon_days=2, include_planned_purchases=True)
        self.assertEqual(baseline["cash_now"], Decimal("10000"))
        self.assertEqual(scenario["cash_minimum_30d"], Decimal("8000"))
        self.assertEqual(baseline["safe_spend"], baseline["cash_minimum_30d"])

    def test_balances_and_actual_transactions_are_scoped_to_each_cash_account(self):
        records = [
            record("cash-a", "残高", "2026-09-10", 100, "口座A"),
            record("cash-b", "残高", "2026-09-14", 200, "口座B"),
            record("income-a", "収入", "2026-09-12", 30, "口座A"),
            record("planned-a", "収入", "2026-09-13", 500, "口座A", PLANNED),
            record("expense-a", "支出", "2026-09-13", 20, "口座A"),
        ]
        result = simulate(records, "2026-09-14", forecast_days=0, payoff_horizon_days=0)
        self.assertEqual(result["cash_now"], Decimal("310"))

    def test_repayment_decreases_payment_cash_account_and_loan_principal(self):
        records = [
            record("cash", "残高", "2026-09-10", 1000, "普通預金"),
            {**record("loan", "借入", "2026-09-10", 500, "ローンA", rate="0"), "rate_known": True},
            {**record("repay", "返済", "2026-09-11", 100, "ローンA"), "cash_account": "普通預金"},
        ]
        result = simulate(records, "2026-09-14", forecast_days=0, payoff_horizon_days=0)
        self.assertEqual(result["cash_now"], Decimal("900"))
        self.assertEqual(result["debt_now"], Decimal("400"))

    def test_corrections_keep_source_history_and_latest_correction_wins(self):
        original = record("voice:a:0", "支出", "2026-09-10", 100, "現金")
        correction1 = {"id": "voice:a:1", "kind": "訂正", "date": "2026-09-11", "currency": "JPY",
                       "replaces": "voice:a:0", "amount": "80", "account": "", "cash_account": "",
                       "status": None, "value_label": None, "corrected_date": None}
        correction2 = {"id": "voice:a:2", "kind": "訂正", "date": "2026-09-12", "currency": "JPY",
                       "replaces": "voice:a:0", "amount": "60", "account": "", "cash_account": "",
                       "status": None, "value_label": None, "corrected_date": None}
        active = effective_records([original, correction1, correction2])
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["id"], "voice:a:2")
        self.assertEqual(active[0]["amount"], "60")
        self.assertEqual(original["amount"], "100")

    def test_payoff_is_unavailable_without_interest_rate(self):
        result = simulate([record("cash", "残高", "2026-09-14", 1000, "現金"), record("debt", "借入", "2026-09-14", 100, "借入A")], "2026-09-14", payoff_horizon_days=5)
        self.assertIsNone(result["payoff_date"])
        self.assertEqual(result["missing_interest_accounts"], ["借入A"])

    def test_ml_is_gated_then_evaluated_after_sixty_days(self):
        start = date(2026, 7, 1)
        short = [record(f"r{i}", "収入", (start + timedelta(days=i)).isoformat(), 1000, "現金") for i in range(59)]
        self.assertFalse(ml_forecast(short, "2026-08-28", minimum_days=60)["available"])
        records = [record(f"r{i}", "収入" if i % 2 == 0 else "支出", (start + timedelta(days=i)).isoformat(), 1000 if i % 2 == 0 else 400, "現金", label="生き金" if i % 5 == 0 else "必要支出") for i in range(61)]
        result = ml_forecast(records, "2026-08-30", minimum_days=60, horizon_days=30)
        self.assertTrue(result["available"])
        self.assertEqual(result["model"], "Ridge")

    def test_summary_event_is_idempotent_for_a_day(self):
        self.assertEqual(summary_event("2026-09-14", "x")["id"], summary_event("2026-09-14", "y")["id"])


if __name__ == "__main__":
    unittest.main()
