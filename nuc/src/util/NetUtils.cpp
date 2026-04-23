#include "util/NetUtils.hpp"

#include <winsock2.h>
#include <ws2tcpip.h>
#include <iphlpapi.h>

#include <cstddef>
#include <memory>
#include <stdexcept>

namespace femto::net {

std::vector<std::string> localIpv4Addresses() {
    ULONG bufferSize = 16 * 1024;
    std::vector<std::byte> buffer(bufferSize);
    auto *addresses = reinterpret_cast<IP_ADAPTER_ADDRESSES *>(buffer.data());
    DWORD result = GetAdaptersAddresses(AF_INET, GAA_FLAG_SKIP_ANYCAST | GAA_FLAG_SKIP_MULTICAST | GAA_FLAG_SKIP_DNS_SERVER, nullptr, addresses, &bufferSize);
    if(result == ERROR_BUFFER_OVERFLOW) {
        buffer.resize(bufferSize);
        addresses = reinterpret_cast<IP_ADAPTER_ADDRESSES *>(buffer.data());
        result = GetAdaptersAddresses(AF_INET, GAA_FLAG_SKIP_ANYCAST | GAA_FLAG_SKIP_MULTICAST | GAA_FLAG_SKIP_DNS_SERVER, nullptr, addresses, &bufferSize);
    }

    std::vector<std::string> values;
    if(result != NO_ERROR) {
        return values;
    }

    for(auto *adapter = addresses; adapter != nullptr; adapter = adapter->Next) {
        if(adapter->OperStatus != IfOperStatusUp || adapter->IfType == IF_TYPE_SOFTWARE_LOOPBACK) {
            continue;
        }
        for(auto *unicast = adapter->FirstUnicastAddress; unicast != nullptr; unicast = unicast->Next) {
            char addressBuffer[INET_ADDRSTRLEN] = {};
            auto *sockAddr = reinterpret_cast<sockaddr_in *>(unicast->Address.lpSockaddr);
            if(sockAddr && InetNtopA(AF_INET, &sockAddr->sin_addr, addressBuffer, sizeof(addressBuffer))) {
                values.emplace_back(addressBuffer);
            }
        }
    }
    return values;
}

std::string firstReachableIpv4() {
    const auto addresses = localIpv4Addresses();
    if(addresses.empty()) {
        return "127.0.0.1";
    }
    return addresses.front();
}

}  // namespace femto::net
