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

## Network and the game's HTTP server
    ./run-mac.sh --update 0160 --lpt-device emulated --network-nat --forward-local 8080:80 --forward-local 2323:23
Then open http://127.0.0.1:8080/ (status page with high scores) or `telnet 127.0.0.1 2323`
(login Pin2000 / Manager, as shown in Adjustments > Communications > Network).

First time only, write the IP settings into the game's adjustments (they persist in savedata):
    ./run-mac.sh --update 0160 --lpt-device emulated --http-port 8080 --setip 10.0.2.15 255.255.255.0 10.0.2.2

Two things had to be fixed for this to work:
- Memory: with the network stack enabled RFM 1.60 runs out of XINU heap at power-up ("malloc(131072): getmem
  failed", fatal). run-mac.sh sets P2K_MEM_DETECT_PATCH=1 (Encore's 4 MiB -> 14 MiB sizmem override) for any
  network option.
- Peer ports: XINA's TCP demultiplexer compares the segment's source port zero-extended with the connection's
  stored port sign-extended, so any client port >= 32768 never matches after the SYN and gets RST (modern hosts
  and libslirp use 49152+; 1999 clients used < 5000). The emulated SMC8416 now folds such ports into 0..32767 on
  receive and restores them on transmit (`P2K_SMC_PORT_FOLD=0` disables; `P2K_SMC_RX_DELAY_US` adds latency).
