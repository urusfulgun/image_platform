// src/app/components/project/project-upload.component.ts
import { Component, signal, inject, input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router'; // For [routerLink]
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { PresignResponse, UploadService } from '../../services/upload.service';
import { finalize } from 'rxjs';
import { ProjectGalleryComponent } from './project-gallery.component';

@Component({
    standalone: true,
    selector: 'app-project-upload',
    templateUrl: '../../pages/project/project-upload.html',
    styleUrl: '../../pages/project/project-upload.css',
    imports: [
        CommonModule,
        RouterLink,
        MatButtonModule,
        MatCardModule,
        MatIconModule,
        MatProgressBarModule,
        ProjectGalleryComponent
    ]
})
export class ProjectUploadComponent {
    projectId = input.required<string>();
    private uploadSvc = inject(UploadService);

    // Signals for UI State
    uploadQueue = signal<File[]>([]);
    progressMap = signal<Record<string, number>>({});
    isUploading = signal(false);
    isDragging = signal(false); // Controls the CSS class in the template

    // --- Drag and Drop Handlers ---

    onDragOver(event: DragEvent) {
        event.preventDefault();
        event.stopPropagation();
        this.isDragging.set(true);
    }

    onDragLeave(event: DragEvent) {
        event.preventDefault();
        event.stopPropagation();
        this.isDragging.set(false);
    }

    onDrop(event: DragEvent) {
        event.preventDefault();
        event.stopPropagation();
        this.isDragging.set(false);

        const files = event.dataTransfer?.files;
        if (files && files.length > 0) {
            this.onFilesSelected(files);
        }
    }

    onFilesSelected(files: FileList | null) {
        if (files) this.uploadQueue.set(Array.from(files));
    }

    startBulkUpload() {
        if (this.uploadQueue().length === 0) return;
        this.isUploading.set(true);

        const files = this.uploadQueue();

        // We use a loop to handle multiple files. 
        // For massive sets, you could use forkJoin for parallel or concatMap for sequential.
        files.forEach(file => {
            this.uploadSvc.getPresignedUrl(this.projectId(), file).subscribe({
                next: (res: PresignResponse) => {
                    this.performUpload(res.upload_url, file);
                },
                error: (err) => console.error(`Failed to register ${file.name}`, err)
            });
        });
    }

    private performUpload(url: string, file: File) {
        this.uploadSvc.uploadToPresignedUrl(url, file).pipe(
            finalize(() => {
                // Check if all files in queue are at 100% to toggle isUploading
                if (Object.values(this.progressMap()).every(v => v === 100)) {
                    this.isUploading.set(false);
                }
            })
        ).subscribe(p => {
            this.progressMap.update(prev => ({ ...prev, [file.name]: p }));
            // Trigger notification only when this specific file is done
            if (p === 100) {
                this.uploadSvc.notifyUploadComplete();
            }
        });
    }
}