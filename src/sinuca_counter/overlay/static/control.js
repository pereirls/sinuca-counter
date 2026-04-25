// Control panel — one-page operator UI.
(function () {
  const els = {
    p1Card: document.getElementById("card-p1"),
    p2Card: document.getElementById("card-p2"),
    p1Name: document.querySelector("#card-p1 .name"),
    p2Name: document.querySelector("#card-p2 .name"),
    p1Score: document.getElementById("score-p1"),
    p2Score: document.getElementById("score-p2"),
    setP1: document.getElementById("set-p1"),
    setP2: document.getElementById("set-p2"),
    setScoreBtn: document.getElementById("set-score-btn"),
    swap: document.getElementById("swap-turn-btn"),
    undo: document.getElementById("undo-btn"),
    pause: document.getElementById("pause-btn"),
    resume: document.getElementById("resume-btn"),
    reset: document.getElementById("reset-btn"),
    renameP1: document.getElementById("rename-p1"),
    renameP2: document.getElementById("rename-p2"),
    renameBtn: document.getElementById("rename-btn"),
    correctColor: document.getElementById("correct-color"),
    correctBtn: document.getElementById("correct-btn"),
    timeline: document.getElementById("timeline"),
    rules: document.getElementById("rules"),
    startMatch: document.getElementById("start-match-btn"),
    stopMatch: document.getElementById("stop-match-btn"),
    matchBadge: document.getElementById("match-badge"),
  };

  async function post(path, body) {
    const opts = { method: "POST", headers: { "Content-Type": "application/json" } };
    if (body !== undefined) opts.body = JSON.stringify(body);
    const res = await fetch(path, opts);
    if (!res.ok) {
      console.warn(path, "failed", res.status);
    }
    return res.ok ? res.json() : null;
  }

  function render(state) {
    els.p1Name.textContent = state.p1_name;
    els.p2Name.textContent = state.p2_name;
    els.p1Score.textContent = String(state.p1_score);
    els.p2Score.textContent = String(state.p2_score);
    els.setP1.value = state.p1_score;
    els.setP2.value = state.p2_score;
    els.p1Card.classList.toggle("active", state.current_player === "p1");
    els.p2Card.classList.toggle("active", state.current_player === "p2");
    els.rules.textContent = state.rules_name
      ? "modalidade: " + state.rules_name
      : "";
    els.timeline.innerHTML = "";
    (state.timeline || []).slice().reverse().forEach((entry) => {
      const li = document.createElement("li");
      const t = entry.t_ms ? new Date(entry.t_ms).toISOString().slice(11, 19) : "";
      li.textContent = (t ? t + " " : "") + entry.description;
      els.timeline.appendChild(li);
    });
    if (document.activeElement !== els.renameP1) els.renameP1.value = state.p1_name;
    if (document.activeElement !== els.renameP2) els.renameP2.value = state.p2_name;

    const started = Boolean(state.match_started);
    if (els.matchBadge) {
      els.matchBadge.textContent = started
        ? "partida em andamento — detecção ativa"
        : "partida não iniciada — aquecimento";
      els.matchBadge.classList.toggle("live", started);
    }
    if (els.startMatch) els.startMatch.disabled = started;
    if (els.stopMatch) els.stopMatch.disabled = !started;
  }

  document.querySelectorAll("button[data-player]").forEach((btn) => {
    btn.addEventListener("click", () => {
      post("/control/adjust", {
        player: btn.dataset.player,
        delta: parseInt(btn.dataset.delta, 10),
      });
    });
  });

  els.setScoreBtn.addEventListener("click", () => {
    post("/control/set_score", {
      p1: parseInt(els.setP1.value, 10) || 0,
      p2: parseInt(els.setP2.value, 10) || 0,
    });
  });
  els.swap.addEventListener("click", () => post("/control/swap_turn"));
  els.undo.addEventListener("click", () => post("/control/undo"));
  els.pause.addEventListener("click", () => post("/control/pause"));
  els.resume.addEventListener("click", () => post("/control/resume"));
  els.reset.addEventListener("click", () => {
    if (confirm("Resetar a partida?")) post("/control/reset");
  });
  els.renameBtn.addEventListener("click", () => {
    post("/control/rename", { p1: els.renameP1.value, p2: els.renameP2.value });
  });
  els.correctBtn.addEventListener("click", () => {
    post("/control/correct_last", { color: els.correctColor.value });
  });
  if (els.startMatch) {
    els.startMatch.addEventListener("click", () => post("/control/start_match"));
  }
  if (els.stopMatch) {
    els.stopMatch.addEventListener("click", () => post("/control/stop_match"));
  }

  function connect() {
    const ws = new WebSocket(
      (location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws"
    );
    ws.onmessage = (event) => {
      try {
        render(JSON.parse(event.data));
      } catch (err) {
        console.error("bad payload", err);
      }
    };
    ws.onclose = () => setTimeout(connect, 1000);
    ws.onerror = () => ws.close();
  }
  connect();
})();
