"""方框拟合与状态平滑。

坐标系：像素坐标，左上角为原点。视频不镜像，x = lm.x * width。
"""

import math

WRIST = 0
THUMB_TIP = 4
INDEX_TIP = 8
INDEX_MCP = 5
MIDDLE_MCP = 9

MAX_LOST_FRAMES = 25
JUMP_CONFIRM_FRAMES = 2


def _to_pixel(lm, w, h):
    return {"x": lm["x"] * w, "y": lm["y"] * h}


def _dist(a, b):
    return math.hypot(a["x"] - b["x"], a["y"] - b["y"])


def _lerp(a, b, t):
    return {"x": a["x"] + (b["x"] - a["x"]) * t, "y": a["y"] + (b["y"] - a["y"]) * t}


def _polygon_area(pts):
    a = 0.0
    n = len(pts)
    for i in range(n):
        p = pts[i]
        q = pts[(i + 1) % n]
        a += p["x"] * q["y"] - q["x"] * p["y"]
    return abs(a / 2.0)


def compute_quad(hands, w, h, frame_active):
    """恰好两只手时返回 4 个角点（按解剖顺序），否则返回 None。

    角点顺序：[左.index, 右.thumb, 右.index, 左.thumb]
    """
    if len(hands) != 2:
        return None

    info = []
    for lm in hands:
        wrist = _to_pixel(lm[WRIST], w, h)
        middle_mcp = _to_pixel(lm[MIDDLE_MCP], w, h)
        info.append({
            "index": _to_pixel(lm[INDEX_TIP], w, h),
            "thumb": _to_pixel(lm[THUMB_TIP], w, h),
            "wristX": wrist["x"],
            "scale": _dist(wrist, middle_mcp) + 1.0,
        })

    # 需要拇指和食指张开（开放的 "L"）。迟滞：激活后放松阈值。
    needed = 0.2 if frame_active else 0.75
    for hd in info:
        if _dist(hd["thumb"], hd["index"]) < hd["scale"] * needed:
            return None

    info.sort(key=lambda d: d["wristX"])
    a, b = info[0], info[1]
    pts = [a["index"], b["index"], b["thumb"], a["thumb"]]

    # 角点按角度排序后的凸包面积门控（退化/交叉框面积近零）。
    cx = sum(p["x"] for p in pts) / 4.0
    cy = sum(p["y"] for p in pts) / 4.0
    hull = sorted(pts, key=lambda p: math.atan2(p["y"] - cy, p["x"] - cx))
    min_area = 0.0005 if frame_active else 0.005
    if _polygon_area(hull) < w * h * min_area:
        return None
    return pts


class QuadTracker:
    """保持上一帧四边形、平滑角点、处理短暂丢失的逐帧状态机。

    用法：
        tracker = QuadTracker()
        corners, presence = tracker.update(hands, w, h)
    """

    def __init__(self):
        self.corners = None
        self.presence = 0.0
        self.frame_active = False
        self.lost_frames = 0
        self.jump_frames = 0

    def reset(self):
        self.__init__()

    def update(self, hands, w, h):
        target = compute_quad(hands, w, h, self.frame_active)

        if target is not None:
            if self.corners is None:
                self.lost_frames = 0
                self.frame_active = True
                self.jump_frames = 0
                self.corners = target
                self.presence = min(1.0, self.presence + 0.12)
            else:
                moved = sum(_dist(target[i], self.corners[i]) for i in range(4)) / 4.0
                # 遮挡/交叉手会产生单帧误检；远跳的四边形仅当其持续才接受。
                if moved > w * 0.3:
                    self.jump_frames += 1
                    if self.jump_frames < JUMP_CONFIRM_FRAMES:
                        self.lost_frames += 1
                        if self.lost_frames > MAX_LOST_FRAMES:
                            self.presence = max(0.0, self.presence - 0.05)
                    else:
                        self._accept(target, moved, w)
                else:
                    self.lost_frames = 0
                    self.frame_active = True
                    self.jump_frames = 0
                    self._accept(target, moved, w)
        elif self.corners is not None:
            self.lost_frames += 1
            if self.lost_frames <= MAX_LOST_FRAMES:
                # 短暂丢失：保持上一帧四边形。
                self.presence = min(1.0, self.presence + 0.12)
            else:
                self.presence = max(0.0, self.presence - 0.05)
                if self.presence == 0.0:
                    self.corners = None
                    self.frame_active = False
                    self.jump_frames = 0
        else:
            self.presence = max(0.0, self.presence - 0.05)

        return self.corners, self.presence

    def _accept(self, target, moved, w):
        self.lost_frames = 0
        self.frame_active = True
        self.jump_frames = 0
        alpha = min(0.85, max(0.35, moved / (w * 0.05)))
        self.corners = [_lerp(self.corners[i], target[i], alpha) for i in range(4)]
        self.presence = min(1.0, self.presence + 0.12)