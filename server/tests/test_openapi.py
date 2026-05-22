from api.app import app


def test_openapi_includes_security_schemes():
    schema = app.openapi()
    schemes = schema["components"]["securitySchemes"]
    assert "BearerAccessKey" in schemes
    assert "SessionCookie" in schemes
    assert schemes["BearerAccessKey"]["scheme"] == "bearer"


def test_openapi_protected_routes_require_auth():
    schema = app.openapi()
    files_list = schema["paths"]["/api/files/"]["get"]
    assert files_list["security"] == [
        {"BearerAccessKey": []},
        {"SessionCookie": []},
    ]


def test_openapi_login_is_public():
    schema = app.openapi()
    login = schema["paths"]["/api/auth/login"]["post"]
    assert "security" not in login


def test_openapi_session_requires_auth():
    schema = app.openapi()
    session = schema["paths"]["/api/auth/session"]["get"]
    assert session["security"] == [
        {"BearerAccessKey": []},
        {"SessionCookie": []},
    ]


def test_openapi_injects_error_responses():
    schema = app.openapi()
    files_list = schema["paths"]["/api/files/"]["get"]
    assert "401" in files_list["responses"]
    assert "404" in files_list["responses"]
    assert "ErrorDetail" in schema["components"]["schemas"]


def test_openapi_has_tag_descriptions():
    schema = app.openapi()
    tags = {tag["name"]: tag["description"] for tag in schema["tags"]}
    assert "uploads" in tags
    assert "SigV4" in tags["s3"]


def test_openapi_app_description_documents_auth():
    schema = app.openapi()
    assert "Bearer access key" in schema["info"]["description"]
    assert "/s3/" in schema["info"]["description"]
