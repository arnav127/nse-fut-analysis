"""
order_book_cpp.cpp — Data-Oriented Design (DOD) Limit Order Book Engine.
Optimizations:
1. Packed 16-byte OrderInfo struct (zero wasted padding, cache-line aligned: 4 orders per 64B cache line).
2. FlatPriceBook using contiguous memory std::vector<PriceLevel> instead of pointer-chasing std::map nodes.
3. Fast binary search (std::lower_bound) and cache-friendly contiguous scans for LOB depth snapshots.
4. Pre-reserved hash table buckets to eliminate re-allocation overhead during trading sessions.
"""
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <vector>
#include <unordered_map>
#include <string>
#include <cmath>
#include <algorithm>
#include <cstdint>

namespace py = pybind11;

// 1. DOD Packed OrderInfo Struct: exactly 16 bytes (8+4+1+3)
#pragma pack(push, 1)
struct alignas(16) OrderInfo {
    double price;      // 8 bytes (offset 0)
    int32_t qty;       // 4 bytes (offset 8)
    char side;         // 1 byte  (offset 12: 'B' or 'S')
    char pad[3];       // 3 bytes explicit padding -> 16 bytes total
};
#pragma pack(pop)

// 2. DOD Contiguous Memory Price Level (16 bytes)
struct alignas(16) PriceLevel {
    double price;      // 8 bytes
    long long volume;  // 8 bytes
};

// 3. Flat Cache-Friendly Price Book (replaces pointer-chasing std::map Red-Black Tree)
class FlatPriceBook {
private:
    std::vector<PriceLevel> levels;
    bool is_bid; // true for descending order, false for ascending order

public:
    explicit FlatPriceBook(bool bid_side) : is_bid(bid_side) {
        levels.reserve(256); // Pre-allocate contiguous memory for price levels
    }

    void add_volume(double price, long long qty) {
        auto cmp = [this](const PriceLevel& a, double val) {
            return is_bid ? (a.price > val) : (a.price < val);
        };
        auto it = std::lower_bound(levels.begin(), levels.end(), price, cmp);
        if (it != levels.end() && std::abs(it->price - price) < 1e-9) {
            it->volume += qty;
        } else {
            levels.insert(it, {price, qty});
        }
    }

    void remove_volume(double price, long long qty) {
        auto cmp = [this](const PriceLevel& a, double val) {
            return is_bid ? (a.price > val) : (a.price < val);
        };
        auto it = std::lower_bound(levels.begin(), levels.end(), price, cmp);
        if (it != levels.end() && std::abs(it->price - price) < 1e-9) {
            it->volume -= qty;
            if (it->volume <= 0) {
                levels.erase(it); // memmove in L1 cache is orders of magnitude faster than heap node deletion
            }
        }
    }

    bool empty() const { return levels.empty(); }
    double best_price() const { return levels.empty() ? 0.0 : levels.front().price; }
    const std::vector<PriceLevel>& get_levels() const { return levels; }
};

class OrderBookCpp {
private:
    FlatPriceBook bid_book;
    FlatPriceBook ask_book;
    std::unordered_map<long long, OrderInfo> orders;

    void add_order(long long order_number, char side, double price, long long qty) {
        if (price <= 0 || qty <= 0) return;
        if (side == 'B') {
            bid_book.add_volume(price, qty);
        } else {
            ask_book.add_volume(price, qty);
        }
        orders[order_number] = {price, static_cast<int32_t>(qty), side, {0, 0, 0}};
    }

    void cancel_order(long long order_number) {
        auto it = orders.find(order_number);
        if (it == orders.end()) return;

        const auto& info = it->second;
        if (info.side == 'B') {
            bid_book.remove_volume(info.price, info.qty);
        } else {
            ask_book.remove_volume(info.price, info.qty);
        }
        orders.erase(it);
    }

public:
    OrderBookCpp() : bid_book(true), ask_book(false) {
        orders.reserve(65536); // Pre-reserve hash buckets to prevent rehashing during trading session
        orders.max_load_factor(0.7f);
    }

    void process_event(long long order_number, int activity_type, const std::string& side, double price, long long qty) {
        char side_char = (!side.empty() && side[0] == 'B') ? 'B' : 'S';
        if (activity_type == 1) {        // Entry
            add_order(order_number, side_char, price, qty);
        } else if (activity_type == 3) { // Cancel
            cancel_order(order_number);
        } else if (activity_type == 4) { // Modify
            cancel_order(order_number);
            add_order(order_number, side_char, price, qty);
        }
    }

    void remove_traded_qty(long long order_number, long long traded_qty) {
        auto it = orders.find(order_number);
        if (it == orders.end()) return;

        auto& info = it->second;
        long long rem_qty = std::min(static_cast<long long>(info.qty), traded_qty);
        info.qty -= static_cast<int32_t>(rem_qty);

        if (info.side == 'B') {
            bid_book.remove_volume(info.price, rem_qty);
        } else {
            ask_book.remove_volume(info.price, rem_qty);
        }

        if (info.qty <= 0) {
            orders.erase(it);
        }
    }

    py::dict snapshot(int depth = 10) {
        py::dict snap;

        const auto& bids = bid_book.get_levels();
        const auto& asks = ask_book.get_levels();

        bool has_bid = !bids.empty();
        bool has_ask = !asks.empty();

        double best_bid = has_bid ? bids.front().price : 0.0;
        double best_ask = has_ask ? asks.front().price : 0.0;

        if (has_bid) snap["best_bid"] = best_bid; else snap["best_bid"] = py::none();
        if (has_ask) snap["best_ask"] = best_ask; else snap["best_ask"] = py::none();

        if (has_bid && has_ask) {
            double midpoint = (best_bid + best_ask) * 0.5;
            double spread = best_ask - best_bid;
            double spread_bps = (midpoint > 0.0) ? (spread / midpoint * 10000.0) : 0.0;

            snap["midpoint"] = midpoint;
            snap["spread"] = spread;
            snap["spread_bps"] = spread_bps;
        } else {
            snap["midpoint"] = py::none();
            snap["spread"] = py::none();
            snap["spread_bps"] = py::none();
        }

        long long tot_bid_vol = 0;
        int count = 0;
        for (size_t i = 0; i < bids.size() && count < depth; ++i, ++count) {
            tot_bid_vol += bids[i].volume;
            std::string key = "bid_depth_" + std::to_string(count + 1);
            snap[key.c_str()] = bids[i].volume;
        }
        for (int i = count + 1; i <= depth; ++i) {
            std::string key = "bid_depth_" + std::to_string(i);
            snap[key.c_str()] = 0;
        }

        long long tot_ask_vol = 0;
        count = 0;
        for (size_t i = 0; i < asks.size() && count < depth; ++i, ++count) {
            tot_ask_vol += asks[i].volume;
            std::string key = "ask_depth_" + std::to_string(count + 1);
            snap[key.c_str()] = asks[i].volume;
        }
        for (int i = count + 1; i <= depth; ++i) {
            std::string key = "ask_depth_" + std::to_string(i);
            snap[key.c_str()] = 0;
        }

        snap["total_bid_volume"] = tot_bid_vol;
        snap["total_ask_volume"] = tot_ask_vol;

        double imbalance = 0.0;
        if (tot_bid_vol + tot_ask_vol > 0) {
            imbalance = static_cast<double>(tot_bid_vol - tot_ask_vol) / static_cast<double>(tot_bid_vol + tot_ask_vol);
        }
        snap["book_imbalance"] = imbalance;

        return snap;
    }

    py::list process_event_stream(
        py::array_t<int32_t> event_kind_arr,
        py::array_t<int64_t> order_num_arr,
        py::array_t<int32_t> act_type_arr,
        py::array_t<int32_t> side_code_arr,
        py::array_t<double> price_arr,
        py::array_t<int64_t> vol_arr,
        py::array_t<int64_t> buy_num_arr,
        py::array_t<int64_t> sell_num_arr,
        py::array_t<int64_t> trade_qty_arr,
        py::array_t<int32_t> t_sec_arr,
        int start_sec,
        int end_sec,
        const std::string& symbol,
        const std::string& trade_date,
        int depth = 10
    ) {
        py::list snaps;
        auto kind_buf = event_kind_arr.unchecked<1>();
        auto order_num_buf = order_num_arr.unchecked<1>();
        auto act_type_buf = act_type_arr.unchecked<1>();
        auto side_buf = side_code_arr.unchecked<1>();
        auto price_buf = price_arr.unchecked<1>();
        auto vol_buf = vol_arr.unchecked<1>();
        auto buy_num_buf = buy_num_arr.unchecked<1>();
        auto sell_num_buf = sell_num_arr.unchecked<1>();
        auto trade_qty_buf = trade_qty_arr.unchecked<1>();
        auto sec_buf = t_sec_arr.unchecked<1>();

        int n = (int)kind_buf.shape(0);
        int last_snap_sec = -1;

        for (int i = 0; i < n; ++i) {
            int ek = kind_buf(i);
            int sec = sec_buf(i);

            if (ek == 1) {
                int sc = side_buf(i);
                std::string s = (sc == 1) ? "B" : "S";
                process_event(order_num_buf(i), act_type_buf(i), s, price_buf(i), vol_buf(i));
            } else if (ek == 2) {
                int64_t tq = trade_qty_buf(i);
                remove_traded_qty(buy_num_buf(i), tq);
                remove_traded_qty(sell_num_buf(i), tq);
            }

            if (sec >= start_sec && sec <= end_sec) {
                int sec_from_1500 = sec - start_sec;
                if (sec_from_1500 != last_snap_sec) {
                    last_snap_sec = sec_from_1500;
                    py::dict snap = snapshot(depth);
                    snap["symbol"] = symbol;
                    snap["trade_date"] = trade_date;
                    snap["seconds_from_1500"] = sec_from_1500;

                    int h = 15 + sec_from_1500 / 3600;
                    int m = (sec_from_1500 % 3600) / 60;
                    int s = sec_from_1500 % 60;
                    char buf[16];
                    snprintf(buf, sizeof(buf), "%02d:%02d:%02d", h, m, s);
                    snap["snapshot_time"] = std::string(buf);
                    snaps.append(snap);
                }
            }
        }
        return snaps;
    }
};

PYBIND11_MODULE(order_book_cpp, m) {
    m.doc() = "Data-Oriented Design (DOD) Limit Order Book Engine for NSE Expiry Day Analysis";

    py::class_<OrderBookCpp>(m, "OrderBookCpp")
        .def(py::init<>())
        .def("process_event", &OrderBookCpp::process_event, py::arg("order_number"), py::arg("activity_type"), py::arg("side"), py::arg("price"), py::arg("qty"))
        .def("remove_traded_qty", &OrderBookCpp::remove_traded_qty, py::arg("order_number"), py::arg("traded_qty"))
        .def("process_event_stream", &OrderBookCpp::process_event_stream,
             py::arg("event_kind_arr"), py::arg("order_num_arr"), py::arg("act_type_arr"), py::arg("side_code_arr"),
             py::arg("price_arr"), py::arg("vol_arr"), py::arg("buy_num_arr"), py::arg("sell_num_arr"),
             py::arg("trade_qty_arr"), py::arg("t_sec_arr"), py::arg("start_sec"), py::arg("end_sec"),
             py::arg("symbol"), py::arg("trade_date"), py::arg("depth") = 10)
        .def("snapshot", &OrderBookCpp::snapshot, py::arg("depth") = 10);
}
