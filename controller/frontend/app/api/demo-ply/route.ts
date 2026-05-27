import { readdir, readFile, stat } from "fs/promises";
import { resolve } from "path";

export const runtime = "nodejs";

async function findLatestPly(rootDir: string, minMtimeMs: number | null) {
    const entries: Array<{ path: string; mtimeMs: number }> = [];
    const queue = [rootDir];

    while (queue.length > 0) {
        const current = queue.pop();
        if (!current) {
            continue;
        }
        let dirents: Awaited<ReturnType<typeof readdir>>;
        try {
            dirents = await readdir(current, { withFileTypes: true });
        } catch {
            continue;
        }

        for (const dirent of dirents) {
            const fullPath = resolve(current, dirent.name);
            if (dirent.isDirectory()) {
                queue.push(fullPath);
                continue;
            }
            if (!dirent.isFile() || !dirent.name.toLowerCase().endsWith(".ply")) {
                continue;
            }
            try {
                const info = await stat(fullPath);
                if (minMtimeMs == null || info.mtimeMs >= minMtimeMs) {
                    entries.push({ path: fullPath, mtimeMs: info.mtimeMs });
                }
            } catch {
                continue;
            }
        }
    }

    entries.sort((a, b) => b.mtimeMs - a.mtimeMs);
    return entries[0] ?? null;
}

export async function GET(request: Request) {
    const captureRoot = resolve(process.cwd(), "..", "..", "calib_out", "captures");
    const requestUrl = new URL(request.url);
    const requestedFile = requestUrl.searchParams.get("file");
    const afterParam = requestUrl.searchParams.get("after");
    const checkOnly = requestUrl.searchParams.get("check") === "1";
    const normalizedFile = requestedFile?.trim() || "";
    const minMtimeMs = afterParam ? Number(afterParam) : null;

    const afterMs = Number.isFinite(minMtimeMs ?? Number.NaN) ? minMtimeMs : null;

    let targetPath: string | null = null;
    if (normalizedFile) {
        if (!normalizedFile.toLowerCase().endsWith(".ply") || /[\\/]/.test(normalizedFile)) {
            return new Response("Invalid PLY file", { status: 400 });
        }
        const candidatePath = resolve(captureRoot, normalizedFile);
        try {
            const info = await stat(candidatePath);
            if (afterMs != null && info.mtimeMs < afterMs) {
                return new Response("PLY capture not ready", { status: 404 });
            }
            targetPath = candidatePath;
        } catch {
            return new Response("No PLY capture found", { status: 404 });
        }
    } else {
        const latest = await findLatestPly(captureRoot, afterMs);
        targetPath = latest?.path ?? null;
    }

    if (!targetPath) {
        return new Response("No PLY capture found", { status: 404 });
    }

    if (checkOnly) {
        return new Response(null, { status: 204 });
    }

    try {
        const data = await readFile(targetPath);
        return new Response(data, {
            status: 200,
            headers: {
                "Content-Type": "application/octet-stream",
                "Cache-Control": "no-store",
            },
        });
    } catch {
        return new Response("Failed to load capture", { status: 500 });
    }
}
