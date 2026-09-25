"""Run locally once. Tokens go directly to Secret Manager, never to stdout."""
import argparse
import json
import os
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
from google.cloud import secretmanager
from google.api_core.exceptions import AlreadyExists
from oauthlib.oauth2 import InvalidClientError
from app import PROJECT, SCOPES, Store, Workspace
from local_auth import cloud_credentials


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("client_json", nargs="?", help="Downloaded Desktop OAuth client JSON")
    parser.add_argument("--client-id", help="Desktop OAuth client ID. Use this when JSON download is unavailable.")
    parser.add_argument("--client-secret", help="OAuth client secret. Prefer VOICE_COACH_CLIENT_SECRET for local prompts.")
    parser.add_argument("--enable-audio-cleanup", action="store_true", help="Authorize Drive changes and enable trashing fully processed audio")
    args = parser.parse_args()
    scopes = SCOPES + (["https://www.googleapis.com/auth/drive"] if args.enable_audio_cleanup else [])
    if args.client_id:
        client_secret = (args.client_secret or os.getenv("VOICE_COACH_CLIENT_SECRET") or "").strip()
        if not client_secret:
            parser.error("Client Secret is empty. Copy the full secret shown when it is created in GCP.")
        if client_secret.endswith(".apps.googleusercontent.com"):
            parser.error("You entered a Client ID. Enter the Client Secret from the same OAuth client instead.")
        if any(char in client_secret for char in ("*", "\u2022", "\u2026")):
            parser.error("The secret appears masked. Create an additional secret in GCP and copy its full value immediately.")
        client_config = {"installed": {
            "client_id": args.client_id,
            "client_secret": client_secret,
            "project_id": PROJECT,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "redirect_uris": ["http://localhost"]}}
        flow = InstalledAppFlow.from_client_config(client_config, scopes)
    elif args.client_json:
        flow = InstalledAppFlow.from_client_secrets_file(args.client_json, scopes)
    else:
        parser.error("Provide a Desktop OAuth client JSON or --client-id")
    try:
        credentials = flow.run_local_server(port=0, access_type="offline", prompt="consent",
                                            authorization_prompt_message="ブラウザでGoogleアカウントを選び、認証してください。")
    except InvalidClientError:
        parser.exit(1, "Google rejected the Client Secret (invalid_client). Use the full, active secret belonging to this exact OAuth client. If unavailable, add a new secret in GCP and copy it immediately.\n")
    if not credentials.refresh_token:
        raise RuntimeError("No refresh token was granted; repeat with consent")
    granted = credentials.granted_scopes or credentials.scopes or []
    if args.enable_audio_cleanup and "https://www.googleapis.com/auth/drive" not in granted:
        raise RuntimeError("Drive modification permission was not granted; cleanup was not enabled")
    workspace = Workspace(credentials)
    # Validate the authorized account can read the user's actual source before storing anything.
    config_path = Path(__file__).with_name("config.json")
    local_config = json.loads(config_path.read_text(encoding="utf-8"))
    gcp_credentials = cloud_credentials()
    store = Store(gcp_credentials)
    config = store.read("config.json") or local_config
    workspace.audio_files(config["drive_folder"])
    workspace.call("GET", "calendar/v3/calendars/primary/events", params={"maxResults": 1})
    workspace.task_lists()
    secrets = secretmanager.SecretManagerServiceClient(credentials=gcp_credentials)
    parent = f"projects/{PROJECT}"
    try:
        secrets.create_secret(request={"parent": parent, "secret_id": "voice-coach-oauth",
                                       "secret": {"replication": {"automatic": {}}}})
    except AlreadyExists:
        pass
    secrets.add_secret_version(request={"parent": parent + "/secrets/voice-coach-oauth",
                                       "payload": {"data": credentials.to_json().encode()}})
    config["write_calendar"] = "primary"
    if args.enable_audio_cleanup:
        config["trash_processed_audio"] = True
    store.write("config.json", config)
    local_config["write_calendar"] = config["write_calendar"]
    local_config["trash_processed_audio"] = config.get("trash_processed_audio", False)
    config_path.write_text(json.dumps(local_config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("認証とメインカレンダーの設定が完了しました。認証情報はSecret Managerに保存しました。")


if __name__ == "__main__":
    main()
