import { demoApi, DEMO_DATA_BASE, isDemoMode } from './demo';
import { localApi, caseIntakeImageUrl } from './local';
import { mediaUrl } from './media';
import { ApiError } from './http';

export const api = isDemoMode ? demoApi : localApi;

export { ApiError, DEMO_DATA_BASE, caseIntakeImageUrl, isDemoMode, mediaUrl };
