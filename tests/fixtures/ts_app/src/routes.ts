import { authenticateToken } from "./auth";

export function registerAuthRoutes(app: any) {
  app.get("/me", (request: any, response: any) => {
    const user = authenticateToken(request.headers.authorization);
    response.json({ user });
  });
}
