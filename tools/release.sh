#!/usr/bin/env bash
# Publish a release of Dictator.app that every installed copy will offer as
# an update.
#
#   tools/release.sh 0.1.3 [notes.md]
#
# What it does, in order:
#   1. builds build/Dictator-<VERSION>.dmg, signed with the release
#      certificate (tools/release_cert.sh), so permissions survive the update
#   2. signs that .dmg with the Sparkle update key, which the app checks
#      before installing anything: an update that is not signed by this key
#      is refused, whoever hosts it
#   3. writes build/appcast.xml, the feed the app reads
#   4. creates the GitHub release v<VERSION> with the .dmg (under its own name
#      and as Dictator.dmg, for the README link) and appcast.xml
#
# The app looks for updates at releases/latest/download/appcast.xml, so the
# newest release is always the one offered, and nothing else has to be hosted.
#
# Needs: ~/.dictator-release/{release.p12,release.pass,sparkle_ed25519.key},
# build/cache/sparkle (tools/build_dmg.sh fetches it), and a GitHub token in
# GH_TOKEN, or in GITPAT_TOKEN_MYNK03 in .env. Run it from a clean tree on the
# commit you want to ship; it refuses otherwise, so a release is always a
# commit somebody can check out.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="${1:?usage: tools/release.sh VERSION [notes.md]}"
NOTES="${2:-}"
REPO="${DICTATOR_REPO:-cc-vb/dictator}"
KEYDIR="${DICTATOR_RELEASE_DIR:-$HOME/.dictator-release}"
SPARKLE="$ROOT/build/cache/sparkle/bin"
DMG="$ROOT/build/Dictator-$VERSION.dmg"
FEED="$ROOT/build/appcast.xml"

cd "$ROOT"
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
    echo "uncommitted changes; commit first so the release is a real commit" >&2
    exit 1
fi
if [ -z "${GH_TOKEN:-}" ] && [ -f .env ]; then
    GH_TOKEN="$(sed -n 's/^GITPAT_TOKEN_MYNK03=//p' .env)"
fi
export GH_TOKEN
[ -n "${GH_TOKEN:-}" ] || { echo "no GitHub token (GH_TOKEN or .env)" >&2; exit 1; }
[ -f "$KEYDIR/sparkle_ed25519.key" ] || { echo "no update key in $KEYDIR" >&2; exit 1; }

# 1. build and sign with the release certificate
ID="$(tools/release_cert.sh unlock)"
trap 'tools/release_cert.sh lock' EXIT
DICTATOR_SIGN_ID="$ID" tools/build_dmg.sh "$VERSION"
BUILD="$(plutil -extract CFBundleVersion raw build/stage/Dictator.app/Contents/Info.plist)"

# 2. the update signature
SIG_LINE="$("$SPARKLE/sign_update" --ed-key-file "$KEYDIR/sparkle_ed25519.key" "$DMG")"

# 3. the feed: one item, the release this run makes
URL="https://github.com/$REPO/releases/download/v$VERSION/Dictator-$VERSION.dmg"
cat > "$FEED" <<EOF
<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle">
  <channel>
    <title>Dictator</title>
    <item>
      <title>Dictator $VERSION</title>
      <pubDate>$(LC_ALL=C date -u '+%a, %d %b %Y %H:%M:%S +0000')</pubDate>
      <sparkle:version>$BUILD</sparkle:version>
      <sparkle:shortVersionString>$VERSION</sparkle:shortVersionString>
      <sparkle:minimumSystemVersion>14.0</sparkle:minimumSystemVersion>
      <link>https://github.com/$REPO/releases/tag/v$VERSION</link>
      <enclosure url="$URL" type="application/octet-stream" $SIG_LINE />
    </item>
  </channel>
</rss>
EOF

# 4. publish
cp "$DMG" build/Dictator.dmg
notes_args=(--generate-notes)
[ -n "$NOTES" ] && notes_args=(--notes-file "$NOTES")
gh release create "v$VERSION" -R "$REPO" --target "$(git rev-parse HEAD)" \
    --title "Dictator $VERSION" --latest "${notes_args[@]}" \
    "$DMG" build/Dictator.dmg "$DMG.sha256" "$FEED"
echo "published v$VERSION: https://github.com/$REPO/releases/tag/v$VERSION"
