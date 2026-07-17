#!/usr/bin/env bash
set -euo pipefail

readonly required_models=(
    gpt-5.6-sol
    gpt-5.6-terra
    gpt-5.6-luna
)

smoke=false
case "${1:-}" in
    "") ;;
    --smoke) smoke=true ;;
    *)
        printf 'Usage: %s [--smoke]\n' "$0" >&2
        exit 2
        ;;
esac

if ! command -v claude-openai >/dev/null 2>&1; then
    printf 'claude-openai is not available on PATH.\n' >&2
    exit 127
fi

available_models="$(claude-openai --list-models)"
missing=()
for model in "${required_models[@]}"; do
    if ! grep -Fxq "$model" <<<"$available_models"; then
        missing+=("$model")
    fi
done

if ((${#missing[@]})); then
    printf 'Missing required CLIProxyAPI model(s): %s\n' "${missing[*]}" >&2
    exit 1
fi

printf 'Required CLIProxyAPI models are available:\n'
printf '  gpt-5.6-sol\n'
printf '  gpt-5.6-terra\n'
printf '  gpt-5.6-luna\n'

if [[ "$smoke" == false ]]; then
    exit 0
fi

for model in "${required_models[@]}"; do
    expected="${model} ok"
    response="$(timeout 120s claude-openai \
        --model "$model" \
        -p \
        --output-format text \
        "Reply with exactly: ${expected}")"
    response="${response//$'\r'/}"
    response="${response%$'\n'}"
    if [[ "$response" != "$expected" ]]; then
        printf 'Smoke check failed for %s: received %q\n' "$model" "$response" >&2
        exit 1
    fi
    printf 'Smoke check passed: %s\n' "$model"
done
