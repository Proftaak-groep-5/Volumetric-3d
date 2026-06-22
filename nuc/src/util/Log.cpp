#include "util/Log.hpp"

#include <functional>
#include <iostream>
#include <mutex>
#include <string>

#include <spdlog/fmt/fmt.h>
#include <spdlog/sinks/base_sink.h>
#include <spdlog/sinks/stdout_color_sinks.h>
#include <spdlog/spdlog.h>

namespace femto::log {
namespace {
std::shared_ptr<spdlog::logger> g_logger;
std::once_flag g_once;
std::mutex g_lineMutex;
std::string g_latestLine;
std::function<void(std::string)> g_lineCallback;

class LatestLineSink final : public spdlog::sinks::base_sink<std::mutex> {
protected:
    void sink_it_(const spdlog::details::log_msg &message) override {
        spdlog::memory_buf_t formatted;
        formatter_->format(message, formatted);
        std::string line = fmt::to_string(formatted);
        while(!line.empty() && (line.back() == '\n' || line.back() == '\r')) {
            line.pop_back();
        }

        std::function<void(std::string)> callback;
        {
            std::scoped_lock lock(g_lineMutex);
            g_latestLine = line;
            callback = g_lineCallback;
        }
        if(callback) {
            callback(std::move(line));
        }
    }

    void flush_() override {}
};
}  // namespace

void init(std::string_view level) {
    std::call_once(g_once, [&]() {
        g_logger = spdlog::stdout_color_mt("FemtoBoltNuc");
        g_logger->sinks().push_back(std::make_shared<LatestLineSink>());
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

std::optional<std::string> latestLine() {
    std::scoped_lock lock(g_lineMutex);
    if(g_latestLine.empty()) {
        return std::nullopt;
    }
    return g_latestLine;
}

void setLineCallback(std::function<void(std::string)> callback) {
    std::scoped_lock lock(g_lineMutex);
    g_lineCallback = std::move(callback);
}

}  // namespace femto::log
