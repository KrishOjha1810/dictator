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
#   5. with DICTATOR_DOWNLOAD_BASE set (environment or .env), uploads the same .dmg and
#      feed to the R2 bucket the website serves (tools/publish_r2.sh)
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
DMG="$ROOT/build/Dictator-$VERSION.dmg"
FEED="$ROOT/build/appcast.xml"

cd "$ROOT"
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
    echo "uncommitted changes; commit first so the release is a real commit" >&2
    exit 1
fi
# Only from a release branch: the list is RELEASE_BRANCHES in
# .github/workflows/release.yml, so a tag pushed by hand and a release made
# here follow the same rule (the feature branch while it is tested, later
# only main).
ALLOWED="$(sed -n 's/^  RELEASE_BRANCHES: "\(.*\)"/\1/p' .github/workflows/release.yml)"
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
case " $ALLOWED " in
    *" $BRANCH "*) ;;
    *) echo "releases come from: $ALLOWED (this is $BRANCH)" >&2; exit 1 ;;
esac
if [ "$(git rev-parse HEAD)" != "$(git rev-parse "origin/$BRANCH" 2>/dev/null)" ]; then
    echo "push $BRANCH first: the release must be a commit that is on GitHub" >&2
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

# 2 and 3. the update signature and the feed, shared with the CI release job
tools/appcast.sh "$VERSION" "$REPO" "$KEYDIR/sparkle_ed25519.key"

# 4. publish
cp "$DMG" build/Dictator.dmg
notes_args=(--generate-notes)
[ -n "$NOTES" ] && notes_args=(--notes-file "$NOTES")
gh release create "v$VERSION" -R "$REPO" --target "$(git rev-parse HEAD)" \
    --title "Dictator $VERSION" --latest "${notes_args[@]}" \
    "$DMG" build/Dictator.dmg "$DMG.sha256" "$FEED"
echo "published v$VERSION: https://github.com/$REPO/releases/tag/v$VERSION"

# 5. the website's copy, and the feed apps on the new address read
. tools/env.sh
if [ -n "${DICTATOR_DOWNLOAD_BASE:-}" ]; then
    tools/publish_r2.sh "$VERSION"
fi
