import asyncio
import subprocess
import re
import requests
import edge_tts
import imageio_ffmpeg

from main import build_reel_script, generate_reel_frame_image, send_text_message, REEL_WIDTH, REEL_HEIGHT

BOT_TOKEN = "8919908599:AAGTBdy69N5NFXY5KTIMhTkO7q2VpOXwYa8"
CHAT_ID = "7898015877"

VOICE_ID = "en-US-GuyNeural"
PAUSE_SECONDS = 0.4
FPS = 30

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

async def synthesize_line(text, output_path):
    communicate = edge_tts.Communicate(text, VOICE_ID)
    await communicate.save(output_path)

def make_silence_clip(path, seconds):
    subprocess.run(
        [FFMPEG, "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
         "-t", str(seconds), "-q:a", "9", path],
        check=True, capture_output=True
    )

def concat_audio(segment_paths, output_path):
    list_path = "/tmp/reel_audio_concat_list.txt"
    with open(list_path, "w") as f:
        for p in segment_paths:
            f.write(f"file '{p}'\n")
    subprocess.run(
        [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", list_path,
         "-c:a", "libmp3lame", "-q:a", "4", output_path],
        check=True, capture_output=True
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
    subprocess.run(
        [FFMPEG, "-y", "-loop", "1", "-i", image_path,
         "-c:v", "libx264", "-t", str(duration), "-pix_fmt", "yuv420p",
         "-vf", f"scale={REEL_WIDTH}:{REEL_HEIGHT}", "-r", str(FPS), output_path],
        check=True, capture_output=True
    )

def concat_videos(clip_paths, output_path):
    list_path = "/tmp/reel_video_concat_list.txt"
    with open(list_path, "w") as f:
        for p in clip_paths:
            f.write(f"file '{p}'\n")
    subprocess.run(
        [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", list_path,
         "-c", "copy", output_path],
        check=True, capture_output=True
    )

def mux_video_audio(video_path, audio_path, output_path):
    subprocess.run(
        [FFMPEG, "-y", "-i", video_path, "-i", audio_path,
         "-c:v", "copy", "-c:a", "aac", "-shortest", output_path],
        check=True, capture_output=True
    )

def send_video(file_path, caption):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo"
    with open(file_path, "rb") as f:
        files = {"video": (file_path, f, "video/mp4")}
        data = {"chat_id": CHAT_ID, "caption": caption, "supports_streaming": True}
        response = requests.post(url, files=files, data=data, timeout=180)
    result = response.json()
    if not result.get("ok"):
        print(f"  [telegram ERROR] failed to send video: {result}")
    else:
        print("  [telegram] video sent OK")

async def main():
    send_text_message("🎬 Building the full reel — voice, visuals, and video assembly. This will take several minutes, please wait...")

    lines, headlines_used, headlines_available, est_seconds = build_reel_script()
    n = len(lines)
    print(f"  [reel video] {n} lines to process")

    make_silence_clip("/tmp/reel_silence.mp3", PAUSE_SECONDS)

    audio_segment_paths = []
    video_clip_paths = []

    for i, line_obj in enumerate(lines):
        text = line_obj["text"]
        image_url = line_obj.get("image_url")
        category = line_obj.get("category")

        print(f"  [reel video] line {i}/{n}: {text[:60]}")

        seg_audio_path = f"/tmp/reel_seg_{i}.mp3"
        await synthesize_line(text, seg_audio_path)
        seg_duration = get_media_duration(seg_audio_path) or 3.0
        clip_duration = seg_duration + (PAUSE_SECONDS if i < n - 1 else 0)

        frame_buffer = generate_reel_frame_image(text, image_url=image_url, category=category)
        frame_path = f"/tmp/reel_frame_{i}.png"
        with open(frame_path, "wb") as f:
            f.write(frame_buffer.read())

        clip_path = f"/tmp/reel_clip_{i}.mp4"
        make_frame_video_clip(frame_path, clip_duration, clip_path)
        video_clip_paths.append(clip_path)

        audio_segment_paths.append(seg_audio_path)
        if i < n - 1:
            audio_segment_paths.append("/tmp/reel_silence.mp3")

    print("  [reel video] stitching video clips...")
    combined_video_path = "/tmp/reel_video_silent.mp4"
    concat_videos(video_clip_paths, combined_video_path)

    print("  [reel video] stitching narration audio...")
    final_audio_path = "/tmp/reel_narration_final.mp3"
    concat_audio(audio_segment_paths, final_audio_path)

    print("  [reel video] muxing final video...")
    final_video_path = "/tmp/reel_final.mp4"
    mux_video_audio(combined_video_path, final_audio_path, final_video_path)

    total_duration = get_media_duration(final_video_path)
    duration_label = f"~{round(total_duration)}s (actual)" if total_duration else f"~{est_seconds}s (estimated)"

    send_video(final_video_path, f"Full reel draft — {duration_label}, {n} segments")
    send_text_message(f"✅ Reel video sent. Length: {duration_label}. Reply with feedback or 'ready' if this looks good for Facebook.")

if __name__ == "__main__":
    asyncio.run(main())
