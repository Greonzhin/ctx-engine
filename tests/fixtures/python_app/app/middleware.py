from dataclasses import dataclass


@dataclass
class User:
    name: str


def authenticate_request(headers: dict[str, str]) -> User | None:
    token = headers.get("Authorization", "").replace("Bearer ", "")
    if token == "valid-token":
        return User(name="fixture")
    return None


class AuthMiddleware:
    def __init__(self, app):
        self.app = app

    def __call__(self, request):
        request.user = authenticate_request(request.headers)
        return self.app(request)
