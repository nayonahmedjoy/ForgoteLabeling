import { API_BASE } from "./api";

// Export is a file download, so we point the browser straight at the endpoint.
export const yoloExportUrl = (projectId) =>
  `${API_BASE}/projects/${projectId}/export/yolo`;
