from datamodel import Order, TradingState  # type: ignore
from typing import Dict, List


class Trader:
    POSITION_LIMIT = 10
    BASE_SIZE = 2

    def run(self, state):
        orders = {}

        for product in state.order_depths.keys():
            product_orders = self.trade_rw(state, product)

            if product_orders:
                orders[product] = product_orders

        return orders, 0, ""

    def trade_rw(self, state, product):
        """
        Version A1: passive market making.

        For a random-walk / no-alpha product:
            - bid at current best bid + 1
            - ask at current best ask - 1
            - respect position limit
            - no inventory skew yet
            - no spread filter yet
            - no quote improvement yet
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
        buy_price = best_bid + 1
        sell_price = best_ask - 1

        # Invalid/crossed book guard
        if buy_price >= sell_price:
            return orders

        max_buy = 10 - position
        max_sell = 10 + position

        buy_size = min(self.BASE_SIZE, max_buy)
        sell_size = min(self.BASE_SIZE, max_sell)

        # Passive buy at best bid
        if buy_size > 0:
            orders.append(Order(product, buy_price, buy_size))

        # Passive sell at best ask
        if sell_size > 0:
            orders.append(Order(product, sell_price, -sell_size))

        return orders