from datamodel import Order, TradingState
from typing import List, Dict
import json

class Trader:
    ASH_SPREAD_TRADE_SIZE = 3
    ASH_SPREAD_MAX_POSITION = 40

    def bid(self):
        return 12501
    POSITION_LIMITS = {
        "ASH_COATED_OSMIUM": 80,
        "INTARIAN_PEPPER_ROOT": 80,
    }

    ASH_FAIR_VALUE = 10000
    PEPPER_AGGRESSIVE_TARGET = 60

    # simple pepper model
    PEPPER_TIMESTAMP_SLOPE = 0.001
    PEPPER_DAY_STEP = 1000
    PEPPER_DAY0_BASE = 12000   # day 0 starts around 12000

    def bid(self):
        return 15

    def run(self, state: TradingState):
        result: Dict[str, List[Order]] = {}

        result["ASH_COATED_OSMIUM"] = self.trade_ash_on_spread(state)
        # result["INTARIAN_PEPPER_ROOT"] = self.trade_pepper(state)

        traderData = ""
        conversions = 0
        return result, conversions, traderData

    def trade_ash_merged(self, state: TradingState) -> List[Order]:
        symbol = "ASH_COATED_OSMIUM"
        position = state.position.get(symbol, 0)
        buy_capacity = self.POSITION_LIMITS[symbol] - position
        sell_capacity = self.POSITION_LIMITS[symbol] + position

        merged_orders: List[Order] = []

        for order in self.trade_ash_on_spread(state) + self.trade_ash(state):
            if order.quantity > 0:
                qty = min(order.quantity, buy_capacity)
                if qty <= 0:
                    continue
                merged_orders.append(Order(order.symbol, order.price, qty))
                buy_capacity -= qty
            elif order.quantity < 0:
                qty = min(-order.quantity, sell_capacity)
                if qty <= 0:
                    continue
                merged_orders.append(Order(order.symbol, order.price, -qty))
                sell_capacity -= qty

        return merged_orders
    

    # -------------------------
    # PEPPER helpers
    # -------------------------

    def infer_pepper_day(self, state: TradingState) -> int:
        symbol = "INTARIAN_PEPPER_ROOT"

        if symbol not in state.order_depths:
            return 0

        depth = state.order_depths[symbol]

        buy_orders = dict(sorted(depth.buy_orders.items(), key=lambda x: x[0], reverse=True))
        sell_orders = dict(sorted(depth.sell_orders.items(), key=lambda x: x[0]))

        best_bid = max(buy_orders.keys()) if buy_orders else None
        best_ask = min(sell_orders.keys()) if sell_orders else None

        if best_bid is not None and best_ask is not None:
            observed_price = (best_bid + best_ask) / 2
        elif best_bid is not None:
            observed_price = best_bid
        elif best_ask is not None:
            observed_price = best_ask
        else:
            return 0

        # remove intraday drift, then infer day from the price level
        base_level = observed_price - self.PEPPER_TIMESTAMP_SLOPE * state.timestamp
        inferred_day = int(round((base_level - self.PEPPER_DAY0_BASE) / self.PEPPER_DAY_STEP))
        return inferred_day

    def get_pepper_fair_value(self, state: TradingState) -> int:
        inferred_day = self.infer_pepper_day(state)
        fair = (
            self.PEPPER_DAY0_BASE
            + self.PEPPER_DAY_STEP * inferred_day
            + self.PEPPER_TIMESTAMP_SLOPE * state.timestamp
        )
        return int(round(fair))

    def trade_pepper(self, state: TradingState) -> List[Order]:
        orders: List[Order] = []
        symbol = "INTARIAN_PEPPER_ROOT"

        if symbol not in state.order_depths:
            return orders

        fair_value = self.get_pepper_fair_value(state)

        depth = state.order_depths[symbol]
        pos = state.position.get(symbol, 0)
        limit = self.POSITION_LIMITS[symbol]

        buy_orders = dict(sorted(depth.buy_orders.items(), key=lambda x: x[0], reverse=True))
        sell_orders = dict(sorted(depth.sell_orders.items(), key=lambda x: x[0]))

        best_bid = max(buy_orders.keys()) if buy_orders else None
        best_ask = min(sell_orders.keys()) if sell_orders else None

        max_buy = limit - pos

        # 1) TAKE ALL ASKS BELOW FAIR
        for ask_price, ask_qty in sell_orders.items():
            visible = -ask_qty  # sell quantities are negative

            if max_buy <= 0:
                break

            if ask_price < fair_value:
                qty = min(visible, max_buy)
                if qty > 0:
                    orders.append(Order(symbol, ask_price, qty))
                    pos += qty
                    max_buy -= qty
            else:
                break

        # refresh after taking
        # best_bid = max(buy_orders.keys()) if buy_orders else None
        # best_ask = min(sell_orders.keys()) if sell_orders else None
        max_buy = limit - pos
        max_sell = limit + pos
        # 0) AGGRESSIVE BUY-UP TO +30 INVENTORY
        if pos < self.PEPPER_AGGRESSIVE_TARGET and max_buy > 0:
            aggressive_need = min(self.PEPPER_AGGRESSIVE_TARGET - pos, max_buy)

            for ask_price, ask_qty in sell_orders.items():
                if aggressive_need <= 0:
                    break

                visible = -ask_qty
                qty = min(visible, aggressive_need)

                if qty > 0:
                    orders.append(Order(symbol, ask_price, qty))
                    pos += qty
                    max_buy -= qty
                    aggressive_need -= qty

        # 2) MARKET MAKE ON THE ASK SIDE
        # if best_ask - 1 > fair, sell max possible there, even if not currently long
        if best_ask is not None and max_sell > 0:
            sell_price = best_ask - 1

            # do not cross the bid
            if best_bid is None or sell_price > best_bid:
                if sell_price > fair_value:
                    orders.append(Order(symbol, sell_price, -max_sell))

        # 3) MARKET MAKE ON THE BID SIDE
        # if best_bid + 1 < fair, buy max possible there
        if best_bid is not None and max_buy > 0:
            buy_price = best_bid + 1

            # do not cross the ask
            if best_ask is None or buy_price < best_ask:
                if buy_price < fair_value:
                    orders.append(Order(symbol, buy_price, max_buy))

        return orders

        
    # -------------------------
    # ASH helpers
    # -------------------------
    def ash_init_state(self, state: TradingState) -> None:
        self.ash_orders: List[Order] = []
        self.ash_symbol = "ASH_COATED_OSMIUM"
        self.ash_position_limit = self.POSITION_LIMITS[self.ash_symbol]
        self.ash_initial_position = state.position.get(self.ash_symbol, 0)
        self.ash_trade_position = 0
        self.ash_mkt_buy_orders, self.ash_mkt_sell_orders = self.ash_get_order_depth(state)
        self.ash_bid_wall, self.ash_wall_mid, self.ash_ask_wall = self.ash_get_walls()
        self.ash_mid_price = self.ash_wall_mid
        self.ash_max_allowed_buy_volume, self.ash_max_allowed_sell_volume = self.ash_get_max_allowed_volume()

    def ash_get_order_depth(self, state: TradingState) -> tuple[Dict[int, int], Dict[int, int]]:
        order_depth, buy_orders, sell_orders = {}, {}, {}

        try:
            order_depth = state.order_depths[self.ash_symbol]
        except Exception:
            pass
        try:
            order_depth = order_depth  # type: OrderDepth
            buy_orders = {
                bp: abs(bv)
                for bp, bv in sorted(order_depth.buy_orders.items(), key=lambda x: x[0], reverse=True)
            }
        except Exception:
            pass
        try:
            sell_orders = {
                sp: abs(sv)
                for sp, sv in sorted(order_depth.sell_orders.items(), key=lambda x: x[0])
            }
        except Exception:
            pass

        return buy_orders, sell_orders

    def ash_get_walls(self) -> tuple[int | None, float | None, int | None]:
        bid_wall = wall_mid = ask_wall = None

        try:
            bid_wall = min([x for x, _ in self.ash_mkt_buy_orders.items()])
        except Exception:
            pass

        try:
            ask_wall = max([x for x, _ in self.ash_mkt_sell_orders.items()])
        except Exception:
            pass

        try:
            wall_mid = (bid_wall + ask_wall) / 2
        except Exception:
            pass

        if not bid_wall:
            bid_wall = self.ash_bid_wall
        if not wall_mid:
            wall_mid = self.ash_wall_mid
        if not ask_wall:
            ask_wall =self.ash_ask_wall

        return bid_wall, wall_mid, ask_wall

    def ash_get_max_allowed_volume(self) -> tuple[int, int]:
        max_allowed_buy_volume = self.ash_position_limit - self.ash_initial_position
        max_allowed_sell_volume = self.ash_position_limit + self.ash_initial_position
        return max_allowed_buy_volume, max_allowed_sell_volume

    def ash_bid(self, price: float | int, volume: float | int) -> None:
        abs_volume = min(abs(int(volume)), self.ash_max_allowed_buy_volume)
        order = Order(self.ash_symbol, int(price), abs_volume)
        self.ash_max_allowed_buy_volume -= abs_volume
        self.ash_orders.append(order)

    def ash_ask(self, price: float | int, volume: float | int) -> None:
        abs_volume = min(abs(int(volume)), self.ash_max_allowed_sell_volume)
        order = Order(self.ash_symbol, int(price), -abs_volume)
        self.ash_max_allowed_sell_volume -= abs_volume
        self.ash_orders.append(order)

    def trade_ash_on_spread(self, state: TradingState) -> List[Order]:
        self.ash_init_state(state)

        if not self.ash_mkt_buy_orders or not self.ash_mkt_sell_orders:
            return self.ash_orders

        best_bid = max(self.ash_mkt_buy_orders)
        best_ask = min(self.ash_mkt_sell_orders)
        spread = best_ask - best_bid
        current_position = self.ash_trade_position
        # buy_size = self.ASH_SPREAD_TRADE_SIZE
        # sell_size = self.ASH_SPREAD_TRADE_SIZE
        buy_size = min(self.ASH_SPREAD_TRADE_SIZE, self.ash_mkt_sell_orders[best_ask], self.ash_max_allowed_buy_volume)
        sell_size = min(self.ASH_SPREAD_TRADE_SIZE, self.ash_mkt_buy_orders[best_bid], self.ash_max_allowed_sell_volume)

        # Let the spread leg scale up to +2 / -2 total position, one clip at a time.
        if spread == 5 and current_position < self.ASH_SPREAD_MAX_POSITION:
            target_buy_size = min(buy_size, self.ASH_SPREAD_MAX_POSITION - current_position)
            if target_buy_size > 0:
                self.ash_trade_position += 1
                self.ash_bid(best_ask, target_buy_size)

        elif spread == 7 and current_position > -self.ASH_SPREAD_MAX_POSITION:
            target_sell_size = min(sell_size, current_position + self.ASH_SPREAD_MAX_POSITION)
            if target_sell_size > 0:
                self.ash_trade_position -= 1
                self.ash_ask(best_bid, target_sell_size)

        return self.ash_orders

    def trade_ash(self, state: TradingState) -> List[Order]:
        self.ash_init_state(state)

        if self.ash_mid_price is None:
            self.ash_mid_price = 10000
        else:
            print((self.ash_ask_wall + self.ash_bid_wall) / 2)
            if self.ash_mkt_sell_orders and self.ash_mkt_buy_orders:
                self.ash_mid_price = (self.ash_ask_wall + self.ash_bid_wall) / 2

        if self.ash_bid_wall is None:
            self.ash_bid_wall = self.ash_mid_price - 8

        if self.ash_ask_wall is None:
            self.ash_ask_wall = self.ash_mid_price + 8

        bid_price = self.ash_bid_wall + 1
        ask_price = self.ash_ask_wall - 1
        print(self.ash_mid_price)

        # 1. Taking
        for sp, sv in self.ash_mkt_sell_orders.items():
            if sp <= self.ash_mid_price - 1:
                self.ash_bid(sp, sv)
                print("Taking: It's ME")
            elif sp <= self.ash_mid_price and self.ash_initial_position < 0:
                volume = min(sv, abs(self.ash_initial_position))
                self.ash_bid(sp, volume)
                print("Taking: It's ME")

        for bp, bv in self.ash_mkt_buy_orders.items():
            if bp >= self.ash_mid_price + 1:
                self.ash_ask(bp, bv)
                print("Taking: It's ME")
            elif bp >= self.ash_mid_price and self.ash_initial_position > 0:
                volume = min(bv, self.ash_initial_position)
                self.ash_ask(bp, volume)
                print("Taking: It's ME")

        # 2. Making
        for bp, bv in self.ash_mkt_buy_orders.items():
            overbidding_price = bp + 1
            if bv > 1 and overbidding_price < self.ash_mid_price:
                bid_price = max(bid_price, overbidding_price)
                break
            elif bp < self.ash_mid_price:
                bid_price = max(bid_price, bp)
                break

        for sp, sv in self.ash_mkt_sell_orders.items():
            underbidding_price = sp - 1
            if sv > 1 and underbidding_price > self.ash_mid_price:
                ask_price = min(ask_price, underbidding_price)
                break
            elif sp > self.ash_mid_price:
                ask_price = min(ask_price, sp)
                break

        self.ash_bid(bid_price, self.ash_max_allowed_buy_volume)
        self.ash_ask(ask_price, self.ash_max_allowed_sell_volume)

        return self.ash_orders
