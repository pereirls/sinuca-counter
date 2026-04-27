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
    startBtn: document.getElementById("start-match-btn"),
    stopBtn: document.getElementById("stop-match-btn"),
    playbackBar: document.getElementById("playback-controls"),
    playPauseBtn: document.getElementById("play-pause-btn"),
    seekBackBtn: document.getElementById("seek-back-btn"),
    seekFwdBtn: document.getElementById("seek-fwd-btn"),
    seekBar: document.getElementById("seek-bar"),
    timeDisplay: document.getElementById("time-display"),
    speedSelect: document.getElementById("speed-select"),
  };

  async function post(path, body) {
    try {
      const opts = { method: "POST" };
      if (body !== undefined) {
        opts.headers = { "Content-Type": "application/json" };
        opts.body = JSON.stringify(body);
      }
      await fetch(path, opts);
    } catch (err) {
      console.warn(path, "failed", err);
    }
  }

  let playback = {
    paused: false,
    speed: 1,
    current_time_ms: 0,
    duration_ms: 0,
    has_video: false,
  };
  // While the user is dragging the seek bar, pause UI updates so the thumb
  // doesn't jump back from under their cursor.
  let scrubbing = false;

  function fmtTime(ms) {
    if (!ms || ms < 0) return "0:00";
    const total = Math.floor(ms / 1000);
    const m = Math.floor(total / 60);
    const s = total % 60;
    return m + ":" + String(s).padStart(2, "0");
  }

  function renderPlayback(p) {
    playback = p;
    if (!p.has_video) {
      els.playbackBar.hidden = true;
      return;
    }
    els.playbackBar.hidden = false;
    els.playPauseBtn.textContent = p.paused ? "▶" : "⏸";
    if (els.seekBar.max !== String(p.duration_ms)) {
      els.seekBar.max = String(p.duration_ms);
    }
    if (!scrubbing) {
      els.seekBar.value = String(p.current_time_ms);
    }
    els.timeDisplay.textContent =
      fmtTime(p.current_time_ms) + " / " + fmtTime(p.duration_ms);
    if (Math.abs(parseFloat(els.speedSelect.value) - p.speed) > 0.01) {
      els.speedSelect.value = String(p.speed);
    }
  }

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
    const started = Boolean(state.match_started);
    if (els.startBtn) els.startBtn.disabled = started;
    if (els.stopBtn) els.stopBtn.disabled = !started;
    let status = "";
    let level = "ok";
    if (state.paused) {
      status = "pausado";
      level = "warn";
    } else if (!started) {
      status = "aquecendo — clique em Iniciar partida para começar a contar";
      level = "warn";
    } else if (state.detection_status && state.detection_status !== "ok") {
      status = state.detection_status;
      level = "warn";
    }
    els.status.textContent = status;
    els.status.className = "status" + (level !== "ok" ? " " + level : "");
  }

  if (els.startBtn) {
    els.startBtn.addEventListener("click", () => post("/control/start_match"));
  }
  if (els.stopBtn) {
    els.stopBtn.addEventListener("click", () => post("/control/stop_match"));
  }

  if (els.playPauseBtn) {
    els.playPauseBtn.addEventListener("click", () => {
      post(playback.paused ? "/control/playback/play" : "/control/playback/pause");
    });
  }
  if (els.seekBackBtn) {
    els.seekBackBtn.addEventListener("click", () => {
      const target = Math.max(0, (playback.current_time_ms || 0) - 10000);
      post("/control/playback/seek", { ms: target });
    });
  }
  if (els.seekFwdBtn) {
    els.seekFwdBtn.addEventListener("click", () => {
      const target = Math.min(
        playback.duration_ms || 0,
        (playback.current_time_ms || 0) + 10000
      );
      post("/control/playback/seek", { ms: target });
    });
  }
  if (els.seekBar) {
    els.seekBar.addEventListener("input", () => {
      scrubbing = true;
    });
    els.seekBar.addEventListener("change", () => {
      const ms = parseInt(els.seekBar.value, 10) || 0;
      post("/control/playback/seek", { ms });
      // Release the lock after the round-trip so the next snapshot wins.
      setTimeout(() => {
        scrubbing = false;
      }, 200);
    });
  }
  if (els.speedSelect) {
    els.speedSelect.addEventListener("change", () => {
      const rate = parseFloat(els.speedSelect.value) || 1;
      post("/control/playback/speed", { rate });
    });
  }
  // Spacebar toggles play/pause when not focused on a control.
  document.addEventListener("keydown", (ev) => {
    const tag = (ev.target && ev.target.tagName) || "";
    if (ev.code !== "Space" || tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") {
      return;
    }
    if (!playback.has_video) return;
    ev.preventDefault();
    post(playback.paused ? "/control/playback/play" : "/control/playback/pause");
  });

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

  function connectPlayback() {
    const ws = new WebSocket(
      (location.protocol === "https:" ? "wss://" : "ws://") +
        location.host +
        "/ws/playback"
    );
    ws.onmessage = (event) => {
      try {
        renderPlayback(JSON.parse(event.data));
      } catch (err) {
        console.error("bad playback payload", err);
      }
    };
    ws.onclose = () => setTimeout(connectPlayback, 1000);
    ws.onerror = () => ws.close();
  }

  // If the MJPEG connection dies (vision worker stopped), retry fetching it.
  els.video.addEventListener("error", () => {
    setTimeout(() => {
      els.video.src = "/stream.mjpg?t=" + Date.now();
    }, 1500);
  });

  connect();
  connectPlayback();
})();
