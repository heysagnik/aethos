from django.urls import path

from apps.accounts.api import api as accounts_api
from apps.dashboard.api import api as dashboard_api
from apps.github.views import install_redirect, setup_callback, webhook
from apps.reviews.views import run_step

urlpatterns = [
    path("api/github/install", install_redirect, name="github-install"),
    path("api/github/setup", setup_callback, name="github-setup"),
    path("api/github/webhook", webhook, name="github-webhook"),
    path("api/steps/<str:step>", run_step, name="review-step"),
    path("api/auth/", accounts_api.urls),
    path("api/dashboard/", dashboard_api.urls),
]
