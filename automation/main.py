"""Free-first kids cartoon slideshow pipeline.
Creates animated still-image videos (Ken Burns motion), narration, captions and thumbnail.
It does not generate full AI video footage; scene images are animated into a video with FFmpeg.
"""
import base64, json, os, subprocess, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
import requests
from PIL import Image, ImageDraw, ImageFont
from gtts import gTTS

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / os.getenv("OUTPUT_DIR", "output")
ASSETS = ROOT / "assets"
OUT.mkdir(parents=True, exist_ok=True)
API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
HF_TOKEN = os.getenv("HF_TOKEN", "").strip()
MODEL = os.getenv("HF_IMAGE_MODEL", "stabilityai/stable-diffusion-xl-base-1.0")
VIDEO_MODE = os.getenv("VIDEO_MODE", "auto").lower()
MADE_FOR_KIDS = os.getenv("MADE_FOR_KIDS", "true").lower() == "true"

def log(message):
    print(f"[{datetime.now(timezone.utc).isoformat()}] {message}", flush=True)

def run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def post_with_retries(url, **kwargs):
    last = None
    for attempt in range(1, 4):
        try:
            response = requests.post(url, **kwargs)
            if response.status_code in (429, 500, 502, 503, 504):
                last = RuntimeError(f"Transient HTTP {response.status_code}: {response.text[:300]}")
                time.sleep(attempt * 8)
                continue
            response.raise_for_status()
            return response
        except (requests.RequestException, RuntimeError) as exc:
            last = exc
            if attempt < 3:
                time.sleep(attempt * 8)
    raise RuntimeError(f"Provider request failed after 3 attempts: {last}")

def generate_story():
    mode = VIDEO_MODE
    if mode == "auto":
        mode = "short" if datetime.now(timezone.utc).day % 3 else "long"
    scenes_n = int(os.getenv("SHORT_SCENES" if mode == "short" else "LONG_SCENES", "5" if mode == "short" else "12"))
    duration = int(os.getenv("SHORT_SCENE_SECONDS" if mode == "short" else "LONG_SCENE_SECONDS", "7" if mode == "short" else "15"))
    if not API_KEY:
        raise RuntimeError("GEMINI_API_KEY is missing. Add it as a GitHub Actions repository secret.")
    prompt = f"""Create an original, gentle, child-safe 3D cartoon story for children ages 3-7.
Return ONLY valid JSON with keys title, description, tags (array of 5-10 strings), moral, scenes (array of exactly {scenes_n} objects).
Each scene object has narration (one or two simple English sentences) and image_prompt (detailed visual prompt).
Keep one main character design consistent across every image. No copyrighted characters, brand names, frightening imagery, violence, unsafe imitation, text in images, or watermarks.
Video format: {mode}. Each scene will last about {duration} seconds. Make the story complete and original."""
    response = post_with_retries(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
        params={"key": API_KEY},
        json={"contents":[{"parts":[{"text":prompt}]}],
              "generationConfig":{"temperature":0.8,"responseMimeType":"application/json"}},
        timeout=90,
    )
    raw = response.json()["candidates"][0]["content"]["parts"][0]["text"]
    story = json.loads(raw)
    if len(story.get("scenes", [])) != scenes_n:
        raise RuntimeError("Story API returned an unexpected number of scenes.")
    return story, mode, duration

def generate_image(prompt: str, destination: Path):
    if not HF_TOKEN:
        raise RuntimeError("HF_TOKEN is missing. Add a Hugging Face token with inference access.")
    url = f"https://router.huggingface.co/hf-inference/models/{quote(MODEL, safe='/')}"
    response = post_with_retries(url, headers={"Authorization": f"Bearer {HF_TOKEN}", "Content-Type":"application/json"},
                             json={"inputs":prompt, "options":{"wait_for_model":True}}, timeout=180)
    if not response.headers.get("content-type","").startswith("image/"):
        raise RuntimeError(f"Image provider did not return an image: {response.text[:300]}")
    destination.write_bytes(response.content)
    with Image.open(destination) as im:
        im.verify()

def font(size):
    for f in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"]:
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()

def make_thumbnail(image_path: Path, title: str, destination: Path):
    im = Image.open(image_path).convert("RGB")
    im.thumbnail((1280,720))
    canvas = Image.new("RGB", (1280,720), (45,95,120))
    canvas.paste(im, ((1280-im.width)//2, (720-im.height)//2))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0,560,1280,720), fill=(0,0,0))
    draw.text((45,585), title[:65], font=font(46), fill=(255,255,255), stroke_width=2, stroke_fill=(0,0,0))
    canvas.save(destination, quality=92)

def srt_time(seconds):
    ms = int((seconds-int(seconds))*1000)
    total = int(seconds)
    return f"{total//3600:02}:{(total%3600)//60:02}:{total%60:02},{ms:03}"

def render(story, mode, scene_seconds):
    width, height = (1080,1920) if mode == "short" else (1920,1080)
    scenes_dir = OUT / "scenes"
    scenes_dir.mkdir(parents=True, exist_ok=True)
    scene_files, audio_files, captions = [], [], []
    total_time = 0.0
    for i, scene in enumerate(story["scenes"], 1):
        img_path = scenes_dir / f"scene_{i:02}.png"
        audio_path = scenes_dir / f"voice_{i:02}.mp3"
        prompt = scene["image_prompt"] + ". High-quality cute 3D family animation, vibrant colors, soft cinematic light, child-safe, consistent recurring characters, no text, no watermark."
        generate_image(prompt, img_path)
        gTTS(text=scene["narration"], lang="en", slow=False).save(str(audio_path))
        clip = scenes_dir / f"clip_{i:02}.mp4"
        frames = max(24, int(scene_seconds*24))
        vf = (f"scale={width*2}:{height*2}:force_original_aspect_ratio=increase,"
              f"crop={width*2}:{height*2},zoompan=z='min(zoom+0.0007,1.08)':"
              f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={width}x{height}:fps=24,"
              "format=yuv420p")
        run(["ffmpeg","-y","-loop","1","-i",str(img_path),"-t",str(scene_seconds),"-vf",vf,
             "-an","-c:v","libx264","-preset","ultrafast","-pix_fmt","yuv420p",str(clip)])
        scene_files.append(clip)
        audio_files.append(audio_segment)
        captions.append((total_time, total_time+scene_seconds, scene["narration"]))
        total_time += scene_seconds
    concat = scenes_dir / "concat.txt"
    concat.write_text("\n".join(f"file '{p.as_posix()}'" for p in scene_files), encoding="utf-8")
    silent = OUT / "silent.mp4"
    run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(concat),"-c","copy",str(silent)])
    voice_list = scenes_dir / "audio.txt"
    voice_list.write_text("\n".join(f"file '{p.as_posix()}'" for p in audio_files), encoding="utf-8")
    voice = OUT / "voice.mp3"
    run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(voice_list),"-c","copy",str(voice)])
    srt = OUT / "captions.srt"
    srt.write_text("\n\n".join(f"{i}\n{srt_time(a)} --> {srt_time(b)}\n{text}" for i,(a,b,text) in enumerate(captions,1)), encoding="utf-8")
    output = OUT / "final.mp4"
    music = ASSETS / "background_music.mp3"
    encoded_music = os.getenv("BACKGROUND_MUSIC_BASE64","").strip()
    if encoded_music and not music.exists():
        ASSETS.mkdir(exist_ok=True)
        music.write_bytes(base64.b64decode(encoded_music))
    if music.exists():
        run(["ffmpeg","-y","-i",str(silent),"-i",str(voice),"-stream_loop","-1","-i",str(music),
             "-filter_complex","[1:a]volume=1.0[voice];[2:a]volume=0.10[music];[voice][music]amix=inputs=2:duration=first[a]",
             "-map","0:v","-map","[a]","-shortest","-c:v","copy","-c:a","aac","-b:a","128k",str(output)])
    else:
        run(["ffmpeg","-y","-i",str(silent),"-i",str(voice),"-map","0:v","-map","1:a","-shortest",
             "-c:v","copy","-c:a","aac","-b:a","128k",str(output)])
    probe = subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","json",str(output)], text=True)
    if float(json.loads(probe)["format"]["duration"]) < scene_seconds:
        raise RuntimeError("Rendered video is unexpectedly short.")
    return output, scenes_dir / "scene_01.png", srt

def youtube_service():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    raw = os.getenv("YOUTUBE_TOKEN_JSON","").strip()
    if not raw:
        raise RuntimeError("YOUTUBE_TOKEN_JSON secret is missing. See docs/DEPLOYMENT.md.")
    creds = Credentials.from_authorized_user_info(json.loads(raw), ["https://www.googleapis.com/auth/youtube.upload"])
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    if not creds.valid:
        raise RuntimeError("YouTube OAuth token is invalid/expired; regenerate it and update the secret.")
    return build("youtube","v3",credentials=creds)

def upload(video, thumbnail, story):
    from googleapiclient.http import MediaFileUpload
    service = youtube_service()
    title = str(story.get("title","A Little Story About Kindness"))[:95]
    description = str(story.get("description","An original, gentle animated story for children."))[:4500]
    tags = [str(x)[:30] for x in story.get("tags",[])[:15]]
    privacy = os.getenv("YOUTUBE_PRIVACY_STATUS","private")
    status = {"privacyStatus": privacy, "selfDeclaredMadeForKids": MADE_FOR_KIDS}
    publish_at = os.getenv("YOUTUBE_PUBLISH_AT","").strip()
    auto_schedule = os.getenv("AUTO_SCHEDULE","false").lower() == "true"
    if auto_schedule and privacy == "private" and not publish_at:
        from datetime import timedelta
        delay_hours = max(1, int(os.getenv("PUBLISH_DELAY_HOURS", "24")))
        publish_at = (datetime.now(timezone.utc) + timedelta(hours=delay_hours)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    if publish_at and privacy == "private":
        status["publishAt"] = publish_at
    body = {"snippet":{"title":title,"description":description,"tags":tags,"categoryId":os.getenv("YOUTUBE_CATEGORY_ID","1")},
            "status":status}
    response = service.videos().insert(part="snippet,status", body=body,
        media_body=MediaFileUpload(str(video), mimetype="video/mp4", resumable=True)).execute()
    video_id = response["id"]
    try:
        service.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(str(thumbnail), mimetype="image/png")).execute()
    except Exception as exc:
        log(f"Thumbnail upload failed (video uploaded): {exc}")
    return f"https://www.youtube.com/watch?v={video_id}"

def safety_review(story):
    """Ask a second model call to block obvious child-safety and originality risks."""
    prompt = """Review this proposed children's cartoon story for ages 3-7. Return ONLY JSON:
    {"pass": true/false, "reasons": ["..."]}.
    Fail if it includes violence, sexual content, dangerous imitation, hateful content,
    frightening distress, unsafe child behavior, copyrighted characters, brands, or unclear
    material. Be conservative; if uncertain, fail. This is a screening layer, not a guarantee.
    STORY JSON: """ + json.dumps(story, ensure_ascii=False)
    response = post_with_retries(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
        params={"key": API_KEY},
        json={"contents":[{"parts":[{"text":prompt}]}],
              "generationConfig":{"temperature":0.1,"responseMimeType":"application/json"}},
        timeout=90,
    )
    result = json.loads(response.json()["candidates"][0]["content"]["parts"][0]["text"])
    if result.get("pass") is not True:
        raise RuntimeError("AI safety review failed; upload blocked: " + json.dumps(result.get("reasons", [])))
    return result

def main():
    log("Starting kids video pipeline.")
    story, mode, scene_seconds = generate_story()
    (OUT / "story.json").write_text(json.dumps(story, indent=2, ensure_ascii=False), encoding="utf-8")
    video, first_image, captions = render(story, mode, scene_seconds)
    thumb = OUT / "thumbnail.png"
    make_thumbnail(first_image, story.get("title","Kids Cartoon"), thumb)
    text_blob = json.dumps(story, ensure_ascii=False).lower()
    blocked = ["graphic violence", "sexual content", "self-harm", "hate speech"]
    if any(term in text_blob for term in blocked):
        raise RuntimeError("Safety keyword check failed; video will not be uploaded.")
    if not story.get("title") or not story.get("scenes"):
        raise RuntimeError("Quality check failed: missing title/scenes.")
    safety = safety_review(story)
    (OUT / "safety_review.json").write_text(json.dumps(safety, indent=2), encoding="utf-8")
    url = upload(video, thumb, story)
    report = {"status":"uploaded_or_scheduled","url":url,"mode":mode,"title":story["title"],
              "video_path":str(video),"captions_path":str(captions),"created_at":datetime.now(timezone.utc).isoformat()}
    (OUT / "result.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    log(f"Completed: {url}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"FAILED: {e}")
        raise
