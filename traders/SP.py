from datamodel import Order, TradingState  # type: ignore
from typing import Dict, List


class Trader:
    BASE_SIZE = 2
    POSITION_LIMIT = 10
    FLATTEN_LIMIT = 8
    SNACKPACK_PRODUCTS = {
        "SNACKPACK_CHOCOLATE",
        "SNACKPACK_VANILLA",
        "SNACKPACK_PISTACHIO",
        "SNACKPACK_STRAWBERRY",
        "SNACKPACK_RASPBERRY",
    }
    def run(self, state):
        orders = {}

        for product in self.SNACKPACK_PRODUCTS:
            product_orders = self.trade_snackpack_wi_mm(state, product)

            if product_orders:
                orders[product] = product_orders

        return orders, 0, ""

    
    def trade_snackpack_wi_mm(self, state, product):
        """
        Snackpack-specific weighted-imbalance market making.

        Positive weighted imbalance:
            expected short-term upward pressure
            quote bid more aggressively
            buy larger size
            quote ask less aggressively / smaller size

        Negative weighted imbalance:
            expected short-term downward pressure
            quote ask more aggressively
            sell larger size
            quote bid less aggressively / smaller size
        """

        orders = []

        if product not in state.order_depths:
            return orders

        depth = state.order_depths[product]

        if not depth.buy_orders or not depth.sell_orders:
            return orders

        position = state.position.get(product, 0)

        best_bid = max(depth.buy_orders.keys())
        best_ask = min(depth.sell_orders.keys())

        if best_bid >= best_ask:
            return orders

        spread = best_ask - best_bid

        # ----------------------------
        # Weighted imbalance
        # ----------------------------

        bid_levels = sorted(depth.buy_orders.items(), reverse=True)[:3]
        ask_levels = sorted(depth.sell_orders.items())[:3]

        weights = [1.0, 0.5, 0.25]

        weighted_bid_volume = 0
        weighted_ask_volume = 0

        for i, (_, volume) in enumerate(bid_levels):
            weighted_bid_volume += weights[i] * volume

        for i, (_, volume) in enumerate(ask_levels):
            weighted_ask_volume += weights[i] * abs(volume)

        weighted_total_volume = weighted_bid_volume + weighted_ask_volume

        if weighted_total_volume == 0:
            return orders

        wi = (weighted_bid_volume - weighted_ask_volume) / weighted_total_volume

        # ----------------------------
        # Signal-based quote skew
        # ----------------------------

        MILD = 0.10
        STRONG = 0.25

        # Neutral baseline
        buy_improve = 1
        sell_improve = 1
        buy_size = self.BASE_SIZE
        sell_size = self.BASE_SIZE

        if wi >= STRONG:
            # Strong upward pressure
            buy_improve = 3
            sell_improve = 0
            buy_size = self.BASE_SIZE + 3
            sell_size = 0

        elif wi >= MILD:
            # Mild upward pressure
            buy_improve = 2
            sell_improve = 1
            buy_size = self.BASE_SIZE + 1
            sell_size = max(0, self.BASE_SIZE - 1)

        elif wi <= -STRONG:
            # Strong downward pressure
            buy_improve = 0
            sell_improve = 3
            buy_size = 0
            sell_size = self.BASE_SIZE + 3

        elif wi <= -MILD:
            # Mild downward pressure
            buy_improve = 1
            sell_improve = 2
            buy_size = max(0, self.BASE_SIZE - 1)
            sell_size = self.BASE_SIZE + 1

        # ----------------------------
        # Inventory safety override
        # ----------------------------

        if position >= self.FLATTEN_LIMIT:
            # Too long: stop buying, prioritize selling
            buy_size = 0
            sell_size = max(sell_size, self.BASE_SIZE + 2)
            sell_improve = max(sell_improve, 2)

        elif position <= -self.FLATTEN_LIMIT:
            # Too short: stop selling, prioritize buying
            buy_size = max(buy_size, self.BASE_SIZE + 2)
            sell_size = 0
            buy_improve = max(buy_improve, 2)

        # ----------------------------
        # Prevent crossing quotes
        # ----------------------------

        buy_improve = max(0, buy_improve)
        sell_improve = max(0, sell_improve)

        while buy_improve + sell_improve >= spread:
            if buy_improve >= sell_improve and buy_improve > 0:
                buy_improve -= 1
            elif sell_improve > 0:
                sell_improve -= 1
            else:
                break

        buy_price = best_bid + buy_improve
        sell_price = best_ask - sell_improve

        if buy_price >= sell_price:
            return orders

        # ----------------------------
        # Position limit caps
        # ----------------------------

        max_buy = self.POSITION_LIMIT - position
        max_sell = self.POSITION_LIMIT + position

        buy_size = min(buy_size, max_buy)
        sell_size = min(sell_size, max_sell)

        if buy_size > 0:
            orders.append(Order(product, buy_price, buy_size))

        if sell_size > 0:
            orders.append(Order(product, sell_price, -sell_size))

        return orders