"""
main/permissions.py — access control helpers.

Managers don't have individual logins; instead the manager-facing pages
sit behind one shared site PIN (set in settings.SITE_ACCESS_PIN). Admin
pages use Django's normal login_required instead.
"""

from functools import wraps
from django.shortcuts import redirect


def pin_required(view_func):
    """Require that the shared site PIN has been entered this session."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.session.get("site_access_granted"):
            return redirect("main:pin_gate")
        return view_func(request, *args, **kwargs)
    return wrapper