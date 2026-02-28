export interface Project {
  id: string; // uuid
  name: string;
  description?: string;
  created_at: string;
}

export interface CreateProjectRequest {
  name: string;
  description?: string;
}
