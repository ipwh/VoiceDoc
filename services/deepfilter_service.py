"""
DeepFilterNet AI Noise Reduction Service
pip install deepfilternet==0.5.6
"""
_model = None
_df_state = None


def _get_model():
    global _model, _df_state
    if _model is None:
        from df import init_df
        _model, _df_state, _ = init_df()
    return _model, _df_state


def deepfilter_denoise(input_path: str, output_path: str) -> str:
    import soundfile as sf
    import numpy as np
    from df import enhance

    model, df_state = _get_model()
    audio, sr = sf.read(input_path)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    # DeepFilterNet expects float32
    audio = audio.astype(np.float32)
    enhanced = enhance(model, df_state, audio)
    sf.write(output_path, enhanced, sr)
    return output_path
