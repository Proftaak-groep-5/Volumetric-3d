#include "util/Log.hpp"

#include <iostream>
#include <mutex>

#include <spdlog/sinks/stdout_color_sinks.h>
#include <spdlog/spdlog.h>

namespace femto::log {
namespace {
std::shared_ptr<spdlog::logger> g_logger;
std::once_flag g_once;
}  // namespace

void init(std::string_view level) {
    std::call_once(g_once, [&]() {
        g_logger = spdlog::stdout_color_mt("FemtoBoltNuc");
        g_logger->set_pattern("%Y-%m-%d %H:%M:%S.%e [%^%l%$] %v");
    });
    auto parsed = spdlog::level::from_str(std::string(level));
    g_logger->set_level(parsed);
    spdlog::set_default_logger(g_logger);
}

std::shared_ptr<spdlog::logger> get() {
    if(!g_logger) {
        init("info");
    }
    return g_logger;
}

void stderrError(std::string_view message) {
    std::cerr << "[error] " << message << '\n';
}

}  // namespace femto::log
