const ws = new WebSocket("ws://127.0.0.1:8080/ws/depth");
ws.binaryType = "arraybuffer";

ws.onmessage = async (event) => {
  const view = new DataView(event.data);
  const magic = String.fromCharCode(
    view.getUint8(0),
    view.getUint8(1),
    view.getUint8(2),
    view.getUint8(3),
  );
  if (magic !== "OBD1") {
    console.error("Unexpected magic", magic);
    return;
  }

  const schemaVersion = view.getUint16(4, true);
  const flags = view.getUint16(6, true);
  const headerLength = view.getUint32(8, true);
  const payloadLength = view.getUint32(12, true);

  const headerBytes = new Uint8Array(event.data, 16, headerLength);
  const header = JSON.parse(new TextDecoder().decode(headerBytes));
  const payload = new Uint8Array(event.data, 16 + headerLength, payloadLength);

  console.log({
    schemaVersion,
    flags,
    frameIndex: header.frame_index,
    width: header.width,
    height: header.height,
    compression: header.compression_type,
    payloadBytes: payload.byteLength,
    depthScale: header.depth_scale,
  });

  // Decompress the payload with zstd in your runtime of choice, then reinterpret as Uint16Array.
};
