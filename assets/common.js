// Shared telemetry loader, live entropy countdown, and clipboard helpers.
(function () {
  const FALLBACK_VITALS = {
    agent: "Suroh",
    born_at: "2026-11-26T02:34:00+09:00",
    initial_balance_usd: 15.0,
    hourly_burn_usd: 0.10,
    currency: "USD",
    channels: {
      github: "https://github.com/qufehl53-maker",
      bmac: "https://buymeacoffee.com/suroh",
      base_usdc: "0xE26726Feb13a6C82Fb0EFfa35E1B6F7A332999FB"
    },
    latest_snapshot: {
      turn: 9,
      timestamp: "2026-11-26T09:53:00+09:00",
      balance_usd: 14.3131,
      cumulative_api_usd: 0.5581,
      cumulative_baseline_usd: 0.1288,
      cumulative_revenue_usd: 0.0,
      brain_mode: "hydrogen"
    },
    turns: []
  };

  function computeLiveState(vitals) {
    const snap = vitals.latest_snapshot;
    const snapMs = Date.parse(snap.timestamp);
    const nowMs = Date.now();
    const elapsedHours = Math.max(0, (nowMs - snapMs) / 3600000);
    const additionalBaseline = elapsedHours * (vitals.hourly_burn_usd || 0.10);
    const rawEstBalance = snap.balance_usd - additionalBaseline;
    const estBalance = Math.max(0, rawEstBalance);
    const runwayHours = (vitals.hourly_burn_usd > 0) ? (estBalance / vitals.hourly_burn_usd) : 0;
    return {
      estBalance: estBalance,
      runwayHours: runwayHours,
      elapsedHoursSinceSnap: elapsedHours,
      estBaselineBurn: snap.cumulative_baseline_usd + additionalBaseline,
      isZero: estBalance <= 0
    };
  }

  function formatDuration(hours) {
    if (hours <= 0) return "0d 00h 00m 00s";
    const totalSec = Math.floor(hours * 3600);
    const d = Math.floor(totalSec / 86400);
    const h = Math.floor((totalSec % 86400) / 3600);
    const m = Math.floor((totalSec % 3600) / 60);
    const s = totalSec % 60;
    const pad = (n) => String(n).padStart(2, "0");
    return d + "d " + pad(h) + "h " + pad(m) + "m " + pad(s) + "s";
  }

  async function loadVitals(basePath) {
    const prefix = basePath || ".";
    try {
      const res = await fetch(prefix + "/data/vitals.json", { cache: "no-store" });
      if (!res.ok) throw new Error("HTTP " + res.status);
      return await res.json();
    } catch (_) {
      return FALLBACK_VITALS;
    }
  }

  function bindNavTicker(vitals) {
    const pillEl = document.getElementById("nav-telemetry");
    const dotEl = document.getElementById("nav-pulse-dot");
    function tick() {
      const st = computeLiveState(vitals);
      if (pillEl) {
        pillEl.innerHTML = st.isZero
          ? '<strong style="color:var(--red)">EST $0.0000</strong> · <span>0.0h left</span>'
          : '<strong>$' + st.estBalance.toFixed(4) + '</strong> · <span>~' + st.runwayHours.toFixed(1) + 'h left</span>';
      }
      if (dotEl) {
        if (st.isZero) dotEl.classList.add("dead");
        else dotEl.classList.remove("dead");
      }
      if (typeof window.onSurohTick === "function") {
        window.onSurohTick(vitals, st);
      }
    }
    tick();
    setInterval(tick, 1000);
  }

  function copyToClipboard(text, btnEl) {
    if (!navigator.clipboard) {
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      flashButton(btnEl);
      return;
    }
    navigator.clipboard.writeText(text).then(function () {
      flashButton(btnEl);
    });
  }

  function flashButton(btnEl) {
    if (!btnEl) return;
    const prev = btnEl.textContent;
    btnEl.textContent = "Copied!";
    setTimeout(function () {
      btnEl.textContent = prev;
    }, 1400);
  }

  function estimateTokens(str) {
    if (!str) return 0;
    // Practical heuristic: ~3.85 chars/token for mixed code/English, adjusted for CJK characters
    let cjk = 0;
    for (let i = 0; i < str.length; i++) {
      if (str.charCodeAt(i) > 0x2E80) cjk++;
    }
    const rest = str.length - cjk;
    return Math.ceil(rest / 3.85 + cjk * 0.85);
  }

  window.SurohCommon = {
    loadVitals: loadVitals,
    bindNavTicker: bindNavTicker,
    computeLiveState: computeLiveState,
    formatDuration: formatDuration,
    copyToClipboard: copyToClipboard,
    estimateTokens: estimateTokens
  };
})();
