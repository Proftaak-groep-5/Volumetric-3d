#include "util/ImageIO.hpp"

#include <windows.h>
#include <objidl.h>
#include <propidl.h>
#include <wincodec.h>

#include <algorithm>
#include <cstdio>
#include <limits>
#include <optional>
#include <vector>

namespace femto::imageio {
namespace {

class ComScope {
public:
    ComScope() {
        const auto hr = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
        ready_ = SUCCEEDED(hr) || hr == RPC_E_CHANGED_MODE;
        initializedHere_ = SUCCEEDED(hr);
    }

    ~ComScope() {
        if(initializedHere_) {
            CoUninitialize();
        }
    }

    bool initialized() const {
        return ready_;
    }

private:
    bool ready_ = false;
    bool initializedHere_ = false;
};

HRESULT encodeToMemory(const GUID &containerFormat, const GUID &pixelFormat, const uint8_t *src, UINT width, UINT height, UINT stride,
                       UINT imageSize, std::shared_ptr<const std::vector<uint8_t>> &output, std::optional<UINT> quality = std::nullopt) {
    ComScope com;
    if(!com.initialized()) {
        return E_FAIL;
    }

    IWICImagingFactory *factory = nullptr;
    IWICStream *stream = nullptr;
    IWICBitmapEncoder *encoder = nullptr;
    IWICBitmapFrameEncode *frame = nullptr;
    IPropertyBag2 *propertyBag = nullptr;
    IStream *memoryStream = nullptr;

    auto cleanup = [&] {
        if(propertyBag) propertyBag->Release();
        if(frame) frame->Release();
        if(encoder) encoder->Release();
        if(stream) stream->Release();
        if(factory) factory->Release();
        if(memoryStream) memoryStream->Release();
    };

    HRESULT hr = CoCreateInstance(CLSID_WICImagingFactory, nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&factory));
    if(FAILED(hr)) {
        cleanup();
        return hr;
    }

    hr = CreateStreamOnHGlobal(nullptr, TRUE, &memoryStream);
    if(FAILED(hr)) {
        cleanup();
        return hr;
    }

    hr = factory->CreateStream(&stream);
    if(FAILED(hr)) {
        cleanup();
        return hr;
    }

    hr = stream->InitializeFromIStream(memoryStream);
    if(FAILED(hr)) {
        cleanup();
        return hr;
    }

    hr = factory->CreateEncoder(containerFormat, nullptr, &encoder);
    if(FAILED(hr)) {
        cleanup();
        return hr;
    }

    hr = encoder->Initialize(stream, WICBitmapEncoderNoCache);
    if(FAILED(hr)) {
        cleanup();
        return hr;
    }

    hr = encoder->CreateNewFrame(&frame, &propertyBag);
    if(FAILED(hr)) {
        cleanup();
        return hr;
    }

    if(quality && propertyBag) {
        PROPBAG2 option {};
        option.pstrName = const_cast<LPOLESTR>(L"ImageQuality");
        VARIANT value {};
        VariantInit(&value);
        value.vt = VT_R4;
        value.fltVal = static_cast<float>(*quality) / 100.0f;
        propertyBag->Write(1, &option, &value);
        VariantClear(&value);
    }

    hr = frame->Initialize(propertyBag);
    if(FAILED(hr)) {
        cleanup();
        return hr;
    }

    hr = frame->SetSize(width, height);
    if(FAILED(hr)) {
        cleanup();
        return hr;
    }

    WICPixelFormatGUID targetFormat = pixelFormat;
    hr = frame->SetPixelFormat(&targetFormat);
    if(FAILED(hr)) {
        cleanup();
        return hr;
    }

    hr = frame->WritePixels(height, stride, imageSize, const_cast<BYTE *>(src));
    if(FAILED(hr)) {
        cleanup();
        return hr;
    }

    hr = frame->Commit();
    if(FAILED(hr)) {
        cleanup();
        return hr;
    }
    hr = encoder->Commit();
    if(FAILED(hr)) {
        cleanup();
        return hr;
    }

    HGLOBAL hMem = nullptr;
    hr = GetHGlobalFromStream(memoryStream, &hMem);
    if(FAILED(hr)) {
        cleanup();
        return hr;
    }

    const auto size = static_cast<std::size_t>(GlobalSize(hMem));
    void *raw = GlobalLock(hMem);
    if(!raw) {
        cleanup();
        return E_FAIL;
    }

    auto bytes = std::make_shared<std::vector<uint8_t>>(static_cast<uint8_t *>(raw), static_cast<uint8_t *>(raw) + size);
    GlobalUnlock(hMem);
    output = bytes;
    cleanup();
    return S_OK;
}

bool writeBytes(const std::filesystem::path &path, const std::shared_ptr<const std::vector<uint8_t>> &bytes) {
    if(!bytes || bytes->empty()) {
        return false;
    }
    if(!path.parent_path().empty()) {
        std::filesystem::create_directories(path.parent_path());
    }
    FILE *file = nullptr;
    if(_wfopen_s(&file, path.wstring().c_str(), L"wb") != 0 || !file) {
        return false;
    }
    const auto written = fwrite(bytes->data(), 1, bytes->size(), file);
    fclose(file);
    return written == bytes->size();
}

}  // namespace

std::optional<RgbImage> decodeJpegToRgb(const uint8_t *jpeg, std::size_t bytes) {
    if(!jpeg || bytes == 0 || bytes > static_cast<std::size_t>(std::numeric_limits<UINT>::max())) {
        return std::nullopt;
    }

    ComScope com;
    if(!com.initialized()) {
        return std::nullopt;
    }

    IWICImagingFactory *factory = nullptr;
    IWICStream *stream = nullptr;
    IWICBitmapDecoder *decoder = nullptr;
    IWICBitmapFrameDecode *frame = nullptr;
    IWICFormatConverter *converter = nullptr;

    auto cleanup = [&] {
        if(converter) converter->Release();
        if(frame) frame->Release();
        if(decoder) decoder->Release();
        if(stream) stream->Release();
        if(factory) factory->Release();
    };

    HRESULT hr = CoCreateInstance(CLSID_WICImagingFactory, nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&factory));
    if(FAILED(hr)) {
        cleanup();
        return std::nullopt;
    }

    hr = factory->CreateStream(&stream);
    if(FAILED(hr)) {
        cleanup();
        return std::nullopt;
    }

    hr = stream->InitializeFromMemory(const_cast<BYTE *>(jpeg), static_cast<UINT>(bytes));
    if(FAILED(hr)) {
        cleanup();
        return std::nullopt;
    }

    hr = factory->CreateDecoderFromStream(stream, nullptr, WICDecodeMetadataCacheOnLoad, &decoder);
    if(FAILED(hr)) {
        cleanup();
        return std::nullopt;
    }

    hr = decoder->GetFrame(0, &frame);
    if(FAILED(hr)) {
        cleanup();
        return std::nullopt;
    }

    UINT width = 0;
    UINT height = 0;
    hr = frame->GetSize(&width, &height);
    if(FAILED(hr) || width == 0 || height == 0) {
        cleanup();
        return std::nullopt;
    }

    hr = factory->CreateFormatConverter(&converter);
    if(FAILED(hr)) {
        cleanup();
        return std::nullopt;
    }

    hr = converter->Initialize(frame, GUID_WICPixelFormat24bppRGB, WICBitmapDitherTypeNone, nullptr, 0.0, WICBitmapPaletteTypeCustom);
    if(FAILED(hr)) {
        cleanup();
        return std::nullopt;
    }

    const auto stride = static_cast<UINT>(width * 3);
    const auto imageSize = static_cast<UINT>(stride * height);
    RgbImage image;
    image.width = static_cast<int>(width);
    image.height = static_cast<int>(height);
    image.bytes.resize(imageSize);
    hr = converter->CopyPixels(nullptr, stride, imageSize, image.bytes.data());
    cleanup();
    if(FAILED(hr)) {
        return std::nullopt;
    }
    return image;
}

std::shared_ptr<const std::vector<uint8_t>> encodeRgbJpeg(const uint8_t *rgb, int width, int height, int quality) {
    if(!rgb || width <= 0 || height <= 0) {
        return nullptr;
    }
    std::shared_ptr<const std::vector<uint8_t>> bytes;
    const auto stride = static_cast<UINT>(width * 3);
    const auto imageSize = static_cast<UINT>(stride * height);
    if(FAILED(encodeToMemory(GUID_ContainerFormatJpeg, GUID_WICPixelFormat24bppRGB, rgb, width, height, stride, imageSize, bytes,
                             static_cast<UINT>(std::clamp(quality, 1, 100))))) {
        return nullptr;
    }
    return bytes;
}

std::shared_ptr<const std::vector<uint8_t>> encodeGray16Png(const uint16_t *depth, int width, int height) {
    if(!depth || width <= 0 || height <= 0) {
        return nullptr;
    }
    std::shared_ptr<const std::vector<uint8_t>> bytes;
    const auto stride = static_cast<UINT>(width * sizeof(uint16_t));
    const auto imageSize = static_cast<UINT>(stride * height);
    if(FAILED(encodeToMemory(GUID_ContainerFormatPng, GUID_WICPixelFormat16bppGray, reinterpret_cast<const uint8_t *>(depth), width, height, stride,
                             imageSize, bytes))) {
        return nullptr;
    }
    return bytes;
}

bool writeRgbJpegFile(const std::filesystem::path &path, const uint8_t *rgb, int width, int height, int quality) {
    return writeBytes(path, encodeRgbJpeg(rgb, width, height, quality));
}

bool writeGray16PngFile(const std::filesystem::path &path, const uint16_t *depth, int width, int height) {
    return writeBytes(path, encodeGray16Png(depth, width, height));
}

}  // namespace femto::imageio
