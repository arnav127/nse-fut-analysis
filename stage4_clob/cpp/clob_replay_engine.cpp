"""
clob_replay_engine.cpp — Data-Oriented Design (DOD) Vectorized Replay Engine.
Optimized for L1/L2 CPU cache locality, zero wasted padding, and contiguous memory access.
"""
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/numpy.h>
#include <vector>
#include <unordered_map>
#include <string>
#include <cmath>
#include <algorithm>
#include <cstdint>

namespace py = pybind11;

// 1. DOD Packed 16-byte CppOrderInfo (cache line holds 4 orders)
#pragma pack(push, 1)
struct alignas(16) CppOrderInfo {
    double price;      // 8 bytes
    int32_t qty;       // 4 bytes
    char side;         // 1 byte ('B' or 'S')
    char pad[3];       // 3 bytes padding
};
#pragma pack(pop)

// 2. Contiguous Memory Price Level
struct alignas(16) PriceLevel {
    double price;
    long long volume;
};

// 3. Contiguous Memory Cache-Friendly FlatPriceBook
class FlatPriceBook {
private:
    std::vector<PriceLevel> levels;
    bool is_bid;

public:
    explicit FlatPriceBook(bool bid_side) : is_bid(bid_side) {
        levels.reserve(256);
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
                levels.erase(it); // Fast memory shift in L1 cache
            }
        }
    }

    bool empty() const { return levels.empty(); }
    const std::vector<PriceLevel>& get_levels() const { return levels; }
};

class FastCLOBReplayEngine {
private:
    FlatPriceBook bid_book;
    FlatPriceBook ask_book;
    std::unordered_map<long long, CppOrderInfo> orders;

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
    FastCLOBReplayEngine() : bid_book(true), ask_book(false) {
        orders.reserve(65536);
        orders.max_load_factor(0.7f);
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
        if (info.qty <= 0) orders.erase(it);
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
            double mid = (best_bid + best_ask) * 0.5;
            double spr = best_ask - best_bid;
            snap["midpoint"] = mid;
            snap["spread"] = spr;
            snap["spread_bps"] = (mid > 0.0) ? (spr / mid * 10000.0) : 0.0;
        } else {
            snap["midpoint"] = py::none();
            snap["spread"] = py::none();
            snap["spread_bps"] = py::none();
        }

        long long tot_bid = 0, tot_ask = 0;
        int count = 0;
        for (size_t i = 0; i < bids.size() && count < depth; ++i, ++count) {
            tot_bid += bids[i].volume;
            std::string key = "bid_depth_" + std::to_string(count + 1);
            snap[key.c_str()] = bids[i].volume;
        }
        for (int i = count + 1; i <= depth; ++i) {
            std::string key = "bid_depth_" + std::to_string(i);
            snap[key.c_str()] = 0;
        }

        count = 0;
        for (size_t i = 0; i < asks.size() && count < depth; ++i, ++count) {
            tot_ask += asks[i].volume;
            std::string key = "ask_depth_" + std::to_string(count + 1);
            snap[key.c_str()] = asks[i].volume;
        }
        for (int i = count + 1; i <= depth; ++i) {
            std::string key = "ask_depth_" + std::to_string(i);
            snap[key.c_str()] = 0;
        }

        snap["total_bid_volume"] = tot_bid;
        snap["total_ask_volume"] = tot_ask;
        double imb = 0.0;
        if (tot_bid + tot_ask > 0) {
            imb = static_cast<double>(tot_bid - tot_ask) / static_cast<double>(tot_bid + tot_ask);
        }
        snap["book_imbalance"] = imb;

        return snap;
    }
};

PYBIND11_MODULE(clob_replay_engine, m) {
    m.doc() = "DOD Vectorized Replay Engine";
    py::class_<FastCLOBReplayEngine>(m, "FastCLOBReplayEngine")
        .def(py::init<>())
        .def("remove_traded_qty", &FastCLOBReplayEngine::remove_traded_qty)
        .def("snapshot", &FastCLOBReplayEngine::snapshot);
}
