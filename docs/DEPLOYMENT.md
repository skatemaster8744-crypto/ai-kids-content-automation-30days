# Deploy the kids cartoon automation (free-first)

This adds a GitHub Actions pipeline that creates a story, generates scene images, turns them into gently animated still-image clips, adds English TTS narration/captions, renders an MP4 and thumbnail, then uploads the video to YouTube. It is a **cartoon slideshow/animatic**, not full text-to-video footage. Full AI video generation is generally not reliably available at unlimited zero cost.

## What runs automatically

- Daily workflow trigger at 10:30 UTC (16:00 India time), plus manual trigger in GitHub Actions.
- Story/scene script via Gemini API.
- Scene images via Hugging Face Inference API (model access and free quota can change).
- English voice-over via gTTS; FFmpeg makes Ken Burns-style motion clips and joins them.
- SRT captions and a thumbnail are generated.
- Basic output validation, then YouTube upload with the channel's OAuth token.
- Failed jobs are marked failed in Actions logs; GitHub can notify you according to your notification settings.

## Important limitations / safety

- The initial code uses simple keyword checks, not a reliable semantic child-safety review. For this reason, the workflow **uploads as private** by default. Review the first outputs before enabling public publishing.
- Auto-publication is not enabled by default. For a future scheduled publish, set YOUTUBE_PUBLISH_AT as an RFC3339 UTC timestamp at least 15 minutes in the future, with YOUTUBE_PRIVACY_STATUS=private. The current workflow deliberately keeps uploads private until you've tested it.
- YouTube's selfDeclaredMadeForKids flag is set to true. Verify the setting matches the actual content and your channel's audience.
- The pipeline does not create real character rigging or full AI motion. It animates generated still images.
- A background track is optional. To include one, place a properly licensed track at assets/background_music.mp3, or set BACKGROUND_MUSIC_BASE64 as a repository secret. Do not use copyrighted music without permission.
- Hugging Face models may return 503/rate-limit/model-gated errors. The job fails visibly rather than pretending to have made a video.
- A free quota is not a guarantee of unlimited usage. Keep API billing disabled where possible, monitor quotas, and do not add a payment method unless you intend to pay.

## 1. Add GitHub Actions secrets

Open the repository on GitHub → Settings → Secrets and variables → Actions → New repository secret.

Required secrets:
- GEMINI_API_KEY: create a key at https://aistudio.google.com/app/apikey. Free quota/availability depends on Google's current plan and region.
- HF_TOKEN: create a Hugging Face access token at https://huggingface.co/settings/tokens. Model access and inference quotas vary.
- YOUTUBE_TOKEN_JSON: OAuth token JSON for the YouTube channel owner, with https://www.googleapis.com/auth/youtube.upload scope. Never paste this token into a public file or chat.

Optional:
- BACKGROUND_MUSIC_BASE64: base64-encoded MP3 of a track you have rights to use. Alternatively commit assets/background_music.mp3 (check its licence first).

## 2. Enable YouTube upload authorization

1. Open https://console.cloud.google.com/ and create/select a Google Cloud project.
2. Enable YouTube Data API v3.
3. Configure the OAuth consent screen and create an OAuth Client ID (Desktop app is simplest for one-time setup).
4. On a trusted computer, run the OAuth authorization once with the YouTube upload scope and save the resulting token.json.
5. Copy the complete JSON content into GitHub secret YOUTUBE_TOKEN_JSON. It includes a refresh token; treat it as a password. If your OAuth app is in Testing mode, refresh tokens may expire after a limited period; use the appropriate published/verified configuration for durable operation.
6. YouTube API uploads are subject to API quota and project compliance policies. The API can upload a video and set selfDeclaredMadeForKids; see https://developers.google.com/youtube/v3/docs/videos/insert.

The workflow does not currently include a helper to create the OAuth token automatically. This must be done once by the channel owner.

## 3. Run a test

1. Open Actions → Generate and upload kids cartoon → Run workflow.
2. Choose short for the first test.
3. Open the run to see logs. Download the kids-video-run artifact to inspect MP4, thumbnail, captions and story JSON.
4. The video uploads as Private. Watch the video and verify audio, image consistency, title, thumbnail, captions, and audience settings.
5. Only after you are happy with the result should you separately change the workflow's publishing policy. Do not publish unchecked outputs automatically.

## 4. Costs

- GitHub Actions: free allowance varies by repository visibility/account plan; public repositories have different runner rules from private repositories.
- Gemini API: may have a free tier, with model/region quotas and terms subject to change.
- Hugging Face Inference API: may have limited free credits; generation can be rate-limited or unavailable for a model.
- gTTS and FFmpeg: no paid API key is used, but gTTS depends on an online service and should be used within its terms.
- YouTube Data API: no direct per-upload fee, but quota and policy restrictions apply.
- Cloud Run/Cloud Storage are not used by this version, so no separate cloud deployment is required. GitHub Actions is the runner.

A guaranteed ₹0, unlimited, fully AI-video-generating system does not exist. This is a free-first prototype and depends on limited third-party quotas. Set repository spending alerts and monitor usage.

## Troubleshooting

- GEMINI_API_KEY is missing: add the secret.
- HF_TOKEN is missing / 503 / 429: add token, check model access and retry later.
- YOUTUBE_TOKEN_JSON is missing or expired: renew OAuth token JSON and replace the secret.
- ffmpeg not found: workflow installs FFmpeg; for local use, install FFmpeg separately.
- Upload succeeds but thumbnail fails: the video remains uploaded; check thumbnail requirements and API permissions.
- Do not set the video public until you manually inspect at least the first few generated outputs.
