from datamodel import Order, TradingState  # type: ignore
from typing import Dict, List


class Trader:
    POSITION_LIMIT = 10
    BASE_SIZE = 2
    AVG_SPREAD = {
        "GALAXY_SOUNDS_BLACK_HOLES": 14.513,
        "GALAXY_SOUNDS_DARK_MATTER": 13.051,
        "GALAXY_SOUNDS_PLANETARY_RINGS": 13.69,
        "GALAXY_SOUNDS_SOLAR_FLAMES": 14.072,
        "GALAXY_SOUNDS_SOLAR_WINDS": 13.301,
        "MICROCHIP_CIRCLE": 8.262,
        "MICROCHIP_OVAL": 7.45,
        "MICROCHIP_RECTANGLE": 7.886,
        "MICROCHIP_SQUARE": 11.719,
        "MICROCHIP_TRIANGLE": 8.635,
        "OXYGEN_SHAKE_CHOCOLATE": 12.185,
        "OXYGEN_SHAKE_EVENING_BREATH": 11.86,
        "OXYGEN_SHAKE_GARLIC": 15.055,
        "OXYGEN_SHAKE_MINT": 12.594,
        "OXYGEN_SHAKE_MORNING_BREATH": 12.783,
        "PANEL_1X2": 11.51,
        "PANEL_1X4": 8.377,
        "PANEL_2X2": 8.515,
        "PANEL_2X4": 9.84,
        "PANEL_4X4": 8.75,
        "PEBBLES_L": 13.02,
        "PEBBLES_M": 13.121,
        "PEBBLES_S": 11.552,
        "PEBBLES_XL": 16.631,
        "PEBBLES_XS": 9.745,
        "ROBOT_DISHES": 7.35,
        "ROBOT_IRONING": 6.393,
        "ROBOT_LAUNDRY": 7.165,
        "ROBOT_MOPPING": 7.971,
        "ROBOT_VACUUMING": 6.753,
        "SLEEP_POD_COTTON": 10.05,
        "SLEEP_POD_LAMB_WOOL": 9.4,
        "SLEEP_POD_NYLON": 8.565,
        "SLEEP_POD_POLYESTER": 10.296,
        "SLEEP_POD_SUEDE": 9.949,
        "SNACKPACK_CHOCOLATE": 16.471,
        "SNACKPACK_PISTACHIO": 15.926,
        "SNACKPACK_RASPBERRY": 16.842,
        "SNACKPACK_STRAWBERRY": 17.826,
        "SNACKPACK_VANILLA": 16.869,
        "TRANSLATOR_ASTRO_BLACK": 8.366,
        "TRANSLATOR_ECLIPSE_CHARCOAL": 8.7,
        "TRANSLATOR_GRAPHITE_MIST": 8.912,
        "TRANSLATOR_SPACE_GRAY": 8.402,
        "TRANSLATOR_VOID_BLUE": 9.525,
        "UV_VISOR_AMBER": 10.32,
        "UV_VISOR_MAGENTA": 14.092,
        "UV_VISOR_ORANGE": 13.284,
        "UV_VISOR_RED": 14.039,
        "UV_VISOR_YELLOW": 13.91,
    }

    # inventory-aware parameters
    INVENTORY_PRICE_SKEW = 0.35
    SOFT_LIMIT = 5
    FLATTEN_LIMIT = 8
    MAX_EXTRA_SIZE = 3

    STRATEGY_BY_PRODUCT = {
        "PEBBLES_XL": "B_GEN",
        "PANEL_1X4": "B",
        "PEBBLES_S": "B",
        "OXYGEN_SHAKE_CHOCOLATE": "B_GEN",
        "SLEEP_POD_POLYESTER": "B_GEN",
        "PANEL_2X4": "C_WI",
        "OXYGEN_SHAKE_MORNING_BREATH": "B_GEN",
        "UV_VISOR_ORANGE": "C_WI",
        "SNACKPACK_CHOCOLATE": "B",
        "GALAXY_SOUNDS_DARK_MATTER": "C_WI",
        "SNACKPACK_PISTACHIO": "A",
        "SNACKPACK_RASPBERRY": "B",
        "SNACKPACK_STRAWBERRY": "B_GEN",
        "OXYGEN_SHAKE_EVENING_BREATH": "B",
        "SLEEP_POD_NYLON": "B",
        "MICROCHIP_SQUARE": "B",
        "PANEL_2X2": "B",
        "TRANSLATOR_ASTRO_BLACK": "B_GEN",
        "GALAXY_SOUNDS_BLACK_HOLES": "B_GEN",
        "OXYGEN_SHAKE_GARLIC": "D",
        "UV_VISOR_AMBER": "D",
        "UV_VISOR_YELLOW": "D",
        "TRANSLATOR_GRAPHITE_MIST": "D",
        "SNACKPACK_VANILLA": "D",
        "SLEEP_POD_SUEDE": "D",
        "SLEEP_POD_COTTON": "D",
        "ROBOT_LAUNDRY": "D",
        "UV_VISOR_RED": "D",
        "ROBOT_VACUUMING": "D",
        "TRANSLATOR_ECLIPSE_CHARCOAL": "A",
        "ROBOT_IRONING": "A",
        "MICROCHIP_OVAL": "A",
        "MICROCHIP_CIRCLE": "A",
        "MICROCHIP_TRIANGLE": "A",
        "TRANSLATOR_VOID_BLUE": "B_GEN",
    }

    def run(self, state):
        orders = {}

        for product in state.order_depths.keys():
            product_orders = self.trade_product(state, product)

            if product_orders:
                orders[product] = product_orders

        return orders, 0, ""

    def trade_product(self, state, product):
        """
        Select product-specific strategy.
        Default strategy is D if product is not explicitly mapped.
        """

        strat = self.STRATEGY_BY_PRODUCT.get(product, "D")

        if strat == "A":
            return self.trade_rwa(state, product)

        if strat == "B":
            return self.trade_rwb(state, product)

        if strat == "B_GEN":
            return self.trade_rwbgen(state, product)

        if strat == "C":
            return self.trade_rwc(state, product)

        if strat == "C_WI":
            return self.trade_rwc_wi(state, product)

        if strat == "D":
            return self.trade_rwd(state, product)

        # Safety fallback
        return self.trade_rwd(state, product)

    # baseline
    def trade_rwa(self, state, product):
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
    
    # spread-aware price and volume adjustment
    def trade_rwb(self, state, product):
        """
        Version B: spread-aware market making.

        Compared to rwa:
            - if spread is wide, quote deeper inside the spread
            - if spread is wide, use larger size
            - if spread is tight, quote smaller size or do not improve much
            - still respects position limits
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

        # ----------------------------
        # Spread-based aggressiveness
        # ----------------------------
        if spread >= 12:
            improve = 2
            base_size = self.BASE_SIZE + 2
        elif spread >= 8:
            improve = 1
            base_size = self.BASE_SIZE + 1
        elif spread >= 4:
            improve = 1
            base_size = self.BASE_SIZE
        else:
            improve = 0
            base_size = 1

        # Never improve so much that bid >= ask
        max_improve = (spread - 1) // 2
        improve = min(improve, max_improve)

        buy_price = best_bid + improve
        sell_price = best_ask - improve

        if buy_price >= sell_price:
            return orders

        max_buy = self.POSITION_LIMIT - position
        max_sell = self.POSITION_LIMIT + position

        buy_size = min(base_size, max_buy)
        sell_size = min(base_size, max_sell)

        if buy_size > 0:
            orders.append(Order(product, buy_price, buy_size))

        if sell_size > 0:
            orders.append(Order(product, sell_price, -sell_size))

        return orders
    
    # not hardcoded B
    def trade_rwbgen(self, state, product):
            """
            Version B: spread-aware market making.

            Uses current spread relative to that product's average spread.
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
            avg_spread = self.AVG_SPREAD.get(product, 10)

            spread_ratio = spread / avg_spread

            # Product-relative spread logic
            if spread_ratio >= 1.25:
                # unusually wide spread
                improve = 2
                base_size = self.BASE_SIZE + 2

            elif spread_ratio >= 0.90:
                # normal / slightly wide spread
                improve = 1
                base_size = self.BASE_SIZE

            elif spread_ratio >= 0.70:
                # somewhat tight spread
                improve = 1
                base_size = max(1, self.BASE_SIZE - 1)

            else:
                # unusually tight spread, not worth quoting
                return orders

            # Do not improve so much that quotes cross
            max_improve = (spread - 1) // 2
            improve = min(improve, max_improve)

            buy_price = best_bid + improve
            sell_price = best_ask - improve

            if buy_price >= sell_price:
                return orders

            max_buy = self.POSITION_LIMIT - position
            max_sell = self.POSITION_LIMIT + position

            buy_size = min(base_size, max_buy)
            sell_size = min(base_size, max_sell)

            if buy_size > 0:
                orders.append(Order(product, buy_price, buy_size))

            if sell_size > 0:
                orders.append(Order(product, sell_price, -sell_size))

            return orders
    
    # imbalance-aware price and volume adjustment
    def trade_rwc(self, state, product):
        """
        Version C: imbalance-aware market making.

        Compared to rwa:
            - if bid-side volume dominates, quote more aggressively on the buy side
            - if ask-side volume dominates, quote more aggressively on the sell side
            - if imbalance is neutral, behave like rwa
            - still respects position limits
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

        # ----------------------------
        # Compute total book imbalance
        # ----------------------------
        total_bid_volume = sum(depth.buy_orders.values())
        total_ask_volume = sum(abs(v) for v in depth.sell_orders.values())

        total_volume = total_bid_volume + total_ask_volume

        if total_volume == 0:
            return orders

        imbalance = (total_bid_volume - total_ask_volume) / total_volume

        # ----------------------------
        # Imbalance-based aggressiveness
        # ----------------------------
        # Positive imbalance:
        #     more bid volume than ask volume
        #     possible upward pressure
        #
        # Negative imbalance:
        #     more ask volume than bid volume
        #     possible downward pressure

        if imbalance >= 0.30:
            # Strong buy pressure
            buy_improve = 2
            sell_improve = 0
            buy_base_size = self.BASE_SIZE + 2
            sell_base_size = max(1, self.BASE_SIZE - 1)

        elif imbalance >= 0.10:
            # Mild buy pressure
            buy_improve = 2
            sell_improve = 1
            buy_base_size = self.BASE_SIZE + 1
            sell_base_size = self.BASE_SIZE

        elif imbalance <= -0.30:
            # Strong sell pressure
            buy_improve = 0
            sell_improve = 2
            buy_base_size = max(1, self.BASE_SIZE - 1)
            sell_base_size = self.BASE_SIZE + 2

        elif imbalance <= -0.10:
            # Mild sell pressure
            buy_improve = 1
            sell_improve = 2
            buy_base_size = self.BASE_SIZE
            sell_base_size = self.BASE_SIZE + 1

        else:
            # Neutral book
            buy_improve = 1
            sell_improve = 1
            buy_base_size = self.BASE_SIZE
            sell_base_size = self.BASE_SIZE

        # ----------------------------
        # Prevent crossing quotes
        # ----------------------------
        buy_improve = max(0, buy_improve)
        sell_improve = max(0, sell_improve)

        while buy_improve + sell_improve >= spread:
            if buy_improve >= sell_improve and buy_improve > 0:
                buy_improve -= 1
            elif sell_improve > 0:
                sell_improve -= 1
            else:
                break

        buy_price = best_bid + buy_improve
        sell_price = best_ask - sell_improve

        if buy_price >= sell_price:
            return orders

        # ----------------------------
        # Position limit caps
        # ----------------------------
        max_buy = self.POSITION_LIMIT - position
        max_sell = self.POSITION_LIMIT + position

        buy_size = min(buy_base_size, max_buy)
        sell_size = min(sell_base_size, max_sell)

        if buy_size > 0:
            orders.append(Order(product, buy_price, buy_size))

        if sell_size > 0:
            orders.append(Order(product, sell_price, -sell_size))

        return orders
    
    # same but weighted imbalance
    def trade_rwc_wi(self, state, product):
        """
        Version C-WI: weighted-imbalance-aware market making.

        Compared to trade_rwc:
            - uses weighted book imbalance instead of raw total imbalance
            - level 1 matters most
            - level 2 matters less
            - level 3 matters least
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

        # ----------------------------
        # Sort book levels
        # ----------------------------
        # Bids: highest price first
        bid_levels = sorted(depth.buy_orders.items(), reverse=True)

        # Asks: lowest price first
        ask_levels = sorted(depth.sell_orders.items())

        # Keep top 3 levels
        bid_levels = bid_levels[:3]
        ask_levels = ask_levels[:3]

        # Level weights
        weights = [1.0, 0.5, 0.25]

        weighted_bid_volume = 0
        weighted_ask_volume = 0

        for i, (_, volume) in enumerate(bid_levels):
            weighted_bid_volume += weights[i] * volume

        for i, (_, volume) in enumerate(ask_levels):
            weighted_ask_volume += weights[i] * abs(volume)

        weighted_total_volume = weighted_bid_volume + weighted_ask_volume

        if weighted_total_volume == 0:
            return orders

        weighted_imbalance = (
            weighted_bid_volume - weighted_ask_volume
        ) / weighted_total_volume

        # ----------------------------
        # Weighted-imbalance-based aggressiveness
        # ----------------------------
        if weighted_imbalance >= 0.30:
            # Strong buy pressure
            buy_improve = 2
            sell_improve = 0
            buy_base_size = self.BASE_SIZE + 2
            sell_base_size = max(1, self.BASE_SIZE - 1)

        elif weighted_imbalance >= 0.10:
            # Mild buy pressure
            buy_improve = 2
            sell_improve = 1
            buy_base_size = self.BASE_SIZE + 1
            sell_base_size = self.BASE_SIZE

        elif weighted_imbalance <= -0.30:
            # Strong sell pressure
            buy_improve = 0
            sell_improve = 2
            buy_base_size = max(1, self.BASE_SIZE - 1)
            sell_base_size = self.BASE_SIZE + 2

        elif weighted_imbalance <= -0.10:
            # Mild sell pressure
            buy_improve = 1
            sell_improve = 2
            buy_base_size = self.BASE_SIZE
            sell_base_size = self.BASE_SIZE + 1

        else:
            # Neutral book
            buy_improve = 1
            sell_improve = 1
            buy_base_size = self.BASE_SIZE
            sell_base_size = self.BASE_SIZE

        # ----------------------------
        # Prevent crossing quotes
        # ----------------------------
        buy_improve = max(0, buy_improve)
        sell_improve = max(0, sell_improve)

        while buy_improve + sell_improve >= spread:
            if buy_improve >= sell_improve and buy_improve > 0:
                buy_improve -= 1
            elif sell_improve > 0:
                sell_improve -= 1
            else:
                break

        buy_price = best_bid + buy_improve
        sell_price = best_ask - sell_improve

        if buy_price >= sell_price:
            return orders

        # ----------------------------
        # Position limit caps
        # ----------------------------
        max_buy = self.POSITION_LIMIT - position
        max_sell = self.POSITION_LIMIT + position

        buy_size = min(buy_base_size, max_buy)
        sell_size = min(sell_base_size, max_sell)

        if buy_size > 0:
            orders.append(Order(product, buy_price, buy_size))

        if sell_size > 0:
            orders.append(Order(product, sell_price, -sell_size))

        return orders

    # inventory-aware market making
    def trade_rwd(self, state, product):
        """
        Version D: inventory-aware market making.

        Compared to rwa:
            - starts from A1 quotes: best_bid + 1, best_ask - 1
            - skews prices based on current position
            - skews order sizes based on current position
            - reduces buying when long
            - reduces selling when short
            - near limits, prioritizes flattening inventory
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

        # Start from A1-style one-tick improvement
        max_improve = (spread - 1) // 2
        improve = min(1, max_improve)

        # ----------------------------
        # Inventory price skew
        # ----------------------------
        # position > 0:
        #     long inventory
        #     lower bid  -> less likely to buy more
        #     lower ask  -> more likely to sell
        #
        # position < 0:
        #     short inventory
        #     raise bid  -> more likely to buy back
        #     raise ask  -> less likely to sell more

        price_skew = int(round(self.INVENTORY_PRICE_SKEW * position))

        buy_price = best_bid + improve - price_skew
        sell_price = best_ask - improve - price_skew

        # Keep prices inside the market without crossing
        buy_price = min(buy_price, best_ask - 1)
        sell_price = max(sell_price, best_bid + 1)

        if buy_price >= sell_price:
            return orders

        # ----------------------------
        # Position capacity
        # ----------------------------

        max_buy = self.POSITION_LIMIT - position
        max_sell = self.POSITION_LIMIT + position

        # ----------------------------
        # Inventory quantity skew
        # ----------------------------

        abs_pos = abs(position)

        if position >= self.FLATTEN_LIMIT:
            # Very long: stop buying, sell aggressively
            buy_size = 0
            sell_size = self.BASE_SIZE + self.MAX_EXTRA_SIZE

        elif position > self.SOFT_LIMIT:
            # Moderately long: small/no buy, larger sell
            buy_size = max(0, self.BASE_SIZE - 1)
            sell_size = self.BASE_SIZE + 2

        elif position > 0:
            # Slightly long: bias toward selling
            buy_size = max(1, self.BASE_SIZE - 1)
            sell_size = self.BASE_SIZE + 1

        elif position <= -self.FLATTEN_LIMIT:
            # Very short: stop selling, buy aggressively
            buy_size = self.BASE_SIZE + self.MAX_EXTRA_SIZE
            sell_size = 0

        elif position < -self.SOFT_LIMIT:
            # Moderately short: larger buy, small/no sell
            buy_size = self.BASE_SIZE + 2
            sell_size = max(0, self.BASE_SIZE - 1)

        elif position < 0:
            # Slightly short: bias toward buying
            buy_size = self.BASE_SIZE + 1
            sell_size = max(1, self.BASE_SIZE - 1)

        else:
            # Flat
            buy_size = self.BASE_SIZE
            sell_size = self.BASE_SIZE

        # Final hard caps
        buy_size = min(buy_size, max_buy)
        sell_size = min(sell_size, max_sell)

        if buy_size > 0:
            orders.append(Order(product, buy_price, buy_size))

        if sell_size > 0:
            orders.append(Order(product, sell_price, -sell_size))

        return orders