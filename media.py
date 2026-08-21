"""音频提取与混音：使用 imageio_ffmpeg 内置的 ffmpeg 可执行文件。

- extract_audio(video_path) -> 提取 AAC 音轨到临时 m4a，无音轨返回 None
- mux_audio(video_path, audio_path, output_path) -> 合并音视频
"""

import os
import subprocess
import tempfile

import imageio_ffmpeg


def ffmpeg_exe():
    return imageio_ffmpeg.get_ffmpeg_exe()


def _run(args):
    """运行 ffmpeg，失败抛异常并带上 stderr 信息。"""
    proc = subprocess.run(
        [ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error"] + args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        msg = proc.stderr.decode("utf-8", "ignore").strip()
        raise RuntimeError(msg or f"ffmpeg exited with code {proc.returncode}")
    return proc


def _has_audio_stream(video_path):
    """探测视频是否包含音频流。"""
    proc = subprocess.run(
        [
            ffmpeg_exe(), "-hide_banner", "-loglevel", "error",
            "-i", video_path,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    # 即便 returncode != 0（无输出参数），stderr 也包含流信息。
    text = proc.stderr.decode("utf-8", "ignore")
    return "Audio:" in text


def extract_audio(video_path, workdir=None):
    """提取音轨到临时目录，返回 (audio_path, tmp_dir)；无音轨返回 (None, None)。

    调用方负责在完成后删除 tmp_dir。
    """
    if not _has_audio_stream(video_path):
        return None, None

    tmpdir = tempfile.mkdtemp(prefix="finger_audio_", dir=workdir)
    out_path = os.path.join(tmpdir, "audio.m4a")
    _run([
        "-i", video_path,
        "-vn",
        "-acodec", "aac",
        "-b:a", "192k",
        out_path,
    ])
    return out_path, tmpdir


def mux_audio(video_no_audio, audio_path, output_path):
    """把独立音轨混回视频，视频流直接复制以保持速度。"""
    _run([
        "-i", video_no_audio,
        "-i", audio_path,
        "-c:v", "copy",
        "-c:a", "aac",
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-shortest",
        output_path,
    ])