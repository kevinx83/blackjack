"""
HeatManager: casino heat scoring, camouflage tracking, and session management.

Heat score (0–100) per casino. Increases on suspicious patterns observed by
pit surveillance; decreases over time as memory fades.

Heat escalation path:
  1. Early shuffle-ups when player raises bet
  2. Bet cap / spread restriction
  3. Flat-bet requirement
  4. Backoff (asked to leave blackjack)
  5. Trespass from property
  6. RFID tracking / industry database (Griffin Investigations)
"""
from __future__ import annotations
import time
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Heat events
# ---------------------------------------------------------------------------

@dataclass
class HeatEvent:
    """A heat-generating or heat-reducing observation."""
    event_type: str     # e.g. 'large_bet_spread', 'index_play', 'shuffle_up'
    severity: float     # heat delta (positive = more heat)
    timestamp: float = field(default_factory=time.time)
    note: str = ''


# ---------------------------------------------------------------------------
# Heat thresholds
# ---------------------------------------------------------------------------

class HeatLevel:
    COOL      = 0    # no attention
    WATCH     = 30   # mild interest from pit
    WARM      = 50   # increased scrutiny
    HOT       = 70   # risk of backoff — start camouflage or leave
    CRITICAL  = 85   # likely backoff imminent
    BANNED    = 100  # banned / trespassed


# ---------------------------------------------------------------------------
# Camouflage techniques (toggleable parameters)
# ---------------------------------------------------------------------------

@dataclass
class CamouflageParams:
    """Toggleable camouflage settings and their approximate EV cost."""
    big_player_cover: bool = False      # large bets at neutral counts; costs 0.2–0.5%
    drunk_tourist_persona: bool = False # occasional suboptimal plays; costs 0.1%
    bet_variance: float = 0.0          # fraction of rounds to vary bet ±1 unit; costs 0.1–0.2%
    session_limit_hours: float = 2.0   # max session length before rotation
    use_players_card: bool = True      # for comp hunting; misleads surveillance
    exit_on_shuffle_up: bool = True    # leave if dealer shuffle-ups mid-session


# ---------------------------------------------------------------------------
# Per-casino heat tracker
# ---------------------------------------------------------------------------

class CasinoRecord:
    """
    Tracks heat score and session history for one casino property.
    Heat decays ~0.5 points per day of absence.
    """

    _HEAT_DECAY_PER_DAY: float = 0.5
    _HOT_THRESHOLD: float = HeatLevel.HOT

    def __init__(self, name: str) -> None:
        self.name = name
        self.heat_score: float = 0.0
        self.last_visit: float = time.time()
        self.events: list[HeatEvent] = []
        self.sessions: int = 0
        self.total_hands: int = 0
        self.recommended_cooldown_days: int = 0

    def add_event(self, event_type: str, severity: float, note: str = '') -> None:
        now = time.time()
        self._apply_decay(now)
        self.events.append(HeatEvent(event_type, severity, now, note))
        self.heat_score = max(0.0, min(100.0, self.heat_score + severity))
        self.last_visit = now

    def _apply_decay(self, now: float) -> None:
        days_away = (now - self.last_visit) / 86400
        self.heat_score = max(0.0, self.heat_score - days_away * self._HEAT_DECAY_PER_DAY)

    def current_heat(self) -> float:
        self._apply_decay(time.time())
        return self.heat_score

    def should_leave(self) -> bool:
        return self.current_heat() >= self._HOT_THRESHOLD

    def heat_label(self) -> str:
        h = self.current_heat()
        if h >= HeatLevel.BANNED:   return 'banned'
        if h >= HeatLevel.CRITICAL: return 'critical'
        if h >= HeatLevel.HOT:      return 'hot'
        if h >= HeatLevel.WARM:     return 'warm'
        if h >= HeatLevel.WATCH:    return 'watch'
        return 'cool'

    def record_session(self, hands: int) -> None:
        self.sessions += 1
        self.total_hands += hands
        self.last_visit = time.time()


# ---------------------------------------------------------------------------
# HeatManager — manages multiple casinos and in-session heat tracking
# ---------------------------------------------------------------------------

class HeatManager:
    """
    Tracks casino heat across multiple properties and the current session.
    Provides camouflage recommendations and session end signals.
    """

    # Heat deltas for specific events
    _HEAT_EVENTS: dict[str, float] = {
        'large_spread_observed':  +8.0,   # pit noticed big bet jump
        'index_play_made':        +5.0,   # split tens, insure, etc.
        'shuffle_up_occurred':    +3.0,   # dealer shuffled due to bet increase
        'comp_inquiry':           -2.0,   # asking about comps appears tourist-like
        'deliberate_mistake':     -3.0,   # intentional "drunk tourist" play
        'cover_bet_placed':       -2.0,   # large bet at neutral count
        'session_normal':         -1.0,   # quiet session with no attention
    }

    def __init__(self, camouflage: CamouflageParams | None = None) -> None:
        self._casinos: dict[str, CasinoRecord] = {}
        self.camouflage = camouflage or CamouflageParams()
        self._session_heat: float = 0.0   # current session heat
        self._current_casino: str | None = None
        self._session_start: float = time.time()
        self._session_hands: int = 0

    # ------------------------------------------------------------------
    # Casino management
    # ------------------------------------------------------------------

    def casino(self, name: str) -> CasinoRecord:
        if name not in self._casinos:
            self._casinos[name] = CasinoRecord(name)
        return self._casinos[name]

    def select_casino(self, name: str) -> None:
        self._current_casino = name
        self._session_heat = 0.0
        self._session_start = time.time()
        self._session_hands = 0

    def rank_casinos(self) -> list[tuple[str, float]]:
        """Return casinos sorted by ascending heat (coolest first)."""
        return sorted(
            [(name, rec.current_heat()) for name, rec in self._casinos.items()],
            key=lambda x: x[1],
        )

    # ------------------------------------------------------------------
    # In-session heat
    # ------------------------------------------------------------------

    def observe(self, event: str, custom_delta: float | None = None) -> None:
        """Record a heat-generating or heat-reducing event in this session."""
        delta = custom_delta if custom_delta is not None else self._HEAT_EVENTS.get(event, 0.0)
        self._session_heat = max(0.0, min(100.0, self._session_heat + delta))
        if self._current_casino:
            self.casino(self._current_casino).add_event(event, delta)

    def record_hand(self) -> None:
        self._session_hands += 1

    def session_elapsed_hours(self) -> float:
        return (time.time() - self._session_start) / 3600

    def should_end_session(self) -> bool:
        """
        True when any of: session heat too high, max session time exceeded,
        or current casino is on cool-down.
        """
        if self._session_heat >= HeatLevel.HOT:
            return True
        if self.session_elapsed_hours() >= self.camouflage.session_limit_hours:
            return True
        if self._current_casino:
            return self.casino(self._current_casino).should_leave()
        return False

    def end_session(self) -> None:
        if self._current_casino:
            self.casino(self._current_casino).record_session(self._session_hands)
        self._session_heat = 0.0
        self._session_hands = 0
        self._session_start = time.time()

    # ------------------------------------------------------------------
    # Camouflage recommendations
    # ------------------------------------------------------------------

    def recommend_cover_bet(self, tc: float, base_units: int) -> bool:
        """
        True if a cover bet (large bet at neutral count) is recommended
        to mask the count-to-bet correlation.
        """
        if not self.camouflage.big_player_cover:
            return False
        # Suggest a cover bet when heat is building and TC is neutral
        return self._session_heat >= HeatLevel.WATCH and -1 <= tc <= 1

    def camouflage_ev_cost(self) -> float:
        """Approximate total EV cost of enabled camouflage techniques."""
        cost = 0.0
        if self.camouflage.big_player_cover:
            cost += 0.003    # 0.3%
        if self.camouflage.drunk_tourist_persona:
            cost += 0.001    # 0.1%
        cost += self.camouflage.bet_variance * 0.001
        return cost

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def expected_value(self) -> float:
        """Approximate EV accounting for camouflage costs and heat restrictions."""
        base_ev = 0.006   # ~0.6% at 75% pen, 1:12 spread
        return base_ev - self.camouflage_ev_cost()

    @property
    def session_heat(self) -> float:
        return self._session_heat

    def heat_label(self) -> str:
        h = self._session_heat
        if h >= HeatLevel.BANNED:   return 'banned'
        if h >= HeatLevel.CRITICAL: return 'critical'
        if h >= HeatLevel.HOT:      return 'hot'
        if h >= HeatLevel.WARM:     return 'warm'
        if h >= HeatLevel.WATCH:    return 'watch'
        return 'cool'

    def __repr__(self) -> str:
        casino = self._current_casino or '(none)'
        return (
            f"HeatManager(casino={casino!r}, "
            f"session_heat={self._session_heat:.0f}, "
            f"label={self.heat_label()!r})"
        )
