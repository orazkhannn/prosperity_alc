from datamodel import OrderDepth, UserId, TradingState, Order
from typing import List
import string
import os


class Trader:

    ENABLE_SIGNAL_1_ONE_SIDED = False
    ENABLE_SIGNAL_2_LEVEL_COUNT = False
    ENABLE_SIGNAL_3_LADDER = False
    ENABLE_SIGNAL_4_SHAPE = False

    ASH_BASE_ORDER_SIZE = 12
    ASH_LIGHT_SKEW_ORDER_SIZE = 14
    ASH_SKEW_ORDER_SIZE = 16
    ASH_SHAPE_ORDER_SIZE = 18
    ASH_EXTREME_ORDER_SIZE = 20

    def __init__(self):
        self.LIMITS = {
            "ASH_COATED_OSMIUM": 80,
            "INTARIAN_PEPPER_ROOT": 80
        }

    def logger_print(self, state: TradingState):
        print("OrderDepth raw state:")
        for key in state.order_depths:
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

    def _ash_one_sided_signal(self, state: TradingState):
        if not self.ENABLE_SIGNAL_1_ONE_SIDED:
            return "two_sided"

        raw_depth = state.order_depths["ASH_COATED_OSMIUM"]
        raw_buy_orders = raw_depth.buy_orders
        raw_sell_orders = raw_depth.sell_orders

        if raw_buy_orders and not raw_sell_orders:
            return "bid_only"
        if raw_sell_orders and not raw_buy_orders:
            return "ask_only"
        return "two_sided"

    def _ash_level_count_signal(self, state: TradingState):
        if not self.ENABLE_SIGNAL_2_LEVEL_COUNT:
            raw_depth = state.order_depths["ASH_COATED_OSMIUM"]
            bid_levels = min(3, len(raw_depth.buy_orders))
            ask_levels = min(3, len(raw_depth.sell_orders))
            return "balanced_depth", (bid_levels, ask_levels)

        raw_depth = state.order_depths["ASH_COATED_OSMIUM"]
        bid_levels = min(3, len(raw_depth.buy_orders))
        ask_levels = min(3, len(raw_depth.sell_orders))
        levels = (bid_levels, ask_levels)

        if levels in {(1, 3), (2, 3)}:
            return "bullish_depth_imbalance", levels
        if levels in {(3, 1), (3, 2)}:
            return "bearish_depth_imbalance", levels
        return "balanced_depth", levels

    def _ash_ladder_signal(self, state: TradingState):
        if not self.ENABLE_SIGNAL_3_LADDER:
            return "ladder_disabled", None, None

        raw_depth = state.order_depths["ASH_COATED_OSMIUM"]
        buy_prices = sorted(raw_depth.buy_orders.keys(), reverse=True)
        sell_prices = sorted(raw_depth.sell_orders.keys())

        if len(buy_prices) < 2 or len(sell_prices) < 2:
            return "ladder_unavailable", None, None

        best_bid = buy_prices[0]
        second_bid = buy_prices[1]
        best_ask = sell_prices[0]
        second_ask = sell_prices[1]

        bid_gap = best_bid - second_bid
        ask_gap = second_ask - best_ask

        if bid_gap < ask_gap:
            return "bullish_ladder", bid_gap, ask_gap
        if bid_gap > ask_gap:
            return "bearish_ladder", bid_gap, ask_gap
        return "flat_ladder", bid_gap, ask_gap

    def _ash_shape_signal(self, state: TradingState):
        if not self.ENABLE_SIGNAL_4_SHAPE:
            return "shape_disabled", None

        raw_depth = state.order_depths["ASH_COATED_OSMIUM"]
        buy_prices = sorted(raw_depth.buy_orders.keys(), reverse=True)
        sell_prices = sorted(raw_depth.sell_orders.keys())

        if len(buy_prices) < 2 or len(sell_prices) < 2:
            return "shape_unavailable", None

        best_bid = buy_prices[0]
        second_bid = buy_prices[1]
        best_ask = sell_prices[0]
        second_ask = sell_prices[1]

        spread = best_ask - best_bid
        bid_gap = best_bid - second_bid
        ask_gap = second_ask - best_ask
        shape = (spread, bid_gap, ask_gap)

        bullish_shapes = {(5, 3, 11), (6, 2, 10), (9, 3, 7), (10, 2, 6)}
        bearish_shapes = {(6, 10, 3), (7, 3, 2), (10, 6, 3), (11, 5, 2)}

        if shape in bullish_shapes:
            return "bullish_shape", shape
        if shape in bearish_shapes:
            return "bearish_shape", shape
        return "shape_neutral", shape

    def _ash_quote_plan(self, state: TradingState, curr_position: int):
        raw_depth = state.order_depths["ASH_COATED_OSMIUM"]
        buy_orders = raw_depth.buy_orders
        sell_orders = raw_depth.sell_orders

        max_allowed_bid_position = self.LIMITS["ASH_COATED_OSMIUM"] - curr_position
        max_allowed_ask_position = self.LIMITS["ASH_COATED_OSMIUM"] + curr_position

        signal = self._ash_one_sided_signal(state)
        depth_signal, levels = self._ash_level_count_signal(state)
        shape_signal, shape = self._ash_shape_signal(state)
        ladder_signal, bid_gap, ask_gap = self._ash_ladder_signal(state)

        if signal == "bid_only":
            best_bid = max(buy_orders)
            bid_price = best_bid + 1
            ask_price = 0
            bid_size = min(max_allowed_bid_position, self.ASH_EXTREME_ORDER_SIZE)
            ask_size = 0
            return signal, levels, shape_signal, shape, ladder_signal, bid_gap, ask_gap, bid_price, ask_price, bid_size, ask_size

        if signal == "ask_only":
            best_ask = min(sell_orders)
            bid_price = 0
            ask_price = best_ask - 1
            bid_size = 0
            ask_size = min(max_allowed_ask_position, self.ASH_EXTREME_ORDER_SIZE)
            return signal, levels, shape_signal, shape, ladder_signal, bid_gap, ask_gap, bid_price, ask_price, bid_size, ask_size

        if not (buy_orders and sell_orders):
            return None

        best_bid = max(buy_orders)
        best_ask = min(sell_orders)
        spread = best_ask - best_bid

        if spread >= 2:
            bid_price = best_bid + 1
            ask_price = best_ask - 1
        else:
            bid_price = best_bid
            ask_price = best_ask

        bid_size = min(max_allowed_bid_position, self.ASH_BASE_ORDER_SIZE)
        ask_size = min(max_allowed_ask_position, self.ASH_BASE_ORDER_SIZE)

        signal = depth_signal

        if depth_signal == "bullish_depth_imbalance":
            if spread >= 3:
                bid_price = min(best_bid + 1, best_ask - 1)
            bid_size = min(max_allowed_bid_position, self.ASH_SKEW_ORDER_SIZE)
            ask_size = min(max_allowed_ask_position, 6)
        elif depth_signal == "bearish_depth_imbalance":
            if spread >= 3:
                ask_price = max(best_ask - 1, best_bid + 1)
            bid_size = min(max_allowed_bid_position, 6)
            ask_size = min(max_allowed_ask_position, self.ASH_SKEW_ORDER_SIZE)
        elif shape_signal == "bullish_shape":
            if spread >= 3:
                bid_price = min(best_bid + 1, best_ask - 1)
            bid_size = min(max_allowed_bid_position, self.ASH_SHAPE_ORDER_SIZE)
            ask_size = min(max_allowed_ask_position, 5)
            signal = shape_signal
        elif shape_signal == "bearish_shape":
            if spread >= 3:
                ask_price = max(best_ask - 1, best_bid + 1)
            bid_size = min(max_allowed_bid_position, 5)
            ask_size = min(max_allowed_ask_position, self.ASH_SHAPE_ORDER_SIZE)
            signal = shape_signal
        elif ladder_signal == "bullish_ladder":
            if spread >= 3:
                bid_price = min(best_bid + 1, best_ask - 1)
            bid_size = min(max_allowed_bid_position, self.ASH_LIGHT_SKEW_ORDER_SIZE)
            ask_size = min(max_allowed_ask_position, 8)
            signal = ladder_signal
        elif ladder_signal == "bearish_ladder":
            if spread >= 3:
                ask_price = max(best_ask - 1, best_bid + 1)
            bid_size = min(max_allowed_bid_position, 8)
            ask_size = min(max_allowed_ask_position, self.ASH_LIGHT_SKEW_ORDER_SIZE)
            signal = ladder_signal

        return signal, levels, shape_signal, shape, ladder_signal, bid_gap, ask_gap, bid_price, ask_price, bid_size, ask_size

    def mm_strategy(self, state: TradingState, key):
        buy_orders = state.order_depths[key].buy_orders
        sell_orders = state.order_depths[key].sell_orders

        curr_position = state.position.get(key, 0)

        result = []

        #######################################################
        ################# Market Making #######################
        #######################################################
        bid_price = 0
        ask_price = 0

        if key == "ASH_COATED_OSMIUM":
            plan = self._ash_quote_plan(state, curr_position)
            if plan is None:
                return []

            signal, levels, shape_signal, shape, ladder_signal, bid_gap, ask_gap, bid_price, ask_price, bid_size, ask_size = plan

            print(
                f"ASH structural step4 signal={signal}, levels={levels}, "
                f"shape={shape_signal}, pattern={shape}, "
                f"ladder={ladder_signal}, gaps=({bid_gap}, {ask_gap}), "
                f"quotes=({bid_price}, {ask_price}), sizes=({bid_size}, {-ask_size})"
            )

            if bid_size > 0:
                result.append(Order(key, bid_price, bid_size))
            if ask_size > 0:
                result.append(Order(key, ask_price, -ask_size))
            return result

        elif key == "INTARIAN_PEPPER_ROOT":
            if not (buy_orders and sell_orders):
                return []

            bid_wall = min([x for x in buy_orders])
            ask_wall = max([x for x in sell_orders])
            wall_mid = (bid_wall + ask_wall) / 2
            max_allowed_bid_position = self.LIMITS[key] - curr_position
            max_allowed_ask_position = -self.LIMITS[key] - curr_position
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

        result.append(Order(key, bid_price, max_allowed_bid_position))
        result.append(Order(key, ask_price, max_allowed_ask_position))

        return result

    def trade_ash(self, state: TradingState):
        return self.mm_strategy(state, "ASH_COATED_OSMIUM")

    def trade_pepper(self, state: TradingState):
        # return self.mm_strategy(state, "INTARIAN_PEPPER_ROOT")
        return []

    def run(self, state: TradingState):
        self.logger_print(state)

        ash_coated_osmium_orders = self.trade_ash(state)
        intarian_pepper_root_orders = self.trade_pepper(state)

        result = {"ASH_COATED_OSMIUM": ash_coated_osmium_orders, "INTARIAN_PEPPER_ROOT": intarian_pepper_root_orders}
        traderData = "ASH_STRUCTURAL_STEP4"
        conversions = 1
        return result, conversions, traderData
