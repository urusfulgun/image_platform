import { HttpBackend, HttpClient, HttpContextToken, HttpEventType, HttpHeaders } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { map } from 'rxjs';

export const IS_EXTERNAL_UPLOAD = new HttpContextToken(() => false);

@Injectable({ providedIn: 'root' })
export class UploadService {
    private externalHttp: HttpClient;

    constructor(private handler: HttpBackend, private http: HttpClient) {
        // This client bypasses the interceptor chain entirely
        this.externalHttp = new HttpClient(handler);
    }

    private BFF_API = 'http://localhost:8000';

    getPresignedUrl(fileName: string) {
        return this.http.post<{ url: string }>(`${this.BFF_API}/presign`, { fileName });
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