#!/usr/bin/env bash
# Publish a built release to the Cloudflare R2 bucket the website and the
# installed apps read.
#
#   tools/publish_r2.sh VERSION
#
# The bucket holds the newest release and the .dmg of the one before it:
#   Dictator-VERSION.dmg   what the website's download button serves, named
#                          with its version so people know what they have
#   latest.json            version, file name, size and SHA256 the site shows,
#                          and the previous release's file
#   appcast.xml            the update feed installed apps read
#
# The feed goes up after the .dmg, so no app is told about an update before
# its file is in place. The previous .dmg is kept until the next release:
# the website is redeployed after this, and until it is, its download button
# still points at that file.
#
# Needs build/Dictator-VERSION.dmg and build/appcast.xml (tools/build_dmg.sh,
# tools/appcast.sh), and in the environment or .env (see .env.example):
#   DICTATOR_DOWNLOAD_BASE
#   CF_ACCOUNT_ID  R2_ACCESS_KEY_ID  R2_SECRET_ACCESS_KEY  R2_BUCKET
#
# Used by tools/release.sh and by the dmg job in .github/workflows/release.yml.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="${1:?usage: tools/publish_r2.sh VERSION}"
DMG="$ROOT/build/Dictator-$VERSION.dmg"
FEED="$ROOT/build/appcast.xml"

# shellcheck source=env.sh
. "$ROOT/tools/env.sh"

for v in DICTATOR_DOWNLOAD_BASE CF_ACCOUNT_ID R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY R2_BUCKET; do
    [ -n "${!v:-}" ] || { echo "no $v (environment or .env)" >&2; exit 1; }
done
DOWNLOAD_BASE="${DICTATOR_DOWNLOAD_BASE%/}"
[ -f "$DMG" ] || { echo "no $DMG" >&2; exit 1; }
[ -f "$FEED" ] || { echo "no $FEED; run tools/appcast.sh first" >&2; exit 1; }
grep -q "<sparkle:shortVersionString>$VERSION<" "$FEED" \
    || { echo "$FEED is not for $VERSION" >&2; exit 1; }

ENDPOINT="https://$CF_ACCOUNT_ID.r2.cloudflarestorage.com/$R2_BUCKET"

# put FILE KEY CONTENT-TYPE CACHE-CONTROL
put() {
    curl -fsS --retry 3 -X PUT \
        --aws-sigv4 "aws:amz:auto:s3" \
        --user "$R2_ACCESS_KEY_ID:$R2_SECRET_ACCESS_KEY" \
        -H "Content-Type: $3" \
        -H "Cache-Control: $4" \
        -H "x-amz-content-sha256: UNSIGNED-PAYLOAD" \
        --upload-file "$1" "$ENDPOINT/$2" >/dev/null
    echo "uploaded $2"
}

FILE="Dictator-$VERSION.dmg"
# What the bucket holds now: its .dmg becomes the previous one, and the one
# before that is no longer pointed at by anything.
CURRENT="$(curl -fsS --max-time 30 "$DOWNLOAD_BASE/latest.json" 2>/dev/null || true)"
field() { printf '%s' "$CURRENT" | sed -n "s/.*\"$1\": *\"\(Dictator-[0-9][0-9.]*\.dmg\)\".*/\1/p" | head -1; }
PREVIOUS="$(field file)"
OLDER="$(field previous)"
[ "$PREVIOUS" != "$FILE" ] || PREVIOUS="$OLDER"

SIZE="$(stat -f %z "$DMG")"
SHA="$(shasum -a 256 "$DMG" | awk '{print $1}')"
LATEST="$(mktemp)"
trap 'rm -f "$LATEST"' EXIT
cat > "$LATEST" <<EOF
{
  "version": "$VERSION",
  "date": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "mac": {
    "file": "$FILE",
    "url": "$DOWNLOAD_BASE/$FILE",
    "size": $SIZE,
    "sha256": "$SHA",
    "minOS": "14.0",
    "arch": "Apple silicon"
  },
  "previous": "$PREVIOUS"
}
EOF

# A versioned .dmg never changes, so it can be cached for good; the feed and
# latest.json must never be stale.
put "$DMG" "$FILE" application/x-apple-diskimage "public, max-age=31536000, immutable"
put "$LATEST" latest.json application/json "no-cache"
put "$FEED" appcast.xml application/xml "no-cache"

if [ -n "$OLDER" ] && [ "$OLDER" != "$FILE" ] && [ "$OLDER" != "$PREVIOUS" ]; then
    curl -fsS --retry 3 -X DELETE \
        --aws-sigv4 "aws:amz:auto:s3" \
        --user "$R2_ACCESS_KEY_ID:$R2_SECRET_ACCESS_KEY" \
        "$ENDPOINT/$OLDER" >/dev/null && echo "removed $OLDER"
fi
echo "published $VERSION to $DOWNLOAD_BASE"
