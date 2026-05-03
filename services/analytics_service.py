"""
Meeting Analytics Service
"""
from collections import defaultdict


def compute_stats(transcript_segs: list, diarization_segs: list = None) -> dict:
    if not transcript_segs:
        return {}
    total_duration = max(s["end"] for s in transcript_segs)
    speaker_times = defaultdict(float)
    if diarization_segs:
        for seg in diarization_segs:
            speaker_times[seg["speaker"]] += seg["end"] - seg["start"]
    else:
        speaker_times["（未分離）"] = total_duration

    total_speech = sum(speaker_times.values()) or 1
    speaker_ratio = {
        spk: round(t / total_speech * 100, 1)
        for spk, t in sorted(speaker_times.items(), key=lambda x: -x[1])
    }
    total_chars = sum(len(s["text"]) for s in transcript_segs)
    cps = round(total_chars / total_duration, 2) if total_duration else 0

    m, s = divmod(int(total_duration), 60)
    return {
        "total_duration_sec": round(total_duration, 1),
        "duration_str": f"{m} 分 {s} 秒",
        "speaker_ratio": speaker_ratio,
        "chars_per_sec": cps,
        "segment_count": len(transcript_segs),
        "total_chars": total_chars,
    }
