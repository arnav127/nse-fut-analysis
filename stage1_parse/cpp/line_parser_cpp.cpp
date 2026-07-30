#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <string>
#include <cstdlib>

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
    int len = line.length();

    if (len < 87) return row;

    row["record_indicator"] = std::string(str, 2);
    row["segment"] = std::string(str + 2, 4);
    row["order_number"] = fast_atoll(str + 6, 16);
    row["txn_time_jiffies"] = fast_atoll(str + 22, 14);
    row["buy_sell"] = std::string(str + 36, 1);
    row["activity_type"] = (int)fast_atoll(str + 37, 1);
    row["symbol"] = std::string(str + 38, 10);
    row["series"] = std::string(str + 48, 2);
    row["volume_disclosed"] = fast_atoll(str + 50, 8);
    row["volume_original"] = fast_atoll(str + 58, 8);
    row["limit_price"] = fast_atoll(str + 66, 8);
    row["trigger_price"] = fast_atoll(str + 74, 8);
    row["mkt_order_flag"] = std::string(str + 82, 1);
    row["stop_loss_flag"] = std::string(str + 83, 1);
    row["ioc_flag"] = std::string(str + 84, 1);
    row["algo_indicator"] = (int)fast_atoll(str + 85, 1);
    row["client_identity"] = (int)fast_atoll(str + 86, 1);

    return row;
}

PYBIND11_MODULE(line_parser_cpp, m) {
    m.doc() = "C++ High-Speed Fixed-Width Line Parser";
    m.def("parse_cm_order_line_fast", &parse_cm_order_line_fast, py::arg("line"));
}
