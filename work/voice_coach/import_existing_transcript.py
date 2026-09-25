"""One-time import of an existing dated transcript; keeps the original Drive file."""
import argparse
import hashlib
import re

from app import Store, Workspace
from core import recording_time
from local_auth import cloud_credentials


def parse_records(text, source_id, version):
    headings = list(re.finditer(
        r"^\u25a0 (\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.(?:mp3|wav|m4a|ogg|flac|webm))\r?$",
        text, re.MULTILINE | re.IGNORECASE))
    if not headings or text[:headings[0].start()].strip():
        raise ValueError("Expected dated recording headings without a preamble")
    records = []
    for index, heading in enumerate(headings):
        name = heading.group(1)
        stamp = recording_time(name)
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        body = text[heading.end():end].strip("\r\n")
        if not body:
            raise ValueError("An empty recording section cannot be imported")
        key = "legacy-" + hashlib.sha256(f"{source_id}:{index}:{name}".encode()).hexdigest()
        records.append({"id": key, "name": name, "version": version,
                        "recorded_at": stamp.isoformat(), "day": stamp.date().isoformat(),
                        "text": body, "legacy_source_id": source_id})
    if len({r["name"] for r in records}) != len(records):
        raise ValueError("Duplicate recording headings")
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("file_id")
    args = parser.parse_args()
    credentials = cloud_credentials()
    store = Store(credentials)
    workspace = Workspace(cloud_credentials=credentials)
    config = store.read("config.json")
    meta = workspace.call("GET", f"drive/v3/files/{args.file_id}", params={
        "supportsAllDrives": "true", "fields": "id,mimeType,parents"})
    if meta["mimeType"] != "text/plain" or config["drive_folder"] not in meta.get("parents", []):
        raise ValueError("Source must be a text file in the configured Drive folder")
    response = workspace.http.get(f"https://www.googleapis.com/drive/v3/files/{args.file_id}",
                                  params={"alt": "media", "supportsAllDrives": "true"}, timeout=120)
    response.raise_for_status()
    records = parse_records(response.content.decode("utf-8-sig"), args.file_id,
                            hashlib.sha256(response.content).hexdigest())
    with store.lock():
        state = store.read("state.json", {"files": {}, "published": {}, "advice": {}})
        names = {r["name"] for r in state["files"].values()}
        imported = 0
        for record in records:
            if record["name"] not in names:
                state["files"][record["id"]] = record
                names.add(record["name"])
                imported += 1
        store.write("state.json", state)
        saved = store.read("state.json")
        if not all(r["name"] in {s["name"] for s in saved["files"].values()} for r in records):
            raise RuntimeError("Import verification failed")
    print(f"Imported {imported} recordings across {len({r['day'] for r in records})} days")


if __name__ == "__main__":
    main()
