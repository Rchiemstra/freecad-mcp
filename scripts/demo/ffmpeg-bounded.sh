#!/usr/bin/env bash
# encode_view_video resolves this wrapper via FREECAD_MCP_FFMPEG.
set -euo pipefail
args=("$@")
destination="${args[-1]}"
unset 'args[-1]'
exec /usr/bin/ffmpeg -threads 1 -filter_threads 1 "${args[@]}" -threads 1 "$destination"
