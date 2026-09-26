import copy
import json
import unittest
from unittest.mock import Mock, patch
from datetime import date, datetime
from zoneinfo import ZoneInfo
from types import SimpleNamespace
from app import Gemini, Workspace, cleanup_pairs_for_processed_audio, coach_units, compact_focus_calendar, focus_block_event, focus_summary_event, model_candidates, run, run_finance, run_focus


class MemoryStore:
    def __init__(self):
        self.data = {}
    def read(self, name, default=None):
        return copy.deepcopy(self.data.get(name, default))
    def write(self, name, value):
        self.data[name] = copy.deepcopy(value)
    def stage_audio(self, source_id, version, data, mime_type):
        class Staged:
            def __init__(self):
                self.deleted = False
            def delete(self):
                self.deleted = True
        staged = Staged()
        self.staged = getattr(self, 'staged', []) + [staged]
        return f'gs://test/{source_id}-{version}', staged


class FakeWorkspace:
    def __init__(self):
        self.files = [dict(id='a', name='2026-09-06_22-00-00.mp3', mimeType='audio/mpeg', size='10',
                           modifiedTime='v1', createdTime='2026-09-07T18:00:00Z')]
        self.events = {}
        self.fail_event = False
        self.trashed = []
        self.task_data = {"active": [], "completed": []}
        self.calendar_context = []
        self.all_task_calls = []
        self.context_calls = []
        self.fail_trash = False
        self.fail_verify = False
        self.metadata_files = {}
    def audio_files(self, folder):
        return self.files
    def audio(self, file_id):
        return getattr(self, 'audio_data', b'audio')
    def file_metadata(self, file_id):
        if file_id in self.metadata_files:
            return copy.deepcopy(self.metadata_files[file_id])
        for item in self.files:
            if item['id'] == file_id:
                return copy.deepcopy(item)
        raise RuntimeError('metadata not found')
    def archive(self, folder, kind, day, text):
        return 'https://drive.google.com/file/d/test/view'
    def upsert_event(self, calendar, body):
        if self.fail_event:
            self.fail_event = False
            raise RuntimeError('simulated calendar failure')
        self.events[body['id']] = body
    def app_events(self, calendar, app, kind, run_day):
        return [copy.deepcopy(event) for event in self.events.values()
                if event.get('extendedProperties', {}).get('private', {}).get('app') == app
                and event.get('extendedProperties', {}).get('private', {}).get('kind') == kind
                and event.get('extendedProperties', {}).get('private', {}).get('run_day') == run_day]
    def delete_event(self, calendar, event_id):
        self.events.pop(event_id, None)
    def context(self, calendars, start, end, include_app_owned=False):
        self.context_calls.append((calendars, start, end, include_app_owned))
        return copy.deepcopy(self.calendar_context)
    def task_lists(self):
        return [{"id": "list", "title": "マイタスク"}]
    def all_tasks(self, include_completed_since=None, include_all_completed=False):
        self.all_task_calls.append((include_completed_since, include_all_completed))
        return copy.deepcopy(self.task_data)
    def verify_saved_output(self, config, kind, day, text):
        if self.fail_verify:
            raise RuntimeError('saved output missing')
    def trash_processed_audio(self, folder, source):
        if self.fail_trash:
            self.fail_trash = False
            raise RuntimeError('temporary trash failure')
        self.trashed.append(source['id'])
        self.files = [f for f in self.files if f['id'] != source['id']]


class FakeAI:
    def __init__(self):
        self.calls = 0
        self.uri_calls = 0
        self.advice_calls = 0
    def transcribe(self, data, mime):
        self.calls += 1
        return 'えー、今日は銀行Aの残高が100円です。'
    def transcribe_uri(self, uri, mime):
        self.uri_calls += 1
        return '大きいWAVを文字起こししました。'
    def analyze(self, record):
        return {'balances': [], 'coach_request': ''}
    def analyze_finance(self, record):
        return {"transactions": [{"kind": "支出", "amount": "500", "currency": "JPY", "account": "現金",
                                  "date": record["day"], "status": "実績", "value_label": "必要支出",
                                  "note": "昼食", "replaces": "", "evidence": "現金で500円払った"}]}
    def generate(self, context, instruction, schema=None):
        self.advice_calls += 1
        self.last_context = context
        if schema:
            return {
                "review": "予定を見て、今日は一点集中にします。",
                "learning_update": {
                    "observations": ["午前の予定が少ない"],
                    "hypotheses": [{"hypothesis": "午前は提案作成を進めやすい", "evidence": "予定がない", "confidence": "低"}],
                    "working_rules": ["空き時間には収入に直結する作業を先に置く"],
                    "next_experiment": "午前に提案を1件送る",
                },
                "priority_assessment": [{"title": "提案作成", "priority": "高", "planning_horizon": "今日", "reason": "収入に直結する", "source_task_id": "task-1"}],
                "deprioritized": [{"title": "整理", "reason": "締切と収入への寄与が低い", "reconsider_when": "今週の主要案件を終えたら", "source_task_id": "task-2"}],
                "selected": [{"title": "提案作成", "reason": "収入に直結する", "source_task_id": "task-1"}],
                "not_today": [{"title": "整理", "reason": "今日の予定量では優先度が低い"}],
                "consultation": [{"title": "未確定", "reason": "必要情報が足りない", "question": "締切はいつですか"}],
                "money_plan": [{"action": "提案を1件送る", "reason": "受注確率を上げる"}],
                "focus_blocks": [{"title": "提案作成", "start": "2026-09-08T09:00:00+09:00", "end": "2026-09-08T10:00:00+09:00", "reason": "午前に空きがある", "source_task_id": "task-1"}],
            }
        return '今日できることを一つ選びましょう。'
    def coach(self, context):
        self.advice_calls += 1
        self.last_context = json.dumps(context, ensure_ascii=False)
        lines = ['音声メモへの一問一答']
        for number, unit in enumerate(context.get('coach_units', []), 1):
            lines.extend([f"Q{number}：{unit['text']}", f'A{number}：回答'])
        return '\n'.join(lines)


class GeminiModelSelectionTest(unittest.TestCase):
    def test_latest_flash_uses_configured_candidates(self):
        config = {
            'model': 'latest_flash',
            'model_candidates': ['gemini-flash-latest', 'gemini-3.8-flash', 'gemini-3-flash-preview', 'gemini-2.5-flash'],
        }
        self.assertEqual(model_candidates(config), ['gemini-flash-latest', 'gemini-3.8-flash', 'gemini-3-flash-preview', 'gemini-2.5-flash'])

    def test_explicit_model_is_respected(self):
        self.assertEqual(model_candidates({'model': 'gemini-2.5-flash'}), ['gemini-2.5-flash'])

    def test_discovered_latest_flash_is_preferred(self):
        ai = Gemini.__new__(Gemini)
        ai.requested_model = 'latest_flash'
        ai.client = SimpleNamespace(models=SimpleNamespace(list=lambda config=None: [
            SimpleNamespace(name='publishers/google/models/gemini-2.5-flash'),
            SimpleNamespace(name='publishers/google/models/gemini-3-flash-preview'),
            SimpleNamespace(name='publishers/google/models/gemini-3.8-flash'),
            SimpleNamespace(name='publishers/google/models/gemini-3.8-pro'),
            SimpleNamespace(name='publishers/google/models/gemini-3.8-flash-image'),
        ]))
        candidates = ai._resolve_model_candidates({
            'model': 'latest_flash',
            'auto_discover_latest_flash': True,
            'model_candidates': ['gemini-flash-latest', 'gemini-2.5-flash'],
        })
        self.assertEqual(candidates[:4], ['gemini-flash-latest', 'gemini-3.8-flash', 'gemini-3-flash-preview', 'gemini-2.5-flash'])

    def test_unavailable_latest_falls_back_once(self):
        calls = []
        def generate_content(model, contents, config):
            calls.append(model)
            if model == 'gemini-future-flash':
                raise RuntimeError('404 model not found')
            return SimpleNamespace(candidates=[SimpleNamespace(finish_reason='STOP')], text='文字起こし')
        ai = Gemini.__new__(Gemini)
        ai.model = 'gemini-future-flash'
        ai.model_candidates = ['gemini-future-flash', 'gemini-3.8-flash']
        ai.client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
        self.assertEqual(ai.generate('content', 'instruction'), '文字起こし')
        self.assertEqual(calls, ['gemini-future-flash', 'gemini-3.8-flash'])
        self.assertEqual(ai.model, 'gemini-3.8-flash')

    def test_rate_limit_retries_same_model_before_failing_over(self):
        calls = []
        def generate_content(model, contents, config):
            calls.append(model)
            if len(calls) == 1:
                raise RuntimeError('429 Too Many Requests')
            return SimpleNamespace(candidates=[SimpleNamespace(finish_reason='STOP')], text='文字起こし')
        ai = Gemini.__new__(Gemini)
        ai.model = 'gemini-3.8-flash'
        ai.model_candidates = ['gemini-3.8-flash', 'gemini-2.5-flash']
        ai.client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
        with patch('app.clock.sleep') as sleep:
            self.assertEqual(ai.generate('content', 'instruction'), '文字起こし')
        self.assertEqual(calls, ['gemini-3.8-flash', 'gemini-3.8-flash'])
        sleep.assert_called_once_with(30)

    def test_coach_rejects_missing_audio_unit(self):
        ai = Gemini.__new__(Gemini)
        ai.generate = lambda *args, **kwargs: {'answers': [], 'actions': [], 'asset_report': ''}
        context = {'coach_units': [{'unit_id': 'memo:1', 'source_id': 'memo', 'name': 'memo.wav',
                                   'recorded_at': '2026-09-15T01:00:00', 'kind': 'reflection', 'text': '反省。'}]}
        with self.assertRaises(RuntimeError):
            ai.coach(context)

    def test_coach_ignores_generic_answer_when_there_are_no_audio_units(self):
        ai = Gemini.__new__(Gemini)
        ai.generate = lambda *args, **kwargs: {
            'answers': [{'unit_id': 'calendar:generic', 'answer': '予定を整理しましょう。'}],
            'actions': [{'action': '今日の予定を確認する', 'time': '10分', 'reason': '空き時間を把握する'}],
            'asset_report': '',
        }
        result = ai.coach({'coach_units': []})
        self.assertNotIn('calendar:generic', result)
        self.assertIn('今日の予定を確認する', result)


class CoachCoverageTest(unittest.TestCase):
    def test_every_recording_becomes_a_unit_and_multiple_questions_are_split(self):
        records = [
            {'id': 'reflection', 'name': 'reflection.wav', 'recorded_at': '2026-09-15T00:00:00',
             'text': '仕事の役割を見失っていました。反省します。'},
            {'id': 'questions', 'name': 'questions.wav', 'recorded_at': '2026-09-15T01:00:00',
             'text': '物価は上がるのでしょうか。政治は必要なのでしょうか。最後の感想です。'},
        ]
        units = coach_units(records)
        self.assertEqual([unit['source_id'] for unit in units],
                         ['reflection', 'reflection', 'questions', 'questions', 'questions'])
        self.assertEqual([unit['kind'] for unit in units],
                         ['reflection', 'reflection', 'question', 'question', 'reflection'])


class FocusContextCompactionTest(unittest.TestCase):
    def test_keeps_every_event_and_compacts_only_long_descriptions(self):
        events = [
            {"id": "today", "planning_horizon": "今日", "description": "a" * 2100},
            {"id": "history", "planning_horizon": "振り返り", "description": "b" * 900},
            {"id": "short", "planning_horizon": "短期", "description": "短い"},
        ]
        compacted = compact_focus_calendar(events)
        self.assertEqual([item["id"] for item in compacted], ["today", "history", "short"])
        self.assertTrue(compacted[0]["description_truncated"])
        self.assertTrue(compacted[1]["description_truncated"])
        self.assertNotIn("description_truncated", compacted[2])
        self.assertEqual(len(compacted[0]["description_sha256"]), 64)
        self.assertEqual(events[0]["description"], "a" * 2100)


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.store, self.workspace, self.ai = MemoryStore(), FakeWorkspace(), FakeAI()
        self.config = dict(write_calendar='primary', read_calendars=['primary'], drive_folder='folder',
                           max_files_per_run=100, max_audio_bytes=10000, max_calendar_bytes=7000,
                           timezone='Asia/Tokyo', history_days=30, future_days=7, goals=[], coach_style='一般',
                           audio_processing_day='current')
    def execute(self):
        run(self.config, self.store, self.workspace, self.ai, date(2026, 9, 8))
    def test_repeat_and_late_arrival_update_same_daily_event(self):
        self.execute()
        self.execute()
        self.assertEqual(self.ai.calls, 1)
        self.assertEqual(len(self.workspace.events), 2)
        self.workspace.files.append(dict(id='b', name='2026-09-06_23-00-00.mp3', mimeType='audio/mpeg',
                                         modifiedTime='v2', createdTime='2026-09-07T19:00:00Z'))
        self.execute()
        self.assertEqual(len(self.workspace.events), 2)
        self.assertEqual(self.ai.calls, 2)
        self.assertIn('04-00-00', next(e for e in self.workspace.events.values() if e['summary'].startswith('音声メモ'))['description'])
    def test_calendar_failure_reuses_saved_transcription(self):
        self.workspace.fail_event = True
        with self.assertRaises(RuntimeError):
            self.execute()
        self.execute()
        self.assertEqual(self.ai.calls, 1)
        self.assertEqual(len(self.workspace.events), 2)
    def test_coach_instruction_change_refreshes_advice_without_retranscribing(self):
        self.execute()
        with patch('app.COACH_INSTRUCTION', 'Updated one-question-one-answer instruction'):
            self.execute()
            self.execute()
        self.assertEqual(self.ai.calls, 1)
        self.assertEqual(self.ai.advice_calls, 2)
        self.assertEqual(len(self.workspace.events), 2)
    def test_original_audio_replaces_legacy_import_without_duplicate(self):
        self.store.write('state.json', {'files': {'legacy': {
            'id': 'legacy', 'name': '2026-09-06_22-00-00.wav', 'version': 'old',
            'recorded_at': '2026-09-06T22:00:00', 'day': '2026-09-06',
            'text': '旧文字起こし', 'legacy_source_id': 'source'}}, 'published': {}, 'advice': {}})
        self.execute()
        self.assertEqual(list(self.store.data['state.json']['files']), ['a'])
        transcript = next(e for e in self.workspace.events.values() if e['summary'].startswith('音声メモ'))
        self.assertNotIn('旧文字起こし', transcript['description'])
        self.assertEqual(len(self.workspace.events), 2)
    def test_current_day_waits_until_next_morning(self):
        self.workspace.files[0]['name'] = '2026-09-08_01-00-00.mp3'
        self.workspace.files[0]['createdTime'] = '2026-09-08T20:00:00Z'
        self.execute()
        self.assertEqual(self.ai.calls, 0)
    def test_current_day_mode_processes_and_cleans_current_audio(self):
        self.workspace.files[0]['name'] = '2026-09-08_01-00-00.mp3'
        self.workspace.files[0]['createdTime'] = '2026-09-07T19:59:59Z'
        self.config['audio_processing_day'] = 'current'
        self.config['trash_processed_audio'] = True
        self.execute()
        self.assertEqual(self.ai.calls, 1)
        self.assertEqual(self.workspace.trashed, ['a'])
    def test_current_day_coach_excludes_previous_day_records(self):
        self.config['audio_processing_day'] = 'current'
        self.workspace.files = []
        self.store.write('state.json', {'files': {
            'previous': {'id': 'previous', 'name': '2026-09-07_23-00-00.wav', 'version': 'v1',
                         'recorded_at': '2026-09-07T23:00:00', 'day': '2026-09-07', 'text': '前日の質問ですか。',
                         'analysis': {'balances': [], 'coach_request': ''}},
            'today': {'id': 'today', 'name': '2026-09-08_01-00-00.wav', 'version': 'v2',
                      'recorded_at': '2026-09-08T01:00:00', 'day': '2026-09-08', 'text': '今日の振り返りです。',
                      'analysis': {'balances': [], 'coach_request': ''}},
        }, 'published': {}, 'advice': {}})
        self.execute()
        self.assertNotIn('前日の質問ですか。', self.ai.last_context)
        self.assertIn('今日の振り返りです。', self.ai.last_context)
    def test_audio_without_recording_timestamp_does_not_stop_coaching(self):
        self.workspace.files = [dict(id='unknown', name='B8366E38-7572-4912-A3A5-ED6BF8C0D776.m4a',
                                     mimeType='audio/mp4', size='10', modifiedTime='v1')]
        self.config['trash_processed_audio'] = True
        self.execute()
        self.assertEqual(self.ai.calls, 0)
        self.assertEqual(self.workspace.trashed, [])
        advice = next(event for event in self.workspace.events.values() if event['summary'].startswith('今日のコーチ'))
        self.assertIn('アップロード日時不明', advice['description'])

    def test_drive_upload_time_assigns_uuid_audio_to_five_am_window(self):
        self.workspace.files = [dict(
            id='B8366E38-7572-4912-A3A5-ED6BF8C0D776',
            name='B8366E38-7572-4912-A3A5-ED6BF8C0D776.m4a',
            mimeType='audio/mp4', size='10', modifiedTime='v1',
            createdTime='2026-09-07T19:59:59Z')]
        self.config['process_lookback_days'] = 1
        self.execute()
        record = self.store.data['state.json']['files']['B8366E38-7572-4912-A3A5-ED6BF8C0D776']
        self.assertEqual(record['day'], '2026-09-08')
        self.assertEqual(record['recorded_at'], '2026-09-08T04:59:59+09:00')
        self.assertEqual(record['name'], '2026-09-08_04-59-59_upload-B8366E38.m4a')
        self.assertEqual(record['source_name'], 'B8366E38-7572-4912-A3A5-ED6BF8C0D776.m4a')
        self.assertEqual(record['time_source'], 'drive_created_time')
        self.assertIn('2026-09-08_04-59-59_upload-B8366E38.m4a',
                      self.store.data['transcripts/2026-09-08.json']['text'])

    def test_five_am_upload_belongs_to_new_day_and_waits_for_next_run(self):
        self.workspace.files = [dict(
            id='exact-cutoff', name='random.m4a', mimeType='audio/mp4', size='10', modifiedTime='v1',
            createdTime='2026-09-07T20:00:00Z')]
        self.config['process_lookback_days'] = 1
        self.execute()
        self.assertEqual(self.ai.calls, 0)
        self.assertNotIn('exact-cutoff', self.store.data['state.json']['files'])

    def test_drive_created_time_overrides_date_in_source_filename(self):
        self.workspace.files = [dict(
            id='dated-source', name='2026-09-08_22-00-00.wav', mimeType='audio/wav', size='10', modifiedTime='v1',
            createdTime='2026-09-07T19:59:59Z')]
        self.config['process_lookback_days'] = 1
        self.execute()
        record = self.store.data['state.json']['files']['dated-source']
        self.assertEqual(record['day'], '2026-09-08')
        self.assertEqual(record['source_name'], '2026-09-08_22-00-00.wav')

    def test_cached_record_is_reclassified_without_retranscription(self):
        self.workspace.files = [dict(
            id='cached', name='UUID.m4a', mimeType='audio/mp4', size='10', modifiedTime='v1',
            createdTime='2026-09-07T19:59:59Z')]
        self.store.write('state.json', {'files': {'cached': {
            'id': 'cached', 'name': 'UUID.m4a', 'version': 'v1',
            'recorded_at': '2026-09-08T04:59:59', 'day': '2026-09-07', 'text': '既存の文字起こし',
            'analysis': {'balances': [], 'coach_request': ''},
        }}, 'published': {}, 'advice': {}})
        self.config['process_lookback_days'] = 1
        self.execute()
        self.assertEqual(self.ai.calls, 0)
        self.assertEqual(self.store.data['state.json']['files']['cached']['day'], '2026-09-08')
        self.assertIn('既存の文字起こし', self.store.data['transcripts/2026-09-08.json']['text'])
        self.assertIn('別の日付へ再分類', self.store.data['transcripts/2026-09-07.json']['text'])

    def test_trashed_legacy_record_is_reclassified_from_drive_metadata(self):
        self.workspace.files = []
        self.workspace.metadata_files['trashed-cached'] = dict(
            id='trashed-cached', name='2026-09-08_02-04-28.WAV', mimeType='audio/wav',
            modifiedTime='v1', createdTime='2026-09-07T17:04:28Z', trashed=True)
        self.store.write('state.json', {'files': {'trashed-cached': {
            'id': 'trashed-cached', 'name': '2026-09-08_02-04-28.WAV', 'version': 'v1',
            'recorded_at': '2026-09-08T02:04:28', 'day': '2026-09-09', 'text': '旧方式の文字起こし',
            'analysis': {'balances': [], 'coach_request': ''}, 'trashed_at': '2026-09-08T06:00:00+09:00',
        }}, 'published': {}, 'advice': {'2026-09-09': 'old'}})
        self.config['process_lookback_days'] = 1
        self.execute()
        record = self.store.data['state.json']['files']['trashed-cached']
        self.assertEqual(record['day'], '2026-09-08')
        self.assertEqual(record['time_source'], 'drive_created_time')
        self.assertIn('旧方式の文字起こし', self.store.data['transcripts/2026-09-08.json']['text'])
        self.assertIn('別の日付へ再分類', self.store.data['transcripts/2026-09-09.json']['text'])
        self.assertIn('別の日付へ再分類', self.store.data['advice/2026-09-09.json']['text'])
    def test_oversized_audio_uses_gcs_uri_and_is_marked_complete(self):
        self.workspace.audio_data = b'a' * (self.config['max_audio_bytes'] + 1)
        self.execute()
        self.assertEqual(self.ai.uri_calls, 1)
        self.assertTrue(self.store.staged[0].deleted)
        self.assertIn('a', self.store.data.get('state.json', {}).get('files', {}))
    def test_config_can_limit_audio_processing_to_previous_day(self):
        self.config['process_lookback_days'] = 1
        self.workspace.files = [
            dict(id='old', name='2026-09-06_22-00-00.mp3', mimeType='audio/mpeg', size='10',
                 modifiedTime='old', createdTime='2026-09-06T18:00:00Z'),
            dict(id='yesterday', name='2026-09-07_22-00-00.mp3', mimeType='audio/mpeg', size='10',
                 modifiedTime='new', createdTime='2026-09-07T18:00:00Z'),
        ]
        self.execute()
        self.assertEqual(self.ai.calls, 1)
        self.assertEqual(list(self.store.data['state.json']['files']), ['yesterday'])

    def test_processed_old_wav_is_trashed_even_when_outside_ingest_lookback(self):
        self.config['process_lookback_days'] = 1
        self.config['trash_processed_audio'] = True
        self.workspace.files = [
            dict(id='old-wav', name='2026-09-01_22-00-00.wav', mimeType='audio/wav', size='10',
                 modifiedTime='old-version', createdTime='2026-09-01T18:00:00Z'),
        ]
        self.store.write('state.json', {'files': {'old-wav': {
            'id': 'old-wav', 'name': '2026-09-01_22-00-00.wav', 'version': 'old-version',
            'recorded_at': '2026-09-01T22:00:00', 'day': '2026-09-01', 'text': '処理済み音声',
            'analysis': {'balances': [], 'coach_request': ''},
        }}, 'published': {}, 'advice': {}})
        self.execute()
        self.assertEqual(self.workspace.trashed, ['old-wav'])

    def test_unprocessed_duplicate_wav_is_not_cleaned_from_matching_mp3(self):
        state = {'files': {'mp3': {
            'id': 'mp3', 'name': '2026-09-01_22-00-00.mp3', 'version': 'mp3-version',
            'day': '2026-09-01', 'analysis': {},
        }}}
        sources = [(datetime(2026, 9, 1, 22, 0), {
            'id': 'wav', 'name': '2026-09-01_22-00-00.wav', 'modifiedTime': 'wav-version',
        })]
        pairs = cleanup_pairs_for_processed_audio(state, sources, date(2026, 9, 8))
        self.assertEqual(pairs, [])

    def test_config_can_limit_coach_transcripts_to_previous_day(self):
        self.config['transcript_context_days'] = 1
        self.store.write('state.json', {'files': {
            'old': {'id': 'old', 'name': '2026-09-06_22-00-00.mp3', 'version': 'old',
                    'recorded_at': '2026-09-06T22:00:00', 'day': '2026-09-06',
                    'text': '前回分の質問です。', 'analysis': {'balances': [], 'coach_request': ''}},
            'new': {'id': 'new', 'name': '2026-09-08_22-00-00.mp3', 'version': 'new',
                    'recorded_at': '2026-09-08T22:00:00', 'day': '2026-09-08',
                    'text': '今回分の質問です。', 'analysis': {'balances': [], 'coach_request': ''}},
        }, 'published': {}, 'advice': {}})
        self.workspace.files = []
        self.execute()
        self.assertNotIn('前回分の質問です。', self.ai.last_context)
        self.assertIn('今回分の質問です。', self.ai.last_context)

    def test_calendar_context_omits_app_owned_events(self):
        workspace = Workspace.__new__(Workspace)
        workspace.pages = lambda url, key, params: [
            {'summary': '仕事', 'description': '打ち合わせ', 'start': {'dateTime': '2026-09-08T09:00:00+09:00'}, 'end': {'dateTime': '2026-09-08T10:00:00+09:00'}},
            {'summary': '音声メモ 2026-09-07', 'description': '自動作成',
             'extendedProperties': {'private': {'app': 'voice-coach-v1'}},
             'start': {'date': '2026-09-07'}, 'end': {'date': '2026-09-08'}},
            {'summary': 'キャンセル', 'status': 'cancelled'}]
        context = workspace.context(['primary'], date(2026, 9, 1), date(2026, 9, 9))
        self.assertEqual(len(context), 1)
        self.assertEqual(context[0]['summary'], '仕事')
        self.assertEqual(context[0]['description'], '打ち合わせ')
        self.assertEqual(context[0]['start'], {'dateTime': '2026-09-08T09:00:00+09:00'})
        self.assertEqual(context[0]['end'], {'dateTime': '2026-09-08T10:00:00+09:00'})

    def test_daily_focus_reads_all_tasks_and_writes_summary_and_blocks(self):
        self.workspace.task_data['active'] = [
            {'tasklist_id': 'list', 'tasklist_title': 'マイタスク', 'id': 'task-1', 'title': '提案作成', 'status': 'needsAction'},
            {'tasklist_id': 'list', 'tasklist_title': 'マイタスク', 'id': 'task-2', 'title': '整理', 'status': 'needsAction'},
        ]
        run_focus(self.config, self.store, self.workspace, self.ai, date(2026, 9, 8), weekly=False)
        summaries = [event['summary'] for event in self.workspace.events.values()]
        self.assertIn('今日の選択と集中 2026-09-08', summaries)
        self.assertIn('集中: 提案作成', summaries)
        self.assertTrue(self.workspace.context_calls[-1][3])
        self.assertIn('提案作成', self.ai.last_context)
        self.assertIn('整理', self.ai.last_context)
        self.assertEqual(self.workspace.all_task_calls[-1], (None, True))

    def test_focus_learning_profile_is_persisted_and_reused(self):
        run_focus(self.config, self.store, self.workspace, self.ai, date(2026, 9, 8), weekly=False)
        profile = self.store.data['focus_learning/latest.json']
        self.assertEqual(profile['agent_identity']['name'], 'コンパス')
        self.assertEqual(profile['next_experiment'], '午前に提案を1件送る')
        run_focus(self.config, self.store, self.workspace, self.ai, date(2026, 9, 9), weekly=False)
        self.assertIn('午前は提案作成を進めやすい', self.ai.last_context)

    def test_daily_focus_marks_all_events_with_planning_horizons(self):
        self.workspace.context = lambda *args, **kwargs: [
            {'summary': '今日の予定', 'start': {'date': '2026-09-08'}, 'end': {'date': '2026-09-09'}},
            {'summary': '短期の予定', 'start': {'date': '2026-09-20'}, 'end': {'date': '2026-09-21'}},
            {'summary': '中期の予定', 'start': {'date': '2026-10-20'}, 'end': {'date': '2026-10-21'}},
        ]
        run_focus(self.config, self.store, self.workspace, self.ai, date(2026, 9, 8), weekly=False)
        calendar = json.loads(self.ai.last_context)['calendar']
        self.assertEqual([event['planning_horizon'] for event in calendar], ['今日', '短期', '中期'])

    def test_weekly_focus_includes_recent_completed_tasks(self):
        self.workspace.task_data['completed'] = [
            {'tasklist_id': 'list', 'tasklist_title': 'マイタスク', 'id': 'done-1', 'title': '完了済み', 'status': 'completed'},
        ]
        run_focus(self.config, self.store, self.workspace, self.ai, date(2026, 9, 11), weekly=True)
        summaries = [event['summary'] for event in self.workspace.events.values()]
        self.assertIn('選択と集中レビュー 2026-W37', summaries)
        self.assertIn('完了済み', self.ai.last_context)

    def test_focus_rerun_does_not_duplicate_events(self):
        run_focus(self.config, self.store, self.workspace, self.ai, date(2026, 9, 8), weekly=False)
        first_ids = set(self.workspace.events)
        run_focus(self.config, self.store, self.workspace, self.ai, date(2026, 9, 8), weekly=False)
        self.assertEqual(first_ids, set(self.workspace.events))
        self.assertEqual(self.ai.advice_calls, 1)

    def test_focus_block_rejects_invalid_time(self):
        with self.assertRaises(ValueError):
            focus_block_event({'title': '失敗', 'start': '2026-09-08T10:00:00+09:00', 'end': '2026-09-08T09:00:00+09:00', 'reason': '逆転'}, date(2026, 9, 8))

    def test_focus_block_time_change_reuses_same_event_id(self):
        morning = focus_block_event({'title': '提案', 'source_task_id': 'task-1',
                                     'start': '2026-09-08T09:00:00+09:00',
                                     'end': '2026-09-08T10:00:00+09:00', 'reason': '空き'}, date(2026, 9, 8))
        afternoon = focus_block_event({'title': '提案', 'source_task_id': 'task-1',
                                       'start': '2026-09-08T13:00:00+09:00',
                                       'end': '2026-09-08T14:00:00+09:00', 'reason': '変更'}, date(2026, 9, 8))
        self.assertEqual(morning['id'], afternoon['id'])

    def test_focus_block_normalizes_repeated_prefix(self):
        event = focus_block_event({'title': '集中: 集中: 提案', 'source_task_id': 'task-1',
                                   'start': '2026-09-08T13:00:00+09:00',
                                   'end': '2026-09-08T14:00:00+09:00', 'reason': '空き'}, date(2026, 9, 8))
        self.assertEqual(event['summary'], '集中: 提案')

    def test_daily_focus_removes_only_stale_app_focus_blocks(self):
        stale = focus_block_event({'title': '古い選択', 'source_task_id': 'old-task',
                                   'start': '2026-09-08T15:00:00+09:00',
                                   'end': '2026-09-08T16:00:00+09:00', 'reason': '旧案'}, date(2026, 9, 8))
        self.workspace.events[stale['id']] = stale
        self.workspace.events['user-event'] = {'id': 'user-event', 'summary': '個人予定'}
        run_focus(self.config, self.store, self.workspace, self.ai, date(2026, 9, 8), weekly=False)
        self.assertNotIn(stale['id'], self.workspace.events)
        self.assertIn('user-event', self.workspace.events)

    def test_daily_focus_skips_block_that_is_already_in_the_past(self):
        run_focus(self.config, self.store, self.workspace, self.ai, date(2026, 9, 8), weekly=False,
                  now=datetime(2026, 9, 8, 10, 0, tzinfo=ZoneInfo('Asia/Tokyo')))
        summaries = [event['summary'] for event in self.workspace.events.values()]
        self.assertNotIn('集中: 提案作成', summaries)

    def test_finance_job_writes_one_daily_summary_and_is_idempotent(self):
        self.workspace.calendar_context = [{
            'calendar': 'primary', 'id': 'transcript-1', 'app': 'voice-coach-v1', 'kind': 'transcript',
            'summary': '音声メモ 2026-09-07', 'description': '現金で昼食に500円払った',
            'start': {'date': '2026-09-07'}, 'end': {'date': '2026-09-08'},
        }]
        self.config['finance_simulation'] = {'payoff_horizon_days': 30, 'lookback_days': 30}
        run_finance(self.config, self.store, self.workspace, self.ai, date(2026, 9, 8))
        run_finance(self.config, self.store, self.workspace, self.ai, date(2026, 9, 8))
        summaries = [event['summary'] for event in self.workspace.events.values()]
        self.assertEqual(summaries.count('財務シミュレーション 2026-09-08'), 1)
        self.assertIn('voice:calendar-transcript:primary:transcript-1:0', self.store.data['finance/ledger.json']['records'])

    def test_finance_calendar_window_is_shorter_than_payoff_simulation(self):
        self.config['finance_simulation'] = {
            'lookback_days': 60, 'calendar_future_days': 90,
            'forecast_days': 30, 'payoff_horizon_days': 3650,
        }
        run_finance(self.config, self.store, self.workspace, self.ai, date(2026, 9, 8))
        _, start, end, include_app_owned = self.workspace.context_calls[-1]
        self.assertEqual(start.date(), date(2026, 7, 10))
        self.assertEqual(end.date(), date(2026, 12, 8))
        self.assertTrue(include_app_owned)

    def test_finance_keeps_historical_manual_record_outside_calendar_window(self):
        self.store.write('finance/ledger.json', {'records': {'calendar:primary:old-balance': {
            'id': 'calendar:primary:old-balance', 'source': 'calendar', 'kind': '残高', 'date': '2024-01-01',
            'amount': '10000', 'currency': 'JPY', 'account': '現金', 'status': '実績', 'rate_known': False}}, 'audit': []})
        self.config['finance_simulation'] = {'lookback_days': 30, 'payoff_horizon_days': 30}
        run_finance(self.config, self.store, self.workspace, self.ai, date(2026, 9, 8))
        self.assertIn('calendar:primary:old-balance', self.store.data['finance/ledger.json']['records'])

    def test_cleanup_only_after_all_outputs_complete(self):
        self.config['trash_processed_audio'] = True
        self.execute()
        self.assertEqual(self.workspace.trashed, ['a'])
        self.assertIn('2026-09-08', self.store.data['state.json']['advice'])
        self.assertIn('trashed_at', self.store.data['state.json']['files']['a'])
    def test_cleanup_keeps_audio_on_calendar_or_archive_failure(self):
        self.config['trash_processed_audio'] = True
        for flag in ['fail_event', 'fail_verify']:
            setattr(self.workspace, flag, True)
            with self.assertRaises(RuntimeError):
                self.execute()
            self.assertEqual(self.workspace.trashed, [])
            setattr(self.workspace, flag, False)
    def test_cleanup_keeps_audio_on_coaching_failure(self):
        self.config['trash_processed_audio'] = True
        def fail(*args):
            raise RuntimeError('coaching unavailable')
        self.ai.coach = fail
        with self.assertRaises(RuntimeError):
            self.execute()
        self.assertEqual(self.workspace.trashed, [])
    def test_cleanup_keeps_audio_on_transcription_failure(self):
        self.config['trash_processed_audio'] = True
        self.workspace.audio_data = b'a' * (self.config['max_audio_bytes'] + 1)
        def fail(*args):
            raise RuntimeError('transcription unavailable')
        self.ai.transcribe_uri = fail
        self.execute()
        self.assertEqual(self.workspace.trashed, [])
        advice = next(event for event in self.workspace.events.values() if event['summary'].startswith('今日のコーチ'))
        self.assertIn('未処理の音声', advice['description'])
    def test_cleanup_retry_reuses_transcript_and_advice(self):
        self.config['trash_processed_audio'] = True
        self.workspace.fail_trash = True
        with self.assertRaises(RuntimeError):
            self.execute()
        self.execute()
        self.assertEqual(self.ai.calls, 1)
        self.assertEqual(self.workspace.trashed, ['a'])
    def test_cleanup_keeps_unprocessed_alternate_format(self):
        self.config['trash_processed_audio'] = True
        self.workspace.files.append(dict(id='wav', name='2026-09-06_22-00-00.wav', mimeType='audio/wav', size='10',
                                         modifiedTime='v2', createdTime='2026-09-07T18:00:00Z'))
        self.execute()
        self.assertEqual(self.workspace.trashed, ['a'])
        self.execute()
        self.assertEqual(self.workspace.trashed, ['a', 'wav'])
        self.assertEqual(list(self.store.data['state.json']['files']), ['wav'])
        self.assertEqual(len(self.workspace.events), 2)
    def test_trash_refuses_changed_moved_or_unpermitted_source(self):
        source = dict(id='a', name='2026-09-06_22-00-00.wav', modifiedTime='v1')
        base = dict(source, parents=['folder'], trashed=False, capabilities={'canTrash': True})
        for change in [dict(modifiedTime='v2'), dict(parents=['elsewhere']),
                       dict(name='different.wav'), dict(capabilities={'canTrash': False})]:
            workspace = Workspace.__new__(Workspace)
            workspace.http = Mock()
            workspace.http.get.return_value.json.return_value = dict(base, **change)
            workspace.call = Mock()
            with self.assertRaises(RuntimeError):
                workspace.trash_processed_audio('folder', source)
            workspace.call.assert_not_called()
    def test_trash_uses_soft_delete_with_readback(self):
        source = dict(id='a', name='2026-09-06_22-00-00.wav', modifiedTime='v1')
        workspace = Workspace.__new__(Workspace)
        workspace.http = Mock()
        workspace.http.get.return_value.json.return_value = dict(source, parents=['folder'], trashed=False,
                                                                capabilities={'canTrash': True})
        workspace.http.get.return_value.headers = {'ETag': 'expected-version'}
        workspace.call = Mock(side_effect=[{}, {'trashed': True}])
        workspace.trash_processed_audio('folder', source)
        first, second = workspace.call.call_args_list
        self.assertEqual(first.args[0], 'PATCH')
        self.assertEqual(first.kwargs['json'], {'trashed': True})
        self.assertEqual(first.kwargs['headers'], {'If-Match': 'expected-version'})
        self.assertEqual(second.args[0], 'GET')


if __name__ == '__main__':
    unittest.main()
