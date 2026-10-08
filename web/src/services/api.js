import axios from 'axios';

// ---- 登录认证 ----
const AUTH_KEY = 'aitc_auth';
const APP_BASE = import.meta.env.BASE_URL || '/';
const API_BASE = `${APP_BASE.replace(/\/$/, '')}/api`;

export const getAuth = () => {
  try {
    return JSON.parse(localStorage.getItem(AUTH_KEY)) || null;
  } catch {
    return null;
  }
};
export const setAuth = (auth) => localStorage.setItem(AUTH_KEY, JSON.stringify(auth));
export const clearAuth = () => localStorage.removeItem(AUTH_KEY);

const api = axios.create({ baseURL: API_BASE });

api.interceptors.request.use((config) => {
  const token = getAuth()?.token;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const requestUrl = error.config?.url || '';
    const isPublicAuthRequest = ['/auth/login', '/auth/register']
      .some(path => requestUrl.endsWith(path));
    if (error.response?.status === 401 && !isPublicAuthRequest) {
      clearAuth();
      const loginPath = `${APP_BASE}login`;
      if (window.location.pathname !== loginPath) window.location.assign(loginPath);
    }
    return Promise.reject(error);
  },
);

export const login = (username, password) =>
  api.post('/auth/login', { username, password }).then(r => r.data);
export const register = (username, password) =>
  api.post('/auth/register', { username, password }).then(r => r.data);
export const logoutRequest = (token) => api.post(
  '/auth/logout',
  { token },
  token ? { headers: { Authorization: `Bearer ${token}` } } : undefined,
).catch(() => {});

export const getSkills = () => api.get('/skills').then(r => r.data);

export const getProjects = () => api.get('/projects').then(r => r.data);
export const getHomeOverview = () => api.get('/projects/overview').then(r => r.data);
export const createProject = (data) => api.post('/projects', data).then(r => r.data);
export const getProject = (id) => api.get(`/projects/${id}`).then(r => r.data);
export const getProjectStage = (id) => api.get(`/projects/${id}/stage`).then(r => r.data);
export const deleteProject = (id) => api.delete(`/projects/${id}`);

export const getRequirements = (projectId) =>
  api.get(`/projects/${projectId}/requirements`).then(r => r.data);
export const createRequirement = (projectId, data) =>
  api.post(`/projects/${projectId}/requirements`, data).then(r => r.data);
export const uploadRequirementFile = (projectId, file, title) => {
  const form = new FormData();
  form.append('file', file);
  if (title?.trim()) form.append('title', title.trim());
  return api.post(`/projects/${projectId}/requirements/upload`, form).then(r => r.data);
};
export const structureRequirement = (projectId, docId) =>
  api.post(`/projects/${projectId}/requirements/${docId}/structure`).then(r => r.data);
export const updateRequirementScope = (projectId, docId, testScope) =>
  api.patch(`/projects/${projectId}/requirements/${docId}/scope`, { test_scope: testScope }).then(r => r.data);
export const generateRequirementScope = (projectId, docId) =>
  api.post(`/projects/${projectId}/requirements/${docId}/scope/generate`).then(r => r.data);
export const exportFeatureList = (projectId, docId, format = 'xlsx') =>
  api.get(`/projects/${projectId}/requirements/${docId}/featurelist/export`, { params: { format }, responseType: 'blob' });
export const importFeatureList = (projectId, file, title) => {
  const form = new FormData();
  form.append('file', file);
  if (title?.trim()) form.append('title', title.trim());
  return api.post(`/projects/${projectId}/requirements/featurelist/import`, form).then(r => r.data);
};
export const confirmRequirement = (projectId, docId, itemIds) =>
  api.post(`/projects/${projectId}/requirements/${docId}/confirm`, { item_ids: itemIds }).then(r => r.data);
export const updateRequirementItem = (projectId, docId, itemId, data) =>
  api.patch(`/projects/${projectId}/requirements/${docId}/items/${itemId}`, data).then(r => r.data);
export const createRequirementItem = (projectId, docId, data) =>
  api.post(`/projects/${projectId}/requirements/${docId}/items`, data).then(r => r.data);
export const deleteRequirementItem = (projectId, docId, itemId) =>
  api.delete(`/projects/${projectId}/requirements/${docId}/items/${itemId}`);

export const getGenerations = (projectId) =>
  api.get(`/projects/${projectId}/generations`).then(r => r.data);
export const getGenerationSummaries = (projectId) =>
  api.get(`/projects/${projectId}/generations/summary`).then(r => r.data);
export const createGeneration = (projectId, data) =>
  api.post(`/projects/${projectId}/generations`, data).then(r => r.data);
export const getGeneration = (projectId, taskId) =>
  api.get(`/projects/${projectId}/generations/${taskId}`).then(r => r.data);
export const reviewDrafts = (projectId, taskId, data) =>
  api.post(`/projects/${projectId}/generations/${taskId}/review`, data).then(r => r.data);
export const editDraft = (projectId, taskId, draftId, data) =>
  api.patch(`/projects/${projectId}/generations/${taskId}/drafts/${draftId}`, data).then(r => r.data);
export const exportGenerationDrafts = (projectId, taskId, format = 'xlsx', smokeOnly = false) =>
  api.get(`/projects/${projectId}/generations/${taskId}/export`, {
    params: { format, smoke_only: smokeOnly },
    responseType: 'blob',
  });
export const rejudgeGeneration = (projectId, taskId) =>
  api.post(`/projects/${projectId}/generations/${taskId}/judge`).then(r => r.data);

export const getKnowledgeDocs = (projectId) =>
  api.get(`/projects/${projectId}/knowledge`).then(r => r.data);
export const createKnowledgeDoc = (projectId, data) =>
  api.post(`/projects/${projectId}/knowledge`, data).then(r => r.data);
export const uploadKnowledgeDoc = (projectId, file, title, sourceType = 'doc') => {
  const form = new FormData();
  form.append('file', file);
  if (title?.trim()) form.append('title', title.trim());
  form.append('source_type', sourceType);
  return api.post(`/projects/${projectId}/knowledge/upload`, form).then(r => r.data);
};
export const getKnowledgeChunks = (projectId, docId) =>
  api.get(`/projects/${projectId}/knowledge/${docId}/chunks`).then(r => r.data);
export const deleteKnowledgeDoc = (projectId, docId) =>
  api.delete(`/projects/${projectId}/knowledge/${docId}`);
export const searchKnowledge = (projectId, query, topK = 5) =>
  api.post(`/projects/${projectId}/knowledge/search`, { query, top_k: topK }).then(r => r.data);

export const getEvalSamples = () =>
  api.get('/evaluations/samples').then(r => r.data);
export const createEvalSample = (data) =>
  api.post('/evaluations/samples', data).then(r => r.data);
export const updateEvalSample = (sampleId, data) =>
  api.put(`/evaluations/samples/${sampleId}`, data).then(r => r.data);
export const deleteEvalSample = (sampleId) =>
  api.delete(`/evaluations/samples/${sampleId}`);
export const getEvalRuns = () =>
  api.get('/evaluations/runs').then(r => r.data);
export const createEvalRun = (data) =>
  api.post('/evaluations/runs', data).then(r => r.data);
export const getEvalRun = (runId) =>
  api.get(`/evaluations/runs/${runId}`).then(r => r.data);
export const getEvalTask = (taskId) =>
  api.get(`/evaluations/tasks/${taskId}`).then(r => r.data);
export const deleteEvalRun = (runId) =>
  api.delete(`/evaluations/runs/${runId}`);

export const getTestcases = (projectId) =>
  api.get(`/projects/${projectId}/testcases`).then(r => r.data);
export const updateTestcase = (projectId, caseId, data) =>
  api.patch(`/projects/${projectId}/testcases/${caseId}`, data).then(r => r.data);
export const renameTestcaseCatalog = (projectId, data) =>
  api.patch(`/projects/${projectId}/testcases/catalog/rename`, data).then(r => r.data);
export const getAllTestcases = (projectId) =>
  api.get('/testcases', { params: projectId ? { project_id: projectId } : {} }).then(r => r.data);

export const getTestTasks = (projectId) =>
  api.get(`/projects/${projectId}/tasks`).then(r => r.data);
export const createTestTask = (projectId, data) =>
  api.post(`/projects/${projectId}/tasks`, data).then(r => r.data);
export const getTestTaskDetail = (projectId, taskId) =>
  api.get(`/projects/${projectId}/tasks/${taskId}`).then(r => r.data);
export const updateTestTask = (projectId, taskId, data) =>
  api.patch(`/projects/${projectId}/tasks/${taskId}`, data).then(r => r.data);
export const deleteTestTask = (projectId, taskId) =>
  api.delete(`/projects/${projectId}/tasks/${taskId}`);
export const getTaskDefects = (projectId, taskId, includeBlocked = false) =>
  api.get(`/projects/${projectId}/tasks/${taskId}/defects`, { params: { include_blocked: includeBlocked } }).then(r => r.data);
export const createBatch = (projectId, taskId, data) =>
  api.post(`/projects/${projectId}/tasks/${taskId}/batches`, data).then(r => r.data);
export const getBatchDetail = (projectId, taskId, batchId) =>
  api.get(`/projects/${projectId}/tasks/${taskId}/batches/${batchId}`).then(r => r.data);
export const updateBatch = (projectId, taskId, batchId, data) =>
  api.patch(`/projects/${projectId}/tasks/${taskId}/batches/${batchId}`, data).then(r => r.data);
export const deleteBatch = (projectId, taskId, batchId) =>
  api.delete(`/projects/${projectId}/tasks/${taskId}/batches/${batchId}`);
export const markBatchCase = (projectId, taskId, batchId, batchCaseId, data) =>
  api.patch(`/projects/${projectId}/tasks/${taskId}/batches/${batchId}/cases/${batchCaseId}`, data).then(r => r.data);
export const batchMarkBatchCases = (projectId, taskId, batchId, data) =>
  api.patch(`/projects/${projectId}/tasks/${taskId}/batches/${batchId}/cases/batch`, data).then(r => r.data);
export const addBatchCases = (projectId, taskId, batchId, caseIds) =>
  api.post(`/projects/${projectId}/tasks/${taskId}/batches/${batchId}/cases`, { case_ids: caseIds }).then(r => r.data);
export const removeBatchCase = (projectId, taskId, batchId, batchCaseId) =>
  api.delete(`/projects/${projectId}/tasks/${taskId}/batches/${batchId}/cases/${batchCaseId}`).then(r => r.data);

export const getSettings = () => api.get('/settings').then(r => r.data);
export const updateSettings = (data) => api.patch('/settings', data).then(r => r.data);
export const testModelConnection = (target) =>
  api.post('/settings/test', { target }).then(r => r.data);

export default api;
