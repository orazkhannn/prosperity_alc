from datamodel import OrderDepth, UserId, TradingState, Order
from typing import List
import string


class Trader:

    ASH_STUB_MAX_VOLUME = 9
    ASH_STUB_MIN_GAP = 5
    ASH_BASE_ORDER_SIZE = 12
    ASH_NEUTRAL_ORDER_SIZE = 8
    ASH_EXTREME_ORDER_SIZE = 18

    def __init__(self):
        self.LIMITS = {
            "ASH_COATED_OSMIUM": 80,
            "INTARIAN_PEPPER_ROOT": 80
        }
        self.orderbook = {"INTARIAN_PEPPER_ROOT": OrderDepth(), "ASH_COATED_OSMIUM": OrderDepth()}

    def _second_best_bid(self, buy_orders):
        if len(buy_orders) < 2:
            return None
        prices = sorted(buy_orders.keys(), reverse=True)
        return prices[1], buy_orders[prices[1]]

    def _second_best_ask(self, sell_orders):
        if len(sell_orders) < 2:
            return None
        prices = sorted(sell_orders.keys())
        return prices[1], sell_orders[prices[1]]

    def _ash_stub_signal(self, buy_orders, sell_orders):
        second_bid = self._second_best_bid(buy_orders)
        second_ask = self._second_best_ask(sell_orders)

        best_bid = max(buy_orders) if buy_orders else None
        best_ask = min(sell_orders) if sell_orders else None

        bid_stub = False
        ask_stub = False
        effective_bid = best_bid
        effective_ask = best_ask

        if best_bid is not None and second_bid is not None:
            bid_gap12 = best_bid - second_bid[0]
            bid_stub = (
                buy_orders[best_bid] <= self.ASH_STUB_MAX_VOLUME
                and bid_gap12 >= self.ASH_STUB_MIN_GAP
            )
            if bid_stub:
                effective_bid = second_bid[0]

        if best_ask is not None and second_ask is not None:
            ask_gap12 = second_ask[0] - best_ask
            ask_stub = (
                sell_orders[best_ask] <= self.ASH_STUB_MAX_VOLUME
                and ask_gap12 >= self.ASH_STUB_MIN_GAP
            )
            if ask_stub:
                effective_ask = second_ask[0]

        return effective_bid, effective_ask, bid_stub, ask_stub

    def ash_gap_tilt_signal(self, buy_orders, sell_orders):
        second_bid = self._second_best_bid(buy_orders)
        second_ask = self._second_best_ask(sell_orders)
        if second_bid is None or second_ask is None:
            return 0

        best_bid = max(buy_orders)
        best_ask = min(sell_orders)
        bid_gap12 = best_bid - second_bid[0]
        ask_gap12 = second_ask[0] - best_ask
        gap_tilt = ask_gap12 - bid_gap12

        return gap_tilt

    def _level_count(self, orders):
        return min(3, len(orders))

    def _ash_signal_score(self, raw_buy_orders, raw_sell_orders):
        bid_levels = self._level_count(raw_buy_orders)
        ask_levels = self._level_count(raw_sell_orders)
        levels = (bid_levels, ask_levels)

        score = 0
        notes = []

        if bid_levels > 0 and ask_levels == 0:
            score += 4
            notes.append("bid_only")
        elif ask_levels > 0 and bid_levels == 0:
            score -= 4
            notes.append("ask_only")

        if levels in {(1, 0), (2, 0)}:
            score += 3
            notes.append("thin_ask_side")
        elif levels in {(0, 1), (0, 2)}:
            score -= 3
            notes.append("thin_bid_side")
        elif levels in {(1, 3), (2, 3)}:
            score += 2
            notes.append("deeper_ask_stack")
        elif levels in {(3, 1), (3, 2)}:
            score -= 2
            notes.append("deeper_bid_stack")

        if bid_levels >= 2 and ask_levels >= 2:
            best_bid = max(raw_buy_orders)
            best_ask = min(raw_sell_orders)
            second_bid = self._second_best_bid(raw_buy_orders)
            second_ask = self._second_best_ask(raw_sell_orders)

            if second_bid is not None and second_ask is not None:
                bid_gap = best_bid - second_bid[0]
                ask_gap = second_ask[0] - best_ask
                shape = (best_ask - best_bid, bid_gap, ask_gap)

                if bid_gap < ask_gap:
                    score += 1
                    notes.append("bid_denser")
                elif bid_gap > ask_gap:
                    score -= 1
                    notes.append("ask_denser")

                bullish_shapes = {(5, 3, 11), (6, 2, 10), (9, 3, 7), (10, 2, 6)}
                bearish_shapes = {(6, 10, 3), (7, 3, 2), (10, 6, 3), (11, 5, 2)}

                if shape in bullish_shapes:
                    score += 2
                    notes.append(f"bull_shape_{shape}")
                elif shape in bearish_shapes:
                    score -= 2
                    notes.append(f"bear_shape_{shape}")

        return score, levels, notes

    def _ash_quote_plan(self, state: TradingState, curr_position, buy_orders, sell_orders):
        raw_depth = state.order_depths["ASH_COATED_OSMIUM"]
        raw_buy_orders = raw_depth.buy_orders
        raw_sell_orders = raw_depth.sell_orders

        effective_bid, effective_ask, bid_stub, ask_stub = self._ash_stub_signal(
            buy_orders, sell_orders
        )
        effective_spread = effective_ask - effective_bid

        if effective_spread >= 2:
            base_bid = effective_bid + 1
            base_ask = effective_ask - 1
        else:
            base_bid = effective_bid
            base_ask = effective_ask

        score, levels, notes = self._ash_signal_score(raw_buy_orders, raw_sell_orders)

        inventory_penalty = curr_position // 20
        adjusted_score = score - inventory_penalty

        bid_shift = 0
        ask_shift = 0
        bid_size = min(self.LIMITS["ASH_COATED_OSMIUM"] - curr_position, self.ASH_NEUTRAL_ORDER_SIZE)
        ask_size = min(self.LIMITS["ASH_COATED_OSMIUM"] + curr_position, self.ASH_NEUTRAL_ORDER_SIZE)

        post_only_gap = max(1, effective_spread - 1)

        if adjusted_score >= 5:
            bid_shift = min(2, max(0, post_only_gap))
            ask_shift = 2
            bid_size = min(self.LIMITS["ASH_COATED_OSMIUM"] - curr_position, self.ASH_EXTREME_ORDER_SIZE)
            ask_size = 0
        elif adjusted_score >= 3:
            bid_shift = min(1, max(0, post_only_gap))
            ask_shift = 1
            bid_size = min(self.LIMITS["ASH_COATED_OSMIUM"] - curr_position, self.ASH_BASE_ORDER_SIZE + 4)
            ask_size = min(self.LIMITS["ASH_COATED_OSMIUM"] + curr_position, 4)
        elif adjusted_score >= 1:
            bid_shift = 1 if effective_spread >= 3 else 0
            ask_shift = 0
            bid_size = min(self.LIMITS["ASH_COATED_OSMIUM"] - curr_position, self.ASH_BASE_ORDER_SIZE)
            ask_size = min(self.LIMITS["ASH_COATED_OSMIUM"] + curr_position, 6)
        elif adjusted_score <= -5:
            bid_shift = -2
            ask_shift = -min(2, max(0, post_only_gap))
            bid_size = 0
            ask_size = min(self.LIMITS["ASH_COATED_OSMIUM"] + curr_position, self.ASH_EXTREME_ORDER_SIZE)
        elif adjusted_score <= -3:
            bid_shift = -1
            ask_shift = -min(1, max(0, post_only_gap))
            bid_size = min(self.LIMITS["ASH_COATED_OSMIUM"] - curr_position, 4)
            ask_size = min(self.LIMITS["ASH_COATED_OSMIUM"] + curr_position, self.ASH_BASE_ORDER_SIZE + 4)
        elif adjusted_score <= -1:
            bid_shift = 0
            ask_shift = -1 if effective_spread >= 3 else 0
            bid_size = min(self.LIMITS["ASH_COATED_OSMIUM"] - curr_position, 6)
            ask_size = min(self.LIMITS["ASH_COATED_OSMIUM"] + curr_position, self.ASH_BASE_ORDER_SIZE)

        bid_price = min(base_bid + bid_shift, effective_ask - 1)
        ask_price = max(base_ask + ask_shift, effective_bid + 1)

        if bid_price >= ask_price:
            bid_price = min(base_bid, effective_ask - 1)
            ask_price = max(base_ask, effective_bid + 1)

        if bid_stub:
            bid_size = min(bid_size, self.ASH_BASE_ORDER_SIZE)
        if ask_stub:
            ask_size = min(ask_size, self.ASH_BASE_ORDER_SIZE)

        return bid_price, ask_price, bid_size, ask_size, adjusted_score, levels, notes

    def logger_print(self, state: TradingState):
        print("OrderDepth after ffil vs before:")
        for key in self.orderbook:
            print(f"{key}: buy_order: {str(self.orderbook[key].buy_orders)}, sell_orders: {str(self.orderbook[key].sell_orders)}")
            print(f"{key}: buy_order: {str(state.order_depths[key].buy_orders)}, sell_orders: {str(state.order_depths[key].sell_orders)}")

        print("-------------------------------------------------------------------------")

        print("own_trades: ")
        for key in state.own_trades:
            trades = [{"symbol": trade.symbol, "price": trade.price, "quantity": trade.quantity, "buyer": trade.buyer, "seller": trade.seller, "timestamp": trade.timestamp} for trade in state.own_trades[key]]
            print(f"{key}: {trades}")

        print("-------------------------------------------------------------------------")

        print("market_trades: ")
        for key in state.market_trades:
            trades = [{"symbol": trade.symbol, "price": trade.price, "quantity": trade.quantity, "buyer": trade.buyer, "seller": trade.seller, "timestamp": trade.timestamp} for trade in state.market_trades[key]]
            print(f"{key}: {trades}")

    def preprocess_state(self, state: TradingState):
        # Forward Filling logic for missing bid_ask
        order_depths = state.order_depths
        for key in order_depths:
            buy_orders = order_depths[key].buy_orders
            sell_orders = order_depths[key].sell_orders
            buy_prices = [x for x in buy_orders]
            sell_prices = [x for x in sell_orders]
            order_depth = OrderDepth()
            if buy_prices and sell_prices:
                order_depth.buy_orders = buy_orders
                order_depth.sell_orders = sell_orders
                self.orderbook[key] = order_depth
            elif sell_prices:
                order_depth.buy_orders = self.orderbook[key].buy_orders
                order_depth.sell_orders = sell_orders
                self.orderbook[key] = order_depth
            elif buy_prices:
                order_depth.buy_orders = buy_orders
                order_depth.sell_orders = self.orderbook[key].sell_orders
                self.orderbook[key] = order_depth

    def mm_strategy(self, state: TradingState, key):
        buy_orders = self.orderbook[key].buy_orders
        sell_orders = self.orderbook[key].sell_orders

        if not (buy_orders and sell_orders):
            return []

        curr_position = state.position.get(key, 0)

        bid_max = max([x for x in buy_orders])
        ask_min = min([x for x in sell_orders])
        price_mid = (bid_max + ask_min) / 2

        bid_wall = min([x for x in buy_orders])
        ask_wall = max([x for x in sell_orders])
        wall_mid = (bid_wall + ask_wall) / 2

        max_allowed_bid_position = self.LIMITS[key] - curr_position
        max_allowed_ask_position = -self.LIMITS[key] - curr_position

        result = []

        #######################################################
        ################# Market Making #######################
        #######################################################
        bid_price = 0
        ask_price = 0
        bid_tilt_vol = 0
        ask_tilt_vol = 0
        vol = 0

        if key == "ASH_COATED_OSMIUM":
            bid_price, ask_price, bid_size, ask_size, score, levels, notes = self._ash_quote_plan(
                state, curr_position, buy_orders, sell_orders
            )
            bid_tilt_vol = min(max_allowed_bid_position, bid_size)
            ask_tilt_vol = -min(-max_allowed_ask_position, ask_size)

            print(
                f"ASH signal score={score}, levels={levels}, notes={notes}, "
                f"quotes=({bid_price}, {ask_price}), sizes=({bid_tilt_vol}, {ask_tilt_vol})"
            )

        elif key in ("INTARIAN_PEPPER_ROOT"):
            bid_price = bid_wall + 1
            ask_price = ask_wall - 1

            for bp, bv in buy_orders.items():
                overbidding_price = bp + 1
                if bv > 1 and overbidding_price < wall_mid:
                    bid_price = max(bid_price, overbidding_price)
                    break
                elif bp < wall_mid:
                    bid_price = max(bid_price, bp)
                    break

            for sp, sv in sell_orders.items():
                underbidding_price = sp - 1
                if sv > 1 and underbidding_price > wall_mid:
                    ask_price = min(ask_price, underbidding_price)
                    break
                elif sp > wall_mid:
                    ask_price = min(ask_price, sp)
                    break

        if bid_tilt_vol > 0:
            result.append(Order(key, bid_price, bid_tilt_vol))
        if ask_tilt_vol < 0:
            result.append(Order(key, ask_price, ask_tilt_vol))

        return result

    def mr_strategy(self, state: TradingState, key):
        buy_orders = self.orderbook[key].buy_orders
        sell_orders = self.orderbook[key].sell_orders

        curr_position = state.position.get(key, 0)

        fp = 1e4

        max_allowed_bid_position = self.LIMITS[key] - curr_position
        max_allowed_ask_position = -self.LIMITS[key] - curr_position

        result = []

        for sp, sv in sell_orders.items():
            if sp < fp:
                result.append(Order(key, sp, min(max_allowed_bid_position, -sv)))
            elif sp <= fp and curr_position < 0:
                result.append(Order(key, sp, min(-sv, abs(curr_position))))

        for bp, bv in buy_orders.items():
            if bp > fp:
                result.append(Order(key, bp, max(max_allowed_ask_position, -bp)))
            elif bp >= fp and curr_position > 0:
                result.append(Order(key, bp, -min(bv, curr_position)))

        return result

    def trade_ash(self, state: TradingState):
        return self.mm_strategy(state, "ASH_COATED_OSMIUM")
    # + self.mr_strategy(state, "ASH_COATED_OSMIUM")
        # return self.mr_strategy(state, "ASH_COATED_OSMIUM")

    def trade_pepper(self, state: TradingState):
        # return self.mm_strategy(state, "INTARIAN_PEPPER_ROOT")
        return []

    def run(self, state: TradingState):
        self.preprocess_state(state)
        self.logger_print(state)

        ash_coated_osmium_orders = self.trade_ash(state)
        intarian_pepper_root_orders = self.trade_pepper(state)

        result = {"ASH_COATED_OSMIUM": ash_coated_osmium_orders, "INTARIAN_PEPPER_ROOT": intarian_pepper_root_orders}
        traderData = "SAMPLE"
        conversions = 1
        return result, conversions, traderData
