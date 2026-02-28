import { HttpBackend, HttpClient, HttpContextToken, HttpEventType, HttpHeaders } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { map } from 'rxjs';

export const IS_EXTERNAL_UPLOAD = new HttpContextToken(() => false);

export interface PresignResponse {
    image_id: string;
    upload_url: string;
}

@Injectable({ providedIn: 'root' })
export class UploadService {
    private externalHttp: HttpClient;

    constructor(private handler: HttpBackend, private http: HttpClient) {
        // This client bypasses the interceptor chain entirely
        this.externalHttp = new HttpClient(handler);
    }

    private BFF_API = 'http://localhost:80';

    getPresignedUrl(projectId: string, file: File) {
        const body = {
            fileName: file.name,
            fileSizeBytes: file.size
        };
        // Passing project_id as a query param or adjusting to your route pattern
        return this.http.post<PresignResponse>(
            `${this.BFF_API}/api/proxy/projects/${projectId}/images/presign`, 
            body
        );
    }

    uploadToPresignedUrl(url: string, file: File) {
        const headers = new HttpHeaders({
            'Content-Type': 'application/octet-stream' // Must match what you used in the console
        });

        return this.externalHttp.put(url, file, {
            headers,
            reportProgress: true,
            observe: 'events'
        }).pipe(
            map(event => {
                if (event.type === HttpEventType.UploadProgress && event.total) {
                    return Math.round((100 * event.loaded) / event.total);
                }
                return event.type === HttpEventType.Response ? 100 : 0;
            })
        );;
    }
}