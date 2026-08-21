"""MediaPipe Hands 封装：返回可用到 2 只手的 21 个关键点。

所有坐标均为归一化 [0,1]，与输入帧宽高无关。
"""

import mediapipe as mp

INDEX_TIP = 8
THUMB_TIP = 4
INDEX_MCP = 5
MIDDLE_MCP = 9
WRIST = 0


class HandTracker:
    def __init__(self, max_hands=2):
        self._mp_hands = mp.solutions.hands
        self._hands = self._mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=max_hands,
            min_detection_confidence=0.3,
            min_tracking_confidence=0.3,
        )

    def process(self, frame_rgb):
        """frame_rgb: RGB numpy 数组 (H, W, 3)。

        返回 list[list[dict]]，每个手为 21 个关键点字典，
        每项形如 {"x":..., "y":..., "z":...}（x,y 归一化）。
        未检测到手时返回空列表。
        """
        results = self._hands.process(frame_rgb)
        hands = []
        if results.multi_hand_landmarks:
            for lm in results.multi_hand_landmarks:
                pts = [
                    {"x": p.x, "y": p.y, "z": p.z}
                    for p in lm.landmark
                ]
                hands.append(pts)
        return hands

    def close(self):
        self._hands.close()