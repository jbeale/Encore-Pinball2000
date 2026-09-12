# Revenge From Mars — switch matrix (from the operator's manual, confirmed against the 1.60 game ROM table)

Number = column×10 + row. Game-internal switch ID = (column−1)×8 + (row−1).
`*` = opto: reads CLOSED with no ball present, OPEN when a ball blocks the beam.

| # | Switch | # | Switch | # | Switch | # | Switch |
|---|---|---|---|---|---|---|---|
| 11 | Right Ramp Entrance | 31 | Center Loop Reed (Bottom) | 51 | Right Lockup 1 * | 71 | Martian Target 3 (Left Top) |
| 12 | Left Ramp Exit | 32 | Center Loop Reed (Top) | 52 | Left Ramp Entrance * | 72 | Martian Target 2 (Left Mid) |
| 13 | Start Button | 33 | Center Target 4 | 53 | not used | 73 | Martian Target 1 (Left Bot) |
| 14 | not used | 34 | Center Target 3 | 54 | not used | 74 | Center Loop Rollover |
| 15 | Drop Target Down | 35 | Center Target 2 | 55 | not used | 75 | Center Deflector Panel |
| 16 | Left Outlane | 36 | Center Target 1 | 56 | not used | 76 | Right Top Lane |
| 17 | Right Return Lane | 37 | Martian Target 4 (Center) | 57 | not used | 77 | Left Top Lane |
| 18 | Shooter Lane | 38 | Up/Down Ramp Up | 58 | not used | 78 | Left Loop (High) |
| 21 | not used | 41 | Trough Jam * | 61 | Left Slingshot | 81 | not used |
| 22 | not used | 42 | Trough Ball 1 * | 62 | Right Slingshot | 82 | not used |
| 23 | Launch Button | 43 | Trough Ball 2 * | 63 | Left Jet Bumper | 83 | not used |
| 24 | not used | 44 | Trough Ball 3 * | 64 | Right Jet Bumper | 84 | not used |
| 25 | Left Loop (Low) | 45 | Trough Ball 4 * | 65 | Bottom Jet Bumper | 85 | Martian Target 7 (Right Bot) |
| 26 | Left Return Lane | 46 | Right Popper * | 66 | not used | 86 | Martian Target 6 (Right Mid) |
| 27 | Right Outlane | 47 | Jet Exit * | 67 | Right Loop (Low) | 87 | Martian Target 5 (Right Top) |
| 28 | Right Ramp Exit | 48 | not used | 68 | Right Loop (High) | 88 | not used |

Direct switches (not in the matrix; handled by Encore's fixed keys): D1-D3 coin slots, D9-D12 Escape/Down/Up/Enter,
D17 slam tilt, D18 coin door closed, D19 plumb bob tilt, D21/D22 right/left flipper button, D23/D24 right/left action button.

Solenoids (game numbering, 0-based in the `drive N` console command): 0 Left Martian, 1 Right Martian, 2 Jet Exit Post,
3 Right Gate, 4 Left Gate, 5 Drop Target Down, 6 Drop Target Up, 7 Right Popper, 8 Trough Eject, 9 Left Sling,
10 Right Sling, 11 Left Jet, 12 Right Jet, 13 Bottom Jet, 14 Autoplunger, 15 Right Lockup, 16-31 flashers,
32/33 Right Flipper power/hold, 34/35 Left Flipper power/hold, 36/37 Lock Diverter, 38/39 Up/Down Ramp, 47 Ticket Dispenser.
