# Encore on macOS — local changes and RFM desktop controls

## Launch
    ./run-mac.sh --update 0160 --lpt-device emulated

## What was changed locally (uncommitted)
- `scripts/build-qemu.sh`: skips the x86 guest-extension check without a cross toolchain; applies `macos/*.patch` on Darwin.
- `scripts/run-qemu.sh`: skips the Debian apt/sudo runtime phase on Darwin.
- `macos/qemu-timer-nanosleep.patch`: sub-millisecond main-loop timer waits (macOS has no ppoll) — fixes the 21% game speed.
- `macos/sdl2-60hz-refresh.patch`: QEMU SDL window refresh 16 ms instead of 30 ms.
- `qemu/p2k-lpt-board.c`: Up/Down coin-door buttons un-swapped; RFM virtual ball model (see below).
- `qemu/p2k-dcs-adsp.c`: DCS stereo channels swapped to match the cabinet.

## Virtual ball model (RFM only, emulated board)
Optos 41-47, 51, 52 read closed with no ball. Four balls start in the trough.
Trough Eject -> ball in shooter lane (switch 18). Autoplunger (Launch button, switch 23) -> ball in play.
Pressing 46/51 puts the ball in the popper/lockup until the game kicks it out.
Backspace, Left Outlane (16) or Right Outlane (27) drain the ball back to the trough.

## Keys (letter bindings: copy macos/rfm-switch-keymap.yaml to ~/.config/encore/switch-keymap.yaml)
Space start · C coin · F7/F8 flippers · F6/F9 action buttons · Backspace drain · F4 coin door
Esc/Left service · Up/Down · Right enter · F2 flip screen · F3 screenshot · F1 quit
Any other switch: type its two digits (from rfm-switch-matrix.md) then hold Ctrl.
