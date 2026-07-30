"""
line_parser_cpp.cpp — Data-Oriented Design (DOD) High-Speed Fixed-Width Line & Columnar Batch Parser.
Optimizations:
1. Columnar Batch Parsing (SoA): Parses entire vectors/batches of text lines in a single C++ loop,
   producing columnar arrays without per-line Python dictionary allocation overhead.
2. Direct raw pointer arithmetic without intermediate std::string heap allocations.
"""
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <string>
#include <vector>
#include <cstdlib>
#include <cstdint>

namespace py = pybind11;

static inline long long fast_atoll(const char* p, int len) {
    long long val = 0;
    for (int i = 0; i < len; ++i) {
        if (p[i] >= '0' && p[i] <= '9') {
            val = val * 10 + (p[i] - '0');
        }
    }
    return val;
}

py::dict parse_cm_order_line_fast(const std::string& line) {
    py::dict row;
    const char* str = line.c_str();
    int len = static_cast<int>(line.length());

    if (len < 87) return row;

    row["record_indicator"] = std::string(str, 2);
    row["segment"] = std::string(str + 2, 4);
    row["order_number"] = fast_atoll(str + 6, 16);
    row["txn_time_jiffies"] = fast_atoll(str + 22, 14);
    row["buy_sell"] = std::string(str + 36, 1);
    row["activity_type"] = static_cast<int>(fast_atoll(str + 37, 1));
    row["symbol"] = std::string(str + 38, 10);
    row["series"] = std::string(str + 48, 2);
    row["volume_disclosed"] = fast_atoll(str + 50, 8);
    row["volume_original"] = fast_atoll(str + 58, 8);
    row["limit_price"] = fast_atoll(str + 66, 8);
    row["trigger_price"] = fast_atoll(str + 74, 8);
    row["mkt_order_flag"] = std::string(str + 82, 1);
    row["stop_loss_flag"] = std::string(str + 83, 1);
    row["ioc_flag"] = std::string(str + 84, 1);
    row["algo_indicator"] = static_cast<int>(fast_atoll(str + 85, 1));
    row["client_identity"] = static_cast<int>(fast_atoll(str + 86, 1));

    return row;
}

// Data-Oriented Columnar Batch Parser (SoA output for DataFrame creation)
py::dict parse_cm_orders_batch(const std::vector<std::string>& lines) {
    size_t n = lines.size();
    std::vector<long long> order_numbers;
    std::vector<long long> txn_times;
    std::vector<std::string> buy_sells;
    std::vector<int> activity_types;
    std::vector<std::string> symbols;
    std::vector<long long> vols_original;
    std::vector<double> prices;
    std::vector<int> algos;
    std::vector<int> clients;

    order_numbers.reserve(n);
    txn_times.reserve(n);
    buy_sells.reserve(n);
    activity_types.reserve(n);
    symbols.reserve(n);
    vols_original.reserve(n);
    prices.reserve(n);
    algos.reserve(n);
    clients.reserve(n);

    for (const auto& line : lines) {
        const char* str = line.c_str();
        if (line.length() < 87) continue;

        order_numbers.push_back(fast_atoll(str + 6, 16));
        txn_times.push_back(fast_atoll(str + 22, 14));
        buy_sells.emplace_back(str + 36, 1);
        activity_types.push_back(static_cast<int>(fast_atoll(str + 37, 1)));
        symbols.emplace_back(str + 38, 10);
        vols_original.push_back(fast_atoll(str + 58, 8));
        prices.push_back(static_cast<double>(fast_atoll(str + 66, 8)) / 100.0); // Convert paise to rupees
        algos.push_back(static_cast<int>(fast_atoll(str + 85, 1)));
        clients.push_back(static_cast<int>(fast_atoll(str + 86, 1)));
    }

    py::dict cols;
    cols["order_number"] = order_numbers;
    cols["txn_time_jiffies"] = txn_times;
    cols["buy_sell"] = buy_sells;
    cols["activity_type"] = activity_types;
    cols["symbol"] = symbols;
    cols["volume_original"] = vols_original;
    cols["limit_price"] = prices;
    cols["algo_indicator"] = algos;
    cols["client_identity"] = clients;

    return cols;
}

PYBIND11_MODULE(line_parser_cpp, m) {
    m.doc() = "C++ Data-Oriented Design (DOD) High-Speed Fixed-Width Line & Columnar Batch Parser";
    m.def("parse_cm_order_line_fast", &parse_cm_order_line_fast, py::arg("line"));
    m.def("parse_cm_orders_batch", &parse_cm_orders_batch, py::arg("lines"));
}
