#include "http/HttpServer.hpp"

#include "http/WebAssets.hpp"
#include "util/Log.hpp"

#include <crow.h>

#include <condition_variable>
#include <exception>
#include <thread>
#include <unordered_set>

namespace femto {
namespace {

crow::response jsonResponse(const nlohmann::json &json, int code = 200) {
    crow::response response;
    response.code = code;
    response.set_header("Content-Type", "application/json");
    response.body = json.dump(2);
    return response;
}

nlohmann::json parseRequestJson(const crow::request &request) {
    if(request.body.empty()) {
        return nlohmann::json::object();
    }
    return nlohmann::json::parse(request.body);
}

}  // namespace

struct HttpServer::Impl {
    crow::SimpleApp app;
    std::thread serverThread;
    std::thread colorDispatchThread;
    std::mutex wsMutex;
    std::mutex colorDispatchMutex;
    std::condition_variable colorDispatchCv;
    std::unordered_set<crow::websocket::connection *> colorClients;
    std::unordered_set<crow::websocket::connection *> depthClients;
    std::unordered_set<crow::websocket::connection *> depthBinaryClients;
    std::shared_ptr<const std::vector<uint8_t>> pendingColorFrame;
    uint64_t pendingColorVersion = 0;
    uint64_t sentColorVersion = 0;
    bool stopRequested = false;
};

HttpServer::HttpServer(const Config &config) : impl_(std::make_unique<Impl>()), config_(config) {}

HttpServer::~HttpServer() {
    stop();
}

void HttpServer::start(Callbacks callbacks) {
    callbacks_ = std::move(callbacks);
    auto &app = impl_->app;
    log::get()->info("event=http_server state=starting bind={} port={}", config_.bindAddress, config_.httpPort);

    CROW_ROUTE(app, "/")([this] {
        crow::response response;
        response.code = 200;
        response.set_header("Content-Type", "text/html; charset=utf-8");
        response.body = web::kIndexHtml;
        return response;
    });
    CROW_ROUTE(app, "/health")([this] { return jsonResponse(callbacks_.health()); });
    CROW_ROUTE(app, "/heartbeat")([this] { return jsonResponse(callbacks_.heartbeat()); });
    CROW_ROUTE(app, "/metadata")([this] { return jsonResponse(callbacks_.metadata()); });
    CROW_ROUTE(app, "/streams")([this] { return jsonResponse(callbacks_.streams()); });
    CROW_ROUTE(app, "/settings").methods(crow::HTTPMethod::Get)([this] { return jsonResponse(callbacks_.settings()); });
    CROW_ROUTE(app, "/settings").methods(crow::HTTPMethod::Post)([this](const crow::request &request) {
        try {
            const auto result = callbacks_.updateSettings(parseRequestJson(request));
            const bool ok = result.value("ok", true);
            return jsonResponse(result, ok ? 200 : 500);
        }
        catch(const std::exception &ex) {
            crow::response response;
            response.code = 400;
            response.set_header("Content-Type", "application/json");
            response.body = nlohmann::json{ { "ok", false }, { "error", ex.what() } }.dump(2);
            return response;
        }
    });
    CROW_ROUTE(app, "/settings/restart-streams").methods(crow::HTTPMethod::Post)([this] {
        const auto result = callbacks_.restartStreams();
        const bool ok = result.value("ok", true);
        return jsonResponse(result, ok ? 200 : 500);
    });
    CROW_ROUTE(app, "/capabilities")([this] { return jsonResponse(callbacks_.capabilities()); });
    CROW_ROUTE(app, "/stats")([this] { return jsonResponse(callbacks_.stats()); });
    CROW_ROUTE(app, "/control/reconnect").methods(crow::HTTPMethod::Post)([this] { return jsonResponse(callbacks_.reconnect()); });
    CROW_ROUTE(app, "/control/restart").methods(crow::HTTPMethod::Post)([this] { return jsonResponse(callbacks_.restart()); });
    CROW_ROUTE(app, "/discovery")([this] { return jsonResponse(callbacks_.discovery()); });
    CROW_ROUTE(app, "/description.xml")([this] {
        const auto info = callbacks_.discovery();
        std::string xml =
            "<?xml version=\"1.0\"?>"
            "<root><device><deviceType>" +
            info.value("service_name", "FemtoBoltNuc") + "</deviceType><friendlyName>" + info.value("instance_id", "femtobolt") + "</friendlyName><serialNumber>" +
            info.value("serial_number", "") + "</serialNumber><modelName>" + info.value("model", "") + "</modelName></device></root>";
        crow::response response;
        response.set_header("Content-Type", "application/xml");
        response.body = std::move(xml);
        return response;
    });
    CROW_ROUTE(app, "/snapshot/color.jpg")([this] {
        if(auto jpeg = callbacks_.latestColorJpeg()) {
            crow::response response;
            response.set_header("Content-Type", "image/jpeg");
            response.set_header("Cache-Control", "no-store, no-cache, must-revalidate");
            response.body.assign(reinterpret_cast<const char *>(jpeg->data()), jpeg->size());
            return response;
        }
        return crow::response(404);
    });
    CROW_ROUTE(app, "/snapshot/depth-preview.jpg")([this] {
        if(auto jpeg = callbacks_.latestDepthPreviewJpeg()) {
            crow::response response;
            response.set_header("Content-Type", "image/jpeg");
            response.set_header("Cache-Control", "no-store, no-cache, must-revalidate");
            response.body.assign(reinterpret_cast<const char *>(jpeg->data()), jpeg->size());
            return response;
        }
        return crow::response(404);
    });
    CROW_ROUTE(app, "/snapshot/depth.png")([this] {
        if(auto snapshot = callbacks_.latestDepthSnapshot()) {
            crow::response response;
            response.set_header("Content-Type", "image/png");
            response.set_header("Cache-Control", "no-store, no-cache, must-revalidate");
            response.set_header("X-Depth-Scale", std::to_string(snapshot->depthScale));
            response.set_header("X-Depth-Width", std::to_string(snapshot->width));
            response.set_header("X-Depth-Height", std::to_string(snapshot->height));
            response.set_header("X-Depth-Pixel-Format", snapshot->pixelFormat);
            response.set_header("X-Depth-Units", "millimeters = raw * scale");
            response.body.assign(reinterpret_cast<const char *>(snapshot->pngBytes->data()), snapshot->pngBytes->size());
            return response;
        }
        return crow::response(404);
    });
    CROW_ROUTE(app, "/snapshot/depth.bin")([this] {
        if(auto packet = callbacks_.latestDepthPacket()) {
            crow::response response;
            response.set_header("Content-Type", "application/octet-stream");
            response.set_header("Cache-Control", "no-store, no-cache, must-revalidate");
            response.body.assign(reinterpret_cast<const char *>(packet->data()), packet->size());
            return response;
        }
        return crow::response(404);
    });

    CROW_WEBSOCKET_ROUTE(app, "/ws/preview/color")
        .onopen([this](crow::websocket::connection &conn) {
            std::scoped_lock lock(impl_->wsMutex);
            impl_->colorClients.insert(&conn);
            log::get()->info("event=ws_client state=connected stream=color_preview clients={}", impl_->colorClients.size());
        })
        .onclose([this](crow::websocket::connection &conn, const std::string &) {
            std::scoped_lock lock(impl_->wsMutex);
            impl_->colorClients.erase(&conn);
            log::get()->info("event=ws_client state=disconnected stream=color_preview clients={}", impl_->colorClients.size());
        });

    CROW_WEBSOCKET_ROUTE(app, "/ws/preview/depth")
        .onopen([this](crow::websocket::connection &conn) {
            std::scoped_lock lock(impl_->wsMutex);
            impl_->depthClients.insert(&conn);
            log::get()->info("event=ws_client state=connected stream=depth_preview clients={}", impl_->depthClients.size());
        })
        .onclose([this](crow::websocket::connection &conn, const std::string &) {
            std::scoped_lock lock(impl_->wsMutex);
            impl_->depthClients.erase(&conn);
            log::get()->info("event=ws_client state=disconnected stream=depth_preview clients={}", impl_->depthClients.size());
        });

    CROW_WEBSOCKET_ROUTE(app, "/ws/depth")
        .onopen([this](crow::websocket::connection &conn) {
            std::scoped_lock lock(impl_->wsMutex);
            impl_->depthBinaryClients.insert(&conn);
            log::get()->info("event=ws_client state=connected stream=depth_binary clients={}", impl_->depthBinaryClients.size());
        })
        .onclose([this](crow::websocket::connection &conn, const std::string &) {
            std::scoped_lock lock(impl_->wsMutex);
            impl_->depthBinaryClients.erase(&conn);
            log::get()->info("event=ws_client state=disconnected stream=depth_binary clients={}", impl_->depthBinaryClients.size());
        });

    impl_->stopRequested = false;
    impl_->colorDispatchThread = std::thread([this] {
        try {
            while(true) {
                std::shared_ptr<const std::vector<uint8_t>> jpeg;
                {
                    std::unique_lock lock(impl_->colorDispatchMutex);
                    impl_->colorDispatchCv.wait(lock, [this] {
                        return impl_->stopRequested || impl_->pendingColorVersion != impl_->sentColorVersion;
                    });
                    if(impl_->stopRequested) {
                        break;
                    }
                    jpeg = impl_->pendingColorFrame;
                    impl_->sentColorVersion = impl_->pendingColorVersion;
                }
                if(!jpeg || jpeg->empty()) {
                    continue;
                }
                std::scoped_lock lock(impl_->wsMutex);
                for(auto *client: impl_->colorClients) {
                    try {
                        client->send_binary(std::string(reinterpret_cast<const char *>(jpeg->data()), jpeg->size()));
                    }
                    catch(const std::exception &ex) {
                        log::get()->warn("event=ws_send_failed stream=color_preview error=\"{}\"", ex.what());
                    }
                    catch(...) {
                        log::get()->warn("event=ws_send_failed stream=color_preview error=unknown");
                    }
                }
            }
        }
        catch(const std::exception &ex) {
            log::get()->error("event=http_color_dispatch state=crashed error=\"{}\"", ex.what());
        }
        catch(...) {
            log::get()->error("event=http_color_dispatch state=crashed error=unknown");
        }
    });

    impl_->serverThread = std::thread([this] {
        try {
            log::get()->info("event=http_server state=running bind={} port={}", config_.bindAddress, config_.httpPort);
            impl_->app.port(config_.httpPort).bindaddr(config_.bindAddress).multithreaded().run();
        }
        catch(const std::exception &ex) {
            log::get()->error("event=http_server state=crashed error=\"{}\"", ex.what());
        }
        catch(...) {
            log::get()->error("event=http_server state=crashed error=unknown");
        }
    });
}

void HttpServer::stop() {
    {
        std::scoped_lock lock(impl_->colorDispatchMutex);
        impl_->stopRequested = true;
    }
    impl_->colorDispatchCv.notify_all();
    impl_->app.stop();
    if(impl_->colorDispatchThread.joinable()) {
        impl_->colorDispatchThread.join();
    }
    if(impl_->serverThread.joinable()) {
        impl_->serverThread.join();
    }
    log::get()->info("event=http_server state=stopped");
}

void HttpServer::publishColorPreview(std::shared_ptr<const std::vector<uint8_t>> jpeg) {
    if(!jpeg || jpeg->empty()) {
        return;
    }
    {
        std::scoped_lock lock(impl_->colorDispatchMutex);
        impl_->pendingColorFrame = std::move(jpeg);
        ++impl_->pendingColorVersion;
    }
    impl_->colorDispatchCv.notify_one();
}

void HttpServer::publishDepthPreview(std::shared_ptr<const std::vector<uint8_t>> jpeg) {
    if(!jpeg || jpeg->empty()) {
        return;
    }
    std::scoped_lock lock(impl_->wsMutex);
    for(auto *client: impl_->depthClients) {
        try {
            client->send_binary(std::string(reinterpret_cast<const char *>(jpeg->data()), jpeg->size()));
        }
        catch(const std::exception &ex) {
            log::get()->warn("event=ws_send_failed stream=depth_preview error=\"{}\"", ex.what());
        }
        catch(...) {
            log::get()->warn("event=ws_send_failed stream=depth_preview error=unknown");
        }
    }
}

void HttpServer::publishDepthBinary(std::shared_ptr<const std::vector<uint8_t>> packet) {
    if(!packet || packet->empty()) {
        return;
    }
    std::scoped_lock lock(impl_->wsMutex);
    for(auto *client: impl_->depthBinaryClients) {
        try {
            client->send_binary(std::string(reinterpret_cast<const char *>(packet->data()), packet->size()));
        }
        catch(const std::exception &ex) {
            log::get()->warn("event=ws_send_failed stream=depth_binary error=\"{}\"", ex.what());
        }
        catch(...) {
            log::get()->warn("event=ws_send_failed stream=depth_binary error=unknown");
        }
    }
}

}  // namespace femto
