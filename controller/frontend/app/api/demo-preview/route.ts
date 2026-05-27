import { readFile } from "fs/promises";
import { resolve } from "path";

export const runtime = "nodejs";

export async function GET() {
    const imagePath = resolve(process.cwd(), "..", "..", "blender", "latest_capture_preview.png");

    try {
        const image = await readFile(imagePath);
        return new Response(image, {
            status: 200,
            headers: {
                "Content-Type": "image/png",
                "Cache-Control": "no-store",
            },
        });
    } catch {
        return new Response("Preview not found", { status: 404 });
    }
}
