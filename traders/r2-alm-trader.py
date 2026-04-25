from datamodel import OrderDepth, Order, TradingState # type: ignore
from typing import List, Dict


class Trader:
    POSITION_LIMITS = {
        "ASH_COATED_OSMIUM": 80,
    }

    def bid(self):
        # You can tune this later for Round 2 market access
        return 15

    def run(self, state: TradingState):
        result: Dict[str, List[Order]] = {}

        result["ASH_COATED_OSMIUM"] = self.trade_ash(state)

        conversions = 0
        traderData = ""
        return result, conversions, traderData

    def trade_ash(self, state: TradingState) -> List[Order]:
        orders: List[Order] = []
        symbol = "ASH_COATED_OSMIUM"

        if symbol not in state.order_depths:
            return orders

        depth: OrderDepth = state.order_depths[symbol]
        pos = state.position.get(symbol, 0)
        limit = self.POSITION_LIMITS[symbol]

        if not depth.buy_orders or not depth.sell_orders:
            return orders

        best_bid = max(depth.buy_orders.keys())
        best_ask = min(depth.sell_orders.keys())

        # Simple fair value = mid price
        fair_value = (best_bid + best_ask) / 2

        buy_capacity = limit - pos
        sell_capacity = limit + pos

        # -----------------------------
        # 1) Aggressively take clearly favorable prices
        # -----------------------------
        # Buy asks below fair value
        for ask_price in sorted(depth.sell_orders.keys()):
            ask_qty = depth.sell_orders[ask_price]   # usually negative in IMC

            if ask_price < fair_value and buy_capacity > 0:
                qty = min(-ask_qty, buy_capacity)
                if qty > 0:
                    orders.append(Order(symbol, ask_price, qty))
                    buy_capacity -= qty

        # Sell into bids above fair value
        for bid_price in sorted(depth.buy_orders.keys(), reverse=True):
            bid_qty = depth.buy_orders[bid_price]

            if bid_price > fair_value and sell_capacity > 0:
                qty = min(bid_qty, sell_capacity)
                if qty > 0:
                    orders.append(Order(symbol, bid_price, -qty))
                    sell_capacity -= qty

        # -----------------------------
        # 2) Passive market making around fair value
        # -----------------------------
        fair_int = round(fair_value)

        # Base quotes around fair value
        passive_buy_price = fair_int - 1
        passive_sell_price = fair_int + 1

        # Improve queue position when possible without crossing
        passive_buy_price = min(passive_buy_price, best_ask - 1)
        passive_buy_price = max(passive_buy_price, best_bid + 1 if best_bid + 1 < best_ask else best_bid)

        passive_sell_price = max(passive_sell_price, best_bid + 1)
        passive_sell_price = min(passive_sell_price, best_ask - 1 if best_bid < best_ask - 1 else best_ask)

        # -----------------------------
        # 3) Inventory skew
        # -----------------------------
        # If long, be less eager to buy and more eager to sell
        # If short, be less eager to sell and more eager to buy
        if pos > 20:
            passive_buy_price -= 1
            passive_sell_price -= 1
        elif pos < -20:
            passive_buy_price += 1
            passive_sell_price += 1

        # Final crossing protection
        if passive_buy_price >= best_ask:
            passive_buy_price = best_ask - 1
        if passive_sell_price <= best_bid:
            passive_sell_price = best_bid + 1

        # Submit passive orders
        if buy_capacity > 0 and passive_buy_price < best_ask:
            # use smaller resting size so you do not instantly max inventory
            # quote_buy_size = min(buy_capacity, 20)
            quote_buy_size = buy_capacity
            if quote_buy_size > 0:
                orders.append(Order(symbol, passive_buy_price, quote_buy_size))

        if sell_capacity > 0 and passive_sell_price > best_bid:
            # quote_sell_size = min(sell_capacity, 20)
            quote_sell_size = sell_capacity
            if quote_sell_size > 0:
                orders.append(Order(symbol, passive_sell_price, -quote_sell_size))

        return orders