import wsgi


def test_wsgi_app_exists():
    assert hasattr(wsgi, "app")
    assert wsgi.app is not None
