# Test report — Sinuca Counter MVP (PR #1, merged)

Tested: end-to-end via browser, two tabs side by side, server in `--no-vision` mode (`uv run sinuca-counter --video /tmp/dummy.mp4 --no-vision --port 8088`). Validated that every action in `/control` reflects in `/?theme=window` via WebSocket.

Devin session: https://app.devin.ai/sessions/37b026bf56a543a190def05f1006a213

## Summary

All 8 tests passed. The critical assertions — turn-dot migration on swap, undo reverting state, manual adjustments still firing while paused, and rename/reset propagating via WebSocket — all behaved as specified.

| # | Test | Result |
|---|---|---|
| 1 | It should sync +1/−1 from panel to overlay via WebSocket | passed |
| 2 | It should swap turn highlight on overlay after Trocar vez | passed |
| 3 | It should set score 7x4 via Aplicar placar | passed |
| 4 | It should undo the last action (revert set_score) | passed |
| 5 | It should undo a swap_turn (turn dot back to P1) | passed |
| 6 | It should rename players to Lucas and Ricardo | passed |
| 7 | It should pause and still accept manual −1 adjustment | passed |
| 8 | It should resume and clear the pausado status | passed |
| 9 | It should reset score to 0x0 while keeping renamed players | passed |

## Out of scope (covered by unit tests / not testable without real video)

- Vision pipeline (calibration, ball detection, pocket/turn-end detectors) — covered by `tests/vision/` fixtures.
- `correct_last` — needs a real `BallPocketed` from the vision layer.

## Evidence

### 1. Initial state — overlay (theme=window)

P1 active (orange turn-dot), both scores 0, no "pausado" banner.

![Initial overlay state](https://app.devin.ai/attachments/b3118084-9051-4a3b-b841-3b03f8783b11/screenshot_c4dbbea2fa6b4d67b9df5a9764ae7082.png)

### 2. After +1×3 P1, +1 P2, −1 P1 — overlay shows 2×1

![Overlay 2x1](https://app.devin.ai/attachments/89f4f19b-a898-43f7-bc3a-e4dc6b061334/screenshot_bc05d3d7711f4bdd9c640c53e4268537.png)

### 3. After Trocar vez — turn-dot migrated to P2

This is the critical assertion: overlay's `.active` class moved from P1 to P2 only because the WebSocket pushed `current_player`.

![Swap turn — P2 active](https://app.devin.ai/attachments/701c3bfc-23af-4198-91c4-b00fb49de043/screenshot_56099e717f574abc9361c6e2349ddefa.png)

### 4. After Aplicar placar 7×4 — overlay shows 7×4

![Set score 7x4](https://app.devin.ai/attachments/1a5c73b7-971f-42d0-82aa-6cb5c6ed8777/screenshot_6c22f70c688545aa871733b735d585e4.png)

### 5. After 2× Desfazer — back to 2×1 with P1 active again

The first undo reverted the set_score; the second reverted the swap_turn. Turn-dot returned to P1.

![Undo back to P1 active](https://app.devin.ai/attachments/cf5be40e-2950-401f-a783-ced45437df58/screenshot_c643e2fedb684fe08dce1ed35f170557.png)

### 6. After Salvar nomes (Lucas / Ricardo) — overlay reflects new names

![Rename to Lucas/Ricardo](https://app.devin.ai/attachments/452a673d-0fa0-41cb-aee9-20cb763ae772/screenshot_9c84d55bbd6d40f0ba4f3c228c8e3dd0.png)

### 7. After Pausar + −1 — "pausado" shown, Lucas dropped to 1

`paused` only blocks vision events; the manual −1 still applied as expected.

![Paused + manual −1](https://app.devin.ai/attachments/67264450-c63e-4d85-8411-33b9e274844e/screenshot_374f7fcf2c474d5086d2c625a39923f9.png)

### 8. After Retomar — "pausado" cleared

![Resume](https://app.devin.ai/attachments/69d02566-fd3f-4b7d-903b-ddbf869fdd30/screenshot_ce544174c8124e5e88e7734bdead0982.png)

### 9. After Resetar partida — 0×0, names persist as Lucas / Ricardo

![Reset preserves names](https://app.devin.ai/attachments/de52d5e8-65cc-4da6-b779-9de4c855d5bd/screenshot_6bdd8847a7a745e38f8471ba437ad69f.png)

## Notes

- Server picked up port 8088 cleanly. No 4xx/5xx errors observed in console.
- The browser console is clean (no JS errors).
- WebSocket reconnects on tab switch (each `/?theme=window` and `/control` share the same `StateBus` and receive the same JSON).
- `paused` correctly blocks only vision events — manual `+1/−1`, `set_score`, etc. still apply, matching the spec.
