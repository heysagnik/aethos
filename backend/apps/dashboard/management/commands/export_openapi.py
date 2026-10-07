from __future__ import annotations

import json
from typing import Any

from django.core.management.base import BaseCommand

from apps.accounts.api import api as accounts_api
from apps.dashboard.api import api as dashboard_api


class Command(BaseCommand):
    help = "Print the OpenAPI schema for the endpoints the frontend uses (auth + dashboard)."

    def handle(self, *args: Any, **options: Any) -> None:
        schema = dashboard_api.get_openapi_schema(path_prefix="/api/dashboard/")
        auth_schema = accounts_api.get_openapi_schema(path_prefix="/api/auth/")
        schema["paths"].update(auth_schema["paths"])
        schema["components"]["schemas"].update(auth_schema["components"]["schemas"])
        self.stdout.write(json.dumps(schema, indent=2, sort_keys=True))
