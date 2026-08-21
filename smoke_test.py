"""冒烟测试：验证导入、读取视频信息，并用默认特效跑通极小片段。"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

SAMPLE = os.path.join(HERE, "..", "examples", "test1.mp4")
SAMPLE = os.path.abspath(SAMPLE)


def test_imports():
    import tracker
    import geometry
    import effects
    import pipeline
    import media

    fx = [eid for eid, _ in effects.list_effects()]
    expected = [
        "pixelate", "blur", "invert", "noir", "glitch", "toon",
        "pencil", "watercolor", "oil", "edge",
    ]
    assert fx == expected, f"特效清单不匹配: {fx}"
    print("[OK] 模块导入成功，特效清单 =", fx)


def test_info():
    from pipeline import get_video_info
    fps, nf, w, h = get_video_info(SAMPLE)
    print(f"[OK] 视频信息: fps={fps}, nframes={nf}, size={w}x{h}")
    assert fps > 0
    assert nf and nf > 0
    return fps, nf, w, h


def test_fx_single():
    import numpy as np
    from effects import apply_effect, list_effects

    frame = np.zeros((64, 64, 3), dtype=np.uint8)
    frame[..., 0] = 40
    frame[..., 1] = 120
    frame[..., 2] = 200
    quad = [
        {"x": 16, "y": 16},
        {"x": 48, "y": 16},
        {"x": 48, "y": 48},
        {"x": 16, "y": 48},
    ]
    for eid, _ in list_effects():
        out = apply_effect(frame, quad, 1.0, eid, 0.0)
        assert out.shape == frame.shape and out.dtype == np.uint8
    print("[OK] 10 个特效单帧均正常")


def test_full_small():
    import shutil
    import tempfile
    from pipeline import process_video

    out = os.path.join(tempfile.mkdtemp(), "out.mp4")
    fps, nf, w, h = test_info()
    print(f"[RUN] 全量处理 {SAMPLE} -> {out} (共 {nf} 帧)")

    seen = []
    def cb(f):
        if int(f * 100) // 10 != (int(seen[0] * 100) // 10 if seen else -1):
            pass
        if not seen or int(f * 100) != seen[-1]:
            seen.append(int(f * 100))

    process_video(SAMPLE, out, effect_id="pencil", draw_outline=True, progress_cb=cb)
    assert os.path.exists(out), "输出文件未生成"
    size = os.path.getsize(out)
    print(f"[OK] 端到端处理完成，输出大小 = {size} bytes")
    assert size > 1000, "输出文件异常小"


if __name__ == "__main__":
    test_imports()
    test_fx_single()
    test_info()
    test_full_small()
    print("ALL SMOKE TESTS PASSED")