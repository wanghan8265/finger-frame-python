"""特效统一接口：只对"取景四边形"内区域应用特效。

所有函数接收 BGR uint8 帧，返回 BGR uint8 帧。
框外保持原帧，框线由 pipeline 视需要绘制。
"""

import cv2
import numpy as np


class EffectError(Exception):
    pass


def _glitch_hash(i):
    """确定性伪随机，保证同一帧输出稳定。"""
    n = np.sin(i * 127.1 + 311.7) * 43758.5453
    return n - np.floor(n)


# ---- 各特效：处理"整帧"，随后由 apply_effect 提取框内区域 ----

def _fx_pixelate(frame, quad, t):
    h, w = frame.shape[:2]
    factor = 24
    sw = max(2, int(round(w / factor)))
    sh = max(2, int(round(h / factor)))
    small = cv2.resize(frame, (sw, sh), interpolation=cv2.INTER_LINEAR)
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)


def _fx_blur(frame, quad, t):
    out = cv2.GaussianBlur(frame, (0, 0), 14)
    hsv = cv2.cvtColor(out, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[..., 1] = np.clip(hsv[..., 1] * 1.1, 0, 255)
    out = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
    return out


def _fx_invert(frame, quad, t):
    return cv2.bitwise_not(frame)


def _fx_noir(frame, quad, t):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
    gray = np.clip((gray - 128.0) * 1.5 + 128.0, 0, 255) * 0.95
    gray = np.clip(gray, 0, 255).astype(np.uint8)
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)


def _fx_glitch(frame, quad, t):
    h, w = frame.shape[:2]
    # 色差鬼影：R/B 通道水平偏移，充满活力。
    amp = 8 + np.sin(t * 9) * 5
    b, g, r = cv2.split(frame.astype(np.int16))
    M = np.float32([[1, 0, amp], [0, 1, 0]])
    r = cv2.warpAffine(r, M, (w, h), borderMode=cv2.BORDER_REFLECT)
    M = np.float32([[1, 0, -amp], [0, 1, 0]])
    b = cv2.warpAffine(b, M, (w, h), borderMode=cv2.BORDER_REFLECT)
    out = cv2.merge([np.clip(b, 0, 255), g, np.clip(r, 0, 255)]).astype(np.uint8)

    # 饱和度/对比度增强。
    out = cv2.convertScaleAbs(out, alpha=1.1, beta=0)
    hsv = cv2.cvtColor(out, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[..., 1] = np.clip(hsv[..., 1] * 1.6, 0, 255)
    out = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

    # 水平切片位移。
    slices = 7
    for i in range(slices):
        seed = np.sin(i * 127.1 + np.floor(t * 12) * 311.7)
        sy = int((seed * 0.5 + 0.5) * h) % max(1, h - 1)
        slice_h = int(6 + abs(seed) * 26)
        slice_h = min(slice_h, h - sy)
        dx = int(seed * 34)
        if slice_h <= 0:
            continue
        roi = out[sy:sy + slice_h]
        shifted = np.roll(roi, dx, axis=1)
        out[sy:sy + slice_h] = shifted

    # 扫描线。
    for y in range(0, h, 6):
        out[y:y + 2] = out[y:y + 2] * 0.84

    return out


def _fx_toon(frame, quad, t):
    h, w = frame.shape[:2]
    tw = 320
    th = max(2, int(round(tw * h / w)))
    small = cv2.resize(frame, (tw, th), interpolation=cv2.INTER_AREA)
    # 轻微平滑 + 饱和。
    small = cv2.bilateralFilter(small, 9, 75, 75)
    small = cv2.convertScaleAbs(small, alpha=1.05, beta=0)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[..., 1] = np.clip(hsv[..., 1] * 1.6, 0, 255)
    small = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

    # 辉度（后处理前）用于边缘检测。
    lum = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32)

    # 海报化：颜色量化成 6 档。
    levels = 6
    lut = (np.round((np.round(np.arange(256) / 255.0 * (levels - 1)) / (levels - 1)) * 255)).astype(np.uint8)
    small = lut[small]

    # Sobel 边缘 -> 暗描边。
    gx = cv2.Sobel(lum, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(lum, cv2.CV_32F, 0, 1, ksize=3)
    mag = np.abs(gx) + np.abs(gy)
    mask = mag > 90
    small[mask] = (small[mask].astype(np.float32) * 0.18).astype(np.uint8)

    return cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)


def _fx_pencil(frame, quad, t):
    _, color = cv2.pencilSketch(frame, sigma_s=60, sigma_r=0.07, shade_factor=0.05)
    return color


def _fx_watercolor(frame, quad, t):
    return cv2.stylization(frame, sigma_s=60, sigma_r=0.45)


def _fx_oil(frame, quad, t):
    return cv2.xphoto.oilPainting(frame, 7, 1)


def _fx_edge(frame, quad, t):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(gray, 50, 150)
    # 白底黑线线稿。
    return cv2.cvtColor(255 - edges, cv2.COLOR_GRAY2BGR)


EFFECTS = {
    "pixelate": ("Pixelate", _fx_pixelate),
    "blur": ("Blur", _fx_blur),
    "invert": ("Invert", _fx_invert),
    "noir": ("Noir", _fx_noir),
    "glitch": ("Glitch", _fx_glitch),
    "toon": ("Toon", _fx_toon),
    "pencil": ("Pencil", _fx_pencil),
    "watercolor": ("Watercolor", _fx_watercolor),
    "oil": ("Oil", _fx_oil),
    "edge": ("Edge", _fx_edge),
}

DEFAULT_EFFECT = "watercolor"


def list_effects():
    """返回 [(id, label), ...]，保持展示顺序。"""
    return [(eid, label) for eid, (label, _) in EFFECTS.items()]


def build_mask(quad, h, w, feather_sigma=None):
    """由四边形生成带羽化的 0..1 浮点 mask（float32）。"""
    mask = np.zeros((h, w), dtype=np.float32)
    pts = np.array([[p["x"], p["y"]] for p in quad], dtype=np.int32)
    cv2.fillPoly(mask, [pts], 1.0)
    if feather_sigma is None:
        feather_sigma = max(2.0, max(h, w) / 40.0)
    mask = cv2.GaussianBlur(mask, (0, 0), feather_sigma)
    return np.clip(mask, 0.0, 1.0)


def apply_effect(frame_bgr, quad, presence, effect_id, t=0.0):
    """对取景框内应用特效，返回 BGR uint8 帧。

    quad 为 None 或 presence<=0.01 时原样返回帧。
    """
    if quad is None or presence <= 0.01:
        return frame_bgr
    if effect_id not in EFFECTS:
        raise EffectError(f"未知特效: {effect_id}")

    h, w = frame_bgr.shape[:2]
    _, fx = EFFECTS[effect_id]
    processed = fx(frame_bgr, quad, t)

    mask = build_mask(quad, h, w)
    alpha = (mask * presence)[..., None].astype(np.float32)
    result = frame_bgr.astype(np.float32) * (1.0 - alpha) + processed.astype(np.float32) * alpha
    return np.clip(result, 0, 255).astype(np.uint8)