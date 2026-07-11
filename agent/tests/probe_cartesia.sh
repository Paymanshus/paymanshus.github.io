#!/usr/bin/env bash
# Probe Cartesia TTS REST API with each candidate model id to find a working one.
cd "$(dirname "$0")/.." || exit 1
set -a; . .env.local; set +a

for MODEL in sonic sonic-2 sonic-3 sonic-turbo; do
  echo "=== $MODEL ==="
  curl -s -m 20 -X POST https://api.cartesia.ai/tts/bytes \
    -H "X-API-Key: $CARTESIA_API_KEY" \
    -H "Cartesia-Version: 2025-04-16" \
    -H "Content-Type: application/json" \
    -d "{\"model_id\": \"$MODEL\", \"transcript\": \"test\", \"voice\": {\"mode\": \"id\", \"id\": \"$CARTESIA_VOICE_ID\"}, \"output_format\": {\"container\": \"mp3\", \"bit_rate\": 128000, \"sample_rate\": 44100}}" \
    -o "/tmp/tts_probe_$MODEL.out" -w "HTTP %{http_code}, %{size_download} bytes\n"
  file "/tmp/tts_probe_$MODEL.out" 2>/dev/null | sed 's/^/  -> /'
  head -c 300 "/tmp/tts_probe_$MODEL.out" | strings | head -2 | sed 's/^/  | /'
done
