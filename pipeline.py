"""离线上传视频处理流水线。

流程：
  读帧(RGB) -> MediaPipe 检测手 -> 拟合/平滑方框 -> 框内应用特效(BGR)
  -> 写无声视频 -> 若有原音轨则混音 -> 输出最终 mp4
"""

import os
import math
import shutil

import cv2
import imageio
import numpy as np

from tracker import HandTracker
from geometry import QuadTracker
from effects import apply_effect, DEFAULT_EFFECT
import media as media


class PipelineError(Exception):
    pass


def _draw_outline(frame_bgr, quad, presence):
    """在帧上绘制取景框（圆圈 + 边线）。"""
    pts = [(int(p["x"]), int(p["y"])) for p in quad]
    pts_np = np.array(pts, dtype=np.int32)
    alpha = presence

    overlay = frame_bgr.copy()
    cv2.polylines(overlay, [pts_np], True, (255, 255, 255), 2, cv2.LINE_AA)
    for x, y in pts:
        cv2.circle(overlay, (x, y), 7, (255, 255, 255), -1, cv2.LINE_AA)
        cv2.circle(overlay, (x, y), 7, (0, 0, 0), 1, cv2.LINE_AA)
    return cv2.addWeighted(overlay, alpha, frame_bgr, 1.0 - alpha, 0)


def get_video_info(path):
    """返回 (fps, nframes, width, height)。"""
    reader = imageio.get_reader(path)
    try:
        meta = reader.get_meta_data()
        fps = meta.get("fps", 30.0)
        if not fps or not math.isfinite(float(fps)):
            fps = 30.0
        size = meta.get("size", None)
        w = h = 0
        if size and len(size) == 2:
            w, h = int(size[0]), int(size[1])  # imageio meta["size"] 为 (W, H)
        nf = meta.get("nframes", None)
        if nf is None or not math.isfinite(float(nf)) or float(nf) <= 0:
            try:
                nf = reader.count_frames()
            except Exception:
                nf = None
        return float(fps), nf, w, h
    finally:
        reader.close()


def process_video(
    input_path,
    output_path,
    effect_id=None,
    draw_outline=False,
    progress_cb=None,
    cancel_check=None,
):
    """处理视频并写出结果。

    progress_cb(fraction)  被频繁调用，fraction 为 0..1
    cancel_check() -> bool 返回 True 时中止
    """
    if effect_id is None:
        effect_id = DEFAULT_EFFECT

    if not os.path.exists(input_path):
        raise PipelineError(f"文件不存在: {input_path}")

    tracker = HandTracker(max_hands=2)
    quad = QuadTracker()
    reader = None
    writer = None

    # 无声视频先写入临时文件，最后视音频情况处理。
    out_dir = os.path.dirname(os.path.abspath(output_path)) or "."
    base = os.path.basename(output_path)
    silent_path = os.path.join(out_dir, f".silent_{base}")
    audio_path = None
    audio_tmpdir = None

    try:
        reader = imageio.get_reader(input_path)
        meta = reader.get_meta_data()
        fps = meta.get("fps", 30.0)
        if not fps or not math.isfinite(float(fps)):
            fps = 30.0
        fps = float(fps)

        nframes = meta.get("nframes", None)
        if nframes is None or not math.isfinite(float(nframes)) or float(nframes) <= 0:
            try:
                nframes = reader.count_frames()
            except Exception:
                nframes = None

        writer = imageio.get_writer(silent_path, fps=fps)

        total = int(nframes) if nframes else None
        idx = 0
        for frame_rgb in reader:
            if cancel_check and cancel_check():
                raise PipelineError("已取消")

            # frame_rgb 为 RGB uint8 (H, W, 3)
            if frame_rgb.ndim == 2:
                frame_rgb = cv2.cvtColor(frame_rgb, cv2.COLOR_GRAY2RGB)
            h, w = frame_rgb.shape[:2]

            hands = tracker.process(frame_rgb)
            corners, presence = quad.update(hands, w, h)

            frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
            t = idx / fps
            out_bgr = apply_effect(frame_bgr, corners, presence, effect_id, t)
            if draw_outline and corners is not None and presence > 0.01:
                out_bgr = _draw_outline(out_bgr, corners, presence)

            writer.append_data(cv2.cvtColor(out_bgr, cv2.COLOR_BGR2RGB))
            idx += 1

            if progress_cb and total:
                progress_cb(min(1.0, idx / total))
            elif progress_cb:
                progress_cb(-1)  # 未知总帧数

        if progress_cb:
            progress_cb(1.0)
    finally:
        if reader is not None:
            reader.close()
        if writer is not None:
            writer.close()
        tracker.close()

    # 混音：若原视频有音轨，则提取并合并；否则直接使用无声视频作为结果。
    try:
        audio_path, audio_tmpdir = media.extract_audio(input_path, out_dir)
        if audio_path is not None:
            media.mux_audio(silent_path, audio_path, output_path)
            os.remove(silent_path)
        else:
            shutil.move(silent_path, output_path)
    finally:
        if audio_tmpdir:
            shutil.rmtree(audio_tmpdir, ignore_errors=True)
        if os.path.exists(silent_path):
            try:
                os.remove(silent_path)
            except OSError:
                pass

    return output_path