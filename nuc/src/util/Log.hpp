#pragma once

#include <memory>
#include <spdlog/spdlog.h>
#include <string_view>

namespace femto::log {

void init(std::string_view level);
std::shared_ptr<spdlog::logger> get();
void stderrError(std::string_view message);

}  // namespace femto::log
