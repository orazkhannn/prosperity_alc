from datamodel import OrderDepth, UserId, TradingState, Order
from typing import List
import string
import json

class Trader:

    def __init__(self):
        self.LIMITS = {
            "ASH_COATED_OSMIUM": 80,
            "INTARIAN_PEPPER_ROOT": 80
        }
        self.PEPPER_CORE_LONG = 40
        self.orderbook = {"INTARIAN_PEPPER_ROOT": OrderDepth(), "ASH_COATED_OSMIUM": OrderDepth()}
        self.pepper_init_price = 0
        self.found_pepper_init_price = False

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
        bid_prce = 0
        ask_price = 0

        if key == "ASH_COATED_OSMIUM":
            bid_price = bid_max + 1
            ask_price = ask_min - 1

        return result
    
    def trade_ash(self, state: TradingState):
        buy_orders = self.orderbook["ASH_COATED_OSMIUM"].buy_orders
        sell_orders = self.orderbook["ASH_COATED_OSMIUM"].sell_orders

        if not (buy_orders and sell_orders):
            return []

        curr_position = state.position.get("ASH_COATED_OSMIUM", 0)

        bid_max = max([x for x in buy_orders])
        ask_min = min([x for x in sell_orders])
        price_mid = (bid_max + ask_min) / 2

        bid_wall = min([x for x in buy_orders])
        ask_wall = max([x for x in sell_orders])
        wall_mid = (bid_wall + ask_wall) / 2

        max_allowed_bid_position = self.LIMITS["ASH_COATED_OSMIUM"] - curr_position
        max_allowed_ask_position = -self.LIMITS["ASH_COATED_OSMIUM"] - curr_position

        result = []

        bid_prce = 0
        ask_price = 0

        bid_price = bid_max + 1
        ask_price = ask_min - 1

        result.append(Order("ASH_COATED_OSMIUM", bid_price, min(max_allowed_bid_position, 100)))
        result.append(Order("ASH_COATED_OSMIUM", ask_price, max(max_allowed_ask_position, -100)))

        return result
    

    def calculate_fair(self, timestamp):
        return int(self.pepper_init_price + 0.001*timestamp)

    def trade_pepper(self, state: TradingState):
        key = "INTARIAN_PEPPER_ROOT"
        buy_orders = self.orderbook[key].buy_orders
        sell_orders = self.orderbook[key].sell_orders
        timestamp = state.timestamp

        if not (buy_orders and sell_orders):
            return []

        curr_position = state.position.get(key, 0)
        max_position = self.LIMITS[key]
        protected_long = min(self.PEPPER_CORE_LONG, max_position)
        result = []

        best_bid = max([x for x in buy_orders])
        best_ask = min([x for x in sell_orders])
        bid_wall = min([x for x in buy_orders])
        ask_wall = max([x for x in sell_orders])
        wall_mid = (bid_wall + ask_wall) / 2
        if buy_orders and sell_orders:
            if not self.found_pepper_init_price:
                self.pepper_init_price = wall_mid
                self.found_pepper_init_price = True
        elif not self.found_pepper_init_price:
            return []

        fv = self.calculate_fair(timestamp)

        core_shortfall = max(0, protected_long - curr_position)
        buy_capacity = max_position - curr_position

        # Build the protected +40 inventory quickly by lifting visible asks.
        if core_shortfall > 0:
            for ask_price in sorted(sell_orders):
                ask_volume = -sell_orders[ask_price]
                if ask_volume <= 0:
                    continue

                take_size = min(core_shortfall, buy_capacity, ask_volume)
                if take_size <= 0:
                    break

                result.append(Order(key, ask_price, take_size))
                core_shortfall -= take_size
                buy_capacity -= take_size

                if core_shortfall == 0 or buy_capacity == 0:
                    break

        position_after_core = curr_position + (max_position - curr_position - buy_capacity)
        mm_bid_capacity = max(0, max_position - position_after_core)
        mm_ask_capacity = max(0, position_after_core - protected_long)

        bid_price = bid_wall + 1
        ask_price = ask_wall - 1

        for bp, bv in buy_orders.items():
            overbidding_price = bp + 1
            if bv > 1 and overbidding_price < fv:
                bid_price = max(bid_price, overbidding_price)
                break
            elif bp < fv:
                bid_price = max(bid_price, bp)
                break

        for sp, sv in sell_orders.items():
            underbidding_price = sp - 1
            if sv > 1 and underbidding_price > fv:
                ask_price = min(ask_price, underbidding_price)
                break
            elif sp > fv:
                ask_price = min(ask_price, sp)
                break

        if mm_bid_capacity > 0:
            result.append(Order(key, bid_price, min(mm_bid_capacity, 100)))

        if mm_ask_capacity > 0:
            result.append(Order(key, ask_price, -min(mm_ask_capacity, 100)))

        return result

    def run(self, state: TradingState):
        self.preprocess_state(state)
        self.logger_print(state)

        ash_coated_osmium_orders = self.trade_ash(state)
        intarian_pepper_root_orders = self.trade_pepper(state)

        result = {"ASH_COATED_OSMIUM": ash_coated_osmium_orders, "INTARIAN_PEPPER_ROOT": intarian_pepper_root_orders}
        traderData = "SAMPLE"
        conversions = 1
        return result, conversions, traderData
