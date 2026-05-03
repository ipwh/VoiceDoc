"""History Service — save/load sessions with multi-version minutes support"""
import json, os, uuid
from datetime import datetime
from services.config import HISTORY_DIR

def _path(filename):
    return os.path.join(HISTORY_DIR, filename)

def _new_version(minutes, note="AI 草稿"):
    return {
        "version_id": uuid.uuid4().hex[:8],
        "timestamp":  datetime.now().isoformat(),
        "note":       note,
        "minutes":    minutes,
    }

def save_session(meeting_info, transcript, minutes, audio_filename="", note="AI 草稿"):
    ts    = datetime.now().strftime("%Y%m%d_%H%M%S")
    name  = meeting_info.get("meeting_name","meeting").replace("/","-")
    fname = f"{ts}_{name}.json"
    version = _new_version(minutes, note)
    record = {
        "saved_at":          datetime.now().isoformat(),
        "meeting_info":      meeting_info,
        "transcript":        transcript,
        "audio_filename":    audio_filename,
        "minutes_versions":  [version],
        "active_version_id": version["version_id"],
    }
    with open(_path(fname), "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    return fname

def add_version(filename, minutes, note="手動修改"):
    fp = _path(filename)
    with open(fp, "r", encoding="utf-8") as f:
        data = json.load(f)
    version = _new_version(minutes, note)
    data.setdefault("minutes_versions", []).append(version)
    data["active_version_id"] = version["version_id"]
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return version["version_id"]

def set_active_version(filename, version_id):
    fp = _path(filename)
    with open(fp, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["active_version_id"] = version_id
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def list_history(limit=10):
    try:
        files = sorted([f for f in os.listdir(HISTORY_DIR) if f.endswith(".json")], reverse=True)[:limit]
        records = []
        for fname in files:
            with open(_path(fname), "r", encoding="utf-8") as fp:
                data = json.load(fp)
            versions = data.get("minutes_versions", [])
            records.append({
                "filename":     fname,
                "saved_at":     data.get("saved_at",""),
                "meeting_name": data.get("meeting_info",{}).get("meeting_name","—"),
                "date":         data.get("meeting_info",{}).get("date",""),
                "has_transcript": bool(data.get("transcript")),
                "has_minutes":  bool(versions),
                "version_count": len(versions),
                "active_version_id": data.get("active_version_id"),
            })
        return records
    except Exception:
        return []

def load_history(filename):
    with open(_path(filename), "r", encoding="utf-8") as f:
        return json.load(f)

def get_active_minutes(record):
    vid      = record.get("active_version_id")
    versions = record.get("minutes_versions", [])
    for v in reversed(versions):
        if v["version_id"] == vid:
            return v["minutes"]
    return versions[-1]["minutes"] if versions else {}

def delete_history(filename):
    fp = _path(filename)
    if os.path.exists(fp):
        os.remove(fp)
