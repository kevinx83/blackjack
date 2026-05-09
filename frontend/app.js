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

function App() {
  const [page, setPage] = useState("home");

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

  function addPlayer(rank) {
    setPlayer((cards) => [...cards, rank]);
    setResult(null);
  }

  function removePlayer(index) {
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
          h(CardSlot, { label: dealer || "Upcard", filled: Boolean(dealer), onRemove: () => setDealer("") }),
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
          h(RankPad, { selected: dealer ? [dealer] : [], onPick: setDealer })
        ),
        h("div", { className: "panel" },
          h("div", { className: "panel-title" }, "Player Hand"),
          h(RankPad, { selected: player, onPick: addPlayer })
        ),
        h("div", { className: "panel control-stack" },
          h("div", { className: "panel-title" }, "Round"),
          h("div", { className: "round-status" },
            h("span", null, `Double ${canDouble ? "available" : "locked"}`),
            h("span", null, `Split ${canSplit ? "available" : "locked"}`),
            h("span", null, roundCounted ? "Visible cards counted" : "Visible cards pending")
          ),
          h("button", {
            className: "primary",
            onClick: countVisibleAndRecommend,
            disabled: busy || !canRecommend || roundCounted,
          }, "Count + Recommend"),
          h("button", {
            className: "secondary",
            onClick: recommendOnly,
            disabled: busy || !canRecommend,
          }, "Recommend Only"),
          h("button", { className: "secondary", onClick: clearRound, disabled: busy }, "New Round")
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
  const [settings, setSettings] = useState({ num_decks: 6, das: true, s17: true, surrender: true });
  const [simState, setSimState] = useState(null);
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
      const payload = await api("/api/sim/start", settings);
      setSimState(payload);
    });
  }

  async function dealRound() {
    await runAction(async () => {
      const payload = await api("/api/sim/new-round", {});
      setSimState(payload);
    });
  }

  async function play(action) {
    await runAction(async () => {
      const payload = await api("/api/sim/action", { action });
      setSimState(payload);
    });
  }

  const recommendation = simState && simState.recommendation;
  const activeHand = simState && simState.hands.find((hand) => hand.active);
  const handLabel = activeHand ? handSummary(activeHand) : "No active hand";
  const legalActions = simState ? simState.legal_actions : [];
  const phase = simState ? simState.phase : "idle";

  return h("div", { className: "app-shell sim-shell" },
    h("aside", { className: "sidebar" },
      h(BrandBlock, { subtitle: "Simulation", navigate }),
      h(SettingsPanel, { settings, setRule, actionLabel: "Start Game", onAction: startGame, busy }),
      h(CountPanel, { state: simState }),
      h(BetPanel, {
        betting: simState && simState.betting && simState.betting.next_hand,
        roundBetting: simState && simState.betting && simState.betting.round,
        mode: "simulation",
      }),
      h(StatsPanel, { stats: simState && simState.stats, shoeCards: simState && simState.shoe_cards_remaining }),
      h(ObservedPanel, { cards: simState && simState.observed_cards })
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
          recommendation,
          handLabel,
          reasoning: recommendation ? recommendation.reasoning : "Deal a round to get a live recommendation",
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
            h("span", null, simState && simState.betting && simState.betting.next_hand
              ? `Next bet ${simState.betting.next_hand.recommended_units} units`
              : "Next bet --"),
            h("span", null, simState && simState.betting && simState.betting.round
              ? `This round ${simState.betting.round.recommended_units} units`
              : "This round --")
          ),
          h("button", { className: "primary", onClick: dealRound, disabled: busy || phase === "player" }, "Deal Round"),
          h("button", { className: "secondary", onClick: startGame, disabled: busy }, "Reset Shoe")
        ),
        h("div", { className: "panel action-panel" },
          h("div", { className: "panel-title" }, "Player Action"),
          h("div", { className: "play-actions" },
            ["HIT", "STAND", "DOUBLE", "SPLIT", "SURRENDER"].map((action) => {
              const recommended = recommendation && recommendation.action === action;
              return h("button", {
                key: action,
                className: recommended ? `play-action recommended ${ACTION_CLASS[action] || ""}` : "play-action",
                onClick: () => play(action),
                disabled: busy || !legalActions.includes(action),
              }, recommended ? `${action} *` : action);
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
        )
      )
    )
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
    }, "Solver")
  );
}

function SettingsPanel({ settings, setRule, actionLabel, onAction, busy }) {
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

function RecommendationPanel({ recommendation, handLabel, reasoning }) {
  return h("div", { className: "recommendation" },
    h("div", { className: "rec-label" }, "Recommendation"),
    recommendation
      ? h("div", { className: `rec-action ${ACTION_CLASS[recommendation.action] || ""}` }, recommendation.action)
      : h("div", { className: "rec-action empty" }, "--"),
    h("div", { className: "rec-meta" },
      h("span", null, handLabel),
      h("span", null, recommendation ? `Code ${recommendation.raw_code}` : "Code --"),
      h("span", null, recommendation && recommendation.is_deviation ? "Deviation" : "Basic")
    ),
    h("div", { className: "reasoning" }, reasoning)
  );
}

function CountPanel({ state }) {
  const count = state && state.count;
  return h("section", { className: "panel stat-panel" },
    h("div", { className: "panel-title" }, "Count"),
    h("div", { className: "stat-grid" },
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

function formatSigned(value) {
  const number = Number(value || 0);
  return `${number >= 0 ? "+" : ""}${number.toFixed(2)}`;
}

function StatsPanel({ stats, shoeCards }) {
  return h("section", { className: "panel stat-panel" },
    h("div", { className: "panel-title" }, "Stats"),
    h("div", { className: "stat-grid" },
      h(Stat, { label: "Rounds", value: stats ? stats.rounds : 0 }),
      h(Stat, { label: "Hands", value: stats ? stats.hands : 0 }),
      h(Stat, { label: "Wins", value: stats ? stats.wins : 0 }),
      h(Stat, { label: "Losses", value: stats ? stats.losses : 0 }),
      h(Stat, { label: "Pushes", value: stats ? stats.pushes : 0 }),
      h(Stat, { label: "Units", value: stats ? formatUnits(stats.bankroll) : 0 }),
      h(Stat, { label: "Blackjacks", value: stats ? stats.blackjacks : 0 }),
      h(Stat, { label: "Shoe cards", value: shoeCards || 0 })
    )
  );
}

function ObservedPanel({ cards }) {
  return h("section", { className: "panel observed-panel" },
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
  return h("div", { className: hand.active ? "sim-hand active" : "sim-hand" },
    h("div", { className: "sim-hand-head" },
      h("span", null, `Hand ${hand.index + 1}`),
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
