import unittest
from core import asset_snapshot, daily_text, event_body, event_id, recording_time, upload_window_time


class RulesTest(unittest.TestCase):
    def test_filename_is_recording_date_not_upload_date(self):
        self.assertEqual(recording_time('2026-09-07_23-59-59.mp3').date().isoformat(), '2026-09-07')
        with self.assertRaises(ValueError):
            recording_time('unknown.mp3')

    def test_upload_window_uses_jst_five_am_boundary(self):
        local, day = upload_window_time('2026-09-15T19:59:59Z')
        self.assertEqual(local.isoformat(), '2026-09-16T04:59:59+09:00')
        self.assertEqual(day.isoformat(), '2026-09-16')
        local, day = upload_window_time('2026-09-15T20:00:00Z')
        self.assertEqual(local.isoformat(), '2026-09-16T05:00:00+09:00')
        self.assertEqual(day.isoformat(), '2026-09-17')

    def test_upload_window_rejects_naive_or_invalid_cutoff(self):
        with self.assertRaises(ValueError):
            upload_window_time('2026-09-16T05:00:00')
        with self.assertRaises(ValueError):
            upload_window_time('2026-09-16T05:00:00+09:00', cutoff_hour=24)

    def test_verbatim_and_chronological_order(self):
        records = [{'id': 'b', 'name': 'late.mp3', 'recorded_at': '2026-09-07T22:00', 'text': 'えー、そのまま。'},
                   {'id': 'a', 'name': 'early.mp3', 'recorded_at': '2026-09-07T01:00', 'text': '<script> & 原文'}]
        text = daily_text(records)
        self.assertEqual(text, '■ early.mp3\n<script> & 原文\n\n■ late.mp3\nえー、そのまま。')
        body = event_body('transcript', '2026-09-07', text, 'https://drive.google.com/file/d/example/view')
        self.assertIn('&lt;script&gt; &amp; 原文', body['description'])
        self.assertEqual(body['end'], {'date': '2026-09-08'})
        self.assertEqual(body['transparency'], 'transparent')

    def test_deterministic_ids_and_separate_coach(self):
        self.assertEqual(event_id('transcript', '2026-09-07'), event_id('transcript', '2026-09-07'))
        self.assertNotEqual(event_id('transcript', '2026-09-07'), event_id('advice', '2026-09-07'))

    def test_overflow_has_full_text_link_no_partial_transcript(self):
        body = event_body('transcript', '2026-09-07', '忠実な原文' * 2000, 'https://drive.google.com/file/d/example/view')
        self.assertIn('文字起こし全文を開く', body['description'])
        self.assertNotIn('忠実な原文', body['description'])

    def test_balances_replace_not_sum_and_currencies_separate(self):
        def balance(account, value, day, kind='cash', currency='JPY'):
            return dict(account=account, amount=value, as_of=day, kind=kind, currency=currency, evidence='原文')
        result = asset_snapshot([balance('銀行A', '100', '2026-09-06'), balance('銀行A', '150', '2026-09-07'),
                                 balance('借入A', '30', '2026-09-07', 'debt'),
                                 balance('米国口座', '20', '2026-09-06', currency='USD'),
                                 balance('不明', 'NaN', '2026-09-07')])
        self.assertEqual(result['reported_net_assets'], {'JPY': '120', 'USD': '20'})
        self.assertEqual(len(result['unresolved']), 1)
        self.assertEqual(len(result['accounts']), 3)


if __name__ == '__main__':
    unittest.main()
