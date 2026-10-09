#!/usr/bin/env bash
# Sign a release .dmg for Sparkle and write the feed installed apps read.
#
#   tools/appcast.sh VERSION REPO KEYFILE
#
#   VERSION  e.g. 0.1.7; the .dmg is build/Dictator-VERSION.dmg
#   REPO     owner/name on GitHub the release is published to
#   KEYFILE  the Sparkle EdDSA private key (base64, one line)
#
# Writes build/appcast.xml with one item: this release. Apps read
# releases/latest/download/appcast.xml, so publishing the feed WITH the .dmg in
# the same release is what makes the update reach them; a latest release
# without a feed breaks updates for everyone until the next one.
#
# Used by tools/release.sh on the maintainer's Mac and by the dmg job in
# .github/workflows/release.yml, so both publish exactly the same shape.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="${1:?usage: tools/appcast.sh VERSION REPO KEYFILE}"
REPO="${2:?usage: tools/appcast.sh VERSION REPO KEYFILE}"
KEY="${3:?usage: tools/appcast.sh VERSION REPO KEYFILE}"
DMG="$ROOT/build/Dictator-$VERSION.dmg"
APP="$ROOT/build/stage/Dictator.app"
FEED="$ROOT/build/appcast.xml"

[ -f "$DMG" ] || { echo "no $DMG; run tools/build_dmg.sh $VERSION first" >&2; exit 1; }
[ -s "$KEY" ] || { echo "no update key at $KEY" >&2; exit 1; }
SPARKLE="$("$ROOT/tools/fetch_sparkle.sh")/bin"

# The build number Sparkle compares, from the app that went into this .dmg.
BUILD="$(plutil -extract CFBundleVersion raw "$APP/Contents/Info.plist")"
SHORT="$(plutil -extract CFBundleShortVersionString raw "$APP/Contents/Info.plist")"
[ "$SHORT" = "$VERSION" ] || { echo "staged app is $SHORT, not $VERSION" >&2; exit 1; }

# Installed apps take an update only if its build number is higher than
# their own. The build number is the commit count of the branch released
# from, so a squash merge, or releasing from a branch with fewer commits,
# would quietly produce a LOWER one and every installed copy would ignore
# every release from then on. Refuse that here, before anything is published.
LIVE="https://github.com/$REPO/releases/latest/download/appcast.xml"
PUBLISHED="$(curl -fsSL --max-time 30 "$LIVE" 2>/dev/null \
    | sed -n 's:.*<sparkle\:version>\([0-9]*\)</sparkle\:version>.*:\1:p' | head -1 || true)"
if [ -n "$PUBLISHED" ] && [ "$BUILD" -le "$PUBLISHED" ]; then
    echo "build $BUILD is not higher than the published $PUBLISHED: installed apps would never take it" >&2
    echo "(the build number is the commit count of the release branch)" >&2
    exit 1
fi

SIG_LINE="$("$SPARKLE/sign_update" --ed-key-file "$KEY" "$DMG")"
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
echo "$FEED (build $BUILD)"
