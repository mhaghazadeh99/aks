from django.shortcuts import redirect
from django.urls import reverse, resolve

class LoginRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        # Allow these paths without login
        exempt_urls = [
            reverse("login"),
            reverse("logout"),
            reverse("admin:login"),
            reverse("auth_signup"),
        ]

        # allow static/media if needed
        if request.path.startswith("/static/") or request.path.startswith("/media/"):
            return self.get_response(request)

        if not request.user.is_authenticated:
            if not any(request.path.startswith(url) for url in exempt_urls):
                return redirect("login")

        return self.get_response(request)