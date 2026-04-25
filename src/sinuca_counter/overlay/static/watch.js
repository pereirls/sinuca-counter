// Connects to /ws and renders the ScoreState as an overlay sitting on top of
// the MJPEG video stream. Same wire format as /overlay, with optional
// snooker-style "next target" badge.
(function () {
  const BALL_LABELS = {
    red: "vermelha",
    vermelha: "vermelha",
    amarela: "amarela",
    verde: "verde",
    marrom: "marrom",
    azul: "azul",
    rosa: "rosa",
    preta_bola_7: "preta",
    colour: "qualquer colorida",
  };

  const els = {
    p1Name: document.querySelector("#player-p1 .name"),
    p2Name: document.querySelector("#player-p2 .name"),
    p1Score: document.querySelector("#player-p1 .score"),
    p2Score: document.querySelector("#player-p2 .score"),
    p1: document.querySelector("#player-p1"),
    p2: document.querySelector("#player-p2"),
    status: document.querySelector("#status"),
    target: document.querySelector("#target"),
    video: document.querySelector("#video"),
  };

  function renderTarget(state) {
    if (!state.target_ball) {
      els.target.classList.remove("visible");
      els.target.textContent = "";
      return;
    }
    const label = BALL_LABELS[state.target_ball] || state.target_ball;
    els.target.textContent = "próxima: " + label;
    els.target.classList.add("visible");
  }

  function render(state) {
    els.p1Name.textContent = state.p1_name;
    els.p2Name.textContent = state.p2_name;
    els.p1Score.textContent = String(state.p1_score);
    els.p2Score.textContent = String(state.p2_score);
    els.p1.classList.toggle("active", state.current_player === "p1");
    els.p2.classList.toggle("active", state.current_player === "p2");
    renderTarget(state);
    let status = "";
    let level = "ok";
    if (state.paused) {
      status = "pausado";
      level = "warn";
    } else if (state.detection_status && state.detection_status !== "ok") {
      status = state.detection_status;
      level = "warn";
    }
    els.status.textContent = status;
    els.status.className = "status" + (level !== "ok" ? " " + level : "");
  }

  function connect() {
    const ws = new WebSocket(
      (location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws"
    );
    ws.onmessage = (event) => {
      try {
        render(JSON.parse(event.data));
      } catch (err) {
        console.error("bad ws payload", err);
      }
    };
    ws.onclose = () => setTimeout(connect, 1000);
    ws.onerror = () => ws.close();
  }

  // If the MJPEG connection dies (vision worker stopped), retry fetching it.
  els.video.addEventListener("error", () => {
    setTimeout(() => {
      els.video.src = "/stream.mjpg?t=" + Date.now();
    }, 1500);
  });

  connect();
})();
