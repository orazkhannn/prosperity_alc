from datamodel import Order, TradingState
from typing import List, Dict


class Trader:
    POSITION_LIMITS = {
        "ASH_COATED_OSMIUM": 80,
        "INTARIAN_PEPPER_ROOT": 80,
    }

    ASH_FAIR_VALUE = 10000

    # Replace these if you refit on the real exchange timestamp
    PEPPER_SLOPE = 0.10000060034133326
    PEPPER_INTERCEPT = 9999.987095180175

    def bid(self):
        return 15

    def run(self, state: TradingState):
        result: Dict[str, List[Order]] = {}

        result["ASH_COATED_OSMIUM"] = self.trade_ash(state)
        result["INTARIAN_PEPPER_ROOT"] = self.trade_pepper(state)

        traderData = ""
        conversions = 0
        return result, conversions, traderData

    def get_pepper_fair_value(self, timestamp: int) -> int:
        fair = self.PEPPER_SLOPE * timestamp + self.PEPPER_INTERCEPT
        return int(round(fair))

    def trade_ash(self, state: TradingState) -> List[Order]:
        orders: List[Order] = []
        symbol = "ASH_COATED_OSMIUM"
        fair_value = self.ASH_FAIR_VALUE

        if symbol not in state.order_depths:
            return orders

        depth = state.order_depths[symbol]
        pos = state.position.get(symbol, 0)
        limit = self.POSITION_LIMITS[symbol]

        buy_capacity = limit - pos
        sell_capacity = limit + pos

        # 1. TAKE MISPRICED ORDERS
        for ask_price, ask_qty in depth.sell_orders.items():
            if ask_price < fair_value and buy_capacity > 0:
                qty = min(-ask_qty, buy_capacity)
                if qty > 0:
                    orders.append(Order(symbol, ask_price, qty))
                    buy_capacity -= qty

        for bid_price, bid_qty in depth.buy_orders.items():
            if bid_price > fair_value and sell_capacity > 0:
                qty = min(bid_qty, sell_capacity)
                if qty > 0:
                    orders.append(Order(symbol, bid_price, -qty))
                    sell_capacity -= qty

        # 2. MARKET MAKE / PENNY JUMP
        best_bid = max(depth.buy_orders.keys()) if depth.buy_orders else None
        best_ask = min(depth.sell_orders.keys()) if depth.sell_orders else None

        if best_bid is not None and best_bid < fair_value:
            passive_buy_price = best_bid + 1
        else:
            passive_buy_price = fair_value - 4

        if best_ask is not None and best_ask > fair_value:
            passive_sell_price = best_ask - 1
        else:
            passive_sell_price = fair_value + 4

        if best_ask is not None:
            passive_buy_price = min(passive_buy_price, best_ask - 1)
        if best_bid is not None:
            passive_sell_price = max(passive_sell_price, best_bid + 1)

        if buy_capacity > 0 and passive_buy_price < fair_value:
            orders.append(Order(symbol, passive_buy_price, buy_capacity))

        if sell_capacity > 0 and passive_sell_price > fair_value:
            orders.append(Order(symbol, passive_sell_price, -sell_capacity))

        # 3. POSITION REDUCTION AT FAIR VALUE
        # done after MM logic, as requested
        if pos < 0 and fair_value in depth.sell_orders:
            fair_ask_qty = -depth.sell_orders[fair_value]
            qty = min(fair_ask_qty, -pos)
            if qty > 0:
                orders.append(Order(symbol, fair_value, qty))

        if pos > 0 and fair_value in depth.buy_orders:
            fair_bid_qty = depth.buy_orders[fair_value]
            qty = min(fair_bid_qty, pos)
            if qty > 0:
                orders.append(Order(symbol, fair_value, -qty))

        return orders

    def trade_pepper(self, state: TradingState) -> List[Order]:
        orders: List[Order] = []
        symbol = "INTARIAN_PEPPER_ROOT"
        fair_value = self.get_pepper_fair_value(state.timestamp)

        if symbol not in state.order_depths:
            return orders

        depth = state.order_depths[symbol]
        pos = state.position.get(symbol, 0)
        limit = self.POSITION_LIMITS[symbol]

        buy_capacity = limit - pos
        sell_capacity = limit + pos

        # 1. TAKE MISPRICED ORDERS RELATIVE TO MOVING FAIR VALUE
        for ask_price, ask_qty in depth.sell_orders.items():
            if ask_price < fair_value and buy_capacity > 0:
                qty = min(-ask_qty, buy_capacity)
                if qty > 0:
                    orders.append(Order(symbol, ask_price, qty))
                    buy_capacity -= qty

        for bid_price, bid_qty in depth.buy_orders.items():
            if bid_price > fair_value and sell_capacity > 0:
                qty = min(bid_qty, sell_capacity)
                if qty > 0:
                    orders.append(Order(symbol, bid_price, -qty))
                    sell_capacity -= qty

        # 2. MARKET MAKE AROUND MOVING FAIR VALUE
        best_bid = max(depth.buy_orders.keys()) if depth.buy_orders else None
        best_ask = min(depth.sell_orders.keys()) if depth.sell_orders else None

        # Pepper is trending, so quote tighter around the current moving fair value
        if best_bid is not None and best_bid < fair_value:
            passive_buy_price = best_bid + 1
        else:
            passive_buy_price = fair_value - 3

        if best_ask is not None and best_ask > fair_value:
            passive_sell_price = best_ask - 1
        else:
            passive_sell_price = fair_value + 3

        if best_ask is not None:
            passive_buy_price = min(passive_buy_price, best_ask - 1)
        if best_bid is not None:
            passive_sell_price = max(passive_sell_price, best_bid + 1)

        if buy_capacity > 0 and passive_buy_price < fair_value:
            orders.append(Order(symbol, passive_buy_price, buy_capacity))

        if sell_capacity > 0 and passive_sell_price > fair_value:
            orders.append(Order(symbol, passive_sell_price, -sell_capacity))

        # 3. POSITION REDUCTION AT MOVING FAIR VALUE
        # done after MM logic
        if pos < 0 and fair_value in depth.sell_orders:
            fair_ask_qty = -depth.sell_orders[fair_value]
            qty = min(fair_ask_qty, -pos)
            if qty > 0:
                orders.append(Order(symbol, fair_value, qty))

        if pos > 0 and fair_value in depth.buy_orders:
            fair_bid_qty = depth.buy_orders[fair_value]
            qty = min(fair_bid_qty, pos)
            if qty > 0:
                orders.append(Order(symbol, fair_value, -qty))

        return orders