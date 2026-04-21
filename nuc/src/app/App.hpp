#pragma once

#include "config/Config.hpp"
#include "util/StatsCollector.hpp"

#include <atomic>
#include <filesystem>
#include <memory>
#include <optional>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

namespace femto {

class OrbbecCamera;
class IPreviewPublisher;
class DepthBinaryPublisher;
class HttpServer;
class SsdpService;
class SyntheticFrameGenerator;

class App {
public:
    App();
    ~App();

    int run(int argc, char **argv);
    void requestStop();

private:
    int runTestCapture(const std::filesystem::path &outputDir);
    void wireCallbacks();
    void handleColorFrame(const OrbbecCamera::FrameEnvelope &frame);
    void handleDepthFrame(const OrbbecCamera::DepthEnvelope &frame, const nlohmann::json &calibration);
    void logRuntimeDependencyHints() const;
    bool syntheticSourceEnabled() const;
    std::optional<OrbbecCamera::DepthEnvelope> latestDepthFrameForSnapshots() const;
    nlohmann::json metadataJson() const;
    nlohmann::json statsJson() const;
    std::string sourceMode() const;
    nlohmann::json healthJson() const;
    nlohmann::json heartbeatJson() const;
    nlohmann::json streamsJson() const;
    nlohmann::json discoveryJson() const;
    void publishDepthPreview(const std::vector<uint16_t> &values, int width, int height, float depthScale, uint64_t timestampUs);

    Config config_;
    StatsCollector stats_;
    std::unique_ptr<OrbbecCamera> camera_;
    std::unique_ptr<SyntheticFrameGenerator> synthetic_;
    std::unique_ptr<IPreviewPublisher> colorPreview_;
    std::unique_ptr<IPreviewPublisher> depthPreview_;
    std::unique_ptr<DepthBinaryPublisher> depthBinary_;
    std::unique_ptr<HttpServer> http_;
    std::unique_ptr<SsdpService> discovery_;
    std::atomic<bool> stopRequested_{ false };
};

}  // namespace femto
