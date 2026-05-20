#pragma once

#include "config/Config.hpp"

#include <atomic>
#include <functional>
#include <string>
#include <thread>

#include <nlohmann/json.hpp>

namespace femto {

class SsdpService {
public:
    explicit SsdpService(const Config &config);
    ~SsdpService();

    void start(std::function<nlohmann::json()> discoveryProvider);
    void stop();

private:
    void workerLoop();
    void announceOnce();

    Config config_;
    std::function<nlohmann::json()> discoveryProvider_;
    std::thread worker_;
    std::atomic<bool> running_{ false };
};

}  // namespace femto
