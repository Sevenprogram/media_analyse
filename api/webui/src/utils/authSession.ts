export interface AuthUser {
  id: number;
  email: string;
  display_name?: string | null;
  status: string;
  email_verified: boolean;
  created_at?: string | null;
}

export interface AuthOrganization {
  id: number;
  name: string;
  slug: string;
  status: string;
}

export interface AuthMembership {
  id: number;
  user_id: number;
  org_id: number;
  role: string;
  status: string;
}

export interface AuthPermissions {
  is_platform_admin: boolean;
}

export interface AuthResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: AuthUser;
  organization: AuthOrganization;
  membership: AuthMembership;
  permissions?: AuthPermissions;
}

export interface AuthSession {
  accessToken: string;
  refreshToken: string;
  tokenType: string;
  user: AuthUser;
  organization: AuthOrganization;
  membership: AuthMembership;
  permissions: AuthPermissions;
}

const STORAGE_KEY = "media_analyse_auth_session";

function canUseStorage() {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

export function toAuthSession(response: AuthResponse): AuthSession {
  return {
    accessToken: response.access_token,
    refreshToken: response.refresh_token,
    tokenType: response.token_type || "bearer",
    user: response.user,
    organization: response.organization,
    membership: response.membership,
    permissions: response.permissions || { is_platform_admin: false },
  };
}

export function getStoredAuthSession(): AuthSession | null {
  if (!canUseStorage()) return null;
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<AuthSession>;
    if (!parsed.accessToken || !parsed.refreshToken || !parsed.user || !parsed.organization) {
      return null;
    }
    return {
      ...parsed,
      permissions: parsed.permissions || { is_platform_admin: false },
    } as AuthSession;
  } catch {
    window.localStorage.removeItem(STORAGE_KEY);
    return null;
  }
}

export function saveAuthSession(session: AuthSession) {
  if (!canUseStorage()) return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
}

export function clearAuthSession() {
  if (!canUseStorage()) return;
  window.localStorage.removeItem(STORAGE_KEY);
}

export function authDisplayName(session: AuthSession | null) {
  if (!session) return "";
  return session.user.display_name?.trim() || session.user.email;
}

export function authInitial(session: AuthSession | null) {
  const name = authDisplayName(session).trim();
  return Array.from(name)[0]?.toUpperCase() || "U";
}

export function isPlatformAdmin(session: AuthSession | null) {
  return Boolean(session?.permissions?.is_platform_admin);
}
