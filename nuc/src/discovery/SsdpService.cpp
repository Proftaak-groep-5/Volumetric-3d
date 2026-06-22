#include "discovery/SsdpService.hpp"

#include "util/BuildFeatures.hpp"
#include "util/Log.hpp"
#include "util/NetUtils.hpp"

#include <winsock2.h>
#include <ws2tcpip.h>

#include <algorithm>
#include <chrono>
#include <exception>
#include <sstream>

namespace femto {

SsdpService::SsdpService(const Config &config) : config_(config) {}

SsdpService::~SsdpService() {
    stop();
}

void SsdpService::start(std::function<nlohmann::json()> discoveryProvider) {
    if(!config_.discovery.enabled || running_.exchange(true)) {
        return;
    }
    discoveryProvider_ = std::move(discoveryProvider);
    worker_ = std::thread([this] {
        while(running_) {
            try {
                workerLoop();
            }
            catch(const std::exception &ex) {
                log::get()->error("event=ssdp state=crashed error=\"{}\" action=retry", ex.what());
            }
            catch(...) {
                log::get()->error("event=ssdp state=crashed error=unknown action=retry");
            }
            if(running_) {
                std::this_thread::sleep_for(std::chrono::seconds(1));
            }
        }
    });
}

void SsdpService::stop() {
    if(!running_.exchange(false)) {
        return;
    }
    if(worker_.joinable()) {
        worker_.join();
    }
}

void SsdpService::workerLoop() {
    while(running_) {
        announceOnce();
        for(int i = 0; i < std::max(1, config_.discovery.announcementIntervalSec) * 10 && running_; ++i) {
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
        }
    }
}

void SsdpService::announceOnce() {
    SOCKET sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if(sock == INVALID_SOCKET) {
        return;
    }
    const BOOL reuse = TRUE;
    setsockopt(sock, SOL_SOCKET, SO_BROADCAST, reinterpret_cast<const char *>(&reuse), sizeof(reuse));

    sockaddr_in target {};
    target.sin_family = AF_INET;
    target.sin_port = htons(1900);
    InetPtonA(AF_INET, "239.255.255.250", &target.sin_addr);

    const auto discovery = discoveryProvider_ ? discoveryProvider_() : nlohmann::json::object();
    const auto ip = discovery.value("hostname_or_ip", net::firstReachableIpv4());
    const auto location = "http://" + ip + ":" + std::to_string(config_.httpPort) + "/description.xml";
    std::ostringstream payload;
    payload << "NOTIFY * HTTP/1.1\r\n"
            << "HOST: 239.255.255.250:1900\r\n"
            << "NT: " << config_.discovery.serviceType << "\r\n"
            << "NTS: ssdp:alive\r\n"
            << "USN: uuid:" << config_.instanceId << "\r\n"
            << "LOCATION: " << location << "\r\n"
            << "CACHE-CONTROL: max-age=120\r\n"
            << "SERVER: Windows/10 UPnP/1.1 FemtoBoltNuc/" << FEMTOBOLTNUC_VERSION << "\r\n"
            << "X-SERIAL: " << discovery.value("serial_number", "") << "\r\n"
            << "X-MODEL: " << discovery.value("model", "") << "\r\n"
            << "\r\n";

    const auto message = payload.str();
    sendto(sock, message.c_str(), static_cast<int>(message.size()), 0, reinterpret_cast<const sockaddr *>(&target), sizeof(target));
    closesocket(sock);
}

}  // namespace femto
