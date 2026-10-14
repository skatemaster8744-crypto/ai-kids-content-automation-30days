# Automated AI Kids Cartoon Pipeline

A free-first GitHub Actions prototype for creating kids cartoon **animated slideshow videos** and uploading them to YouTube.

## Quick start
1. Read docs/DEPLOYMENT.md.
2. Add repository secrets: GEMINI_API_KEY, HF_TOKEN, and YOUTUBE_TOKEN_JSON.
3. Go to GitHub Actions → Generate and upload kids cartoon → Run workflow → short.
4. Inspect the private upload and download artifacts before publishing.

## Pipeline
Story generation → scene image generation → English narration → FFmpeg motion/assembly → captions → thumbnail → validation → private YouTube upload.

The pipeline is not a full AI text-to-video generator and cannot promise unlimited free generation. Provider free quotas and model access vary. Public publishing is intentionally not enabled in the initial version; see the deployment guide.
