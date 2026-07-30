#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <map>
#include <unordered_map>
#include <string>
#include <vector>
#include <cmath>
#include <algorithm>

namespace py = pybind11;

struct OrderInfo {
    std::string side;
    double price;
    long long qty;
};

class OrderBookCpp {
private:
    // bid: highest price first (std::greater)
    std::map<double, long long, std::greater<double>> bid;
    // ask: lowest price first (std::less)
    std::map<double, long long> ask;
    // fast lookup for order details by order_number
    std::unordered_map<long long, OrderInfo> orders;

    void add_order(long long order_number, const std::string& side, double price, long long qty) {
        if (price <= 0 || qty <= 0) return;
        if (side == "B") {
            bid[price] += qty;
        } else {
            ask[price] += qty;
        }
        orders[order_number] = {side, price, qty};
    }

    void cancel_order(long long order_number) {
        auto it = orders.find(order_number);
        if (it == orders.end()) return;

        const auto& info = it->second;
        if (info.side == "B") {
            auto b_it = bid.find(info.price);
            if (b_it != bid.end()) {
                b_it->second -= info.qty;
                if (b_it->second <= 0) bid.erase(b_it);
            }
        } else {
            auto a_it = ask.find(info.price);
            if (a_it != ask.end()) {
                a_it->second -= info.qty;
                if (a_it->second <= 0) ask.erase(a_it);
            }
        }
        orders.erase(it);
    }

public:
    OrderBookCpp() {}

    void process_event(long long order_number, int activity_type, const std::string& side, double price, long long qty) {
        if (activity_type == 1) {        // Entry
            add_order(order_number, side, price, qty);
        } else if (activity_type == 3) { // Cancel
            cancel_order(order_number);
        } else if (activity_type == 4) { // Modify
            cancel_order(order_number);
            add_order(order_number, side, price, qty);
        }
    }

    void remove_traded_qty(long long order_number, long long traded_qty) {
        auto it = orders.find(order_number);
        if (it == orders.end()) return;

        auto& info = it->second;
        info.qty -= traded_qty;

        if (info.side == "B") {
            auto b_it = bid.find(info.price);
            if (b_it != bid.end()) {
                b_it->second -= traded_qty;
                if (b_it->second <= 0) bid.erase(b_it);
            }
        } else {
            auto a_it = ask.find(info.price);
            if (a_it != ask.end()) {
                a_it->second -= traded_qty;
                if (a_it->second <= 0) ask.erase(a_it);
            }
        }

        if (info.qty <= 0) {
            orders.erase(it);
        }
    }

    py::dict snapshot(int depth = 10) {
        py::dict snap;

        double best_bid = 0.0;
        double best_ask = 0.0;
        bool has_bid = !bid.empty();
        bool has_ask = !ask.empty();

        if (has_bid) best_bid = bid.begin()->first;
        if (has_ask) best_ask = ask.begin()->first;

        if (has_bid) snap["best_bid"] = best_bid; else snap["best_bid"] = py::none();
        if (has_ask) snap["best_ask"] = best_ask; else snap["best_ask"] = py::none();

        double midpoint = 0.0;
        double spread = 0.0;
        double spread_bps = 0.0;

        if (has_bid && has_ask) {
            midpoint = (best_bid + best_ask) / 2.0;
            spread = best_ask - best_bid;
            spread_bps = (midpoint > 0) ? (spread / midpoint * 10000.0) : 0.0;

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
        for (auto b_it = bid.begin(); b_it != bid.end() && count < depth; ++b_it, ++count) {
            tot_bid_vol += b_it->second;
            std::string key = "bid_depth_" + std::to_string(count + 1);
            snap[key.c_str()] = b_it->second;
        }
        for (int i = count + 1; i <= depth; ++i) {
            std::string key = "bid_depth_" + std::to_string(i);
            snap[key.c_str()] = 0;
        }

        long long tot_ask_vol = 0;
        count = 0;
        for (auto a_it = ask.begin(); a_it != ask.end() && count < depth; ++a_it, ++count) {
            tot_ask_vol += a_it->second;
            std::string key = "ask_depth_" + std::to_string(count + 1);
            snap[key.c_str()] = a_it->second;
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
};

PYBIND11_MODULE(order_book_cpp, m) {
    m.doc() = "Ultra-fast C++ Limit Order Book Engine for NSE Expiry Day Analysis";

    py::class_<OrderBookCpp>(m, "OrderBookCpp")
        .def(py::init<>())
        .def("process_event", &OrderBookCpp::process_event, py::arg("order_number"), py::arg("activity_type"), py::arg("side"), py::arg("price"), py::arg("qty"))
        .def("remove_traded_qty", &OrderBookCpp::remove_traded_qty, py::arg("order_number"), py::arg("traded_qty"))
        .def("snapshot", &OrderBookCpp::snapshot, py::arg("depth") = 10);
}
