#!/usr/bin/env sh
# Install the Firefly themes for Helix.
set -eu

dest="${XDG_CONFIG_HOME:-$HOME/.config}/helix/themes"
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

mkdir -p "$dest"
cp "$here"/themes/firefly-*.toml "$dest"/
printf 'installed firefly-dark.toml and firefly-light.toml to %s\n' "$dest"
printf 'set theme = "firefly-dark" in %s/config.toml\n' "${XDG_CONFIG_HOME:-$HOME/.config}/helix"
