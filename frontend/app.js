const h = React.createElement;
const { useEffect, useMemo, useState } = React;

const RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"];
const ACTION_CLASS = {
  HIT: "action-hit",
  STAND: "action-stand",
  DOUBLE: "action-double",
  SPLIT: "action-split",
  SURRENDER: "action-surrender",
  INSURANCE: "action-insurance",
};

async function api(path, body) {
  const options = body === undefined
    ? {}
    : {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      };
  const response = await fetch(path, options);
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Request failed");
  }
  return payload;
}

function formatNumber(value, digits = 2) {
  return Number(value || 0).toFixed(digits);
}

function formatUnits(value) {
  const number = Number(value || 0);
  return Number.isInteger(number) ? String(number) : number.toFixed(1);
}

function rankValue(rank) {
  if (rank === "A") return 11;
  if (["10", "J", "Q", "K"].includes(rank)) return 10;
  return Number(rank);
}

function isPair(cards) {
  return cards.length === 2 && rankValue(cards[0]) === rankValue(cards[1]);
}

function handStats(cards) {
  let total = cards.reduce((sum, rank) => sum + rankValue(rank), 0);
  let aces = cards.filter((rank) => rank === "A").length;
  while (total > 21 && aces > 0) {
    total -= 10;
    aces -= 1;
  }
  return {
    total,
    isSoft: aces > 0 && total <= 21,
    isBust: total > 21,
    isBlackjack: cards.length === 2 && total === 21,
  };
}

function handTotalLabel(stats) {
  if (stats.isBlackjack) return "Blackjack";
  if (stats.isBust) return `Bust ${stats.total}`;
  return `${stats.isSoft ? "Soft" : "Hard"} ${stats.total}`;
}

function upcardTotalLabel(rank) {
  if (!rank) return "--";
  if (rank === "A") return "11 / 1";
  return String(rankValue(rank));
}

function normalizeBetUnits(value) {
  const parsed = Number.parseInt(String(value).trim(), 10);
  if (!Number.isFinite(parsed)) return 1;
  return Math.max(1, Math.min(20, parsed));
}

function parseBetUnits(value) {
  const raw = String(value).trim();
  if (!/^\d+$/.test(raw)) {
    return { valid: false, value: null, error: "Bet must be a whole number from 1 to 20 units." };
  }
  const parsed = Number.parseInt(raw, 10);
  if (parsed < 1 || parsed > 20) {
    return { valid: false, value: parsed, error: "Bet must be between 1 and 20 units." };
  }
  return { valid: true, value: parsed, error: "" };
}

function parseStartingUnits(value) {
  const raw = String(value).trim();
  if (!/^\d+$/.test(raw)) {
    return { valid: false, value: null, error: "Starting units must be a whole number." };
  }
  const parsed = Number.parseInt(raw, 10);
  if (parsed < 1 || parsed > 10000) {
    return { valid: false, value: parsed, error: "Starting units must be between 1 and 10000." };
  }
  return { valid: true, value: parsed, error: "" };
}

function parseBulkHands(value) {
  const raw = String(value).trim();
  if (!/^\d+$/.test(raw)) {
    return { valid: false, value: null, error: "Hands must be a whole number." };
  }
  const parsed = Number.parseInt(raw, 10);
  if (parsed < 1 || parsed > 1000000) {
    return { valid: false, value: parsed, error: "Hands must be between 1 and 1,000,000." };
  }
  return { valid: true, value: parsed, error: "" };
}

function parseUnitValue(value) {
  const raw = String(value).trim();
  if (!/^\d+(\.\d+)?$/.test(raw)) {
    return { valid: false, value: null, error: "Unit value must be a positive number." };
  }
  const parsed = Number.parseFloat(raw);
  if (parsed <= 0 || parsed > 1000000) {
    return { valid: false, value: parsed, error: "Unit value must be between 0 and 1,000,000." };
  }
  return { valid: true, value: parsed, error: "" };
}

function formatMoney(value) {
  const number = Number(value || 0);
  return number.toLocaleString(undefined, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: Number.isInteger(number) ? 0 : 2,
  });
}

function formatLargeNumber(value) {
  return Number(value || 0).toLocaleString();
}

function App() {
  const [page, setPage] = useState("home");

  if (page === "bulk") {
    return h(BulkPage, { navigate: setPage });
  }
  if (page === "solver") {
    return h(SolverPage, { navigate: setPage });
  }
  if (page === "simulation") {
    return h(SimulationPage, { navigate: setPage });
  }
  return h(HomePage, { navigate: setPage });
}

function HomePage({ navigate }) {
  return h("main", { className: "home-screen" },
    h("div", { className: "home-brand" },
      h("div", { className: "mark large-mark" }, "BJ"),
      h("div", null,
        h("h1", null, "Blackjack Advisor"),
        h("p", null, "Choose a practice mode")
      )
    ),
    h("section", { className: "mode-grid" },
      h("button", { className: "mode-card", onClick: () => navigate("simulation") },
        h("span", { className: "mode-kicker" }, "Game Mode"),
        h("strong", null, "Simulation"),
        h("span", null, "Play through a shuffled shoe with live count, stats, and recommendations.")
      ),
      h("button", { className: "mode-card", onClick: () => navigate("solver") },
        h("span", { className: "mode-kicker" }, "Manual Mode"),
        h("strong", null, "Solver"),
        h("span", null, "Enter cards yourself, update the count, and query the strategy engine.")
      ),
      h("button", { className: "mode-card", onClick: () => navigate("bulk") },
        h("span", { className: "mode-kicker" }, "Backtest Mode"),
        h("strong", null, "Bulk Run"),
        h("span", null, "Auto-play a large sample with the recommended strategy and count-based bet sizing.")
      )
    )
  );
}

function SolverPage({ navigate }) {
  const [settings, setSettings] = useState({ num_decks: 6, das: true, s17: true, surrender: true });
  const [state, setState] = useState(null);
  const [dealer, setDealer] = useState("");
  const [player, setPlayer] = useState([]);
  const [extraCards, setExtraCards] = useState([]);
  const [roundCounted, setRoundCounted] = useState(false);
  const [countedPlayerCount, setCountedPlayerCount] = useState(0);
  const [roundBetting, setRoundBetting] = useState(null);
  const [result, setResult] = useState(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api("/api/state")
      .then(setState)
      .catch((error) => setMessage(error.message));
  }, []);

  const canRecommend = dealer && player.length >= 2;
  const canDouble = player.length === 2;
  const canSplit = isPair(player);
  const playerStats = useMemo(() => handStats(player), [player]);
  const pendingHitCards = roundCounted ? player.slice(countedPlayerCount) : [];

  const handLabel = useMemo(() => {
    if (!result) return player.length ? handTotalLabel(playerStats) : "No hand";
    const mode = result.hand.is_soft ? "Soft" : "Hard";
    if (result.hand.is_blackjack) return "Blackjack";
    if (result.hand.is_bust) return "Bust";
    return `${mode} ${result.hand.total}`;
  }, [player.length, playerStats, result]);

  function setRule(key, value) {
    setSettings((current) => ({ ...current, [key]: value }));
  }

  function chooseDealer(rank) {
    if (roundCounted) {
      setMessage("Dealer upcard has already been counted. Start a new round to change it.");
      return;
    }
    setDealer(rank);
    setResult(null);
  }

  async function runAction(work) {
    setBusy(true);
    setMessage("");
    try {
      await work();
    } catch (error) {
      setMessage(error.message);
    } finally {
      setBusy(false);
    }
  }

  function clearRound() {
    setDealer("");
    setPlayer([]);
    setExtraCards([]);
    setResult(null);
    setRoundBetting(null);
    setRoundCounted(false);
    setCountedPlayerCount(0);
    setMessage("");
  }

  async function startShoe() {
    await runAction(async () => {
      const nextState = await api("/api/start", settings);
      setState(nextState);
      clearRound();
    });
  }

  async function recommendOnly() {
    if (!canRecommend) return;
    await runAction(async () => {
      const payload = await api("/api/recommend", {
        dealer,
        player,
        can_double: canDouble,
        can_split: canSplit,
      });
      setResult(payload);
      setRoundBetting(null);
      setState(payload.state);
    });
  }

  async function countVisibleAndRecommend() {
    if (!canRecommend || roundCounted) return;
    await runAction(async () => {
      const payload = await api("/api/count-recommend", {
        dealer,
        player,
        can_double: canDouble,
        can_split: canSplit,
      });
      setResult(payload);
      setRoundBetting(payload.pre_round_betting);
      setState(payload.state);
      setRoundCounted(true);
      setCountedPlayerCount(player.length);
    });
  }

  async function recordPendingHitCards() {
    if (pendingHitCards.length === 0 || !dealer) return;
    await runAction(async () => {
      const nextState = await api("/api/observe", { cards: pendingHitCards });
      setState(nextState);
      setCountedPlayerCount(player.length);

      const payload = await api("/api/recommend", {
        dealer,
        player,
        can_double: false,
        can_split: false,
      });
      setResult(payload);
      setState(payload.state);
    });
  }

  async function recordExtraCards() {
    if (extraCards.length === 0) return;
    await runAction(async () => {
      const nextState = await api("/api/observe", { cards: extraCards });
      setState(nextState);
      setExtraCards([]);
    });
  }

  async function startNewSolverRound() {
    await runAction(async () => {
      const cardsToCommit = [...pendingHitCards, ...extraCards];
      if (cardsToCommit.length > 0) {
        const nextState = await api("/api/observe", { cards: cardsToCommit });
        setState(nextState);
      }
      clearRound();
    });
  }

  async function addPlayer(rank) {
    if (!roundCounted) {
      setPlayer((cards) => [...cards, rank]);
      setResult(null);
      return;
    }
    setPlayer((cards) => [...cards, rank]);
    setResult(null);
    setMessage("Hit card staged. Record pending cards when you are ready to update the count.");
  }

  function removePlayer(index) {
    if (roundCounted && index < countedPlayerCount) {
      setMessage("Counted player cards cannot be removed. Start a new round to edit the initial hand.");
      return;
    }
    setPlayer((cards) => cards.filter((_, cardIndex) => cardIndex !== index));
    setResult(null);
  }

  return h("div", { className: "app-shell" },
    h("aside", { className: "sidebar" },
      h(BrandBlock, { subtitle: "Solver", navigate }),
      h(SettingsPanel, { settings, setRule, actionLabel: "Start Shoe", onAction: startShoe, busy }),
      h(CountPanel, { state }),
      h(BetPanel, { betting: state && state.betting, roundBetting, mode: "solver" }),
      h(ObservedPanel, { cards: state && state.observed_cards })
    ),
    h("main", { className: "workspace" },
      h(PageNav, { active: "solver", navigate }),
      message && h("div", { className: "message" }, message),
      h("section", { className: "table" },
        h("div", { className: "dealer-zone" },
          h("div", { className: "zone-label" }, "Dealer"),
          h(CardSlot, {
            label: dealer || "Upcard",
            filled: Boolean(dealer),
            onRemove: roundCounted ? undefined : () => setDealer(""),
          }),
          h(TotalBadge, { label: "Upcard Value", value: dealer ? upcardTotalLabel(dealer) : "--" })
        ),
        h(RecommendationPanel, {
          recommendation: result && result.recommendation,
          handLabel,
          reasoning: result ? result.recommendation.reasoning : "No recommendation",
        }),
        h("div", { className: "player-zone" },
          h("div", { className: "zone-label" }, "Player"),
          h("div", { className: "hand-row" },
            player.length
              ? player.map((rank, index) => h(CardSlot, {
                  key: `${rank}-${index}`,
                  label: rank,
                  filled: true,
                  onRemove: () => removePlayer(index),
                }))
              : h(CardSlot, { label: "Empty", filled: false })
          ),
          h(TotalBadge, { label: "Player Total", value: player.length ? handTotalLabel(playerStats) : "--" })
        )
      ),
      h("section", { className: "actions-grid" },
        h("div", { className: "panel" },
          h("div", { className: "panel-title" }, "Dealer Upcard"),
          h(RankPad, { selected: dealer ? [dealer] : [], onPick: chooseDealer })
        ),
        h("div", { className: "panel" },
          h("div", { className: "panel-title" }, roundCounted ? "Hit Card" : "Player Hand"),
          h(RankPad, { selected: player, onPick: addPlayer })
        ),
        h("div", { className: "panel control-stack" },
          h("div", { className: "panel-title" }, "Round"),
          h("div", { className: "round-status" },
            h("span", null, `Double ${canDouble ? "available" : "locked"}`),
            h("span", null, `Split ${canSplit ? "available" : "locked"}`),
            h("span", null, roundCounted ? `${pendingHitCards.length} pending hit card(s)` : "Visible cards pending")
          ),
          h("button", {
            className: "primary",
            onClick: countVisibleAndRecommend,
            disabled: busy || !canRecommend || roundCounted,
          }, "Count + Recommend"),
          h("button", {
            className: "secondary",
            onClick: recordPendingHitCards,
            disabled: busy || pendingHitCards.length === 0,
          }, "Record Pending + Recommend"),
          h("button", {
            className: "secondary",
            onClick: recommendOnly,
            disabled: busy || !canRecommend,
          }, "Recommend Only"),
          h("button", { className: "secondary", onClick: startNewSolverRound, disabled: busy }, "New Round")
        ),
        h("div", { className: "panel" },
          h("div", { className: "panel-title" }, "Extra Cards"),
          h(RankPad, { selected: extraCards, onPick: (rank) => setExtraCards((cards) => [...cards, rank]) }),
          h("div", { className: "chip-row" },
            extraCards.map((rank, index) => h("button", {
              className: "chip",
              key: `${rank}-${index}`,
              onClick: () => setExtraCards((cards) => cards.filter((_, cardIndex) => cardIndex !== index)),
            }, rank))
          ),
          h("button", {
            className: "secondary full",
            onClick: recordExtraCards,
            disabled: busy || extraCards.length === 0,
          }, "Record Cards")
        )
      )
    )
  );
}

function SimulationPage({ navigate }) {
  const [settings, setSettings] = useState({ num_decks: 6, das: true, s17: true, surrender: true, starting_units: "100" });
  const [simState, setSimState] = useState(null);
  const [playerBet, setPlayerBet] = useState("1");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api("/api/sim/state")
      .then(setSimState)
      .catch((error) => setMessage(error.message));
  }, []);

  function setRule(key, value) {
    setSettings((current) => ({ ...current, [key]: value }));
  }

  async function runAction(work) {
    setBusy(true);
    setMessage("");
    try {
      await work();
    } catch (error) {
      setMessage(error.message);
    } finally {
      setBusy(false);
    }
  }

  async function startGame() {
    await runAction(async () => {
      const parsedStartingUnits = parseStartingUnits(settings.starting_units);
      if (!parsedStartingUnits.valid) {
        throw new Error(parsedStartingUnits.error);
      }
      const payload = await api("/api/sim/start", settings);
      setSimState(payload);
    });
  }

  async function dealRound() {
    await runAction(async () => {
      const parsedBet = parseBetUnits(playerBet);
      if (!parsedBet.valid) {
        throw new Error(parsedBet.error);
      }
      const betUnits = parsedBet.value;
      const payload = await api("/api/sim/new-round", { bet_units: betUnits });
      setSimState(payload);
    });
  }

  async function play(action) {
    await runAction(async () => {
      const payload = await api("/api/sim/action", { action });
      setSimState(payload);
    });
  }

  const activeHand = simState && simState.hands.find((hand) => hand.active);
  const handLabel = activeHand ? handSummary(activeHand) : "No active hand";
  const legalActions = simState ? simState.legal_actions : [];
  const phase = simState ? simState.phase : "idle";
  const decisionLog = simState && simState.decision_log ? simState.decision_log : [];
  const lastDecision = phase === "round_over" && decisionLog.length ? decisionLog[decisionLog.length - 1] : null;
  const revealedRecommendation = lastDecision ? lastDecision.recommendation : null;
  const selectedBet = parseBetUnits(playerBet);

  return h("div", { className: "app-shell sim-shell" },
    h("aside", { className: "sidebar" },
      h(BrandBlock, { subtitle: "Simulation", navigate }),
      h(SettingsPanel, { settings, setRule, actionLabel: "Start Game", onAction: startGame, busy, showStartingUnits: true }),
      h(SimulationBetPanel, { simState, playerBet, setPlayerBet, phase, busy })
    ),
    h("main", { className: "workspace" },
      h(PageNav, { active: "simulation", navigate }),
      message && h("div", { className: "message" }, message),
      simState && h("div", { className: "sim-message" }, simState.message),
      h("section", { className: "table sim-table" },
        h("div", { className: "dealer-zone" },
          h("div", { className: "zone-label" }, "Dealer"),
          h("div", { className: "hand-row" },
            simState && simState.dealer.cards.length
              ? simState.dealer.cards.map((card, index) => h(DisplayCard, { card, key: `${card.label}-${index}` }))
              : h(DisplayCard, { card: null })
          ),
          h("div", { className: "total-row" },
            h(TotalBadge, {
              label: "Upcard Value",
              value: simState && simState.dealer.cards[0] ? upcardTotalLabel(simState.dealer.cards[0].rank) : "--",
            }),
            h(TotalBadge, {
              label: "Dealer Total",
              value: simState && simState.dealer.revealed ? dealerTotalLabel(simState.dealer) : "Hidden",
            })
          )
        ),
        h(RecommendationPanel, {
          recommendation: revealedRecommendation,
          handLabel: revealedRecommendation ? `You chose ${lastDecision.chosen_action}` : handLabel,
          hidden: phase === "player",
          reasoning: phase === "player"
            ? "Recommendation hidden until the round is complete"
            : revealedRecommendation
              ? revealedRecommendation.reasoning
              : "Deal a round and make your own decisions"
        }),
        h("div", { className: "player-zone multi-hand-zone" },
          h("div", { className: "zone-label" }, "Player"),
          h(TotalBadge, { label: "Active Player Total", value: activeHand ? handSummary(activeHand) : "--" }),
          h("div", { className: "sim-hands" },
            simState && simState.hands.length
              ? simState.hands.map((hand) => h(SimHandView, { hand, key: hand.index }))
              : h("span", { className: "empty-hand" }, "No round dealt")
          )
        )
      ),
      h("section", { className: "sim-controls" },
        h("div", { className: "panel control-stack" },
          h("div", { className: "panel-title" }, "Game"),
          h("div", { className: "round-status" },
            h("span", null, selectedBet.valid
              ? `Selected bet ${selectedBet.value} unit${selectedBet.value === 1 ? "" : "s"}`
              : "Selected bet invalid"),
            h("span", null, simState && simState.betting && simState.betting.round
              ? `Recommended ${simState.betting.round.recommended_units} units`
              : simState && simState.betting && simState.betting.player_round_units
                ? `This round ${simState.betting.player_round_units} units`
              : "This round --")
          ),
          h("button", { className: "primary", onClick: dealRound, disabled: busy || phase === "player" }, "Deal Round"),
          h("button", { className: "secondary", onClick: startGame, disabled: busy }, "Reset Shoe")
        ),
        h("div", { className: "panel action-panel" },
          h("div", { className: "panel-title" }, "Player Action"),
          h("div", { className: "play-actions" },
            ["HIT", "STAND", "DOUBLE", "SPLIT", "SURRENDER"].map((action) => {
              return h("button", {
                key: action,
                className: "play-action",
                onClick: () => play(action),
                disabled: busy || !legalActions.includes(action),
              }, action);
            })
          )
        ),
        h("div", { className: "panel result-panel" },
          h("div", { className: "panel-title" }, "Round Results"),
          simState && simState.hands.length
            ? simState.hands.map((hand) => h("div", { className: "result-row", key: `result-${hand.index}` },
                h("span", null, `Hand ${hand.index + 1}`),
                h("strong", null, hand.result ? `${hand.result} (${formatUnits(hand.payout)})` : hand.status)
              ))
            : h("span", { className: "muted" }, "No results")
        ),
        h(DecisionReviewPanel, { decisions: decisionLog, phase })
      ),
      h(SimulationDashboard, { simState })
    )
  );
}

function SimulationDashboard({ simState }) {
  return h("section", { className: "sim-dashboard" },
    h("div", { className: "dashboard-main" },
      h(CountPanel, { state: simState, compact: true }),
      h(StatsPanel, { stats: simState && simState.stats, shoeCards: simState && simState.shoe_cards_remaining, compact: true })
    ),
    h(ObservedPanel, { cards: simState && simState.observed_cards, compact: true })
  );
}

function BulkPage({ navigate }) {
  const [settings, setSettings] = useState({
    num_decks: 6,
    das: true,
    s17: true,
    surrender: true,
    wonging: true,
    hands: "100000",
    unit_value: "1",
    seed: "",
  });
  const [result, setResult] = useState(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const parsedHands = parseBulkHands(settings.hands);
  const parsedUnitValue = parseUnitValue(settings.unit_value);

  function setRule(key, value) {
    setSettings((current) => ({ ...current, [key]: value }));
  }

  async function runBulk() {
    setBusy(true);
    setMessage("");
    try {
      if (!parsedHands.valid) throw new Error(parsedHands.error);
      if (!parsedUnitValue.valid) throw new Error(parsedUnitValue.error);
      const payload = await api("/api/bulk/run", {
        ...settings,
        hands: parsedHands.value,
        unit_value: parsedUnitValue.value,
      });
      setResult(payload);
    } catch (error) {
      setMessage(error.message);
    } finally {
      setBusy(false);
    }
  }

  return h("div", { className: "app-shell bulk-shell" },
    h("aside", { className: "sidebar" },
      h(BrandBlock, { subtitle: "Bulk Run", navigate }),
      h(BulkSettingsPanel, {
        settings,
        setRule,
        runBulk,
        busy,
        parsedHands,
        parsedUnitValue,
      })
    ),
    h("main", { className: "workspace" },
      h(PageNav, { active: "bulk", navigate }),
      message && h("div", { className: "message" }, message),
      h("section", { className: "bulk-hero" },
        h("div", null,
          h("span", { className: "mode-kicker" }, "Strategy Backtest"),
          h("h2", null, result ? formatMoney(result.net_money) : "Ready to simulate"),
          h("p", null, result
            ? `${formatLargeNumber(result.rounds)} rounds autoplayed with engine decisions`
            : "Run a large sample using the same recommendation engine and Hi-Lo bet ramp.")
        ),
        h("button", { className: "primary", onClick: runBulk, disabled: busy },
          busy ? "Running..." : "Run Simulation"
        )
      ),
      h(BulkResultDashboard, { result, unitValue: parsedUnitValue.valid ? parsedUnitValue.value : 1 })
    )
  );
}

function BulkSettingsPanel({ settings, setRule, runBulk, busy, parsedHands, parsedUnitValue }) {
  return h("section", { className: "panel" },
    h("div", { className: "panel-title" }, "Run Setup"),
    h("label", { className: "field" },
      h("span", null, "Hands"),
      h("input", {
        type: "text",
        inputMode: "numeric",
        value: settings.hands,
        onChange: (event) => setRule("hands", event.target.value),
      }),
      h("small", { className: parsedHands.valid ? "" : "field-error" },
        parsedHands.valid ? "Initial rounds to deal, up to 1,000,000." : parsedHands.error
      )
    ),
    h("label", { className: "field" },
      h("span", null, "Unit Value"),
      h("input", {
        type: "text",
        inputMode: "decimal",
        value: settings.unit_value,
        onChange: (event) => setRule("unit_value", event.target.value),
      }),
      h("small", { className: parsedUnitValue.valid ? "" : "field-error" },
        parsedUnitValue.valid ? "Dollar value for each betting unit." : parsedUnitValue.error
      )
    ),
    h("label", { className: "field" },
      h("span", null, "Decks"),
      h("input", {
        type: "number",
        min: "1",
        max: "8",
        value: settings.num_decks,
        onChange: (event) => setRule("num_decks", Number(event.target.value)),
      })
    ),
    h("label", { className: "field" },
      h("span", null, "Seed"),
      h("input", {
        type: "text",
        inputMode: "numeric",
        value: settings.seed,
        onChange: (event) => setRule("seed", event.target.value),
        placeholder: "Optional",
      }),
      h("small", null, "Use the same seed to reproduce a run.")
    ),
    h(Toggle, {
      label: "Double after split",
      checked: settings.das,
      onChange: (value) => setRule("das", value),
    }),
    h(Toggle, {
      label: "Dealer stands S17",
      checked: settings.s17,
      onChange: (value) => setRule("s17", value),
    }),
    h(Toggle, {
      label: "Late surrender",
      checked: settings.surrender,
      onChange: (value) => setRule("surrender", value),
    }),
    h(Toggle, {
      label: "Wonging / back-counting",
      checked: settings.wonging,
      onChange: (value) => setRule("wonging", value),
    }),
    h("button", { className: "primary full", onClick: runBulk, disabled: busy },
      busy ? "Running..." : "Run Simulation"
    )
  );
}

function BulkResultDashboard({ result, unitValue }) {
  if (!result) {
    return h("section", { className: "bulk-empty panel" },
      h("div", { className: "panel-title" }, "Results"),
      h("span", { className: "muted" }, "No bulk run yet.")
    );
  }

  const netClass = result.net_units >= 0 ? "bulk-net positive" : "bulk-net negative";
  return h("section", { className: "bulk-results" },
    h("div", { className: netClass },
      h("span", null, "Net Result"),
      h("strong", null, formatMoney(result.net_money)),
      h("em", null, `${formatUnits(result.net_units)} units at ${formatMoney(unitValue)} per unit`)
    ),
    h("div", { className: "panel stat-panel" },
      h("div", { className: "panel-title" }, "Volume"),
      h("div", { className: "stat-grid bulk-stat-grid" },
        h(Stat, { label: "Rounds", value: formatLargeNumber(result.rounds) }),
        h(Stat, { label: "Hands", value: formatLargeNumber(result.hands_played) }),
        h(Stat, { label: "Decisions", value: formatLargeNumber(result.decisions) }),
        h(Stat, { label: "Shoes", value: formatLargeNumber(result.shoes) })
      )
    ),
    h("div", { className: "panel stat-panel" },
      h("div", { className: "panel-title" }, "Outcomes"),
      h("div", { className: "stat-grid bulk-stat-grid" },
        h(Stat, { label: "Wins", value: formatLargeNumber(result.wins) }),
        h(Stat, { label: "Losses", value: formatLargeNumber(result.losses) }),
        h(Stat, { label: "Pushes", value: formatLargeNumber(result.pushes) }),
        h(Stat, { label: "Blackjacks", value: formatLargeNumber(result.blackjacks) }),
        h(Stat, { label: "Surrenders", value: formatLargeNumber(result.surrendered) }),
        h(Stat, { label: "Win Rate", value: `${formatNumber(result.win_rate * 100, 1)}%` })
      )
    ),
    h("div", { className: "panel stat-panel" },
      h("div", { className: "panel-title" }, "Money Trail"),
      h("div", { className: "stat-grid bulk-stat-grid" },
        h(Stat, { label: "Wagered", value: `${formatUnits(result.total_wagered_units)} units` }),
        h(Stat, { label: "High Water", value: `${formatUnits(result.max_bankroll_units)} units` }),
        h(Stat, { label: "Low Water", value: `${formatUnits(result.min_bankroll_units)} units` }),
        h(Stat, { label: "Unit", value: formatMoney(result.unit_value) })
      )
    )
  );
}

function DecisionReviewPanel({ decisions, phase }) {
  return h("div", { className: "panel review-panel" },
    h("div", { className: "panel-title" }, "Decision Review"),
    phase === "player"
      ? h("span", { className: "muted" }, "Recommendations are hidden until the round is over.")
      : decisions.length
        ? h("div", { className: "decision-list" },
            decisions.map((decision, index) => h("div", {
              className: decision.matched ? "decision-row matched" : "decision-row missed",
              key: `decision-${index}`,
            },
              h("div", { className: "decision-main" },
                h("strong", null, `Hand ${decision.hand_index + 1}: ${decision.chosen_action}`),
                h("span", null, `Engine: ${decision.recommendation ? decision.recommendation.action : "--"}`)
              ),
              h("div", { className: "decision-meta" },
                h("span", null, `Player ${decision.is_soft ? "soft" : "hard"} ${decision.player_total}`),
                h("span", null, `TC ${formatSigned(decision.true_count)}`),
                h("span", null, decision.matched ? "Matched" : "Different")
              )
            ))
          )
        : h("span", { className: "muted" }, "No player decisions to review this round.")
  );
}

function BrandBlock({ subtitle, navigate }) {
  return h("div", { className: "brand-row" },
    h("button", { className: "mark mark-button", onClick: () => navigate("home") }, "BJ"),
    h("div", null,
      h("h1", null, "Blackjack Advisor"),
      h("p", null, subtitle)
    )
  );
}

function PageNav({ active, navigate }) {
  return h("nav", { className: "page-nav" },
    h("button", { className: "nav-button", onClick: () => navigate("home") }, "Home"),
    h("button", {
      className: active === "simulation" ? "nav-button active" : "nav-button",
      onClick: () => navigate("simulation"),
    }, "Simulation"),
    h("button", {
      className: active === "solver" ? "nav-button active" : "nav-button",
      onClick: () => navigate("solver"),
    }, "Solver"),
    h("button", {
      className: active === "bulk" ? "nav-button active" : "nav-button",
      onClick: () => navigate("bulk"),
    }, "Bulk Run")
  );
}

function SettingsPanel({ settings, setRule, actionLabel, onAction, busy, showStartingUnits = false }) {
  const parsedStartingUnits = showStartingUnits ? parseStartingUnits(settings.starting_units) : null;
  return h("section", { className: "panel" },
    h("div", { className: "panel-title" }, "Shoe"),
    h("label", { className: "field" },
      h("span", null, "Decks"),
      h("input", {
        type: "number",
        min: "1",
        max: "8",
        value: settings.num_decks,
        onChange: (event) => setRule("num_decks", Number(event.target.value)),
      })
    ),
    showStartingUnits && h("label", { className: "field" },
      h("span", null, "Starting Units"),
      h("input", {
        type: "text",
        inputMode: "numeric",
        value: settings.starting_units,
        onChange: (event) => setRule("starting_units", event.target.value),
      }),
      h("small", { className: parsedStartingUnits.valid ? "" : "field-error" },
        parsedStartingUnits.valid ? "Bankroll for a new simulation." : parsedStartingUnits.error
      )
    ),
    h(Toggle, {
      label: "Double after split",
      checked: settings.das,
      onChange: (value) => setRule("das", value),
    }),
    h(Toggle, {
      label: "Dealer stands S17",
      checked: settings.s17,
      onChange: (value) => setRule("s17", value),
    }),
    h(Toggle, {
      label: "Late surrender",
      checked: settings.surrender,
      onChange: (value) => setRule("surrender", value),
    }),
    h("button", { className: "primary full", onClick: onAction, disabled: busy }, actionLabel)
  );
}

function RecommendationPanel({ recommendation, handLabel, reasoning, hidden = false }) {
  return h("div", { className: hidden ? "recommendation hidden-recommendation" : "recommendation" },
    h("div", { className: "rec-label" }, hidden ? "Practice Mode" : "Recommendation"),
    hidden
      ? h("div", { className: "rec-action empty" }, "Hidden")
      : recommendation
        ? h("div", { className: `rec-action ${ACTION_CLASS[recommendation.action] || ""}` }, recommendation.action)
        : h("div", { className: "rec-action empty" }, "--"),
    h("div", { className: "rec-meta" },
      h("span", null, handLabel),
      h("span", null, hidden ? "No hint" : recommendation ? `Code ${recommendation.raw_code}` : "Code --"),
      h("span", null, hidden ? "Review later" : recommendation && recommendation.is_deviation ? "Deviation" : "Basic")
    ),
    h("div", { className: "reasoning" }, reasoning)
  );
}

function CountPanel({ state, compact = false }) {
  const count = state && state.count;
  return h("section", { className: compact ? "panel stat-panel compact-panel" : "panel stat-panel" },
    h("div", { className: "panel-title" }, "Count"),
    h("div", { className: compact ? "stat-grid compact-stat-grid" : "stat-grid" },
      h(Stat, { label: "Running", value: count ? count.running_count : 0 }),
      h(Stat, { label: "True", value: count ? formatNumber(count.true_count, 2) : "0.00" }),
      h(Stat, { label: "Decks left", value: count ? formatNumber(count.decks_remaining, 2) : "0.00" }),
      h(Stat, { label: "Seen", value: count ? count.cards_seen : 0 }),
      h(Stat, { label: "Aces", value: count ? count.aces_seen : 0 }),
      h(Stat, { label: "Pen", value: count ? `${formatNumber(count.deck_penetration * 100, 1)}%` : "0.0%" })
    )
  );
}
function BetPanel({ betting, roundBetting, mode }) {
  const current = betting || null;
  const round = roundBetting || null;
  return h("section", { className: "panel bet-panel" },
    h("div", { className: "panel-title" }, "Bet Units"),
    h("div", { className: "bet-card primary-bet" },
      h("span", null, mode === "simulation" ? "Next Hand" : "Current Shoe"),
      h("strong", null, current ? `${current.recommended_units} unit${current.recommended_units === 1 ? "" : "s"}` : "--"),
      h("em", null, current ? `Pre-round TC ${formatSigned(current.true_count)}` : "Pre-round TC --")
    ),
    h("div", { className: "bet-card" },
      h("span", null, "This Round"),
      h("strong", null, round ? `${round.recommended_units} unit${round.recommended_units === 1 ? "" : "s"}` : "--"),
      h("em", null, round ? `Locked before deal at TC ${formatSigned(round.true_count)}` : "Locks before cards are counted")
    )
  );
}

function SimulationBetPanel({ simState, playerBet, setPlayerBet, phase, busy }) {
  const betting = simState && simState.betting;
  const roundRecommendation = betting && betting.round;
  const roundPlayerBet = betting && betting.player_round_units;
  const locked = phase === "player";
  const parsedBet = parseBetUnits(playerBet);

  return h("section", { className: "panel bet-panel" },
    h("div", { className: "panel-title" }, "Bet Practice"),
    h("label", { className: "field bet-field" },
      h("span", null, "Your Next Bet"),
      h("input", {
        type: "text",
        inputMode: "numeric",
        value: playerBet,
        disabled: busy || locked,
        onChange: (event) => setPlayerBet(event.target.value),
      }),
      h("small", { className: parsedBet.valid ? "" : "field-error" },
        parsedBet.valid ? "Allowed range: 1-20 units" : parsedBet.error
      )
    ),
    h("div", { className: "bet-card primary-bet" },
      h("span", null, "This Round"),
      h("strong", null, roundPlayerBet ? `${roundPlayerBet} unit${roundPlayerBet === 1 ? "" : "s"}` : "--"),
      h("em", null, roundPlayerBet ? "Your locked bet" : "Choose before dealing")
    ),
    h("div", { className: "bet-card" },
      h("span", null, "Engine Recommendation"),
      h("strong", null, roundRecommendation ? `${roundRecommendation.recommended_units} unit${roundRecommendation.recommended_units === 1 ? "" : "s"}` : "Hidden"),
      h("em", null, roundRecommendation
        ? `Was based on pre-round TC ${formatSigned(roundRecommendation.true_count)}`
        : "Reveals after the round")
    )
  );
}

function formatSigned(value) {
  const number = Number(value || 0);
  return `${number >= 0 ? "+" : ""}${number.toFixed(2)}`;
}

function StatsPanel({ stats, shoeCards, compact = false }) {
  return h("section", { className: compact ? "panel stat-panel compact-panel" : "panel stat-panel" },
    h("div", { className: "panel-title" }, "Stats"),
    h("div", { className: "stat-grid" },
      h(Stat, { label: "Balance", value: stats ? formatUnits(stats.balance) : 0 }),
      h(Stat, { label: "Net", value: stats ? formatUnits(stats.bankroll) : 0 }),
      h(Stat, { label: "Rounds", value: stats ? stats.rounds : 0 }),
      h(Stat, { label: "Hands", value: stats ? stats.hands : 0 }),
      h(Stat, { label: "Wins", value: stats ? stats.wins : 0 }),
      h(Stat, { label: "Losses", value: stats ? stats.losses : 0 }),
      h(Stat, { label: "Pushes", value: stats ? stats.pushes : 0 }),
      h(Stat, { label: "Blackjacks", value: stats ? stats.blackjacks : 0 }),
      h(Stat, { label: "Shoe cards", value: shoeCards || 0 })
    )
  );
}

function ObservedPanel({ cards, compact = false }) {
  return h("section", { className: compact ? "panel observed-panel compact-panel" : "panel observed-panel" },
    h("div", { className: "panel-title" }, "Observed"),
    h("div", { className: "observed-list" },
      cards && cards.length
        ? cards.map((card, index) => h("span", { className: "mini-card", key: `${card}-${index}` }, card))
        : h("span", { className: "muted" }, "None")
    )
  );
}

function Stat({ label, value }) {
  return h("div", { className: "stat" },
    h("span", null, label),
    h("strong", null, value)
  );
}

function TotalBadge({ label, value }) {
  return h("div", { className: "total-badge" },
    h("span", null, label),
    h("strong", null, value)
  );
}

function Toggle({ label, checked, onChange }) {
  return h("label", { className: "toggle" },
    h("input", {
      type: "checkbox",
      checked,
      onChange: (event) => onChange(event.target.checked),
    }),
    h("span", { className: "toggle-track" },
      h("span", { className: "toggle-dot" })
    ),
    h("span", null, label)
  );
}

function RankPad({ selected, onPick }) {
  return h("div", { className: "rank-pad" },
    RANKS.map((rank) => h("button", {
      key: rank,
      className: selected.includes(rank) ? "rank selected" : "rank",
      onClick: () => onPick(rank),
    }, rank))
  );
}

function CardSlot({ label, filled, onRemove }) {
  return h("button", {
    className: filled ? "card-slot filled" : "card-slot",
    onClick: onRemove,
    disabled: !filled || !onRemove,
  },
    h("span", null, label)
  );
}

function DisplayCard({ card }) {
  if (!card) {
    return h("div", { className: "display-card empty-card" }, h("span", null, "--"));
  }
  const red = card.suit === "h" || card.suit === "d";
  return h("div", {
    className: card.hidden ? "display-card hidden-card" : red ? "display-card red-card" : "display-card black-card",
  }, h("span", null, card.label));
}

function SimHandView({ hand }) {
  const handLabel = hand.from_split ? `Split ${hand.index + 1}` : `Hand ${hand.index + 1}`;
  return h("div", { className: hand.active ? "sim-hand active" : "sim-hand" },
    h("div", { className: "sim-hand-head" },
      h("span", null, handLabel),
      h("strong", null, handSummary(hand))
    ),
    h("div", { className: "hand-row compact-row" },
      hand.cards.map((card, index) => h(DisplayCard, { card, key: `${hand.index}-${index}` }))
    ),
    h("div", { className: "sim-total-row" },
      h(TotalBadge, { label: "Player Total", value: handSummary(hand) }),
      h(TotalBadge, { label: "Bet", value: formatUnits(hand.bet) })
    ),
    h("div", { className: "sim-hand-foot" },
      h("span", null, hand.result ? `${hand.result} ${formatUnits(hand.payout)}` : hand.status)
    )
  );
}

function dealerTotalLabel(dealer) {
  if (!dealer) return "--";
  if (dealer.is_bust) return `Bust ${dealer.total}`;
  return `${dealer.is_soft ? "Soft" : "Hard"} ${dealer.total}`;
}

function handSummary(hand) {
  if (hand.is_blackjack) return "Blackjack";
  if (hand.is_bust) return "Bust";
  const mode = hand.is_soft ? "Soft" : "Hard";
  return `${mode} ${hand.total}`;
}

ReactDOM.createRoot(document.getElementById("root")).render(h(App));
