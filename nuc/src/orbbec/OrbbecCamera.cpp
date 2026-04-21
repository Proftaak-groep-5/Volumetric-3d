#include "orbbec/OrbbecCamera.hpp"

#include "util/BuildFeatures.hpp"
#include "util/ImageIO.hpp"
#include "util/Log.hpp"

#include <algorithm>
#include <chrono>
#include <cstring>
#include <stdexcept>

#if NUC_HAS_ORBBEC
#include <libobsensor/ObSensor.hpp>
#endif

namespace femto {
namespace {

nlohmann::json profileToJson(int width, int height, int fps, const std::string &format) {
    return {
        { "width", width },
        { "height", height },
        { "fps", fps },
        { "format", format },
    };
}

std::string obFormatToString(int format) {
    switch(format) {
    case 22:
        return "RGB";
    case 23:
        return "BGR";
    case 25:
        return "BGRA";
    case 31:
        return "RGBA";
    case 5:
        return "MJPEG";
    case 0:
        return "YUYV";
    case 8:
        return "Y16";
    case 28:
        return "Z16";
    default:
        return std::to_string(format);
    }
}

void yuyvToRgb(const uint8_t *src, int width, int height, std::vector<uint8_t> &dst) {
    dst.resize(static_cast<std::size_t>(width) * static_cast<std::size_t>(height) * 3);
    auto clamp = [](int value) { return static_cast<uint8_t>(std::max(0, std::min(255, value))); };
    for(int i = 0, j = 0; i < width * height * 2; i += 4, j += 6) {
        const int y0 = src[i + 0];
        const int u = src[i + 1] - 128;
        const int y1 = src[i + 2];
        const int v = src[i + 3] - 128;
        const int c1 = y0 - 16;
        const int c2 = y1 - 16;
        const int d = u;
        const int e = v;

        const auto writePixel = [&](int c, int offset) {
            const int r = (298 * c + 409 * e + 128) >> 8;
            const int g = (298 * c - 100 * d - 208 * e + 128) >> 8;
            const int b = (298 * c + 516 * d + 128) >> 8;
            dst[offset + 0] = clamp(r);
            dst[offset + 1] = clamp(g);
            dst[offset + 2] = clamp(b);
        };
        writePixel(c1, j);
        writePixel(c2, j + 3);
    }
}

void bgrToRgb(const uint8_t *src, int width, int height, std::vector<uint8_t> &dst) {
    dst.resize(static_cast<std::size_t>(width) * static_cast<std::size_t>(height) * 3);
    for(int i = 0; i < width * height; ++i) {
        dst[3 * i + 0] = src[3 * i + 2];
        dst[3 * i + 1] = src[3 * i + 1];
        dst[3 * i + 2] = src[3 * i + 0];
    }
}

void bgraToRgb(const uint8_t *src, int width, int height, std::vector<uint8_t> &dst, bool rgba) {
    dst.resize(static_cast<std::size_t>(width) * static_cast<std::size_t>(height) * 3);
    for(int i = 0; i < width * height; ++i) {
        if(rgba) {
            dst[3 * i + 0] = src[4 * i + 0];
            dst[3 * i + 1] = src[4 * i + 1];
            dst[3 * i + 2] = src[4 * i + 2];
        }
        else {
            dst[3 * i + 0] = src[4 * i + 2];
            dst[3 * i + 1] = src[4 * i + 1];
            dst[3 * i + 2] = src[4 * i + 0];
        }
    }
}

}  // namespace

struct OrbbecCamera::Impl {
#if NUC_HAS_ORBBEC
    std::unique_ptr<ob::Context> context;
    std::shared_ptr<ob::Device> device;
    std::unique_ptr<ob::Pipeline> pipeline;
    std::shared_ptr<ob::Config> pipelineConfig;
    std::shared_ptr<ob::VideoStreamProfile> colorProfile;
    std::shared_ptr<ob::VideoStreamProfile> depthProfile;
#endif
};

OrbbecCamera::OrbbecCamera(Config &config, StatsCollector &stats)
    : impl_(std::make_unique<Impl>()), config_(config), stats_(stats), runtimeSettings_(config.runtime) {
    metadata_ = {
        { "connected", false },
        { "device", nullptr },
        { "sdk", { { "orbbec_available", static_cast<bool>(NUC_HAS_ORBBEC) } } },
    };
    capabilities_ = {
        { "orbbec_available", static_cast<bool>(NUC_HAS_ORBBEC) },
        { "runtime_update_supported", { { "color_controls", true }, { "profile_change_requires_restart", true } } },
    };
}

OrbbecCamera::~OrbbecCamera() {
    stop();
}

void OrbbecCamera::start() {
    if(running_.exchange(true)) {
        return;
    }
    log::get()->info("event=camera state=starting");
    worker_ = std::thread([this] { workerLoop(); });
}

void OrbbecCamera::stop() {
    if(!running_.exchange(false)) {
        return;
    }
    if(worker_.joinable()) {
        worker_.join();
    }
    std::scoped_lock lock(mutex_);
    disconnectLocked();
    log::get()->info("event=camera state=stopped");
}

void OrbbecCamera::requestReconnect() {
    reconnectRequested_ = true;
    log::get()->info("event=camera action=reconnect_requested");
}

void OrbbecCamera::requestRestartStreams() {
    restartRequested_ = true;
    log::get()->info("event=camera action=restart_streams_requested");
}

void OrbbecCamera::setColorCallback(ColorCallback callback) {
    std::scoped_lock lock(mutex_);
    colorCallback_ = std::move(callback);
}

void OrbbecCamera::setDepthCallback(DepthCallback callback) {
    std::scoped_lock lock(mutex_);
    depthCallback_ = std::move(callback);
}

nlohmann::json OrbbecCamera::metadataJson() const {
    std::scoped_lock lock(mutex_);
    return metadata_;
}

nlohmann::json OrbbecCamera::capabilitiesJson() const {
    std::scoped_lock lock(mutex_);
    return capabilities_;
}

nlohmann::json OrbbecCamera::settingsJson() const {
    std::scoped_lock lock(mutex_);
    return {
        { "color", {
            { "enabled", runtimeSettings_.colorEnabled },
            { "width", config_.color.width },
            { "height", config_.color.height },
            { "fps", config_.color.fps },
            { "target_bitrate_mbps", config_.color.targetBitrateMbps },
            { "exposure_auto", runtimeSettings_.colorExposureAuto },
            { "exposure_value", runtimeSettings_.colorExposureValue },
            { "gain", runtimeSettings_.colorGain },
            { "white_balance_auto", runtimeSettings_.colorWhiteBalanceAuto },
            { "white_balance_value", runtimeSettings_.colorWhiteBalanceValue },
            { "brightness", runtimeSettings_.colorBrightness },
            { "contrast", runtimeSettings_.colorContrast },
            { "saturation", runtimeSettings_.colorSaturation },
        } },
        { "depth_preview", {
            { "enabled", runtimeSettings_.depthPreviewEnabled },
            { "min_depth_mm", runtimeSettings_.depthPreviewMinMm },
            { "max_depth_mm", runtimeSettings_.depthPreviewMaxMm },
            { "target_bitrate_mbps", config_.depthPreview.targetBitrateMbps },
            { "mode", config_.depthPreview.mode },
        } },
        { "authoritative_depth", {
            { "enabled", runtimeSettings_.depthBinaryEnabled },
            { "compression", config_.depthBinary.compression },
            { "compression_level", config_.depthBinary.compressionLevel },
        } },
    };
}

RuntimeSettings OrbbecCamera::runtimeSettings() const {
    std::scoped_lock lock(mutex_);
    return runtimeSettings_;
}

bool OrbbecCamera::connected() const {
    std::scoped_lock lock(mutex_);
    return connected_;
}

std::string OrbbecCamera::cameraSerial() const {
    std::scoped_lock lock(mutex_);
    return metadata_.value("device", nlohmann::json::object()).value("serial_number", "");
}

std::string OrbbecCamera::cameraName() const {
    std::scoped_lock lock(mutex_);
    return metadata_.value("device", nlohmann::json::object()).value("name", "");
}

std::string OrbbecCamera::lastError() const {
    std::scoped_lock lock(mutex_);
    return lastError_;
}

std::optional<OrbbecCamera::FrameEnvelope> OrbbecCamera::latestColorFrame() const {
    std::scoped_lock lock(mutex_);
    return latestColorFrame_;
}

std::optional<OrbbecCamera::DepthEnvelope> OrbbecCamera::latestDepthFrame() const {
    std::scoped_lock lock(mutex_);
    return latestDepthFrame_;
}

nlohmann::json OrbbecCamera::applySettings(const nlohmann::json &patch) {
    std::scoped_lock lock(mutex_);
    nlohmann::json applied = nlohmann::json::array();
    nlohmann::json errors = nlohmann::json::array();
    bool restartRequired = false;

    const auto addUnsupported = [&](const std::string &path, const std::string &message) {
        errors.push_back({ { "path", path }, { "error", message } });
    };

#if NUC_HAS_ORBBEC
    const auto trySetInt = [&](int propertyId, std::optional<int> value, const std::string &path) {
        if(!value || !impl_->device) {
            return;
        }
        try {
            if(!impl_->device->isPropertySupported(static_cast<OBPropertyID>(propertyId), OB_PERMISSION_WRITE)) {
                addUnsupported(path, "property not supported");
                return;
            }
            impl_->device->setIntProperty(static_cast<OBPropertyID>(propertyId), *value);
            applied.push_back(path);
        }
        catch(const std::exception &ex) {
            addUnsupported(path, ex.what());
        }
    };
    const auto trySetBool = [&](int propertyId, bool value, const std::string &path) {
        if(!impl_->device) {
            return;
        }
        try {
            if(!impl_->device->isPropertySupported(static_cast<OBPropertyID>(propertyId), OB_PERMISSION_WRITE)) {
                addUnsupported(path, "property not supported");
                return;
            }
            impl_->device->setBoolProperty(static_cast<OBPropertyID>(propertyId), value);
            applied.push_back(path);
        }
        catch(const std::exception &ex) {
            addUnsupported(path, ex.what());
        }
    };
#endif

    if(patch.contains("color")) {
        const auto &color = patch.at("color");
        if(color.contains("enabled")) {
            runtimeSettings_.colorEnabled = color.at("enabled").get<bool>();
            config_.color.enabled = runtimeSettings_.colorEnabled;
            applied.push_back("color.enabled");
        }
        if(color.contains("target_bitrate_mbps")) {
            config_.color.targetBitrateMbps = color.at("target_bitrate_mbps").get<int>();
            applied.push_back("color.target_bitrate_mbps");
        }
        if(color.contains("width")) {
            config_.color.width = color.at("width").get<int>();
            restartRequired = true;
            applied.push_back("color.width");
        }
        if(color.contains("height")) {
            config_.color.height = color.at("height").get<int>();
            restartRequired = true;
            applied.push_back("color.height");
        }
        if(color.contains("fps")) {
            config_.color.fps = color.at("fps").get<int>();
            restartRequired = true;
            applied.push_back("color.fps");
        }
        if(color.contains("exposure_auto")) {
            runtimeSettings_.colorExposureAuto = color.at("exposure_auto").get<bool>();
#if NUC_HAS_ORBBEC
            trySetBool(OB_PROP_COLOR_AUTO_EXPOSURE_BOOL, runtimeSettings_.colorExposureAuto, "color.exposure_auto");
#else
            applied.push_back("color.exposure_auto");
#endif
        }
        if(color.contains("exposure_value")) {
            runtimeSettings_.colorExposureValue = color.at("exposure_value").get<int>();
#if NUC_HAS_ORBBEC
            trySetInt(OB_PROP_COLOR_EXPOSURE_INT, runtimeSettings_.colorExposureValue, "color.exposure_value");
#else
            applied.push_back("color.exposure_value");
#endif
        }
        if(color.contains("gain")) {
            runtimeSettings_.colorGain = color.at("gain").get<int>();
#if NUC_HAS_ORBBEC
            trySetInt(OB_PROP_COLOR_GAIN_INT, runtimeSettings_.colorGain, "color.gain");
#else
            applied.push_back("color.gain");
#endif
        }
        if(color.contains("white_balance_auto")) {
            runtimeSettings_.colorWhiteBalanceAuto = color.at("white_balance_auto").get<bool>();
#if NUC_HAS_ORBBEC
            trySetBool(OB_PROP_COLOR_AUTO_WHITE_BALANCE_BOOL, runtimeSettings_.colorWhiteBalanceAuto, "color.white_balance_auto");
#else
            applied.push_back("color.white_balance_auto");
#endif
        }
        if(color.contains("white_balance_value")) {
            runtimeSettings_.colorWhiteBalanceValue = color.at("white_balance_value").get<int>();
#if NUC_HAS_ORBBEC
            trySetInt(OB_PROP_COLOR_WHITE_BALANCE_INT, runtimeSettings_.colorWhiteBalanceValue, "color.white_balance_value");
#else
            applied.push_back("color.white_balance_value");
#endif
        }
        if(color.contains("brightness")) {
            runtimeSettings_.colorBrightness = color.at("brightness").get<int>();
#if NUC_HAS_ORBBEC
            trySetInt(OB_PROP_COLOR_BRIGHTNESS_INT, runtimeSettings_.colorBrightness, "color.brightness");
#else
            applied.push_back("color.brightness");
#endif
        }
        if(color.contains("contrast")) {
            runtimeSettings_.colorContrast = color.at("contrast").get<int>();
#if NUC_HAS_ORBBEC
            trySetInt(OB_PROP_COLOR_CONTRAST_INT, runtimeSettings_.colorContrast, "color.contrast");
#else
            applied.push_back("color.contrast");
#endif
        }
        if(color.contains("saturation")) {
            runtimeSettings_.colorSaturation = color.at("saturation").get<int>();
#if NUC_HAS_ORBBEC
            trySetInt(OB_PROP_COLOR_SATURATION_INT, runtimeSettings_.colorSaturation, "color.saturation");
#else
            applied.push_back("color.saturation");
#endif
        }
    }

    if(patch.contains("depth_preview")) {
        const auto &depthPreview = patch.at("depth_preview");
        if(depthPreview.contains("enabled")) {
            runtimeSettings_.depthPreviewEnabled = depthPreview.at("enabled").get<bool>();
            config_.depthPreview.enabled = runtimeSettings_.depthPreviewEnabled;
            applied.push_back("depth_preview.enabled");
        }
        if(depthPreview.contains("min_depth_mm")) {
            runtimeSettings_.depthPreviewMinMm = depthPreview.at("min_depth_mm").get<int>();
            config_.depthPreview.minDepthMm = runtimeSettings_.depthPreviewMinMm;
            applied.push_back("depth_preview.min_depth_mm");
        }
        if(depthPreview.contains("max_depth_mm")) {
            runtimeSettings_.depthPreviewMaxMm = depthPreview.at("max_depth_mm").get<int>();
            config_.depthPreview.maxDepthMm = runtimeSettings_.depthPreviewMaxMm;
            applied.push_back("depth_preview.max_depth_mm");
        }
        if(depthPreview.contains("mode")) {
            config_.depthPreview.mode = depthPreview.at("mode").get<std::string>();
            applied.push_back("depth_preview.mode");
        }
        if(depthPreview.contains("target_bitrate_mbps")) {
            config_.depthPreview.targetBitrateMbps = depthPreview.at("target_bitrate_mbps").get<int>();
            applied.push_back("depth_preview.target_bitrate_mbps");
        }
    }

    if(patch.contains("authoritative_depth")) {
        const auto &depthBinary = patch.at("authoritative_depth");
        if(depthBinary.contains("enabled")) {
            runtimeSettings_.depthBinaryEnabled = depthBinary.at("enabled").get<bool>();
            config_.depthBinary.enabled = runtimeSettings_.depthBinaryEnabled;
            applied.push_back("authoritative_depth.enabled");
        }
        if(depthBinary.contains("compression_level")) {
            config_.depthBinary.compressionLevel = depthBinary.at("compression_level").get<int>();
            applied.push_back("authoritative_depth.compression_level");
        }
    }

    if(restartRequired) {
        restartRequested_ = true;
    }

    const auto settings = nlohmann::json{
        { "color", {
            { "enabled", runtimeSettings_.colorEnabled },
            { "width", config_.color.width },
            { "height", config_.color.height },
            { "fps", config_.color.fps },
            { "target_bitrate_mbps", config_.color.targetBitrateMbps },
            { "exposure_auto", runtimeSettings_.colorExposureAuto },
            { "exposure_value", runtimeSettings_.colorExposureValue },
            { "gain", runtimeSettings_.colorGain },
            { "white_balance_auto", runtimeSettings_.colorWhiteBalanceAuto },
            { "white_balance_value", runtimeSettings_.colorWhiteBalanceValue },
            { "brightness", runtimeSettings_.colorBrightness },
            { "contrast", runtimeSettings_.colorContrast },
            { "saturation", runtimeSettings_.colorSaturation },
        } },
        { "depth_preview", {
            { "enabled", runtimeSettings_.depthPreviewEnabled },
            { "min_depth_mm", runtimeSettings_.depthPreviewMinMm },
            { "max_depth_mm", runtimeSettings_.depthPreviewMaxMm },
            { "target_bitrate_mbps", config_.depthPreview.targetBitrateMbps },
            { "mode", config_.depthPreview.mode },
        } },
        { "authoritative_depth", {
            { "enabled", runtimeSettings_.depthBinaryEnabled },
            { "compression", config_.depthBinary.compression },
            { "compression_level", config_.depthBinary.compressionLevel },
        } },
    };

    return {
        { "ok", errors.empty() },
        { "restart_required", restartRequired },
        { "applied", applied },
        { "errors", errors },
        { "settings", settings },
    };
}

void OrbbecCamera::workerLoop() {
    while(running_) {
        {
            std::scoped_lock lock(mutex_);
            if(reconnectRequested_ || restartRequested_) {
                disconnectLocked();
                reconnectRequested_ = false;
                restartRequested_ = false;
            }
            if(!connected_) {
                connectLocked();
            }
        }

        if(!connected()) {
            const auto now = std::chrono::steady_clock::now();
            if(lastNoCameraLog_.time_since_epoch().count() == 0 || now - lastNoCameraLog_ >= std::chrono::seconds(5)) {
                log::get()->warn("event=camera state=no_camera_mode error=\"{}\" retry_ms={}", lastError(), config_.camera.retryIntervalMs);
                lastNoCameraLog_ = now;
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(config_.camera.retryIntervalMs));
            continue;
        }

        try {
            captureOnce();
        }
        catch(const std::exception &ex) {
            auto logger = log::get();
            logger->warn("capture loop error: {}", ex.what());
            std::scoped_lock lock(mutex_);
            lastError_ = ex.what();
            disconnectLocked();
            std::this_thread::sleep_for(std::chrono::milliseconds(config_.camera.retryIntervalMs));
        }
    }
}

void OrbbecCamera::disconnectLocked() {
    const auto wasConnected = connected_;
#if NUC_HAS_ORBBEC
    if(impl_->pipeline) {
        try {
            impl_->pipeline->stop();
        }
        catch(...) {
        }
    }
    impl_->pipeline.reset();
    impl_->device.reset();
    impl_->pipelineConfig.reset();
    impl_->colorProfile.reset();
    impl_->depthProfile.reset();
#endif
    connected_ = false;
    metadata_["connected"] = false;
    latestColorFrame_.reset();
    latestDepthFrame_.reset();
    if(wasConnected) {
        log::get()->warn("event=camera state=disconnected");
    }
}

bool OrbbecCamera::connectLocked() {
#if !NUC_HAS_ORBBEC
    lastError_ = "built without Orbbec SDK";
    return false;
#else
    try {
        if(!impl_->context) {
            impl_->context = std::make_unique<ob::Context>();
        }
        auto deviceList = impl_->context->queryDeviceList();
        if(deviceList->getCount() == 0) {
            lastError_ = "no Orbbec devices found";
            return false;
        }

        if(!config_.camera.serialNumber.empty()) {
            impl_->device = deviceList->getDeviceBySN(config_.camera.serialNumber);
            if(!impl_->device) {
                lastError_ = "configured serial not found";
                return false;
            }
        }
        else {
            for(uint32_t i = 0; i < deviceList->getCount(); ++i) {
                auto candidate = deviceList->getDevice(i);
                if(!candidate) {
                    continue;
                }
                const auto info = candidate->getDeviceInfo();
                if(info && std::string(info->name()).find("Femto Bolt") != std::string::npos) {
                    impl_->device = candidate;
                    break;
                }
            }
            if(!impl_->device && config_.camera.autoOpenFirstFemtoBolt) {
                impl_->device = deviceList->getDevice(0);
            }
        }
        if(!impl_->device) {
            lastError_ = "no matching Orbbec device found";
            return false;
        }

        if(config_.camera.enableGlobalTimestamp && impl_->device->isGlobalTimestampSupported()) {
            impl_->device->enableGlobalTimestamp(true);
        }

        impl_->pipeline = std::make_unique<ob::Pipeline>(impl_->device);
        impl_->pipelineConfig = std::make_shared<ob::Config>();

        auto colorProfiles = impl_->pipeline->getStreamProfileList(OB_SENSOR_COLOR);
        std::shared_ptr<ob::VideoStreamProfile> selectedColor;
        for(uint32_t i = 0; i < colorProfiles->getCount(); ++i) {
            auto profile = colorProfiles->getProfile(i)->as<ob::VideoStreamProfile>();
            const auto format = profile->getFormat();
            if(profile->getWidth() == config_.color.width && profile->getHeight() == config_.color.height && profile->getFps() == config_.color.fps
               && (format == OB_FORMAT_RGB || format == OB_FORMAT_BGR || format == OB_FORMAT_BGRA || format == OB_FORMAT_RGBA || format == OB_FORMAT_YUYV
                   || format == OB_FORMAT_YUY2 || format == OB_FORMAT_MJPEG)) {
                selectedColor = profile;
                break;
            }
        }
        if(!selectedColor) {
            for(uint32_t i = 0; i < colorProfiles->getCount(); ++i) {
                auto profile = colorProfiles->getProfile(i)->as<ob::VideoStreamProfile>();
                const auto format = profile->getFormat();
                if(format == OB_FORMAT_RGB || format == OB_FORMAT_BGR || format == OB_FORMAT_BGRA || format == OB_FORMAT_RGBA || format == OB_FORMAT_YUYV
                   || format == OB_FORMAT_YUY2 || format == OB_FORMAT_MJPEG) {
                    selectedColor = profile;
                    break;
                }
            }
        }
        if(selectedColor) {
            impl_->pipelineConfig->enableStream(selectedColor);
            impl_->colorProfile = selectedColor;
        }

        auto depthProfiles = impl_->pipeline->getStreamProfileList(OB_SENSOR_DEPTH);
        std::shared_ptr<ob::VideoStreamProfile> selectedDepth;
        for(uint32_t i = 0; i < depthProfiles->getCount(); ++i) {
            auto profile = depthProfiles->getProfile(i)->as<ob::VideoStreamProfile>();
            const auto format = profile->getFormat();
            if(profile->getWidth() == config_.depth.width && profile->getHeight() == config_.depth.height && profile->getFps() == config_.depth.fps
               && (format == OB_FORMAT_Y16 || format == OB_FORMAT_Z16)) {
                selectedDepth = profile;
                break;
            }
        }
        if(!selectedDepth) {
            for(uint32_t i = 0; i < depthProfiles->getCount(); ++i) {
                auto profile = depthProfiles->getProfile(i)->as<ob::VideoStreamProfile>();
                if(profile->getFormat() == OB_FORMAT_Y16 || profile->getFormat() == OB_FORMAT_Z16) {
                    selectedDepth = profile;
                    break;
                }
            }
        }
        if(selectedDepth) {
            impl_->pipelineConfig->enableStream(selectedDepth);
            impl_->depthProfile = selectedDepth;
        }

        if(config_.depth.alignToColor) {
            try {
                impl_->pipelineConfig->setAlignMode(ALIGN_D2C_HW_MODE);
            }
            catch(...) {
            }
        }

        impl_->pipeline->enableFrameSync();
        impl_->pipeline->start(impl_->pipelineConfig);

        connected_ = true;
        lastError_.clear();
        rebuildMetadataLocked();
        rebuildCapabilitiesLocked();
        log::get()->info("event=camera state=connected serial={} name={}", metadata_["device"].value("serial_number", ""),
                         metadata_["device"].value("name", ""));
        return true;
    }
    catch(const std::exception &ex) {
        lastError_ = ex.what();
        log::get()->error("event=camera state=connect_failed error=\"{}\"", ex.what());
        disconnectLocked();
        return false;
    }
#endif
}

void OrbbecCamera::captureOnce() {
#if !NUC_HAS_ORBBEC
    throw std::runtime_error("built without Orbbec SDK");
#else
    std::shared_ptr<ob::FrameSet> frameSet;
    {
        std::scoped_lock lock(mutex_);
        if(!impl_->pipeline) {
            return;
        }
        frameSet = impl_->pipeline->waitForFrameset(1000);
    }
    if(!frameSet) {
        return;
    }

    ColorCallback colorCallback;
    DepthCallback depthCallback;
    {
        std::scoped_lock lock(mutex_);
        colorCallback = colorCallback_;
        depthCallback = depthCallback_;
    }

    if(auto colorFrame = frameSet->getColorFrame()) {
        stats_.onColorInputFrame();
        if(colorCallback && runtimeSettings().colorEnabled) {
            FrameEnvelope envelope;
            envelope.width = static_cast<int>(colorFrame->getWidth());
            envelope.height = static_cast<int>(colorFrame->getHeight());
            envelope.timestampUs = colorFrame->getTimeStampUs();
            envelope.systemTimestampUs = colorFrame->getSystemTimeStampUs();
            envelope.frameIndex = colorFrame->getIndex();
            envelope.format = obFormatToString(colorFrame->getFormat());

            const auto *data = colorFrame->getData();
            switch(colorFrame->getFormat()) {
            case OB_FORMAT_RGB:
                envelope.bytes.assign(data, data + colorFrame->getDataSize());
                break;
            case OB_FORMAT_BGR:
                bgrToRgb(data, envelope.width, envelope.height, envelope.bytes);
                break;
            case OB_FORMAT_BGRA:
                bgraToRgb(data, envelope.width, envelope.height, envelope.bytes, false);
                break;
            case OB_FORMAT_RGBA:
                bgraToRgb(data, envelope.width, envelope.height, envelope.bytes, true);
                break;
            case OB_FORMAT_YUYV:
            case OB_FORMAT_YUY2:
                yuyvToRgb(data, envelope.width, envelope.height, envelope.bytes);
                break;
            case OB_FORMAT_MJPEG: {
                auto decoded = imageio::decodeJpegToRgb(data, colorFrame->getDataSize());
                if(decoded && decoded->width == envelope.width && decoded->height == envelope.height) {
                    envelope.bytes = std::move(decoded->bytes);
                }
                break;
            }
            default:
                stats_.onDroppedOutputFrame();
                break;
            }
            if(!envelope.bytes.empty()) {
                {
                    std::scoped_lock lock(mutex_);
                    latestColorFrame_ = envelope;
                }
                colorCallback(envelope);
            }
        }
    }

    if(auto depthFrame = frameSet->getDepthFrame()) {
        stats_.onDepthInputFrame();
        if(depthCallback) {
            DepthEnvelope envelope;
            envelope.width = static_cast<int>(depthFrame->getWidth());
            envelope.height = static_cast<int>(depthFrame->getHeight());
            envelope.timestampUs = depthFrame->getTimeStampUs();
            envelope.systemTimestampUs = depthFrame->getSystemTimeStampUs();
            envelope.frameIndex = depthFrame->getIndex();
            envelope.format = obFormatToString(depthFrame->getFormat());
            envelope.depthScale = depthFrame->getValueScale();
            const auto valueCount = depthFrame->getDataSize() / sizeof(uint16_t);
            const auto *src = reinterpret_cast<const uint16_t *>(depthFrame->getData());
            envelope.values.assign(src, src + valueCount);
            {
                std::scoped_lock lock(mutex_);
                latestDepthFrame_ = envelope;
                metadata_["depth_scale"] = envelope.depthScale;
            }
            depthCallback(envelope);
        }
    }
#endif
}

void OrbbecCamera::rebuildMetadataLocked() {
#if !NUC_HAS_ORBBEC
    metadata_["connected"] = false;
#else
    if(!impl_->device || !impl_->pipeline) {
        metadata_["connected"] = false;
        return;
    }

    auto info = impl_->device->getDeviceInfo();
    auto currentProfiles = nlohmann::json::object();
    if(impl_->colorProfile) {
        currentProfiles["color"] = profileToJson(
            impl_->colorProfile->getWidth(), impl_->colorProfile->getHeight(), impl_->colorProfile->getFps(), obFormatToString(impl_->colorProfile->getFormat()));
    }
    if(impl_->depthProfile) {
        currentProfiles["depth"] = profileToJson(
            impl_->depthProfile->getWidth(), impl_->depthProfile->getHeight(), impl_->depthProfile->getFps(), obFormatToString(impl_->depthProfile->getFormat()));
    }

    auto colorProfileList = impl_->pipeline->getStreamProfileList(OB_SENSOR_COLOR);
    auto depthProfileList = impl_->pipeline->getStreamProfileList(OB_SENSOR_DEPTH);
    nlohmann::json colorProfiles = nlohmann::json::array();
    nlohmann::json depthProfiles = nlohmann::json::array();
    for(uint32_t i = 0; i < colorProfileList->getCount(); ++i) {
        auto profile = colorProfileList->getProfile(i)->as<ob::VideoStreamProfile>();
        colorProfiles.push_back(profileToJson(profile->getWidth(), profile->getHeight(), profile->getFps(), obFormatToString(profile->getFormat())));
    }
    for(uint32_t i = 0; i < depthProfileList->getCount(); ++i) {
        auto profile = depthProfileList->getProfile(i)->as<ob::VideoStreamProfile>();
        depthProfiles.push_back(profileToJson(profile->getWidth(), profile->getHeight(), profile->getFps(), obFormatToString(profile->getFormat())));
    }

    nlohmann::json calibration = nullptr;
    try {
        const auto cameraParam = impl_->pipeline->getCameraParam();
        calibration = {
            { "depth_intrinsic",
              {
                  { "fx", cameraParam.depthIntrinsic.fx },
                  { "fy", cameraParam.depthIntrinsic.fy },
                  { "cx", cameraParam.depthIntrinsic.cx },
                  { "cy", cameraParam.depthIntrinsic.cy },
                  { "width", cameraParam.depthIntrinsic.width },
                  { "height", cameraParam.depthIntrinsic.height },
              } },
            { "color_intrinsic",
              {
                  { "fx", cameraParam.rgbIntrinsic.fx },
                  { "fy", cameraParam.rgbIntrinsic.fy },
                  { "cx", cameraParam.rgbIntrinsic.cx },
                  { "cy", cameraParam.rgbIntrinsic.cy },
                  { "width", cameraParam.rgbIntrinsic.width },
                  { "height", cameraParam.rgbIntrinsic.height },
              } },
            { "depth_to_color_extrinsic",
              {
                  { "rot", std::vector<float>(std::begin(cameraParam.transform.rot), std::end(cameraParam.transform.rot)) },
                  { "trans", std::vector<float>(std::begin(cameraParam.transform.trans), std::end(cameraParam.transform.trans)) },
              } },
        };
    }
    catch(...) {
    }

    metadata_ = {
        { "connected", true },
        { "device",
          {
              { "serial_number", info->serialNumber() },
              { "name", info->name() },
              { "firmware_version", info->firmwareVersion() },
              { "connection_type", info->connectionType() },
              { "uid", info->uid() },
          } },
        { "stream_capabilities",
          {
              { "supported_color_profiles", colorProfiles },
              { "supported_depth_profiles", depthProfiles },
          } },
        { "current_profiles", currentProfiles },
        { "calibration", calibration },
        { "depth_scale", nullptr },
        { "timestamps", { { "global_timestamp_enabled", config_.camera.enableGlobalTimestamp } } },
    };
#endif
}

void OrbbecCamera::rebuildCapabilitiesLocked() {
#if !NUC_HAS_ORBBEC
    capabilities_["orbbec_available"] = false;
#else
    nlohmann::json controls = nlohmann::json::object();
    if(impl_->device) {
        const auto addIntRange = [&](int propertyId, const std::string &name) {
            try {
                if(impl_->device->isPropertySupported(static_cast<OBPropertyID>(propertyId), OB_PERMISSION_READ)) {
                    const auto range = impl_->device->getIntPropertyRange(static_cast<OBPropertyID>(propertyId));
                    controls[name] = {
                        { "type", "int" },
                        { "min", range.min },
                        { "max", range.max },
                        { "step", range.step },
                        { "default", range.def },
                        { "current", range.cur },
                        { "runtime_update_supported", impl_->device->isPropertySupported(static_cast<OBPropertyID>(propertyId), OB_PERMISSION_WRITE) },
                    };
                }
            }
            catch(...) {
            }
        };
        const auto addBoolRange = [&](int propertyId, const std::string &name) {
            try {
                if(impl_->device->isPropertySupported(static_cast<OBPropertyID>(propertyId), OB_PERMISSION_READ)) {
                    const auto range = impl_->device->getBoolPropertyRange(static_cast<OBPropertyID>(propertyId));
                    controls[name] = {
                        { "type", "bool" },
                        { "default", range.def },
                        { "current", range.cur },
                        { "runtime_update_supported", impl_->device->isPropertySupported(static_cast<OBPropertyID>(propertyId), OB_PERMISSION_WRITE) },
                    };
                }
            }
            catch(...) {
            }
        };

        addBoolRange(OB_PROP_COLOR_AUTO_EXPOSURE_BOOL, "color.auto_exposure");
        addIntRange(OB_PROP_COLOR_EXPOSURE_INT, "color.exposure");
        addIntRange(OB_PROP_COLOR_GAIN_INT, "color.gain");
        addBoolRange(OB_PROP_COLOR_AUTO_WHITE_BALANCE_BOOL, "color.auto_white_balance");
        addIntRange(OB_PROP_COLOR_WHITE_BALANCE_INT, "color.white_balance");
        addIntRange(OB_PROP_COLOR_BRIGHTNESS_INT, "color.brightness");
        addIntRange(OB_PROP_COLOR_CONTRAST_INT, "color.contrast");
        addIntRange(OB_PROP_COLOR_SATURATION_INT, "color.saturation");
    }

    capabilities_ = {
        { "orbbec_available", true },
        { "controls", controls },
        { "profile_change_requires_restart", true },
        { "supported_depth_alignment_modes", { "native_depth_space", "align_to_color_if_supported" } },
    };
#endif
}

}  // namespace femto
