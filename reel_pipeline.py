import asyncio
import subprocess
import re
import edge_tts
import imageio_ffmpeg

from main import (
    build_reel_script, generate_reel_frame_image, send_text_message,
    send_video_for_approval, record_reel_headlines_used,
    REEL_WIDTH, REEL_HEIGHT
)

VOICE_ID = "en-US-GuyNeural"
PAUSE_SECONDS = 0.4
FPS = 24

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

def run_ffmpeg(args, description):
    try:
        subprocess.run(args, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        print(f"  [ffmpeg ERROR] {description} failed (exit {e.returncode})")
        if e.stderr:
            print(f"  [ffmpeg stderr] {e.stderr[-1000:]}")
        raise

async def synthesize_line(text, output_path):
    communicate = edge_tts.Communicate(text, VOICE_ID)
    await communicate.save(output_path)

async def synthesize_all_audio(lines):
    seg_paths = []
    for i, line_obj in enumerate(lines):
        text = line_obj["text"]
        seg_path = f"/tmp/reel_seg_{i}.mp3"
        print(f"  [reel pipeline] synthesizing audio {i}: {text[:60]}")
        await synthesize_line(text, seg_path)
        seg_paths.append(seg_path)
    return seg_paths

def generate_all_frames(lines):
    frame_paths = []
    for i, line_obj in enumerate(lines):
        text = line_obj["text"]
        image_url = line_obj.get("image_url")
        category = line_obj.get("category")
        print(f"  [reel pipeline] generating frame {i}: {text[:60]}")
        buffer = generate_reel_frame_image(text, image_url=image_url, category=category)
        frame_path = f"/tmp/reel_frame_{i}.png"
        with open(frame_path, "wb") as f:
            f.write(buffer.read())
        frame_paths.append(frame_path)
    return frame_paths

def make_silence_clip(path, seconds):
    run_ffmpeg(
        [FFMPEG, "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
         "-t", str(seconds), "-q:a", "9", path],
        "silence clip generation"
    )

def concat_audio(segment_paths, output_path):
    list_path = "/tmp/reel_audio_concat_list.txt"
    with open(list_path, "w") as f:
        for p in segment_paths:
            f.write(f"file '{p}'\n")
    run_ffmpeg(
        [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", list_path,
         "-c:a", "libmp3lame", "-q:a", "4", output_path],
        "audio concat"
    )

def get_media_duration(path):
    result = subprocess.run(
        [FFMPEG, "-i", path, "-f", "null", "-"],
        capture_output=True, text=True
    )
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", result.stderr)
    if not match:
        return None
    h, m, s = match.groups()
    return int(h) * 3600 + int(m) * 60 + float(s)

def make_frame_video_clip(image_path, duration, output_path):
    run_ffmpeg(
        [FFMPEG, "-y", "-loop", "1", "-i", image_path,
         "-c:v", "libx264", "-preset", "ultrafast", "-threads", "1",
         "-t", str(duration), "-pix_fmt", "yuv420p",
         "-vf", f"scale={REEL_WIDTH}:{REEL_HEIGHT}", "-r", str(FPS), output_path],
        f"frame video clip ({image_path})"
    )

def concat_videos(clip_paths, output_path):
    list_path = "/tmp/reel_video_concat_list.txt"
    with open(list_path, "w") as f:
        for p in clip_paths:
            f.write(f"file '{p}'\n")
    run_ffmpeg(
        [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", list_path,
         "-c", "copy", output_path],
        "video concat"
    )

def mux_video_audio(video_path, audio_path, output_path):
    run_ffmpeg(
        [FFMPEG, "-y", "-i", video_path, "-i", audio_path,
         "-c:v", "copy", "-c:a", "aac", "-shortest", output_path],
        "final mux"
    )

def main():
    send_text_message("🎬 Building today's reel — voice, visuals, and video assembly. This will take several minutes, please wait...")

    lines, headlines_used, headlines_available, est_seconds = build_reel_script()
    n = len(lines)
    print(f"  [reel pipeline] {n} lines to process")

    # Mark these headlines as used NOW, right after the script is built --
    # this is the production pipeline, so this run counts toward the
    # same-day dedup window (6am/12pm/5pm shouldn't repeat headlines).
    record_reel_headlines_used(lines)

    frame_paths = generate_all_frames(lines)
    seg_audio_paths = asyncio.run(synthesize_all_audio(lines))

    make_silence_clip("/tmp/reel_silence.mp3", PAUSE_SECONDS)

    audio_segment_paths = []
    video_clip_paths = []

    for i in range(n):
        seg_duration = get_media_duration(seg_audio_paths[i]) or 3.0
        clip_duration = seg_duration + (PAUSE_SECONDS if i < n - 1 else 0)

        clip_path = f"/tmp/reel_clip_{i}.mp4"
        make_frame_video_clip(frame_paths[i], clip_duration, clip_path)
        video_clip_paths.append(clip_path)

        audio_segment_paths.append(seg_audio_paths[i])
        if i < n - 1:
            audio_segment_paths.append("/tmp/reel_silence.mp3")

    print("  [reel pipeline] stitching video clips...")
    combined_video_path = "/tmp/reel_video_silent.mp4"
    concat_videos(video_clip_paths, combined_video_path)

    print("  [reel pipeline] stitching narration audio...")
    final_audio_path = "/tmp/reel_narration_final.mp3"
    concat_audio(audio_segment_paths, final_audio_path)

    print("  [reel pipeline] muxing final video...")
    final_video_path = "/tmp/reel_final.mp4"
    mux_video_audio(combined_video_path, final_audio_path, final_video_path)

    total_duration = get_media_duration(final_video_path)
    duration_label = f"~{round(total_duration)}s" if total_duration else f"~{est_seconds}s (estimated)"

    script_preview = " ".join(d["text"] for d in lines)
    caption = script_preview[:900] + ("…" if len(script_preview) > 900 else "")

    send_video_for_approval(final_video_path, "reel", caption=caption)
    send_text_message(f"🎬 Reel ready for approval — {duration_label}, {n} segments. Approve to post as a Facebook Reel.")

if __name__ == "__main__":
    main()
