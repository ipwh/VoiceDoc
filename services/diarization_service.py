"""
Speaker Diarization Service
Requires pyannote.audio (Python 3.11 only):
  pip install pyannote.audio==3.3.1
"""

def is_available() -> bool:
    try:
        import pyannote.audio
        return True
    except ImportError:
        return False


def diarize(audio_path: str, num_speakers: int = None, hf_token: str = "") -> list:
    if not is_available():
        raise ImportError(
            "說話人分離需要 pyannote.audio，且僅支援 Python 3.11。\n"
            "請先安裝 Python 3.11，再執行：pip install pyannote.audio==3.3.1"
        )
    from pyannote.audio import Pipeline
    import os
    token = hf_token or os.getenv("HF_TOKEN", "")
    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        use_auth_token=token or True,
    )
    kwargs = {}
    if num_speakers:
        kwargs["num_speakers"] = num_speakers
    diarization = pipeline(audio_path, **kwargs)
    segments = []
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        segments.append({"start": round(turn.start, 2),
                         "end":   round(turn.end, 2),
                         "speaker": speaker})
    return segments


def merge_with_speakers(transcript_segs: list, diarization_segs: list) -> list:
    merged = []
    for t in transcript_segs:
        mid = (t["start"] + t["end"]) / 2
        speaker = "SPEAKER"
        for d in diarization_segs:
            if d["start"] <= mid <= d["end"]:
                speaker = d["speaker"]
                break
        merged.append({**t, "speaker": speaker})
    return merged
