#!/usr/bin/env bash
# Publish a built release to the Cloudflare R2 bucket the website and the
# installed apps read, then ask Cloudflare Pages to rebuild the site.
#
#   tools/publish_r2.sh VERSION
#
# The bucket only ever holds the newest release:
#   Dictator.dmg   what the website's download button serves
#   latest.json    version, size and SHA256 the website shows
#   appcast.xml    the update feed installed apps read
#
# The feed goes up last. Until it does, apps still see the previous feed, so
# no app is told about an update before its .dmg is in place.
#
# Needs build/Dictator-VERSION.dmg and build/appcast.xml (tools/build_dmg.sh,
# tools/appcast.sh), and in the environment or .env (see .env.example):
#   DICTATOR_DOWNLOAD_BASE
#   CF_ACCOUNT_ID  R2_ACCESS_KEY_ID  R2_SECRET_ACCESS_KEY  R2_BUCKET
#   CF_PAGES_DEPLOY_HOOK (optional: without it the site rebuilds on its next deploy)
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

SIZE="$(stat -f %z "$DMG")"
SHA="$(shasum -a 256 "$DMG" | awk '{print $1}')"
LATEST="$(mktemp)"
trap 'rm -f "$LATEST"' EXIT
cat > "$LATEST" <<EOF
{
  "version": "$VERSION",
  "date": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "mac": {
    "url": "$DOWNLOAD_BASE/Dictator.dmg",
    "size": $SIZE,
    "sha256": "$SHA",
    "minOS": "14.0",
    "arch": "Apple silicon"
  }
}
EOF

# The .dmg keeps one name, so browsers may cache it only briefly; the feed and
# latest.json must never be stale.
put "$DMG" Dictator.dmg application/x-apple-diskimage "public, max-age=300"
put "$LATEST" latest.json application/json "no-cache"
put "$FEED" appcast.xml application/xml "no-cache"

if [ -n "${CF_PAGES_DEPLOY_HOOK:-}" ]; then
    curl -fsS -X POST "$CF_PAGES_DEPLOY_HOOK" >/dev/null
    echo "site rebuild requested"
fi
echo "published $VERSION to $DOWNLOAD_BASE"
