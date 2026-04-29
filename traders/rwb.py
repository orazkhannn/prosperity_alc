from datamodel import Order, TradingState  # type: ignore
from typing import Dict, List


class Trader:
    POSITION_LIMIT = 10
    BASE_SIZE = 2

    # Tune this later in grid search
    INVENTORY_SKEW = 0.25

    def run(self, state):
        orders = {}

        for product in state.order_depths.keys():
            product_orders = self.trade_rw(state, product)

            if product_orders:
                orders[product] = product_orders

        return orders, 0, ""

    def trade_rw(self, state, product):
        """
        Version B: one-tick improved market making + inventory skew.

        For a random-walk / no-alpha product:
            - estimate fair value using mid price
            - shift fair value against current inventory
            - quote around skewed fair value
            - respect position limit
            - no spread filter yet
            - no quantity skew yet
            - no flattening mode yet
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

        mid_price = (best_bid + best_ask) / 2

        # Inventory-skewed fair value
        reservation_price = mid_price - self.INVENTORY_SKEW * position

        # Keep same effective style as A1:
        # roughly quote one tick inside the spread when possible.
        half_spread = (best_ask - best_bid) / 2
        edge = max(1, half_spread - 1)

        buy_price = int(round(reservation_price - edge))
        sell_price = int(round(reservation_price + edge))

        # Do not quote worse than the old A1 style unless skew pushes us there.
        # This keeps quotes near the current market.
        buy_price = min(buy_price, best_bid + 1)
        sell_price = max(sell_price, best_ask - 1)

        # Invalid/crossed quote guard
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