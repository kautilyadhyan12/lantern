#!/usr/bin/env bash
# Official, pinned workspace tools. Known tool advisory exception: ADR 0006.
set -euo pipefail

if [[ "$(uname -s)" != Linux || "$(uname -m)" != x86_64 ]]; then
    echo 'This workspace setup supports Linux x86_64. Use an x86_64 Codespace.' >&2
    exit 1
fi

readonly NODE_VERSION=24.22.1
readonly UV_VERSION=0.13.5
readonly CODEX_VERSION=0.164.0
readonly NODE_SHA256=6c172a9ab6718f7b801fb5a7bd486af2ee5e32758086a04b84fcce2aa77095e6
readonly UV_SHA256=f68d291c75783122dad58ab77def0e13f3233f358731db5d6d7e8715603b928f
readonly CODEX_SHA256=90dd0b03b28afcb7fa733a4f73b413db2916a47347efd43fb669cc1c774ee8e4
readonly install_root=${1:-"$HOME/.local/share/lantern-tools"}
setup_tmp=$(mktemp -d)
trap 'rm -rf -- "$setup_tmp"' EXIT

download() {
    local url=$1 name=$2 digest=$3
    curl --proto '=https' --proto-redir '=https' --tlsv1.2 --fail --location \
        --retry 2 --retry-max-time 180 --max-time 180 --max-filesize 200000000 \
        --output "$setup_tmp/$name" "$url"
    if ! printf '%s  %s\n' "$digest" "$setup_tmp/$name" | sha256sum --check --status; then
        echo 'A tool archive checksum did not match. Setup stopped; retry from official sources.' >&2
        return 1
    fi
}

readonly node_archive="node-v$NODE_VERSION-linux-x64.tar.xz"
readonly uv_archive=uv-x86_64-unknown-linux-gnu.tar.gz
readonly codex_archive=codex-x86_64-unknown-linux-musl.tar.gz
download "https://nodejs.org/dist/v$NODE_VERSION/$node_archive" "$node_archive" "$NODE_SHA256"
download "https://github.com/astral-sh/uv/releases/download/$UV_VERSION/$uv_archive" \
    "$uv_archive" "$UV_SHA256"
download "https://github.com/openai/codex/releases/download/rust-v$CODEX_VERSION/$codex_archive" \
    "$codex_archive" "$CODEX_SHA256"

# Authenticate every archive before extracting or changing an installation.
for archive in "$node_archive" "$uv_archive" "$codex_archive"; do
    tar -xf "$setup_tmp/$archive" -C "$setup_tmp"
done
mkdir -p "$install_root/bin" "$install_root/node"
cp -a "$setup_tmp/node-v$NODE_VERSION-linux-x64/." "$install_root/node/"
for tool in node npm npx; do
    ln -sfn "../node/bin/$tool" "$install_root/bin/$tool"
done
install -m 0755 "$setup_tmp/uv-x86_64-unknown-linux-gnu/uv" \
    "$setup_tmp/uv-x86_64-unknown-linux-gnu/uvx" "$install_root/bin/"
install -m 0755 "$setup_tmp/codex-x86_64-unknown-linux-musl" "$install_root/bin/codex"
if [[ $# -eq 0 ]]; then
    for startup in "$HOME/.bashrc" "$HOME/.zshrc"; do
        if ! grep -Fqx 'export PATH="$HOME/.local/share/lantern-tools/bin:$PATH"' "$startup" 2>/dev/null; then
            printf '\n%s\n' 'export PATH="$HOME/.local/share/lantern-tools/bin:$PATH"' >> "$startup"
        fi
    done
fi
echo 'Workspace tools installed. Run uv sync --frozen to prepare the project.'
