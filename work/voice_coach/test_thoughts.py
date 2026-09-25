import copy
import json
import unittest
from datetime import date

from thoughts import (DOC_MIME, collect_sources, monthly_event, previous_month,
                      run_monthly_focus, run_thought_inbox, split_document)


class Store:
    def __init__(self):
        self.data = {}

    def read(self, name, default=None):
        return copy.deepcopy(self.data.get(name, default))

    def write(self, name, value):
        self.data[name] = copy.deepcopy(value)

    def read_prefix(self, prefix):
        return [{"name": name, "data": copy.deepcopy(value)}
                for name, value in self.data.items() if name.startswith(prefix)]


class Workspace:
    def __init__(self):
        self.document_text = "一つ目\n\n二つ目\n\n三つ目\n\n四つ目"
        self.metadata = {"id": "doc", "name": "Inbox", "mimeType": DOC_MIME,
                         "parents": ["folder"], "modifiedTime": "2026-09-21T00:00:00Z", "trashed": False}
        self.task_data = {"active": [], "completed": []}
        self.created = []
        self.events = {}
        self.calendar = []
        self.fail_insert = False

    def file_metadata(self, file_id):
        return copy.deepcopy(self.metadata)

    def export_document(self, file_id):
        return self.document_text

    def all_tasks(self, include_completed_since=None, include_all_completed=False):
        return copy.deepcopy(self.task_data)

    def task_lists(self):
        return [{"id": "list", "title": "マイタスク"}]

    def insert_task(self, tasklist, body):
        if self.fail_insert:
            raise RuntimeError("insert failed")
        task = {"id": f"task-{len(self.created) + 1}", "status": "needsAction", **body,
                "tasklist_id": tasklist, "tasklist_title": "マイタスク"}
        self.created.append(task)
        self.task_data["active"].append(task)
        return copy.deepcopy(task)

    def context(self, calendars, start, end, include_app_owned=False):
        return copy.deepcopy(self.calendar)

    def archive(self, folder, kind, day, text):
        return "https://drive.google.com/file/d/archive/view"

    def upsert_event(self, calendar, body):
        self.events[body["id"]] = copy.deepcopy(body)


class AI:
    def __init__(self):
        self.calls = 0

    def generate(self, context_text, instruction, schema):
        self.calls += 1
        context = json.loads(context_text)
        if "sources" in context:
            decisions = ["selected_primary", "selected_support", "selected_support", "selected_support"]
            return {"items": [{
                "source_id": source["source_id"], "classification": "調査",
                "decision": decisions[index], "title": f"調べる {index + 1}", "goal": "前進",
                "reason": "次の行動", "done_definition": "結果を3行で残す",
                "estimated_minutes": 30, "due_date": "", "reconsider_when": "主要タスク完了後",
            } for index, source in enumerate(context["sources"])]}
        return {
            "review": "前月を確認しました。",
            "verified_metrics": [{"name": "完了", "value": "1件", "basis": "Tasks completed"}],
            "achievements": ["1件完了"],
            "unfinished": [],
            "hypotheses": [{"hypothesis": "午前に進む", "evidence": "完了記録", "confidence": "low"}],
            "next_month_focus": [{"focus": "提案", "reason": "収入", "success_measure": "3件"}],
            "stop_doing": [], "experiments": [], "consultations": [],
        }


def config(write=True):
    return {
        "drive_folder": "folder", "inbox_folder_id": "folder", "inbox_document_ids": ["doc"],
        "task_list_title": "マイタスク", "max_primary_tasks": 1, "max_support_tasks": 2,
        "write_google_tasks": write, "source_documents_read_only": True,
        "thought_voice_lookback_days": 0, "goals": [{"title": "ソロプレナーになる"}],
        "timezone": "Asia/Tokyo", "read_calendars": ["primary"], "write_calendar": "primary",
        "max_calendar_bytes": 7000,
    }


class ThoughtInboxTest(unittest.TestCase):
    def setUp(self):
        self.store, self.workspace, self.ai = Store(), Workspace(), AI()

    def test_document_split_and_folder_validation(self):
        self.assertEqual(split_document("\ufeffA\n\n B \n\n\nC"), ["A", "B", "C"])
        sources = collect_sources(config(), self.store, self.workspace, date(2026, 9, 21))
        self.assertEqual([item["text"] for item in sources], ["一つ目", "二つ目", "三つ目", "四つ目"])
        self.workspace.metadata["parents"] = ["other"]
        with self.assertRaises(RuntimeError):
            collect_sources(config(), self.store, self.workspace, date(2026, 9, 21))

    def test_creates_at_most_one_primary_and_two_support_tasks(self):
        summary = run_thought_inbox(config(), self.store, self.workspace, self.ai, date(2026, 9, 21),
                                    {"calendar": [], "assets": {}, "monthly_focus": {}})
        self.assertEqual(len(self.workspace.created), 3)
        self.assertEqual(len(summary["selected"]), 3)
        self.assertEqual(len(summary["created"]), 3)
        self.assertEqual(len(summary["deferred"]), 1)
        self.assertTrue(all("[thought-source:" in task["notes"] for task in self.workspace.created))

    def test_rerun_uses_task_marker_and_does_not_duplicate(self):
        run_thought_inbox(config(), self.store, self.workspace, self.ai, date(2026, 9, 21),
                          {"calendar": [], "assets": {}, "monthly_focus": {}})
        first_calls = self.ai.calls
        run_thought_inbox(config(), self.store, self.workspace, self.ai, date(2026, 9, 21),
                          {"calendar": [], "assets": {}, "monthly_focus": {}})
        self.assertEqual(len(self.workspace.created), 3)
        self.assertEqual(self.ai.calls, first_calls)

    def test_failed_task_insert_stays_retryable(self):
        self.workspace.fail_insert = True
        with self.assertRaises(RuntimeError):
            run_thought_inbox(config(), self.store, self.workspace, self.ai, date(2026, 9, 21),
                              {"calendar": [], "assets": {}, "monthly_focus": {}})
        records = self.store.data["thoughts/ledger.json"]["records"]
        failed = [record for record in records.values() if record.get("status") == "error"]
        self.assertEqual(len(failed), 1)

    def test_preview_does_not_write_tasks(self):
        run_thought_inbox(config(write=False), self.store, self.workspace, self.ai, date(2026, 9, 21),
                          {"calendar": [], "assets": {}, "monthly_focus": {}}, preview=True)
        self.assertEqual(self.workspace.created, [])
        self.assertNotIn("thoughts/ledger.json", self.store.data)


class MonthlyFocusTest(unittest.TestCase):
    def setUp(self):
        self.store, self.workspace, self.ai = Store(), Workspace(), AI()
        self.workspace.task_data = {
            "active": [{"id": "active", "title": "現在も未完了", "status": "needsAction"}],
            "completed": [{"id": "done", "title": "完了", "status": "completed",
                           "completed": "2026-08-20T10:00:00Z"}],
        }
        self.workspace.calendar = [
            {"id": "manual", "summary": "手入力予定", "app": None,
             "start": {"date": "2026-08-10"}, "end": {"date": "2026-08-11"}},
            {"id": "generated", "summary": "今日のコーチ", "app": "voice-coach-v1",
             "start": {"date": "2026-08-10"}, "end": {"date": "2026-08-11"}},
        ]

    def test_previous_month_boundary(self):
        self.assertEqual(previous_month(date(2026, 9, 1)), (date(2026, 8, 1), date(2026, 9, 1)))
        self.assertEqual(previous_month(date(2027, 1, 1)), (date(2026, 12, 1), date(2027, 1, 1)))

    def test_monthly_review_is_idempotent_and_excludes_generated_calendar(self):
        run_monthly_focus(config(), self.store, self.workspace, self.ai, date(2026, 9, 1))
        calls = self.ai.calls
        run_monthly_focus(config(), self.store, self.workspace, self.ai, date(2026, 9, 1))
        self.assertEqual(self.ai.calls, calls)
        self.assertEqual(len(self.workspace.events), 1)
        payload = self.store.data["focus/monthly/2026-08.json"]
        self.assertEqual(payload["input_ids"]["calendar_event_ids"], ["manual"])
        self.assertIn("focus_learning/monthly/latest.json", self.store.data)

    def test_monthly_event_id_is_stable(self):
        first = monthly_event("2026-08", date(2026, 9, 1), "a", "url")
        second = monthly_event("2026-08", date(2026, 9, 2), "b", "url")
        self.assertEqual(first["id"], second["id"])


if __name__ == "__main__":
    unittest.main()
