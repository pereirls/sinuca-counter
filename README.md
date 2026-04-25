# Sinuca Counter

Contador automático de pontos para sinuca brasileira e snooker (6 e 15 reds).
O sistema processa um arquivo de vídeo `.mp4`, exibe o placar como overlay e,
agora, renderiza o próprio vídeo numa página web com o placar sobreposto, para
que o operador possa acompanhar tudo na mesma janela.

> Status: **Fase 1b** — detecção padrão via YOLO (Ultralytics, classe "sports
> ball" pré-treinada na COCO). A camada clássica de OpenCV (HSV/HoughCircles)
> ainda está disponível como fallback (`--detector hsv`) e é usada
> automaticamente quando o extra `[yolo]` não está instalado.

## Visão geral

```
┌─────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  video_source   │ --> │  vision_pipeline │ --> │   rules_engine   │
│  (arquivo .mp4) │     │  YOLO + tracker  │     │ (estado partida) │
└─────────────────┘     └──────────────────┘     └─────────┬────────┘
                                                  ScoreState (JSON)
                                                           ▼
                                              ┌────────────────────────┐
                                              │  overlay_server        │
                                              │  FastAPI + WS + MJPEG  │
                                              └────┬────────┬──────────┘
                                                   ▼        ▼
                                       /watch (vídeo+placar)  /control
```

## Requisitos

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) — gerenciador de ambiente recomendado.
- `ffmpeg` instalado no sistema (necessário para o OpenCV ler vídeos).

## Setup

```bash
# Sem YOLO (fallback clássico, leve):
uv sync

# Com YOLO (~200 MB de dependências por causa do torch CPU):
uv sync --extra yolo
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

Não é necessário clicar nos cantos da mesa — o detector trabalha na resolução
nativa do frame. A pontuação é calculada por **rack-delta**: o pipeline faz um
snapshot das bolas antes e depois de cada tacada (via detecção de movimento
agregado) e qualquer bola que "sumiu" no intervalo é considerada encaçapada.
Isso torna o sistema imune a oclusões temporárias (taco, braço, jogador).

Em seguida, abra:

- **Vídeo + placar na mesma janela:** <http://127.0.0.1:8088/watch>
- Overlay para OBS: <http://127.0.0.1:8088/?theme=transparent>
- Janela autônoma de placar: <http://127.0.0.1:8088/?theme=window>
- Painel de controle: <http://127.0.0.1:8088/control>

### Flags principais

- `--rules {brasileira,snooker-6,snooker-15}` — modalidade.
- `--detector {yolo,hsv}` — backend de detecção. Default: `yolo`.
- `--yolo-weights` — caminho/nome do modelo YOLO (default: `yolov8n.pt`).
- `--no-vision` — sobe apenas o servidor de overlay/controle.
- `--stream-every-n-frames` — reduz FPS do MJPEG para economizar CPU.

### Painel de controle

- `+1` / `−1` / placar livre por jogador.
- Trocar vez (manual swap).
- Desfazer última ação.
- Pausar/retomar a aplicação automática de eventos da câmera.
- Resetar partida (mantém os nomes).
- Renomear jogadores ao vivo.
- Timeline com as últimas ações para contexto do operador.

## Modalidades

### Sinuca brasileira (`--rules brasileira`)

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

### Snooker (`--rules snooker-6` / `--rules snooker-15`)

Pontuação clássica: vermelha=1, amarela=2, verde=3, marrom=4, azul=5, rosa=6,
preta=7. O motor gerencia as duas fases:

- **Fase das vermelhas** — o jogador deve alternar vermelha → colorida →
  vermelha… As coloridas são "recolocadas" a cada encaçapamento.
- **Fase final** — quando todas as vermelhas saem da mesa, as coloridas
  devem ser encaçapadas em ordem crescente de valor (amarela → verde →
  marrom → azul → rosa → preta) e ficam fora da mesa.

A página `/watch` e os overlays exibem a "próxima bola esperada" quando a
modalidade é snooker.

## Roadmap

- **Fase 2** — `WebcamSource`, `ScreenCaptureSource`, fine-tune YOLO com
  dataset próprio, English pool.
- **Fase 3** — recalibração automática para vídeos com cortes/zoom.
- **Fase 4** — `BroadcastOcrPipeline` lendo o placar da emissora.

## Testes

```bash
uv run pytest
```

O motor de regras tem cobertura alta (regras brasileira e snooker). A nova
camada de visão inclui testes unitários para o `ShotPhaseDetector` (state
machine + diff de snapshots) e para o `FrameBroker` (publicação thread-safe).
Testes de protocol ("ghost tests") garantem que consumidores não acoplam em
implementações concretas.

## Licença

MIT.
