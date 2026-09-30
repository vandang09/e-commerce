import pytest

from app import create_app, db


@pytest.fixture

def app(tmp_path):
    database = tmp_path / "test.sqlite"
    application = create_app({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database}",
        "SECRET_KEY": "test-secret",
        "ROTATION_UPLOAD_DIR": str(tmp_path / "uploads" / "rotation"),
        "MODEL_UPLOAD_DIR": str(tmp_path / "uploads" / "models"),
    })
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture

def client(app):
    return app.test_client()
