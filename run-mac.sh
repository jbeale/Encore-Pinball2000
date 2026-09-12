#!/bin/zsh
# macOS launcher for Encore: uses Homebrew bash 5 + GNU coreutils (realpath -m, stat -c)
# and QEMU's main-thread SDL display (the default direct renderer drives SDL from a
# worker thread, which macOS does not allow).
ROOT="$(cd "$(dirname "$0")" && pwd)"
export PATH="/opt/homebrew/opt/coreutils/libexec/gnubin:/opt/homebrew/bin:$PATH"
exec bash "$ROOT/scripts/run-qemu.sh" --display sdl --game rfm "$@"
