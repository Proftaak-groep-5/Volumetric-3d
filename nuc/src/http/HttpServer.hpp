#pragma once

#include "config/Config.hpp"

#include <functional>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

namespace femto {

class HttpServer {
public:
    struct DepthSnapshot {
        std::shared_ptr<const std::vector<uint8_t>> pngBytes;
        float depthScale = 1.0f;
        int width = 0;
        int height = 0;
        std::string pixelFormat;
    };

    struct Callbacks {
        std::function<nlohmann::json()> health;
        std::function<nlohmann::json()> heartbeat;
        std::function<nlohmann::json()> metadata;
        std::function<nlohmann::json()> streams;
        std::function<nlohmann::json()> settings;
        std::function<nlohmann::json(const nlohmann::json &)> updateSettings;
        std::function<nlohmann::json()> restartStreams;
        std::function<nlohmann::json()> capabilities;
        std::function<nlohmann::json()> stats;
        std::function<nlohmann::json()> reconnect;
        std::function<nlohmann::json()> restart;
        std::function<std::shared_ptr<const std::vector<uint8_t>>()> latestColorJpeg;
        std::function<std::shared_ptr<const std::vector<uint8_t>>()> latestDepthPreviewJpeg;
        std::function<std::optional<DepthSnapshot>()> latestDepthSnapshot;
        std::function<std::shared_ptr<const std::vector<uint8_t>>()> latestDepthPacket;
        std::function<nlohmann::json()> discovery;
    };

    explicit HttpServer(const Config &config);
    ~HttpServer();

    void start(Callbacks callbacks);
    void stop();

    void publishColorPreview(std::shared_ptr<const std::vector<uint8_t>> jpeg);
    void publishDepthPreview(std::shared_ptr<const std::vector<uint8_t>> jpeg);
    void publishDepthBinary(std::shared_ptr<const std::vector<uint8_t>> packet);

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
    Config config_;
    Callbacks callbacks_;
};

}  // namespace femto
