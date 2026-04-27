# Test plan — Sinuca Counter MVP (PR #1)

## What changed (user-visible)

Brand-new app. Subindo via CLI, três páginas web ficam disponíveis em
`127.0.0.1:8088`:

- `/?theme=transparent` — overlay para OBS Browser Source (fundo transparente).
- `/?theme=window` — overlay para janela autônoma (fundo sólido).
- `/control` — painel do operador com `+1/−1`, set score, swap turn, undo,
  rename, pause/resume, reset, correct_last e timeline.

Todas as mudanças de estado fluem por um `StateBus` asyncio e são empurradas
por WebSocket (`/ws`) para todos os clientes.

## Setup (já feito, fora do plano)

- `uv sync` no repo, `uv run sinuca-counter --video /tmp/dummy.mp4 --no-vision --port 8088` para levantar o server sem precisar de vídeo real.

## Primary flow — placar sincroniza painel↔overlay por WebSocket

Abrir duas abas lado a lado:

- Aba A: `http://127.0.0.1:8088/?theme=window`
- Aba B: `http://127.0.0.1:8088/control`

### Passos e assertions (cada passo com expected value concreto)

1. **Estado inicial**
   - Aba A deve mostrar "P1  ×  P2", ambos com score `0`.
   - Aba B deve mostrar os mesmos nomes e zeros; o card de P1 deve ter a
     classe `active` (destaque laranja no turn-dot), P2 não.
   - Footer/banner de status vazio (sem "pausado").

2. **+1 em P1** (clicar o botão `+1` do card P1 no painel)
   - Painel: `score-p1` → `1`.
   - Overlay: score de P1 → `1` (via WebSocket).
   - Timeline ganha uma entrada "p1 +1".

3. **+1 em P2** (clicar `+1` no card P2)
   - Painel e overlay: P2 → `1`.
   - P1 permanece `1`.

4. **Set score** (digitar 7 e 4 nos inputs de P1/P2 e clicar "Aplicar placar")
   - Painel: `score-p1 = 7`, `score-p2 = 4`.
   - Overlay: 7 × 4.
   - Timeline ganha "placar = 7 x 4".

5. **Swap turn**
   - Antes: card P1 `active`, card P2 não.
   - Depois: card P2 `active`, card P1 não. **Esta é a assertion crítica** — se
     o WebSocket não estivesse empurrando `current_player`, o destaque laranja
     não migraria.

6. **Undo**
   - Clicar "Desfazer".
   - Placar volta para 7 × 4 ou equivalente ao estado anterior ao swap; na
     prática aqui reverte o swap_turn → volta ativo em P1. Assertion: o
     turn-dot do P1 volta a estar aceso.

7. **Rename P1 → "Lucas", P2 → "Ricardo"** (digitar e clicar "Salvar nomes")
   - Painel: cabeçalhos dos dois cards mostram os nomes novos.
   - Overlay: igual.

8. **Pause + −1** (clicar "Pausar", depois `−1` em P1)
   - Overlay mostra "pausado" no canto inferior direito.
   - `−1` em P1 ainda funciona (é ajuste manual, não afeta paused), P1 = 6.
   - Observação: `paused` bloqueia eventos de visão, não ajustes do painel.

9. **Resume**
   - Overlay remove "pausado".

10. **Reset**
    - Dialog de confirmação → confirmar.
    - Painel: 0 × 0. Overlay: 0 × 0. Nomes "Lucas" e "Ricardo" permanecem.

### Why these assertions would fail if the code is broken

- **Swap-turn destaque no overlay**: exige que o WebSocket empurre
  `current_player` e que `overlay.js` aplique/remova `.active`. Se o push
  estivesse quebrado, o painel mudaria mas o overlay não.
- **Undo** volta ao estado anterior imediato; se `BrazilianRules._on_undo`
  estivesse mal-feito (ex. não consumindo o histórico), o reset não reverteria
  a última ação.
- **Pause** só afeta eventos de visão; ajustes manuais ainda funcionam. Se o
  engine estivesse bloqueando ajustes no modo paused, o `−1` não teria efeito.
- **Reset** mantém nomes: se `_on_manual("reset")` estivesse descartando os
  nomes, "Lucas"/"Ricardo" voltariam a "P1"/"P2".

## Fora do escopo desta sessão

- Calibração real com clique nos 4 cantos da mesa (requer um vídeo real).
- Detecção de bolas encaçapadas (depende do vídeo e de calibração válida).
- `correct_last` — requer um `BallPocketed` real emitido pela visão, e o
  objetivo aqui é validar o caminho painel↔overlay, não a visão.

Essas partes são cobertas pelos testes unitários (`tests/vision/` e
`tests/rules/`) que rodam em CI.
