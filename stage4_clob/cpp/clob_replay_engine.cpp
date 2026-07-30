#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/numpy.h>
#include <map>
#include <unordered_map>
#include <vector>
#include <string>
#include <cmath>
#include <algorithm>

namespace py = pybind11;

struct CppOrderInfo {
    char side;
    double price;
    long long qty;
};

class FastCLOBReplayEngine {
private:
    std::map<double, long long, std::greater<double>> bid;
    std::map<double, long long> ask;
    std::unordered_map<long long, CppOrderInfo> orders;

    void add_order(long long order_number, char side, double price, long long qty) {
        if (price <= 0 || qty <= 0) return;
        if (side == 'B') bid[price] += qty; else ask[price] += qty;
        orders[order_number] = {side, price, qty};
    }

    void cancel_order(long long order_number) {
        auto it = orders.find(order_number);
        if (it == orders.end()) return;
        const auto& info = it->second;
        if (info.side == 'B') {
            auto bit = bid.find(info.price);
            if (bit != bid.end()) {
                bit->second -= info.qty;
                if (bit->second <= 0) bid.erase(bit);
            }
        } else {
            auto ait = ask.find(info.price);
            if (ait != ask.end()) {
                ait->second -= info.qty;
                if (ait->second <= 0) ask.erase(ait);
            }
        }
        orders.erase(it);
    }

public:
    FastCLOBReplayEngine() {}

    void remove_traded_qty(long long order_number, long long traded_qty) {
        auto it = orders.find(order_number);
        if (it == orders.end()) return;
        auto& info = it->second;
        info.qty -= traded_qty;
        if (info.side == 'B') {
            auto bit = bid.find(info.price);
            if (bit != bid.end()) {
                bit->second -= traded_qty;
                if (bit->second <= 0) bid.erase(bit);
            }
        } else {
            auto ait = ask.find(info.price);
            if (ait != ask.end()) {
                ait->second -= traded_qty;
                if (ait->second <= 0) ask.erase(ait);
            }
        }
        if (info.qty <= 0) orders.erase(it);
    }

    py::dict snapshot(int depth = 10) {
        py::dict snap;
        double best_bid = !bid.empty() ? bid.begin()->first : 0.0;
        double best_ask = !ask.empty() ? ask.begin()->first : 0.0;

        snap["best_bid"] = !bid.empty() ? py::cast(best_bid) : py::none();
        snap["best_ask"] = !ask.empty() ? py::cast(best_ask) : py::none();

        if (!bid.empty() && !ask.empty()) {
            double mid = (best_bid + best_ask) / 2.0;
            double spr = best_ask - best_bid;
            snap["midpoint"] = mid;
            snap["spread"] = spr;
            snap["spread_bps"] = (mid > 0) ? (spr / mid * 10000.0) : 0.0;
        } else {
            snap["midpoint"] = py::none();
            snap["spread"] = py::none();
            snap["spread_bps"] = py::none();
        }

        long long tot_bid = 0, tot_ask = 0;
        int count = 0;
        for (auto it = bid.begin(); it != bid.end() && count < depth; ++it, ++count) {
            tot_bid += it->second;
            snap[("bid_depth_" + std::to_string(count + 1)).c_str()] = it->second;
        }
        for (int i = count + 1; i <= depth; ++i) snap[("bid_depth_" + std::to_string(i)).c_str()] = 0;

        count = 0;
        for (auto it = ask.begin(); it != ask.end() && count < depth; ++it, ++count) {
            tot_ask += it->second;
            snap[("ask_depth_" + std::to_string(count + 1)).c_str()] = it->second;
        }
        for (int i = count + 1; i <= depth; ++i) snap[("ask_depth_" + std::to_string(i)).c_str()] = 0;

        snap["total_bid_volume"] = tot_bid;
        snap["total_ask_volume"] = tot_ask;
        snap["book_imbalance"] = (tot_bid + tot_ask > 0) ? static_cast<double>(tot_bid - tot_ask) / (tot_bid + tot_ask) : 0.0;

        return snap;
    }
};

PYBIND11_MODULE(clob_replay_engine, m) {
    m.doc() = "Ultra-Fast C++ Vectorized Replay Engine";
    py::class_<FastCLOBReplayEngine>(m, "FastCLOBReplayEngine")
        .def(py::init<>())
        .def("remove_traded_qty", &FastCLOBReplayEngine::remove_traded_qty)
        .def("snapshot", &FastCLOBReplayEngine::snapshot);
}
