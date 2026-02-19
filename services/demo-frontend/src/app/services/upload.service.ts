// src/app/services/upload.service.ts
import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpEventType } from '@angular/common/http';
import { map } from 'rxjs';

@Injectable({ providedIn: 'root' })
export class UploadService {
  private http = inject(HttpClient);
  private BFF_API = 'http://localhost:8000/api';

  getPresignedUrl(fileName: string) {
    return this.http.post<{ url: string }>(`${this.BFF_API}/${fileName}`, {});
  }

  uploadToPresignedUrl(url: string, file: File) {
    return this.http.put(url, file, {
      reportProgress: true,
      observe: 'events',
      headers: { 'Content-Type': file.type }
    }).pipe(
      map(event => {
        if (event.type === HttpEventType.UploadProgress && event.total) {
          return Math.round((100 * event.loaded) / event.total);
        }
        return event.type === HttpEventType.Response ? 100 : 0;
      })
    );
  }
}
