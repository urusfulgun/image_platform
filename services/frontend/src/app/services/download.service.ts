import { Injectable, signal } from '@angular/core';

@Injectable({ providedIn: 'root' })
export class DownloadService {
    isDownloading = signal(false);

    async downloadAllDirectly(assets: { url: string; filename: string }[]) {
        try {
            // 1. Request a file handle from the OS
            const handle = await (window as any).showSaveFilePicker({
                suggestedName: `archive-${Date.now()}.zip`,
                types: [{ description: 'ZIP Archive', accept: { 'application/zip': ['.zip'] } }]
            });

            this.isDownloading.set(true);

            // 2. Initialize the Worker
            const worker = new Worker(new URL('./download.worker', import.meta.url));

            worker.onmessage = async ({ data }) => {
                if (data.type === 'STREAM_READY') {
                    const zipStream: ReadableStream = data.stream;
                    const fileStream = await handle.createWritable();

                    // 3. Pipe the ZIP stream directly to the file on disk
                    // This is the "Magic" step - zero memory buffering
                    await zipStream.pipeTo(fileStream);

                    this.isDownloading.set(false);
                    worker.terminate();
                    console.log('Download complete and saved to disk.');
                }

                if (data.type === 'ERROR') {
                    console.error(data.message);
                    this.isDownloading.set(false);
                    worker.terminate();
                }
            };

            worker.postMessage({ assets });

        } catch (err) {
            // Handle user cancellation of the file picker
            this.isDownloading.set(false);
            console.warn('User cancelled or browser does not support FS API', err);
        }
    }
}