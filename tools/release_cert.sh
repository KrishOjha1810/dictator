#!/usr/bin/env bash
# The one self-signed certificate every release of Dictator.app is signed with.
#
#   tools/release_cert.sh create   make it, once, ever
#   tools/release_cert.sh unlock   put it where codesign looks; prints its hash
#   tools/release_cert.sh lock     take it off codesign's search list again
#
# Why one certificate and not a fresh one per build: macOS pins each user's
# Microphone and Accessibility grants to the app's signing identity. Sign the
# next release with a different key and every grant silently stops applying,
# with the checkbox still on (README, "If the key does nothing"). So this key
# is created once and kept. Losing it costs every user their permissions on
# the next update.
#
# Everything lives in ~/.dictator-release, outside the repo and outside
# ~/.dictator (which belongs to the running app and can be wiped by it):
#   release.p12        the certificate and key, for backup and for CI secrets
#   release.pass       the password of both the .p12 and the keychain
#   release.keychain-db
# Back up release.p12 and release.pass somewhere safe. Never commit them.
#
# Free: no Apple Developer account is involved. It does not make Gatekeeper
# trust the app; Open Anyway is still needed (docs/platforms.md). It only
# keeps the identity the same from one release to the next.
set -euo pipefail

DIR="${DICTATOR_RELEASE_DIR:-$HOME/.dictator-release}"
NAME="Dictator Release"
KC="$DIR/release.keychain-db"
P12="$DIR/release.p12"
PASS="$DIR/release.pass"
# /usr/bin/openssl is LibreSSL, whose PKCS12 the keychain imports. OpenSSL 3
# writes one `security import` rejects as a wrong password (signing.py).
SSL=/usr/bin/openssl

identity() {
    security find-identity -p codesigning "$KC" 2>/dev/null \
        | awk -v n="\"$NAME\"" 'index($0, n) {print $2; exit}'
}

create() {
    if [ -e "$P12" ]; then
        echo "already exists: $P12 (refusing to replace the release identity)" >&2
        exit 1
    fi
    mkdir -p "$DIR"; chmod 700 "$DIR"
    tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
    head -c 24 /dev/urandom | base64 | tr -d '/+=' > "$PASS"; chmod 600 "$PASS"
    pw="$(cat "$PASS")"
    cat > "$tmp/cnf" <<EOF
[req]
distinguished_name=dn
x509_extensions=v3
prompt=no
[dn]
CN=$NAME
[v3]
basicConstraints=critical,CA:false
keyUsage=critical,digitalSignature
extendedKeyUsage=critical,codeSigning
EOF
    "$SSL" req -x509 -newkey rsa:2048 -keyout "$tmp/key.pem" -out "$tmp/cert.pem" \
        -days 7300 -nodes -config "$tmp/cnf" 2>/dev/null
    "$SSL" pkcs12 -export -inkey "$tmp/key.pem" -in "$tmp/cert.pem" \
        -out "$P12" -passout "pass:$pw" -name "$NAME"
    chmod 600 "$P12"
    security create-keychain -p "$pw" "$KC"
    security set-keychain-settings "$KC"           # no auto-lock timeout
    security unlock-keychain -p "$pw" "$KC"
    security import "$P12" -k "$KC" -P "$pw" -T /usr/bin/codesign >/dev/null
    security set-key-partition-list -S apple-tool:,apple: -s -k "$pw" "$KC" >/dev/null
    echo "created $NAME"
    echo "  identity  $(identity)"
    echo "  back up   $P12 and $PASS"
}

unlock() {
    [ -e "$KC" ] || { echo "no release keychain; run: $0 create" >&2; exit 1; }
    security unlock-keychain -p "$(cat "$PASS")" "$KC"
    current="$(security list-keychains -d user | tr -d '"' | xargs)"
    case " $current " in
        *" $KC "*) ;;
        *) security list-keychains -d user -s $current "$KC" ;;
    esac
    id="$(identity)"
    [ -n "$id" ] || { echo "no '$NAME' identity in $KC" >&2; exit 1; }
    echo "$id"
}

lock() {
    current="$(security list-keychains -d user | tr -d '"' | xargs)"
    keep=""
    for k in $current; do [ "$k" = "$KC" ] || keep="$keep $k"; done
    security list-keychains -d user -s $keep
    [ -e "$KC" ] && security lock-keychain "$KC" || true
}

case "${1:-}" in
    create) create ;;
    unlock) unlock ;;
    lock)   lock ;;
    *) sed -n '2,7p' "$0"; exit 2 ;;
esac
