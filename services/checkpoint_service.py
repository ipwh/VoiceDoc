"""Checkpoint Service — save/restore each pipeline step"""
import json, os, uuid
from datetime import datetime, timedelta
from services.config import CHECKPOINT_DIR, TEMP_MAX_AGE_HOURS

def new_meeting_id() -> str:
    return f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

def _path(meeting_id):
    return os.path.join(CHECKPOINT_DIR, f"{meeting_id}.json")

def save_checkpoint(meeting_id, step, payload):
    fp = _path(meeting_id)
    data = {}
    if os.path.exists(fp):
        with open(fp, "r", encoding="utf-8") as f:
            data = json.load(f)
    data["meeting_id"] = meeting_id
    data["updated_at"] = datetime.now().isoformat()
    data[step]         = payload
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_checkpoint(meeting_id):
    fp = _path(meeting_id)
    if not os.path.exists(fp):
        return {}
    with open(fp, "r", encoding="utf-8") as f:
        return json.load(f)

def detect_incomplete_jobs():
    jobs = []
    for fname in os.listdir(CHECKPOINT_DIR):
        if not fname.endswith(".json"):
            continue
        fp = os.path.join(CHECKPOINT_DIR, fname)
        try:
            with open(fp, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("transcription") and not data.get("minutes"):
                jobs.append(data)
        except Exception:
            continue
    return sorted(jobs, key=lambda x: x.get("updated_at",""), reverse=True)

def delete_checkpoint(meeting_id):
    fp = _path(meeting_id)
    if os.path.exists(fp):
        os.remove(fp)

def cleanup_old_checkpoints():
    cutoff = datetime.now() - timedelta(hours=TEMP_MAX_AGE_HOURS)
    for fname in os.listdir(CHECKPOINT_DIR):
        if not fname.endswith(".json"):
            continue
        fp = os.path.join(CHECKPOINT_DIR, fname)
        mtime = datetime.fromtimestamp(os.path.getmtime(fp))
        if mtime < cutoff:
            try: os.remove(fp)
            except Exception: pass

def estimate_duration(audio_duration_sec, model_size="small"):
    factors = {"tiny":0.3,"base":0.5,"small":0.8,"medium":1.5,"large-v3":2.5}
    est_sec = int(audio_duration_sec * factors.get(model_size, 1.0))
    m, s = divmod(est_sec, 60)
    return f"約 {m} 分 {s} 秒"
