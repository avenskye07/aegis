"""AEGIS ward maker: an XRPL book maker that re-lays its book off an anchor.

The book is laid around an *anchor*, the reference mid at the moment the
quotes were placed. Two things re-lay it:

* age:  a resting quote older than ``executor_refresh_time`` (300 s) is
        replaced, as in any market-making controller.
* band: every ``anchor_poll_sec`` (60 s) the live mid is measured against the
        anchor. Once it has walked more than ``anchor_band_bps`` (50 bps, i.e.
        0.5 %) away, every resting quote on both sides is pulled at once, and
        the next pass lays a fresh book, and a fresh anchor, at the new mid.

The band test is plain arithmetic inside the bot, so no model call is made.
A quote that has started to fill is never pulled by either path.
"""

from decimal import Decimal, InvalidOperation
from typing import List, Optional

from pydantic import Field

from hummingbot.strategy_v2.controllers.market_making_controller_base import (
    MarketMakingControllerBase,
    MarketMakingControllerConfigBase,
)
from hummingbot.strategy_v2.executors.position_executor.data_types import PositionExecutorConfig
from hummingbot.strategy_v2.models.executor_actions import ExecutorAction, StopExecutorAction

BPS_PER_UNIT = Decimal(10_000)


def anchor_walk_bps(anchor: Optional[Decimal], mid: Optional[Decimal]) -> Decimal:
    """How far ``mid`` has moved from ``anchor``, in basis points. 0 if unknown."""
    if anchor is None or mid is None:
        return Decimal(0)
    if not (anchor.is_finite() and mid.is_finite()) or anchor <= 0 or mid <= 0:
        return Decimal(0)
    return abs(mid - anchor) / anchor * BPS_PER_UNIT


class AegisWardMMConfig(MarketMakingControllerConfigBase):
    controller_name: str = "aegis_ward_mm"
    anchor_poll_sec: int = Field(
        default=60,
        ge=5,
        json_schema_extra={
            "prompt": "Seconds between anchor checks (e.g. 60): ",
            "prompt_on_new": True,
        },
    )
    anchor_band_bps: Decimal = Field(
        default=Decimal("50"),
        gt=0,
        json_schema_extra={
            "prompt": "Re-lay the book once mid moves this many bps from the anchor (50 = 0.5%): ",
            "prompt_on_new": True,
        },
    )


class AegisWardMM(MarketMakingControllerBase):
    def __init__(self, config: AegisWardMMConfig, *args, **kwargs):
        super().__init__(config, *args, **kwargs)
        self.config = config
        self._anchor: Optional[Decimal] = None
        self._next_anchor_poll: float = 0.0

    # -- helpers -----------------------------------------------------------

    def _live_mid(self) -> Optional[Decimal]:
        raw = (self.processed_data or {}).get("reference_price")
        if raw is None:
            return None
        try:
            mid = Decimal(str(raw))
        except (InvalidOperation, ValueError):
            return None
        return mid if mid.is_finite() and mid > 0 else None

    def _unfilled_quotes(self):
        return [e for e in self.executors_info if e.is_active and not e.is_trading]

    # -- framework hooks ---------------------------------------------------

    def create_actions_proposal(self) -> List[ExecutorAction]:
        proposal = super().create_actions_proposal()
        if proposal:
            # A new book is being laid: its anchor is the mid it is laid at.
            mid = self._live_mid()
            if mid is not None:
                self._anchor = mid
        return proposal

    def executors_to_early_stop(self) -> List[ExecutorAction]:
        now = self.market_data_provider.time()
        if now < self._next_anchor_poll:
            return []
        self._next_anchor_poll = now + self.config.anchor_poll_sec

        quotes = self._unfilled_quotes()
        mid = self._live_mid()
        if not quotes or mid is None:
            return []
        if self._anchor is None:
            self._anchor = mid
            return []

        walk = anchor_walk_bps(self._anchor, mid)
        if walk <= self.config.anchor_band_bps:
            return []

        self.logger().info(
            f"RE-ANCHOR {self.config.trading_pair}: mid {mid:.6f} is {walk:.1f} bps from "
            f"anchor {self._anchor:.6f} (band {self.config.anchor_band_bps} bps), "
            f"re-laying {len(quotes)} quote(s)"
        )
        self._anchor = None  # the next create pass anchors the new book
        return [StopExecutorAction(controller_id=self.config.id, executor_id=e.id) for e in quotes]

    def get_executor_config(self, level_id: str, price: Decimal, amount: Decimal):
        return PositionExecutorConfig(
            timestamp=self.market_data_provider.time(),
            level_id=level_id,
            connector_name=self.config.connector_name,
            trading_pair=self.config.trading_pair,
            side=self.get_trade_type_from_level_id(level_id),
            entry_price=price,
            amount=amount,
            leverage=self.config.leverage,
            triple_barrier_config=self.config.triple_barrier_config,
        )
