#pragma once

#include <memory>
#include <spdlog/spdlog.h>
#include <functional>
#include <optional>
#include <string>
#include <string_view>

namespace femto::log {

void init(std::string_view level);
std::shared_ptr<spdlog::logger> get();
void stderrError(std::string_view message);
std::optional<std::string> latestLine();
void setLineCallback(std::function<void(std::string)> callback);

}  // namespace femto::log
