# -*- coding: utf-8 -*-
"""Generate a Colab entrypoint using the same deployed job as the daily schedule."""
import json
from pathlib import Path


def cell(kind, source):
    result = {"cell_type": kind, "metadata": {}, "source": source.splitlines(keepends=True)}
    if kind == "code":
        result.update(execution_count=None, outputs=[])
    return result


cells = [cell('markdown', '''# 音声メモ → Googleカレンダー・目標コーチ

Whisperを使わず、Vertex AIのGemini Flash最新候補で音声メモを処理するGCP版です。毎日の音声処理はCloud Runで日本時間6時に実行します。さらに、Google Calendarを判断の中心にした「選択と集中エージェント」が毎日と金曜日に動き、Google Tasks全件・音声メモ・Codex進捗を合わせて集中予定を作ります。このノートブックから同じ処理を手動実行できます。

**前提** ローカルのREADMEに従ってGCP設定・GoogleアカウントのOAuth認証・Cloud Run配置を完了してください。このノートブックで使うColab認証はGCP操作用です。DriveとCalendarへの継続アクセス用認証は別途Secret Managerに保存します。

録音日時ごとに文字起こしを日別集約し、普段使っているメインカレンダーへ登録します。長文はDriveへ全文保存し、カレンダーからリンクします。WAVのまま処理でき、MP3変換は不要です。音声削除を有効にした場合、文字起こし・保存・カレンダー登録を確認できた音声だけDriveのゴミ箱へ移します。現在設定では前日1日分の録音だけが対象です。前々日以前の前回分・過去分は通常処理に含めません。選択と集中エージェントは、Google Tasksの未完了タスクを全件読み、Calendarの空き時間に合わせて複数の集中予定を作ります。
'''), cell('code', '''%pip -q install google-cloud-storage google-auth requests
from google.colab import auth
auth.authenticate_user()
import google.auth
from google.auth.transport.requests import AuthorizedSession
from google.cloud import storage
import json, time

PROJECT = "eng-empire-498517-c6"
REGION = "asia-northeast1"
JOBS = {
    "voice": "voice-coach-daily",

    "finance": "voice-coach-finance",
    "daily_focus": "voice-coach-daily-focus",
    "weekly_focus": "voice-coach-weekly-focus",
}
credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
session = AuthorizedSession(credentials)
bucket = storage.Client(project=PROJECT, credentials=credentials).bucket(PROJECT + "-voice-coach")
config_blob = bucket.blob("config.json")
config = json.loads(config_blob.download_as_text())
print("要求モデル:", config.get("model"))
print("自動検出:", config.get("auto_discover_latest_flash"))
print("候補モデル:", config.get("model_candidates"))
print("処理対象日数:", config.get("process_lookback_days"))
print("コーチ文字起こし参照日数:", config.get("transcript_context_days"))
print("参照カレンダー:", config["read_calendars"])
print("選択と集中設定:", config.get("focus_agent"))

print("財務シミュレーション設定:", config.get("finance_simulation"))
print("設定済み目標:", config["goals"])
'''), cell('markdown', '''## Gemini Flash最新候補の変更（任意）

通常は `model = "latest_flash"` のままで使います。新しいGemini Flashが出たら、`MODEL_CANDIDATES` の先頭に追加して `SAVE_MODEL_CONFIG = True` にして実行してください。これでCloud Runのコード再デプロイなしに、次回実行から新しい候補を優先します。
'''), cell('code', '''SAVE_MODEL_CONFIG = False
MODEL_CANDIDATES = [
    "gemini-flash-latest",
    "gemini-3.8-flash",
    "gemini-3-flash-preview",
    "gemini-2.5-flash",
]
if SAVE_MODEL_CONFIG:
    config_blob.reload()
    generation = config_blob.generation
    latest = json.loads(config_blob.download_as_text(if_generation_match=generation))
    latest["model"] = "latest_flash"
    latest["auto_discover_latest_flash"] = True
    latest["model_candidates"] = MODEL_CANDIDATES
    config_blob.upload_from_string(json.dumps(latest, ensure_ascii=False, indent=2),
                                  content_type="application/json", if_generation_match=generation)
    print("Gemini Flash最新候補の設定を保存しました")
'''), cell('markdown', '''## 目標・口調の変更（任意）

下の `GOALS` を書き、`SAVE_GOALS = True` にして実行すると、次回から反映されます。例の目標は自分の内容へ書き換えてください。口調・重点は音声でも「今日は優しく」「今週は仕事優先」と指定できます。
'''), cell('code', '''SAVE_GOALS = False
GOALS = [
    # {"title": "目標", "deadline": "2026-12-31", "current": "現在の状況", "target": "達成条件"}
]
if SAVE_GOALS:
    config_blob.reload()
    generation = config_blob.generation
    latest = json.loads(config_blob.download_as_text(if_generation_match=generation))
    latest["goals"] = GOALS
    config_blob.upload_from_string(json.dumps(latest, ensure_ascii=False, indent=2),
                                  content_type="application/json", if_generation_match=generation)
    print("目標を保存しました")
'''), cell('markdown', '''## 手動実行

`RUN_TARGET` を選んで実行します。`finance` は財務シミュレーション、`voice` は音声処理、`daily_focus` は今日の選択と集中、`weekly_focus` は週次レビューです。再実行で同じ日のイベントを増やさず、同じイベントを更新します。
'''), cell('code', '''RUN_TARGET = "finance"  # "voice", "finance", "daily_focus", "weekly_focus"
job = JOBS[RUN_TARGET]
url = f"https://run.googleapis.com/v2/projects/{PROJECT}/locations/{REGION}/jobs/{job}:run"
response = session.post(url, json={}, timeout=60)
response.raise_for_status()
operation = response.json()
operation_url = "https://run.googleapis.com/v2/" + operation["name"]
print("実行を開始しました")
for _ in range(60):
    status = session.get(operation_url, timeout=60)
    status.raise_for_status()
    operation = status.json()
    if operation.get("done"):
        if operation.get("error"):
            raise RuntimeError("処理に失敗しました。Cloud Runの実行詳細を確認してください。")
        print("処理完了。Googleカレンダーの音声メモ、今日のコーチ、選択と集中イベントを確認してください。")
        break
    time.sleep(10)
else:
    print("処理は継続中です。Cloud Runの実行履歴を確認してください。")
''')]
notebook = {"nbformat": 4, "nbformat_minor": 5,
            "metadata": {"colab": {"name": "音声メモ_Gemini_GCP.ipynb"},
                         "kernelspec": {"name": "python3", "display_name": "Python 3"}}, "cells": cells}
for i, c in enumerate(cells):
    c["id"] = f"voice-coach-{i}"
Path(__file__).with_name('音声メモ_Gemini_GCP.ipynb').write_text(
    json.dumps(notebook, ensure_ascii=False, indent=2), encoding='utf-8')
