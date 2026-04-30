from datamodel import Order, TradingState  # type: ignore
from typing import Dict, List


class Trader:
    POSITION_LIMIT = 10
    BASE_SIZE = 2

    # Tune later in grid search
    INVENTORY_SKEW = 0.25
    MIN_SPREAD = 4

    def run(self, state):
        orders = {}

        for product in state.order_depths.keys():
            product_orders = self.trade_rw(state, product)

            if product_orders:
                orders[product] = product_orders

        return orders, 0, ""

    def trade_rw(self, state, product):
        """
        Version C: one-tick improved market making
        + inventory skew
        + spread filter.

        Logic:
            - do not trade if spread is too small
            - estimate fair value using mid price
            - shift fair value against current inventory
            - quote around skewed fair value
            - respect position limit
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

        # Version C: spread filter
        if spread < self.MIN_SPREAD:
            return orders

        mid_price = (best_bid + best_ask) / 2

        # Inventory-skewed fair value
        reservation_price = mid_price - self.INVENTORY_SKEW * position

        # Same style as A1 when inventory is 0:
        # bid one tick above best bid, ask one tick below best ask
        half_spread = spread / 2
        edge = max(1, half_spread - 1)

        buy_price = int(round(reservation_price - edge))
        sell_price = int(round(reservation_price + edge))

        # Keep quotes near the current market
        buy_price = min(buy_price, best_bid + 1)
        sell_price = max(sell_price, best_ask - 1)

        if buy_price >= sell_price:
            return orders

        max_buy = self.POSITION_LIMIT - position
        max_sell = self.POSITION_LIMIT + position

        buy_size = min(self.BASE_SIZE, max_buy)
        sell_size = min(self.BASE_SIZE, max_sell)

        if buy_size > 0:
            orders.append(Order(product, buy_price, buy_size))

        if sell_size > 0:
            orders.append(Order(product, sell_price, -sell_size))

        return orders