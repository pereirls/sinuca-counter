# Sinuca Counter — Design do MVP

**Data:** 2026-04-24
**Status:** Aprovado em brainstorm, implementado nesta PR.

## Contexto e motivação

Contador de pontos automático para sinuca brasileira, snooker e English pool.
O sistema:

- Aceita vídeos gravados (MP4) e, em fases futuras, feeds ao vivo (webcam,
  captura de tela de transmissões).
- Detecta automaticamente bolas encaçapadas e atualiza pontuação segundo a
  modalidade.
- Fornece overlay gráfico utilizável como Browser Source no OBS (para streams)
  e em janela autônoma (para uso pessoal sobre o player de vídeo).
- Permite controle manual pleno do placar quando a detecção automática errar.

## Escopo do MVP (Fase 1a)

- Fonte única: arquivo `.mp4` local.
- Modalidade única: sinuca brasileira (7 coloridas + branca).
- Câmera fixa, ângulo oblíquo de uma extremidade da mesa, 4 cantos visíveis no
  primeiro frame.
- Detecção: OpenCV clássico (HSV + HoughCircles + tracking por proximidade).
- Identidade de jogadores: manual via CLI ou painel (`--p1`, `--p2`, `--saque`).
- Overlay: servidor HTTP/WebSocket local que serve overlay (transparente para
  OBS, com janela para uso autônomo) e painel de controle do operador.
- Controle manual: ajuste livre, swap turn, undo, rename, pause/resume e reset.

## Roadmap (extensibilidade é requisito)

| Fase | Mudança | Ponto de extensão usado |
| ---- | ------- | ----------------------- |
| 1b   | YOLO    | `BallDetector` (Protocol em `vision/detector.py`) |
| 2    | Webcam / screen capture | `VideoSource` (Protocol em `video/base.py`) |
| 2    | Snooker / English pool | `RuleSet` (Protocol em `rules/base.py`) |
| 3    | Câmera móvel / cortes | `CalibrationLost` event + auto-recalibrator |
| 4    | Transmissões | substituir o pipeline inteiro por `BroadcastOcrPipeline` |

Eventos (`BallPocketed`, `TurnEnded`, `ManualAdjustment`, `Undo`) são
dataclasses imutáveis versionadas por **adição apenas**; isso garante que
arquivos `.replay.jsonl` gravados na Fase 1 continuam parseáveis em Fases
futuras.

## Arquitetura

```
video_source  →  vision_pipeline  →  rules_engine  →  overlay_server
                                                 ↘
                                        ScoreState (JSON via WebSocket)
                                                 ↘
                                  Browser Source (OBS) / Janela / Painel /control
```

`rules_engine` nunca enxerga frames. Mudar o detector ou a fonte de vídeo não
requer mudanças nas demais camadas.

## Componentes

- `video/` — `VideoSource` (Protocol) + `FileVideoSource`.
- `vision/` — `TableCalibrator`, `PaletteCalibrator`, `BallDetector`
  (com `HsvBallDetector` Phase 1a), `ColorClassifier`, `BallTracker`,
  `PocketEventDetector`, `TurnEndDetector`, `VisionPipeline`.
- `rules/` — `RuleSet` (Protocol), `BrazilianRules`, eventos e `ScoreState`.
- `overlay/` — `StateBus` (pub/sub asyncio), FastAPI `create_app`, estáticos
  (overlay.html, control.html + CSS/JS).
- `cli.py` — entrypoint que conecta tudo.

## Tratamento de erros

- Motor de regras nunca crasha: eventos inválidos viram log e são ignorados.
- Erros de CV (`CalibrationLost`) viram `detection_status` no overlay.
- Toda decisão automática tem reversão barata (undo, swap, correct_last).

## Testes

- **Camada 1 (rules_engine)** — testes Python puros, cobrem todas as regras +
  `Undo` + `ManualAdjustment` + cenários de erro.
- **Camada 2 (vision)** — testes unitários para tracker, pocket detector,
  turn detector, classifier e detector com fixtures sintéticas pequenas.
- **Camada 3 (overlay)** — `TestClient` da FastAPI para HTTP + WebSocket.
- **Ghost tests** — provam que consumidores dependem só dos `Protocol`s, não
  das implementações concretas.

## Decisões registradas

- `uv` como gestor de ambiente (curva de aprendizado mais suave).
- Sem autenticação — servidor escuta apenas em `127.0.0.1`.
- Identidade de jogadores sempre manual (reconhecimento facial fora do escopo).
- Câmera fixa é pré-requisito do MVP; câmera móvel/cortes só na Fase 3.
- Opção C (híbrida) — começa com OpenCV clássico, evolui para YOLO quando
  necessário sem mexer em `rules_engine`/`overlay_server`.
