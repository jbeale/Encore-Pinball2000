#!/bin/zsh
# macOS launcher for Encore: uses Homebrew bash 5 + GNU coreutils (realpath -m, stat -c)
# and QEMU's main-thread SDL display (the default direct renderer drives SDL from a
# worker thread, which macOS does not allow).
#
# Networking (--http-port, --network*, --setip, --expose-services) needs XINA's
# 14 MiB heap: with the stock 4 MiB ceiling the network stack runs the game out of
# memory during CMOS power-up ("malloc(131072): getmem failed"), so it is enabled here.
ROOT="$(cd "$(dirname "$0")" && pwd)"
export PATH="/opt/homebrew/opt/coreutils/libexec/gnubin:/opt/homebrew/bin:$PATH"
for arg in "$@"; do
  case "$arg" in
    --http-port|--network*|--setip|--expose-services|--forward*) export P2K_MEM_DETECT_PATCH=1 ;;
  esac
done
exec bash "$ROOT/scripts/run-qemu.sh" --display sdl --game rfm "$@"
