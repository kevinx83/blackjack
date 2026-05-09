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

function rankValue(rank) {
  if (rank === "A") return 11;
  if (["10", "J", "Q", "K"].includes(rank)) return 10;
  return Number(rank);
}

function isPair(cards) {
  return cards.length === 2 && rankValue(cards[0]) === rankValue(cards[1]);
}

function App() {
  const [settings, setSettings] = useState({ num_decks: 6, das: true, s17: true, surrender: true });
  const [state, setState] = useState(null);
  const [dealer, setDealer] = useState("");
  const [player, setPlayer] = useState([]);
  const [extraCards, setExtraCards] = useState([]);
  const [roundCounted, setRoundCounted] = useState(false);
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

  const handLabel = useMemo(() => {
    if (!result) return "No hand";
    const mode = result.hand.is_soft ? "Soft" : "Hard";
    if (result.hand.is_blackjack) return "Blackjack";
    if (result.hand.is_bust) return "Bust";
    return `${mode} ${result.hand.total}`;
  }, [result]);

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
      setState(payload.state);
    });
  }

  async function countVisibleAndRecommend() {
    if (!canRecommend || roundCounted) return;
    await runAction(async () => {
      const countedState = await api("/api/observe", { cards: [dealer, ...player] });
      setState(countedState);
      setRoundCounted(true);
      const payload = await api("/api/recommend", {
        dealer,
        player,
        can_double: canDouble,
        can_split: canSplit,
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
      h("div", { className: "brand-row" },
        h("div", { className: "mark" }, "BJ"),
        h("div", null,
          h("h1", null, "Blackjack Advisor"),
          h("p", null, "Manual MVP")
        )
      ),
      h("section", { className: "panel" },
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
        h("button", { className: "primary full", onClick: startShoe, disabled: busy }, "Start Shoe")
      ),
      h(CountPanel, { state }),
      h("section", { className: "panel observed-panel" },
        h("div", { className: "panel-title" }, "Observed"),
        h("div", { className: "observed-list" },
          state && state.observed_cards.length
            ? state.observed_cards.map((card, index) => h("span", { className: "mini-card", key: `${card}-${index}` }, card))
            : h("span", { className: "muted" }, "None")
        )
      )
    ),
    h("main", { className: "workspace" },
      message && h("div", { className: "message" }, message),
      h("section", { className: "table" },
        h("div", { className: "dealer-zone" },
          h("div", { className: "zone-label" }, "Dealer"),
          h(CardSlot, { label: dealer || "Upcard", filled: Boolean(dealer), onRemove: () => setDealer("") })
        ),
        h("div", { className: "recommendation" },
          h("div", { className: "rec-label" }, "Recommendation"),
          result
            ? h("div", { className: `rec-action ${ACTION_CLASS[result.recommendation.action] || ""}` }, result.recommendation.action)
            : h("div", { className: "rec-action empty" }, "--"),
          h("div", { className: "rec-meta" },
            h("span", null, handLabel),
            h("span", null, result ? `Code ${result.recommendation.raw_code}` : "Code --"),
            h("span", null, result && result.recommendation.is_deviation ? "Deviation" : "Basic")
          ),
          h("div", { className: "reasoning" },
            result ? result.recommendation.reasoning : "No recommendation"
          )
        ),
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
          )
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

function Stat({ label, value }) {
  return h("div", { className: "stat" },
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

ReactDOM.createRoot(document.getElementById("root")).render(h(App));
