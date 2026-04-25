# Sinuca Counter

Contador automático de pontos para sinuca brasileira (e, em fases futuras,
snooker, English pool e transmissões ao vivo). O MVP processa um arquivo de
vídeo `.mp4`, exibe o placar como overlay (Browser Source no OBS ou janela
autônoma) e oferece um painel de controle web para o operador.

> Status: **Fase 1a (MVP)** — detecção via OpenCV clássico (HSV +
> HoughCircles + tracking por proximidade).

## Visão geral

```
┌─────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  video_source   │ --> │  vision_pipeline │ --> │   rules_engine   │
│  (arquivo .mp4) │     │  (detec + track) │     │ (estado partida) │
└─────────────────┘     └──────────────────┘     └─────────┬────────┘
                                                  ScoreState (JSON)
                                                           ▼
                                              ┌────────────────────────┐
                                              │  overlay_server        │
                                              │  (FastAPI + WebSocket) │
                                              └────┬────────┬──────────┘
                                                   ▼        ▼
                                          Browser Source / Painel /control
```

Detalhes de design em
[`docs/sinuca-counter-mvp-design.md`](docs/sinuca-counter-mvp-design.md).

## Requisitos

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) — gerenciador de ambiente recomendado.
- `ffmpeg` instalado no sistema (necessário para o OpenCV ler vídeos).

## Setup

```bash
uv sync
```

## Uso

```bash
uv run sinuca-counter \
    --video data/samples/jogo.mp4 \
    --rules brasileira \
    --p1 "Lucas" \
    --p2 "Ricardo" \
    --saque p1
```

Na primeira execução, uma janela do OpenCV abre pedindo 4 cliques nos cantos da
mesa (calibração de homografia). A calibração é salva em
`<video>.calib.json` e reaproveitada nas próximas execuções.

Em seguida, abra:

- Overlay para OBS: <http://127.0.0.1:8088/?theme=transparent>
- Janela autônoma: <http://127.0.0.1:8088/?theme=window>
- Painel de controle: <http://127.0.0.1:8088/control>

### Painel de controle

- `+1` / `−1` / placar livre por jogador.
- Trocar vez (manual swap).
- Desfazer última ação.
- Pausar/retomar a aplicação automática de eventos da câmera.
- Resetar partida (mantém os nomes).
- Renomear jogadores ao vivo.
- Corrigir cor do último encaçapamento.
- Timeline com as últimas ações para contexto do operador.

### Modo overlay-only

Útil para testar a interface sem precisar de vídeo:

```bash
uv run sinuca-counter --video data/samples/jogo.mp4 --no-vision
```

### Calibração

- `<video>.calib.json` — matriz de homografia + cantos clicados.
- `<video>.palette.json` — paleta HSV de referência por cor (opcional; sem ela
  o sistema usa um perfil padrão).
- `<video>.replay.jsonl` — log append-only com todos os eventos para debugar
  regras sem reprocessar vídeo.

## Modalidades

MVP suporta **sinuca brasileira** (`--rules brasileira`). Pontuação padrão:

| Cor | Pontos |
| --- | ------ |
| Amarela | 1 |
| Vermelha | 2 |
| Verde | 3 |
| Marrom | 4 |
| Azul | 5 |
| Rosa | 6 |
| Preta (bolão) | 7 |

A flag `--bolao-penalty` ativa a variação em que encaçapar o bolão antes das
demais cores entrega a pontuação ao adversário.

Snooker e English pool entram na Fase 2 sem mudanças nas demais camadas (basta
implementar `RuleSet`).

## Roadmap

- **Fase 1b** — substituir `HsvBallDetector` por um `YoloBallDetector` (mesma
  interface). Os extras `[yolo]` instalam `ultralytics` e `supervision`.
- **Fase 2** — `WebcamSource`, `ScreenCaptureSource`, `SnookerRules`,
  `EnglishPoolRules`.
- **Fase 3** — recalibração automática para vídeos com cortes.
- **Fase 4** — `BroadcastOcrPipeline` lendo o placar da emissora.

## Testes

```bash
uv run pytest
```

A camada do motor de regras é totalmente coberta. Camadas de visão são
testadas com fixtures sintéticas pequenas; testes de protocol ("ghost tests")
garantem que consumidores não acoplam em implementações concretas.

## Licença

MIT.
