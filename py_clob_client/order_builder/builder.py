from py_order_utils.builders import OrderBuilder as UtilsOrderBuilder
from py_order_utils.signer import Signer as UtilsSigner
from py_order_utils.model import (
    EOA,
    OrderData,
    SignedOrder,
    BUY as UtilsBuy,
    SELL as UtilsSell,
)

from .helpers import (
    to_token_decimals,
    round_down,
    round_normal,
)

from .constants import BUY, SELL
from ..config import get_contract_config
from ..signer import Signer

from ..clob_types import (
    OrderArgs,
    CreateOrderOptions,
    TickSize,
    RoundConfig,
    MarketOrderArgs,
    OrderSummary,
    OrderType,
)

# ==========================================================
# ROUNDING CONFIG
# ==========================================================

ROUNDING_CONFIG: dict[TickSize, RoundConfig] = {
    "0.1": RoundConfig(price=1, size=2, amount=3),
    "0.01": RoundConfig(price=2, size=2, amount=4),
    "0.001": RoundConfig(price=3, size=2, amount=5),
    "0.0001": RoundConfig(price=4, size=2, amount=6),
}


# ==========================================================
# PRECISION HELPER
# ==========================================================

def _clamp_precision(value: float, precision: int) -> float:
    return round_down(value, precision)


# ==========================================================
# ORDER BUILDER
# ==========================================================

class OrderBuilder:

    def __init__(self, signer: Signer, sig_type=None, funder=None):

        self.signer = signer
        self.sig_type = sig_type if sig_type is not None else EOA
        self.funder = funder if funder is not None else self.signer.address()

        self.chain_id = self.signer.get_chain_id()
        self.contract_config = get_contract_config(self.chain_id, False)

        self.utils_signer = UtilsSigner(key=self.signer.private_key)

        self.utils_builder = UtilsOrderBuilder(
            self.contract_config.exchange,
            self.chain_id,
            self.utils_signer,
        )

    # ==========================================================
    # LIMIT ORDER AMOUNTS
    # ==========================================================

    def get_order_amounts(
        self,
        side: str,
        size: float,
        price: float,
        round_config: RoundConfig,
        maker_precision: int,
        taker_precision: int,
    ):

        raw_price = round_normal(price, round_config.price)

        if side == BUY:

            raw_taker_amt = round_down(size, round_config.size)
            raw_maker_amt = raw_taker_amt * raw_price

        elif side == SELL:

            raw_maker_amt = round_down(size, round_config.size)
            raw_taker_amt = raw_maker_amt * raw_price

        else:
            raise ValueError(f"order_args.side must be '{BUY}' or '{SELL}'")

        raw_maker_amt = _clamp_precision(raw_maker_amt, maker_precision)
        raw_taker_amt = _clamp_precision(raw_taker_amt, taker_precision)

        maker_amount = to_token_decimals(raw_maker_amt)
        taker_amount = to_token_decimals(raw_taker_amt)

        if side == BUY:
            return UtilsBuy, maker_amount, taker_amount
        else:
            return UtilsSell, maker_amount, taker_amount

    # ==========================================================
    # MARKET ORDER AMOUNTS
    # ==========================================================

    def get_market_order_amounts(
        self,
        side: str,
        amount: float,
        price: float,
        round_config: RoundConfig,
        maker_precision: int,
        taker_precision: int,
    ):

        raw_price = round_normal(price, round_config.price)

        if side == BUY:

            raw_maker_amt = round_down(amount, maker_precision)
            raw_taker_amt = raw_maker_amt / raw_price

        elif side == SELL:

            raw_maker_amt = round_down(amount, round_config.size)
            raw_taker_amt = raw_maker_amt * raw_price

        else:
            raise ValueError(f"order_args.side must be '{BUY}' or '{SELL}'")

        raw_maker_amt = _clamp_precision(raw_maker_amt, maker_precision)
        raw_taker_amt = _clamp_precision(raw_taker_amt, taker_precision)

        maker_amount = to_token_decimals(raw_maker_amt)
        taker_amount = to_token_decimals(raw_taker_amt)

        if side == BUY:
            return UtilsBuy, maker_amount, taker_amount
        else:
            return UtilsSell, maker_amount, taker_amount

    # ==========================================================
    # CREATE LIMIT ORDER
    # ==========================================================

    def create_order(
        self, order_args: OrderArgs, options: CreateOrderOptions
    ) -> SignedOrder:

        round_config = ROUNDING_CONFIG[options.tick_size]
        order_type = getattr(options, "order_type", None)
        is_taker = order_type in (OrderType.FAK, OrderType.FOK)

        # ======================================================
        # PRECISION MATRIX
        # ======================================================

        if order_args.side == BUY:
            if is_taker:
                maker_precision = 2
                taker_precision = 4
            else:
                maker_precision = 4
                taker_precision = 2

        else:  # SELL
            maker_precision = 2
            taker_precision = 4

        # ======================================================

        side, maker_amount, taker_amount = self.get_order_amounts(
            order_args.side,
            order_args.size,
            order_args.price,
            round_config,
            maker_precision,
            taker_precision,
        )

        data = OrderData(
            maker=self.funder,
            taker=order_args.taker,
            tokenId=order_args.token_id,
            makerAmount=str(maker_amount),
            takerAmount=str(taker_amount),
            side=side,
            feeRateBps=str(order_args.fee_rate_bps),
            nonce=str(order_args.nonce),
            signer=self.signer.address(),
            expiration=str(order_args.expiration),
            signatureType=self.sig_type,
        )

        return self.utils_builder.build_signed_order(data)

    # ==========================================================
    # CREATE MARKET ORDER
    # ==========================================================

    def create_market_order(
        self, order_args: MarketOrderArgs, options: CreateOrderOptions
    ) -> SignedOrder:

        base = ROUNDING_CONFIG[options.tick_size]

        if order_args.side == BUY:
            maker_precision = 2
            taker_precision = 4
        else:
            maker_precision = 2
            taker_precision = 4

        side, maker_amount, taker_amount = self.get_market_order_amounts(
            order_args.side,
            order_args.amount,
            order_args.price,
            base,
            maker_precision,
            taker_precision,
        )

        data = OrderData(
            maker=self.funder,
            taker=order_args.taker,
            tokenId=order_args.token_id,
            makerAmount=str(maker_amount),
            takerAmount=str(taker_amount),
            side=side,
            feeRateBps=str(order_args.fee_rate_bps),
            nonce=str(order_args.nonce),
            signer=self.signer.address(),
            expiration="0",
            signatureType=self.sig_type,
        )

        return self.utils_builder.build_signed_order(data)

    # ==========================================================
    # MARKET PRICE HELPERS
    # ==========================================================

    def calculate_buy_market_price(
        self,
        positions: list[OrderSummary],
        amount_to_match: float,
        order_type: OrderType,
    ) -> float:

        if not positions:
            raise Exception("no match")

        total = 0

        for p in reversed(positions):
            total += float(p.size) * float(p.price)

            if total >= amount_to_match:
                return float(p.price)

        if order_type == OrderType.FOK:
            raise Exception("no match")

        return float(positions[0].price)

    def calculate_sell_market_price(
        self,
        positions: list[OrderSummary],
        amount_to_match: float,
        order_type: OrderType,
    ) -> float:

        if not positions:
            raise Exception("no match")

        total = 0

        for p in reversed(positions):
            total += float(p.size)

            if total >= amount_to_match:
                return float(p.price)

        if order_type == OrderType.FOK:
            raise Exception("no match")

        return float(positions[0].price)