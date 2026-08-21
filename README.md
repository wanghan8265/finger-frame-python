# Finger Frame Effect（Python 桌面工具）

选择一段已录好的视频，其中包含用双手食指+拇指围成方框的手势，在方框内应用特效，输出为 mp4。

## 特效
Pixelate、Blur、Invert、Noir、Glitch、Toon
Pencil、Watercolor、Oil、Edge


## 环境
依赖清单见 `requirements.txt`。

## 运行

```bash
python main.py
```

弹出 tkinter 窗口后：
1. 点击「浏览...」选择输入视频（mp4 / mov / avi / mkv / webm / m4v）。
2. 自动生成输出路径（默认 `xxx_processed.mp4`），也可点击「保存到...」自定义。
3. 选择特效，可选勾选「绘制取景框」。
4. 点击「开始处理」，进度条实时更新；支持「取消」。
5. 完成后可点击「打开输出文件」。

## 处理原理
1. `imageio` 逐帧读取为 RGB；
2. `MediaPipe Hands` 检测至多两只手的 21 个关键点；
3. `computeQuad`：恰好两只手、且食指与拇指张成 "L" 形时，拟合四边形（含迟滞阈值、凸包面积门控、速度自适应平滑、短暂丢帧保持）；
4. 生成四边形 mask 并高斯羽化，**仅对框内区域应用特效**，框外保持原帧；
5. 写完视频后，若原视频含音轨，则用 ffmpeg 提取并混回，最终输出 mp4。

## 文件结构
```
tracker.py    MediaPipe 手部检测封装
geometry.py   computeQuad 方框拟合 + 状态平滑移植
effects.py    特效统一接口 apply_effect(frame, quad, presence, effect_id)
pipeline.py   读帧/检测/特效/写帧/混音/进度回调
media.py      ffmpeg 音频提取与混音
main.py       tkinter 图形界面
```

## 命令行批量处理（可选）
`process_video` 也可脱离 GUI 使用：

```python
from pipeline import process_video
process_video("input.mp4", "output.mp4", effect_id="pencil", draw_outline=False)