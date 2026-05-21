import { authenticateToken } from "../src/auth";

test("authenticateToken accepts valid token", () => {
  expect(authenticateToken("valid-token")?.id).toBe("fixture");
});
