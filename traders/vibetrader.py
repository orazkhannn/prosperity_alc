from datamodel import OrderDepth, Order, TradingState # type: ignore
from typing import List, Dict, Optional


class Trader:
    # Replace these if your official limits are different
    POSITION_LIMITS = {
        "ASH_COATED_OSMIUM": 80,
        "INTARIAN_PEPPER_ROOT": 80,
    }

    # ASH looked like the more stable product in your data, so keep a fixed anchor
    FIXED_FAIR_VALUES = {
        "ASH_COATED_OSMIUM": 10000,
    }

    # How many ticks better than fair a quote must be before we aggressively take it
    TAKE_EDGE = {
        "ASH_COATED_OSMIUM": 1,
        "INTARIAN_PEPPER_ROOT": 1,
    }

    # Size of passive market-making quotes
    MM_SIZE = {
        "ASH_COATED_OSMIUM": 12,
        "INTARIAN_PEPPER_ROOT": 10,
    }

    def run(self, state: TradingState):
        result: Dict[str, List[Order]] = {}

        for symbol in ["ASH_COATED_OSMIUM", "INTARIAN_PEPPER_ROOT"]:
            result[symbol] = self.trade_product(state, symbol)

        conversions = 0
        traderData = ""
        return result, conversions, traderData

    def trade_product(self, state: TradingState, symbol: str) -> List[Order]:
        orders: List[Order] = []

        if symbol not in state.order_depths:
            return orders

        depth: OrderDepth = state.order_depths[symbol]
        pos = state.position.get(symbol, 0)
        limit = self.POSITION_LIMITS[symbol]

        best_bid = max(depth.buy_orders) if depth.buy_orders else None
        best_ask = min(depth.sell_orders) if depth.sell_orders else None

        fair_value = self.get_fair_value(symbol, best_bid, best_ask, pos, limit)
        if fair_value is None:
            return orders

        buy_capacity = limit - pos
        sell_capacity = limit + pos
        edge = self.TAKE_EDGE[symbol]

        # 1) Aggressively take clearly mispriced asks
        for ask_price in sorted(depth.sell_orders.keys()):
            ask_qty = depth.sell_orders[ask_price]  # usually negative in Prosperity
            available = -ask_qty

            if ask_price <= fair_value - edge and buy_capacity > 0:
                qty = min(available, buy_capacity)
                if qty > 0:
                    orders.append(Order(symbol, ask_price, qty))
                    buy_capacity -= qty

        # 2) Aggressively hit clearly overpriced bids
        for bid_price in sorted(depth.buy_orders.keys(), reverse=True):
            bid_qty = depth.buy_orders[bid_price]

            if bid_price >= fair_value + edge and sell_capacity > 0:
                qty = min(bid_qty, sell_capacity)
                if qty > 0:
                    orders.append(Order(symbol, bid_price, -qty))
                    sell_capacity -= qty

        # 3) Passive market making with small inventory skew
        passive_buy_price, passive_sell_price = self.get_passive_quotes(
            fair_value, best_bid, best_ask
        )

        buy_mm_size, sell_mm_size = self.get_mm_sizes(
            symbol=symbol,
            pos=pos,
            buy_capacity=buy_capacity,
            sell_capacity=sell_capacity,
        )

        if (
            buy_mm_size > 0
            and passive_buy_price is not None
            and (best_ask is None or passive_buy_price < best_ask)
        ):
            orders.append(Order(symbol, passive_buy_price, buy_mm_size))

        if (
            sell_mm_size > 0
            and passive_sell_price is not None
            and (best_bid is None or passive_sell_price > best_bid)
        ):
            orders.append(Order(symbol, passive_sell_price, -sell_mm_size))

        return orders

    def get_fair_value(
        self,
        symbol: str,
        best_bid: Optional[int],
        best_ask: Optional[int],
        pos: int,
        limit: int,
    ) -> Optional[float]:
        # Fixed-anchor product
        if symbol in self.FIXED_FAIR_VALUES:
            fair = float(self.FIXED_FAIR_VALUES[symbol])
        else:
            # Floating fair from current book
            if best_bid is None or best_ask is None:
                return None
            fair = (best_bid + best_ask) / 2.0

        # Small inventory skew:
        # long -> lower fair a bit to encourage selling
        # short -> raise fair a bit to encourage buying
        skew = 2.0 * pos / limit
        fair -= skew

        return fair

    def get_passive_quotes(
        self,
        fair_value: float,
        best_bid: Optional[int],
        best_ask: Optional[int],
    ):
        fair_int = round(fair_value)

        passive_buy = fair_int - 1
        passive_sell = fair_int + 1

        # If the spread is wide, improve existing quotes by 1 tick
        if best_bid is not None and best_bid < fair_value:
            passive_buy = best_bid + 1

        if best_ask is not None and best_ask > fair_value:
            passive_sell = best_ask - 1

        # Prevent accidental crossing
        if best_ask is not None:
            passive_buy = min(passive_buy, best_ask - 1)

        if best_bid is not None:
            passive_sell = max(passive_sell, best_bid + 1)

        if passive_buy >= passive_sell:
            passive_buy = fair_int - 1
            passive_sell = fair_int + 1

            if best_ask is not None:
                passive_buy = min(passive_buy, best_ask - 1)
            if best_bid is not None:
                passive_sell = max(passive_sell, best_bid + 1)

        return passive_buy, passive_sell

    def get_mm_sizes(
        self,
        symbol: str,
        pos: int,
        buy_capacity: int,
        sell_capacity: int,
    ):
        base_size = self.MM_SIZE[symbol]

        buy_size = min(base_size, buy_capacity)
        sell_size = min(base_size, sell_capacity)

        # Inventory-aware sizing:
        # if already long, quote smaller bid and larger ask
        # if already short, quote larger bid and smaller ask
        if pos > 0:
            buy_size = max(0, buy_size - pos // 10)
            sell_size = min(sell_capacity, sell_size + pos // 10)
        elif pos < 0:
            buy_size = min(buy_capacity, buy_size + (-pos) // 10)
            sell_size = max(0, sell_size - (-pos) // 10)

        return buy_size, sell_size