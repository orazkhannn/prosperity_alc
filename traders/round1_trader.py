from datamodel import Order, TradingState
from typing import List, Dict
import json

class Trader:

    def bid(self):
        return 15
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

        result["ASH_COATED_OSMIUM"] = self.trade_ash(state)
        result["INTARIAN_PEPPER_ROOT"] = self.trade_pepper(state)

        traderData = ""
        conversions = 0
        return result, conversions, traderData
    

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

    def trade_ash(self, state: TradingState) -> List[Order]:
        self.ash_init_state(state)

        if self.ash_mid_price is None:
            self.ash_mid_price = 10000

        if self.ash_bid_wall is None:
            self.ash_bid_wall = self.ash_mid_price - 8

        if self.ash_ask_wall is None:
            self.ash_ask_wall = self.ash_mid_price + 8

        bid_price = self.ash_bid_wall + 1
        ask_price = self.ash_ask_wall - 1

        # 1. Taking
        for sp, sv in self.ash_mkt_sell_orders.items():
            if sp <= self.ash_mid_price - 1:
                self.ash_bid(sp, sv)
            elif sp <= self.ash_mid_price and self.ash_initial_position < 0:
                volume = min(sv, abs(self.ash_initial_position))
                self.ash_bid(sp, volume)

        for bp, bv in self.ash_mkt_buy_orders.items():
            if bp >= self.ash_mid_price + 1:
                self.ash_ask(bp, bv)
            elif bp >= self.ash_mid_price and self.ash_initial_position > 0:
                volume = min(bv, self.ash_initial_position)
                self.ash_ask(bp, volume)

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