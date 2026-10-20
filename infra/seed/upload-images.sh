#!/bin/sh
# Amorcage du bucket : envoie les visuels du catalogue (SVG originaux, sans droits) au filer
# SeaweedFS. Idempotent : un nouvel envoi remplace le fichier existant.
set -eu

FILER_URL="${FILER_URL:-http://seaweedfs:8888}"
BUCKET="${S3_BUCKET:-product-images}"

for file in /seed/images/*.svg; do
  name="$(basename "$file")"
  curl -fsS -X POST -F "file=@${file};type=image/svg+xml" \
    "${FILER_URL}/buckets/${BUCKET}/${name}" > /dev/null
  echo "envoye : ${name}"
done
