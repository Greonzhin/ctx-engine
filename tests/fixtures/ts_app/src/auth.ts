export type User = {
  id: string;
  role: "admin" | "member";
};

export function authenticateToken(token: string): User | null {
  if (token === "valid-token") {
    return { id: "fixture", role: "admin" };
  }
  return null;
}
