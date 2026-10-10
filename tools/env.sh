# Load the repo's .env into the environment, for the release scripts.
#
#   . "$ROOT/tools/env.sh"
#
# A variable already set in the environment wins over .env, so CI (which has
# no .env and sets everything from repository variables and secrets) and a
# one-off `DICTATOR_SITE_URL=... tools/release.sh` both behave as expected.
# .env is never committed; .env.example lists every name the scripts read.

_dictator_env="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/.env"
if [ -f "$_dictator_env" ]; then
    while IFS= read -r _line || [ -n "$_line" ]; do
        case "$_line" in ''|'#'*) continue ;; esac
        _key="${_line%%=*}"
        _val="${_line#*=}"
        case "$_key" in *[!A-Za-z0-9_]*|'') continue ;; esac
        if [ -z "${!_key:-}" ]; then
            export "$_key=$_val"
        fi
    done < "$_dictator_env"
fi
unset _dictator_env _line _key _val
