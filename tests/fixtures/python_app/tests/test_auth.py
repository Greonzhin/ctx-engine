from app.middleware import authenticate_request


def test_authenticate_request_accepts_valid_token():
    assert authenticate_request({"Authorization": "Bearer valid-token"}).name == "fixture"
