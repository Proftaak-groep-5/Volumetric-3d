#include "streaming/PreviewPublisher.hpp"

#include "util/Log.hpp"

#include <algorithm>
#include <chrono>
#include <cstring>
#include <mutex>

#include <spdlog/spdlog.h>

#if NUC_HAS_GSTREAMER
#include <gst/app/gstappsrc.h>
#include <gst/app/gstappsink.h>
#include <gst/gst.h>
#endif

namespace femto {

struct PreviewPublisher::Impl {
#if NUC_HAS_GSTREAMER
    GstElement *pipeline = nullptr;
    GstElement *appsrc = nullptr;
    GstElement *appsink = nullptr;
#endif
    int width = 0;
    int height = 0;
    int fps = 0;
    int quality = 85;
    bool started = false;
    std::chrono::steady_clock::time_point nextFrameAt {};
    std::chrono::steady_clock::time_point lastDropLogAt {};
    std::mutex pushMutex;
    uint64_t droppedRateLimit = 0;
    uint64_t droppedBusy = 0;
    uint64_t droppedInvalidSize = 0;
    uint64_t droppedEncode = 0;
};

PreviewPublisher::PreviewPublisher(std::string name) : impl_(std::make_unique<Impl>()), name_(std::move(name)) {}

PreviewPublisher::~PreviewPublisher() {
    stop();
}

bool PreviewPublisher::start(int width, int height, int fps, int quality) {
    stop();
    impl_->width = width;
    impl_->height = height;
    impl_->fps = fps;
    impl_->quality = quality;
#if !NUC_HAS_GSTREAMER
    (void)quality;
    log::get()->warn("event=preview state=disabled stream={} reason=no_gstreamer_build", name_);
    return false;
#else
    static std::once_flag gstOnce;
    std::call_once(gstOnce, [] {
        gst_init(nullptr, nullptr);
    });

    if(auto *factory = gst_element_factory_find("jpegenc")) {
        gst_object_unref(factory);
    }
    else {
        log::get()->error("event=preview state=start_failed stream={} reason=missing_plugin plugin=jpegenc hint=GST_PLUGIN_PATH", name_);
        return false;
    }
    if(auto *factory = gst_element_factory_find("videoconvert")) {
        gst_object_unref(factory);
    }
    else {
        log::get()->error("event=preview state=start_failed stream={} reason=missing_plugin plugin=videoconvert hint=GST_PLUGIN_PATH", name_);
        return false;
    }

    const std::string pipelineText =
        "appsrc name=src is-live=true format=time block=false do-timestamp=true "
        "caps=video/x-raw,format=RGB,width=" +
        std::to_string(width) + ",height=" + std::to_string(height) + ",framerate=" + std::to_string(std::max(1, fps)) +
        "/1 ! queue leaky=downstream max-size-buffers=2 ! videoconvert ! jpegenc quality=" + std::to_string(quality) +
        " ! appsink name=sink emit-signals=false sync=false max-buffers=2 drop=true";

    GError *error = nullptr;
    impl_->pipeline = gst_parse_launch(pipelineText.c_str(), &error);
    if(!impl_->pipeline) {
        log::get()->error("event=preview state=start_failed stream={} reason=pipeline_create error=\"{}\"", name_, error ? error->message : "unknown");
        if(error) {
            g_error_free(error);
        }
        return false;
    }
    impl_->appsrc = gst_bin_get_by_name(GST_BIN(impl_->pipeline), "src");
    impl_->appsink = gst_bin_get_by_name(GST_BIN(impl_->pipeline), "sink");
    if(!impl_->appsrc || !impl_->appsink) {
        log::get()->error("event=preview state=start_failed stream={} reason=missing_appsrc_or_sink", name_);
        stop();
        return false;
    }
    const auto stateChange = gst_element_set_state(impl_->pipeline, GST_STATE_PLAYING);
    if(stateChange == GST_STATE_CHANGE_FAILURE) {
        log::get()->error("event=preview state=start_failed stream={} reason=state_change_failure", name_);
        stop();
        return false;
    }
    impl_->started = true;
    impl_->nextFrameAt = std::chrono::steady_clock::time_point {};
    impl_->lastDropLogAt = std::chrono::steady_clock::now();
    log::get()->info("event=preview state=started stream={} width={} height={} fps={} queue_max_buffers=2 transport=jpeg-websocket", name_, width, height,
                     fps);
    return true;
#endif
}

void PreviewPublisher::stop() {
    const bool shouldLog = impl_->started
#if NUC_HAS_GSTREAMER
                           || impl_->pipeline || impl_->appsrc || impl_->appsink
#endif
        ;
#if NUC_HAS_GSTREAMER
    if(impl_->pipeline) {
        gst_element_set_state(impl_->pipeline, GST_STATE_NULL);
    }
    if(impl_->appsink) {
        gst_object_unref(impl_->appsink);
        impl_->appsink = nullptr;
    }
    if(impl_->appsrc) {
        gst_object_unref(impl_->appsrc);
        impl_->appsrc = nullptr;
    }
    if(impl_->pipeline) {
        gst_object_unref(impl_->pipeline);
        impl_->pipeline = nullptr;
    }
#endif
    impl_->started = false;
    if(shouldLog) {
        log::get()->info("event=preview state=stopped stream={}", name_);
    }
}

bool PreviewPublisher::running() const {
    return impl_->started;
}

bool PreviewPublisher::pushRgbFrame(const uint8_t *data, std::size_t bytes, uint64_t timestampUs) {
    const auto logDropSummary = [this](const char *reason) {
        const auto now = std::chrono::steady_clock::now();
        if(impl_->lastDropLogAt.time_since_epoch().count() == 0 || now - impl_->lastDropLogAt >= std::chrono::seconds(5)) {
            log::get()->warn(
                "event=preview_drop stream={} reason={} rate_limit={} busy={} invalid_size={} encode={}", name_, reason, impl_->droppedRateLimit,
                impl_->droppedBusy, impl_->droppedInvalidSize, impl_->droppedEncode);
            impl_->lastDropLogAt = now;
        }
    };

    if(!impl_->started) {
        return false;
    }
    const auto expectedBytes = static_cast<std::size_t>(impl_->width) * static_cast<std::size_t>(impl_->height) * 3;
    if(bytes != expectedBytes) {
        ++impl_->droppedInvalidSize;
        logDropSummary("invalid_size");
        return false;
    }
    const auto now = std::chrono::steady_clock::now();
    const auto interval = std::chrono::microseconds(1'000'000 / std::max(1, impl_->fps));
    if(impl_->nextFrameAt.time_since_epoch().count() != 0 && now < impl_->nextFrameAt) {
        ++impl_->droppedRateLimit;
        logDropSummary("rate_limit");
        return false;
    }
    std::unique_lock pushLock(impl_->pushMutex, std::try_to_lock);
    if(!pushLock.owns_lock()) {
        ++impl_->droppedBusy;
        logDropSummary("busy");
        return false;
    }
#if !NUC_HAS_GSTREAMER
    (void)data;
    (void)bytes;
    (void)timestampUs;
    return false;
#else
    const auto started = std::chrono::steady_clock::now();
    GstBuffer *buffer = gst_buffer_new_allocate(nullptr, bytes, nullptr);
    if(!buffer) {
        ++impl_->droppedEncode;
        logDropSummary("buffer_alloc");
        return false;
    }
    GstMapInfo map {};
    gst_buffer_map(buffer, &map, GST_MAP_WRITE);
    std::memcpy(map.data, data, bytes);
    gst_buffer_unmap(buffer, &map);
    GST_BUFFER_PTS(buffer) = static_cast<GstClockTime>(timestampUs) * 1000;
    GST_BUFFER_DTS(buffer) = GST_BUFFER_PTS(buffer);
    GST_BUFFER_DURATION(buffer) = gst_util_uint64_scale_int(1, GST_SECOND, std::max(1, impl_->fps));

    const auto flow = gst_app_src_push_buffer(GST_APP_SRC(impl_->appsrc), buffer);
    if(flow != GST_FLOW_OK) {
        ++impl_->droppedEncode;
        logDropSummary("push_buffer");
        return false;
    }

    GstSample *sample = gst_app_sink_try_pull_sample(GST_APP_SINK(impl_->appsink), 10 * GST_MSECOND);
    if(!sample) {
        ++impl_->droppedEncode;
        logDropSummary("pull_sample");
        return false;
    }
    GstBuffer *jpegBuffer = gst_sample_get_buffer(sample);
    if(!jpegBuffer) {
        gst_sample_unref(sample);
        ++impl_->droppedEncode;
        logDropSummary("jpeg_buffer");
        return false;
    }
    GstMapInfo jpegMap {};
    gst_buffer_map(jpegBuffer, &jpegMap, GST_MAP_READ);
    auto bytesOut = std::make_shared<std::vector<uint8_t>>(jpegMap.data, jpegMap.data + jpegMap.size);
    gst_buffer_unmap(jpegBuffer, &jpegMap);
    gst_sample_unref(sample);

    const double elapsedMs = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - started).count();
    FrameCallback callback;
    {
        std::scoped_lock lock(mutex_);
        latestJpeg_ = bytesOut;
        callback = callback_;
    }
    impl_->nextFrameAt = now + interval;
    if(callback) {
        callback(bytesOut, timestampUs, elapsedMs);
    }
    return true;
#endif
}

std::shared_ptr<const std::vector<uint8_t>> PreviewPublisher::latestJpeg() const {
    std::scoped_lock lock(mutex_);
    return latestJpeg_;
}

void PreviewPublisher::setFrameCallback(FrameCallback callback) {
    std::scoped_lock lock(mutex_);
    callback_ = std::move(callback);
}

}  // namespace femto
