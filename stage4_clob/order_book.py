"""
order_book.py — High-Performance OrderBook implementation.
Supports C++ PyBind11 compiled module ('order_book_cpp') with automatic fallback
to fast Numba/Python implementation.
"""
try:
    # Try importing compiled C++ PyBind11 module if available
    from order_book_cpp import OrderBookCpp as CppEngine
    HAS_CPP = True
except ImportError:
    HAS_CPP = False

from sortedcontainers import SortedDict

class OrderBookPython:
    def __init__(self):
        self.bid = SortedDict()    # price -> total_qty (highest price first when reversed)
        self.ask = SortedDict()    # price -> total_qty (lowest price first)
        self.orders = {}           # order_number -> {"side": "B"/"S", "price": float, "qty": int}

    def process_event(self, order_number, activity_type, side, price, qty):
        """Process a single order event.
        activity_type: 1=Entry, 3=Cancel, 4=Modify
        side: "B" or "S"
        """
        if activity_type == 1:    # New entry
            self._add_order(order_number, side, price, qty)
        elif activity_type == 3:  # Cancel
            self._cancel_order(order_number)
        elif activity_type == 4:  # Modify
            self._cancel_order(order_number)    # Remove old
            self._add_order(order_number, side, price, qty)  # Add new

    def _add_order(self, order_number, side, price, qty):
        if price <= 0 or qty <= 0:
            return
        book = self.bid if side == "B" else self.ask
        book[price] = book.get(price, 0) + qty
        self.orders[order_number] = {"side": side, "price": price, "qty": qty}

    def _cancel_order(self, order_number):
        if order_number not in self.orders:
            return
        info = self.orders.pop(order_number)
        book = self.bid if info["side"] == "B" else self.ask
        if info["price"] in book:
            book[info["price"]] -= info["qty"]
            if book[info["price"]] <= 0:
                del book[info["price"]]

    def remove_traded_qty(self, order_number, traded_qty):
        """Reduce qty for a partially or fully filled order."""
        if order_number not in self.orders:
            return
        info = self.orders[order_number]
        book = self.bid if info["side"] == "B" else self.ask
        info["qty"] -= traded_qty
        if info["price"] in book:
            book[info["price"]] -= traded_qty
            if book[info["price"]] <= 0:
                del book[info["price"]]
        if info["qty"] <= 0:
            del self.orders[order_number]

    def snapshot(self, depth=10):
        """Return current book state: best N bid/ask levels."""
        best_bids = list(self.bid.items())[-depth:][::-1]  # highest prices first
        best_asks = list(self.ask.items())[:depth]          # lowest prices first

        best_bid_price = best_bids[0][0] if best_bids else None
        best_ask_price = best_asks[0][0] if best_asks else None
        midpoint = (best_bid_price + best_ask_price) / 2.0 if (best_bid_price and best_ask_price) else None
        spread = (best_ask_price - best_bid_price) if (best_bid_price and best_ask_price) else None
        spread_bps = (spread / midpoint * 10000.0) if (spread and midpoint and midpoint > 0) else None

        tot_bid_vol = sum(q for _, q in best_bids)
        tot_ask_vol = sum(q for _, q in best_asks)
        imbalance = (tot_bid_vol - tot_ask_vol) / float(tot_bid_vol + tot_ask_vol) if (tot_bid_vol + tot_ask_vol) > 0 else 0.0

        snap = {
            "best_bid": best_bid_price,
            "best_ask": best_ask_price,
            "midpoint": midpoint,
            "spread": spread,
            "spread_bps": spread_bps,
            "total_bid_volume": tot_bid_vol,
            "total_ask_volume": tot_ask_vol,
            "book_imbalance": imbalance
        }

        for i in range(1, depth + 1):
            snap[f"bid_depth_{i}"] = best_bids[i-1][1] if i <= len(best_bids) else 0
            snap[f"ask_depth_{i}"] = best_asks[i-1][1] if i <= len(best_asks) else 0

        return snap


# Wrapper class that selects C++ implementation if compiled, otherwise Python
class OrderBook:
    def __init__(self):
        if HAS_CPP:
            self._engine = CppEngine()
            self.is_cpp = True
        else:
            self._engine = OrderBookPython()
            self.is_cpp = False

    def process_event(self, order_number, activity_type, side, price, qty):
        self._engine.process_event(order_number, activity_type, side, price, qty)

    def remove_traded_qty(self, order_number, traded_qty):
        self._engine.remove_traded_qty(order_number, traded_qty)

    def snapshot(self, depth=10):
        return self._engine.snapshot(depth)
