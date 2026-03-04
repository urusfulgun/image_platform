/// <reference lib="webworker" />
import { Writer } from '@transcend-io/conflux';

addEventListener('message', async ({ data }) => {
    const { assets } = data as { assets: { url: string; filename: string }[] };

    try {
        const { readable, writable } = new Writer();
        const writer = writable.getWriter();

        // Background process to fetch and feed the ZIP writer
        const processFiles = async () => {
            for (const asset of assets) {
                try {
                    const response = await fetch(asset.url);
                    if (!response.ok) continue;

                    await writer.write({
                        name: asset.filename,
                        lastModified: Date.now(),
                        stream: () => response.body!
                    });
                } catch (e) {
                    console.error(`Worker fetch error: ${asset.filename}`, e);
                }
            }
            await writer.close();
        };

        processFiles();

        // CRITICAL: We send the 'readable' stream itself back to the main thread.
        // In modern browsers, ReadableStreams are "transferable".
        postMessage({ type: 'STREAM_READY', stream: readable }, [readable] as any);

    } catch (error: any) {
        postMessage({ type: 'ERROR', message: error.message });
    }
});