from datamodel import OrderDepth, TradingState, Order
import json

ASH = 'ASH_COATED_OSMIUM'
ASH_MID_PRICE = 10000

POS_LIMITS = {
    ASH: 80,
}


class ProductTrader:

    def __init__(self, name, state, prints, new_trader_data):
        self.orders = []

        self.name = name
        self.state = state
        self.prints = prints
        self.new_trader_data = new_trader_data

        self.position_limit = POS_LIMITS.get(self.name, 0)
        self.initial_position = self.state.position.get(self.name, 0)
        self.expected_position = self.initial_position

        self.mkt_buy_orders, self.mkt_sell_orders = self.get_order_depth()
        self.bid_wall, self.wall_mid, self.ask_wall = self.get_walls()
        self.mid_price = self.wall_mid
        self.max_allowed_buy_volume, self.max_allowed_sell_volume = self.get_max_allowed_volume()

    def get_walls(self):
        bid_wall = wall_mid = ask_wall = None

        try:
            bid_wall = min([x for x, _ in self.mkt_buy_orders.items()])
        except:
            pass

        try:
            ask_wall = max([x for x, _ in self.mkt_sell_orders.items()])
        except:
            pass

        try:
            wall_mid = (bid_wall + ask_wall) / 2
        except:
            pass

        return bid_wall, wall_mid, ask_wall

    def get_max_allowed_volume(self):
        max_allowed_buy_volume = self.position_limit - self.initial_position
        max_allowed_sell_volume = self.position_limit + self.initial_position
        return max_allowed_buy_volume, max_allowed_sell_volume

    def get_order_depth(self):
        order_depth, buy_orders, sell_orders = {}, {}, {}

        try:
            order_depth: OrderDepth = self.state.order_depths[self.name]
        except:
            pass
        try:
            buy_orders = {
                bp: abs(bv)
                for bp, bv in sorted(order_depth.buy_orders.items(), key=lambda x: x[0], reverse=True)
            }
        except:
            pass
        try:
            sell_orders = {
                sp: abs(sv)
                for sp, sv in sorted(order_depth.sell_orders.items(), key=lambda x: x[0])
            }
        except:
            pass

        return buy_orders, sell_orders

    def bid(self, price, volume, logging=True):
        abs_volume = min(abs(int(volume)), self.max_allowed_buy_volume)
        order = Order(self.name, int(price), abs_volume)
        self.max_allowed_buy_volume -= abs_volume
        self.expected_position += abs_volume
        self.orders.append(order)

    def ask(self, price, volume, logging=True):
        abs_volume = min(abs(int(volume)), self.max_allowed_sell_volume)
        order = Order(self.name, int(price), -abs_volume)
        self.max_allowed_sell_volume -= abs_volume
        self.expected_position -= abs_volume
        self.orders.append(order)

    def get_orders(self):
        return {}


class AshTrader(ProductTrader):
    def __init__(self, state, prints, new_trader_data):
        super().__init__(ASH, state, prints, new_trader_data)
        # self.mid_price = ASH_MID_PRICE
        self.mid_price = self.wall_mid
        self.soft_edge = 10
        self.hard_edge = 20

    def get_orders(self):

        if self.mid_price is not None:

            ##########################################################
            ####### 1. TAKING
            ##########################################################
            for sp, sv in self.mkt_sell_orders.items():
                if sp <= self.mid_price - 1:
                    self.bid(sp, sv, logging=False)
                elif sp <= self.mid_price and self.expected_position < 0:
                        volume = min(sv, abs(self.expected_position))
                        self.bid(sp, volume, logging=False)

            for bp, bv in self.mkt_buy_orders.items():
                if bp >= self.mid_price + 1:
                    self.ask(bp, bv, logging=False)
                elif bp >= self.mid_price and self.expected_position > 0:
                        volume = min(bv, self.expected_position)
                        self.ask(bp, volume, logging=False)

            ###########################################################
            ####### 2. MAKING
            ###########################################################
            bid_price = self.mid_price - self.hard_edge if self.expected_position > self.position_limit * 0.5 else self.mid_price - self.soft_edge
            ask_price = self.mid_price + self.hard_edge if self.expected_position < self.position_limit * -0.5 else self.mid_price + self.soft_edge

            if self.bid_wall is not None and self.ask_wall is not None:
                bid_price = int(self.bid_wall + 1)
                ask_price = int(self.ask_wall - 1)

            # OVERBIDDING: overbid best bid that is still under the mid price
            for bp, bv in self.mkt_buy_orders.items():
                overbidding_price = bp + 1
                if bv > 1 and overbidding_price < self.mid_price:
                    bid_price = max(bid_price, overbidding_price)
                    break
                elif bp < self.mid_price:
                    bid_price = max(bid_price, bp)
                    break

            # UNDERBIDDING: underbid best ask that is still over the mid price
            for sp, sv in self.mkt_sell_orders.items():
                underbidding_price = sp - 1
                if sv > 1 and underbidding_price > self.mid_price:
                    ask_price = min(ask_price, underbidding_price)
                    break
                elif sp > self.mid_price:
                    ask_price = min(ask_price, sp)
                    break

            # POST ORDERS
            self.bid(bid_price, self.max_allowed_buy_volume)
            self.ask(ask_price, self.max_allowed_sell_volume)


        return {self.name: self.orders}


class Trader:

    def logger_print(self, state: TradingState):
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

    def run(self, state: TradingState):
        self.logger_print(state)
        result: dict[str, list[Order]] = {}
        new_trader_data = {}
        prints = {
            "GENERAL": {
                "TIMESTAMP": state.timestamp,
                "POSITIONS": state.position
            },
        }

        def export(prints):
            try:
                print(json.dumps(prints))
            except:
                pass

        if ASH in state.order_depths:
            try:
                trader = AshTrader(state, prints, new_trader_data)
                result.update(trader.get_orders())
            except:
                pass

        try:
            final_trader_data = json.dumps(new_trader_data)
        except:
            final_trader_data = ''

        export(prints)
        return result, 0, final_trader_data
