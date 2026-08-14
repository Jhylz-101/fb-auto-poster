import asyncio
import subprocess
import re
import requests
import edge_tts
import imageio_ffmpeg

from main import build_reel_script, send_text_message

BOT_TOKEN = "8919908599:AAGTBdy69N5NFXY5KTIMhTkO7q2VpOXwYa8"
CHAT_ID = "7898015877"

VOICE_ID = "en-US-GuyNeural"
PAUSE_SECONDS = 0.4

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

async def synthesize_line(text, output_path):
    communicate = edge_tts.Communicate(text, VOICE_ID)
    await communicate.save(output_path)

def make_silence_clip(path, seconds):
    subprocess.run(
        [FFMPEG, "-y", "-f", "lavfi", "-i", f"anullsrc=r=24000:cl=mono",
         "-t", str(seconds), "-q:a", "9", path],
        check=True, capture_output=True
    )

def concat_audio(segment_paths, output_path):
    list_path = "/tmp/reel_concat_list.txt"
    with open(list_path, "w") as f:
        for p in segment_paths:
            f.write(f"file '{p}'\n")
    subprocess.run(
        [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", list_path,
         "-c:a", "libmp3lame", "-q:a", "4", output_path],
        check=True, capture_output=True
    )

def get_audio_duration(path):
    result = subprocess.run(
        [FFMPEG, "-i", path, "-f", "null", "-"],
        capture_output=True, text=True
    )
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", result.stderr)
    if not match:
        return None
    h, m, s = match.groups()
    return int(h) * 3600 + int(m) * 60 + float(s)

def send_voice_note(file_path, caption):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendAudio"
    with open(file_path, "rb") as f:
        files = {"audio": (file_path, f, "audio/mpeg")}
        data = {"chat_id": CHAT_ID, "caption": caption}
        response = requests.post(url, files=files, data=data)
    result = response.json()
    if not result.get("ok"):
        print(f"  [telegram ERROR] failed to send narration: {result}")
    else:
        print("  [telegram] narration sent OK")

async def main():
    send_text_message("🎙️ Building full narration with Guy — generating each line, this may take a minute...")

    lines, headlines_used, headlines_available, est_seconds = build_reel_script()
    print(f"  [voice test] {len(lines)} lines to synthesize")

    make_silence_clip("/tmp/reel_silence.mp3", PAUSE_SECONDS)

    segment_paths = []
    for i, line in enumerate(lines):
        seg_path = f"/tmp/reel_seg_{i}.mp3"
        print(f"  [voice test] synthesizing line {i}: {line[:60]}")
        await synthesize_line(line, seg_path)
        segment_paths.append(seg_path)
        if i < len(lines) - 1:
            segment_paths.append("/tmp/reel_silence.mp3")

    final_path = "/tmp/reel_narration_final.mp3"
    concat_audio(segment_paths, final_path)

    actual_duration = get_audio_duration(final_path)
    duration_label = f"~{round(actual_duration)}s (actual)" if actual_duration else f"~{est_seconds}s (estimated)"

    send_voice_note(final_path, f"Full narration — Guy — {duration_label}, {len(lines)} lines")
    send_text_message(f"✅ Narration sent. Length: {duration_label}. Reply if pacing/pauses feel right or need adjusting.")

if __name__ == "__main__":
    asyncio.run(main())
