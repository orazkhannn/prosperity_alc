from datamodel import Order, OrderDepth, TradingState
from typing import List, Dict
import json


class Trader:
    POSITION_LIMITS = {
        "ASH_COATED_OSMIUM": 80,
        "INTARIAN_PEPPER_ROOT": 80,
    }

    # =========================
    # PEPPER TREND FIT
    # from your regression
    # =========================
    PEPPER_K_CONTINUOUS = 0.001000006003413
    PEPPER_B_CONTINUOUS = 9999.987095180174947

    PEPPER_TIMESTAMP_COEF = 0.001000006003413
    PEPPER_DAY_COEF = 1000.006003413332678
    PEPPER_INTERCEPT = 11999.999102006840985

    STEP_SIZE = 100
    DAY_SPAN = 1_000_000
    DAY_MIN = -2

    # IMPORTANT:
    # if live trading starts after training days -2,-1,0,
    # then the next unseen day is day = 1
    PEPPER_START_DAY = 1

    def bid(self):
        return 15

    # -------------------------
    # traderData helpers
    # -------------------------
    def load_memory(self, traderData: str) -> dict:
        if traderData:
            try:
                return json.loads(traderData)
            except Exception:
                pass
        return {
            "pepper_day": self.PEPPER_START_DAY,
            "last_timestamp": None,
        }

    def update_memory_day(self, timestamp: int, memory: dict) -> dict:
        last_timestamp = memory.get("last_timestamp")
        pepper_day = memory.get("pepper_day", self.PEPPER_START_DAY)

        # timestamp reset means new day
        if last_timestamp is not None and timestamp < last_timestamp:
            pepper_day += 1

        memory["last_timestamp"] = timestamp
        memory["pepper_day"] = pepper_day
        return memory

    # -------------------------
    # Pepper fair value helpers
    # -------------------------
    def get_pepper_fair_value(self, day: int, timestamp: int) -> int:
        fair = (
            self.PEPPER_TIMESTAMP_COEF * timestamp
            + self.PEPPER_DAY_COEF * day
            + self.PEPPER_INTERCEPT
        )
        return int(round(fair))

    # equivalent version using continuous timestamp
    def get_pepper_fair_value_continuous(self, day: int, timestamp: int) -> int:
        continuous_timestamp = (day - self.DAY_MIN) * self.DAY_SPAN + timestamp
        fair = self.PEPPER_K_CONTINUOUS * continuous_timestamp + self.PEPPER_B_CONTINUOUS
        return int(round(fair))

    def run(self, state: TradingState):
        result: Dict[str, List[Order]] = {}

        memory = self.load_memory(state.traderData)
        memory = self.update_memory_day(state.timestamp, memory)

        result["ASH_COATED_OSMIUM"] = self.trade_ash(state)
        result["INTARIAN_PEPPER_ROOT"] = self.trade_pepper(state, memory["pepper_day"])

        traderData = json.dumps(memory)
        conversions = 0
        return result, conversions, traderData

    def trade_pepper(self, state: TradingState, pepper_day: int) -> List[Order]:
        orders: List[Order] = []
        symbol = "INTARIAN_PEPPER_ROOT"

        if symbol not in state.order_depths:
            return orders

        fair_value = self.get_pepper_fair_value(pepper_day, state.timestamp)
        # or:
        # fair_value = self.get_pepper_fair_value_continuous(pepper_day, state.timestamp)

        depth = state.order_depths[symbol]
        pos = state.position.get(symbol, 0)
        limit = self.POSITION_LIMITS[symbol]

        buy_orders = dict(sorted(depth.buy_orders.items(), key=lambda x: x[0], reverse=True))
        sell_orders = dict(sorted(depth.sell_orders.items(), key=lambda x: x[0]))

        max_buy = limit - pos
        max_sell = limit + pos

        # -------------------------
        # 1. TAKING
        # -------------------------
        for ask_price, ask_qty in sell_orders.items():
            visible = -ask_qty
            if max_buy <= 0:
                break

            if ask_price <= fair_value - 1:
                qty = min(visible, max_buy)
                if qty > 0:
                    orders.append(Order(symbol, ask_price, qty))
                    max_buy -= qty
                    pos += qty

            elif ask_price <= fair_value and pos < 0:
                qty = min(visible, -pos, max_buy)
                if qty > 0:
                    orders.append(Order(symbol, ask_price, qty))
                    max_buy -= qty
                    pos += qty

        for bid_price, bid_qty in buy_orders.items():
            if max_sell <= 0:
                break

            if bid_price >= fair_value + 1:
                qty = min(bid_qty, max_sell)
                if qty > 0:
                    orders.append(Order(symbol, bid_price, -qty))
                    max_sell -= qty
                    pos -= qty

            elif bid_price >= fair_value and pos > 0:
                qty = min(bid_qty, pos, max_sell)
                if qty > 0:
                    orders.append(Order(symbol, bid_price, -qty))
                    max_sell -= qty
                    pos -= qty

        # -------------------------
        # 2. MAKING / PENNY-JUMPING
        # -------------------------
        if buy_orders and sell_orders:
            bid_wall = min(buy_orders.keys())
            ask_wall = max(sell_orders.keys())

            bid_price = int(bid_wall + 1)
            ask_price = int(ask_wall - 1)

            for bp, bv in buy_orders.items():
                overbid_price = bp + 1
                if bv > 1 and overbid_price < fair_value:
                    bid_price = max(bid_price, overbid_price)
                    break
                elif bp < fair_value:
                    bid_price = max(bid_price, bp)
                    break

            for sp, sv in sell_orders.items():
                undercut_price = sp - 1
                if abs(sv) > 1 and undercut_price > fair_value:
                    ask_price = min(ask_price, undercut_price)
                    break
                elif sp > fair_value:
                    ask_price = min(ask_price, sp)
                    break

            if max_buy > 0:
                orders.append(Order(symbol, bid_price, max_buy))
            if max_sell > 0:
                orders.append(Order(symbol, ask_price, -max_sell))

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

        if self.ash_mid_price is not None:
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

            bid_price = int(self.ash_bid_wall + 1)
            ask_price = int(self.ash_ask_wall - 1)

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
