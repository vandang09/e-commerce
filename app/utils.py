from functools import wraps

from flask import abort
from flask_login import current_user


def role_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                from flask import redirect, url_for
                return redirect(url_for("auth.login", next=None))
            if not current_user.is_active:
                abort(403)
            if current_user.role not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def seller_required(view):
    return role_required("seller", "admin")(view)


def admin_required(view):
    return role_required("admin")(view)
