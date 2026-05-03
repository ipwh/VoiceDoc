"""
core/checkpoint.py
對 services/checkpoint_service 的輕量包裝，供各頁直接使用。
"""
from services.checkpoint_service import (
    save_checkpoint,
    load_checkpoint,
    detect_incomplete_jobs,
    delete_checkpoint,
    cleanup_old_checkpoints,
    new_meeting_id,
    estimate_duration,
)

__all__ = [
    "save_checkpoint", "load_checkpoint", "detect_incomplete_jobs",
    "delete_checkpoint", "cleanup_old_checkpoints",
    "new_meeting_id", "estimate_duration",
]
