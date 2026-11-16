"""Publish a .pbix to a Power BI workspace through the REST API.

What it does:

1. signs in with MSAL (device code as yourself, or a service principal for CI);
2. uploads the .pbix with ``Imports - Post Import In Group`` (``CreateOrOverwrite``,
   so re-publishing replaces the same semantic model instead of making a copy);
3. waits for the import to finish and prints the report URL;
4. reads the semantic model back and checks that row-level security roles came with
   it (``isEffectiveIdentityRolesRequired``).

What it cannot do: assign people to an RLS role. The REST API has no endpoint for
role members, so that step is in the Power BI service (semantic model → Security), or
over the XMLA endpoint on a Premium/Fabric capacity. See powerbi/README.md.

API reference: https://learn.microsoft.com/rest/api/power-bi/imports/post-import-in-group
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.core.config import Settings
from app.core.errors import PublishError

logger = logging.getLogger(__name__)

API = "https://api.powerbi.com/v1.0/myorg"
SCOPES = ["https://analysis.windows.net/powerbi/api/.default"]


@dataclass
class PublishResult:
    import_id: str
    dataset_id: str | None
    report_url: str | None
    rls_roles_detected: bool | None


def get_token(settings: Settings, *, show: Callable[[str], None] = print) -> str:
    """An access token for the Power BI REST API."""
    import msal

    if not settings.pbi_client_id:
        raise PublishError(
            "Set PBI_CLIENT_ID in server/.env: the id of an Entra app registration "
            "(see powerbi/README.md, step 'Let the script sign in')."
        )
    authority = f"https://login.microsoftonline.com/{settings.pbi_tenant_id}"

    if settings.pbi_auth == "service_principal":
        if not settings.pbi_client_secret:
            raise PublishError("PBI_AUTH=service_principal needs PBI_CLIENT_SECRET.")
        app = msal.ConfidentialClientApplication(
            settings.pbi_client_id,
            authority=authority,
            client_credential=settings.pbi_client_secret.get_secret_value(),
        )
        result = app.acquire_token_for_client(scopes=SCOPES)
    else:
        cache_path = settings.data_dir / ".msal_token_cache.json"
        cache = msal.SerializableTokenCache()
        if cache_path.exists():
            cache.deserialize(cache_path.read_text(encoding="utf-8"))
        app = msal.PublicClientApplication(
            settings.pbi_client_id, authority=authority, token_cache=cache
        )
        result = None
        accounts = app.get_accounts()
        if accounts:
            result = app.acquire_token_silent(SCOPES, account=accounts[0])
        if not result:
            flow = app.initiate_device_flow(scopes=SCOPES)
            if "user_code" not in flow:
                raise PublishError(f"Could not start sign-in: {flow.get('error_description')}")
            show(flow["message"])
            result = app.acquire_token_by_device_flow(flow)
        if cache.has_state_changed:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(cache.serialize(), encoding="utf-8")

    if not result or "access_token" not in result:
        detail = (result or {}).get("error_description", "no token returned")
        raise PublishError(f"Sign-in failed: {detail}")
    return result["access_token"]


def publish_pbix(
    settings: Settings,
    token: str,
    *,
    client: httpx.Client | None = None,
    poll_seconds: float = 3.0,
    timeout_seconds: float = 300.0,
    sleep: Callable[[float], None] = time.sleep,
) -> PublishResult:
    """Upload the .pbix and wait for Power BI to finish importing it."""
    workspace = settings.pbi_workspace_id.strip()
    if not workspace:
        raise PublishError(
            "Set PBI_WORKSPACE_ID: the GUID in app.powerbi.com/groups/<id>/... "
            "(not 'My workspace'; RLS needs a shared workspace)."
        )
    pbix: Path = settings.pbi_pbix_path
    if not pbix.exists():
        raise PublishError(
            f"{pbix} not found. Build it in Power BI Desktop first (powerbi/README.md)."
        )

    http = client or httpx.Client(timeout=120.0)
    headers = {"Authorization": f"Bearer {token}"}
    try:
        name = settings.pbi_dataset_name
        response = http.post(
            f"{API}/groups/{workspace}/imports",
            params={"datasetDisplayName": f"{name}.pbix", "nameConflict": "CreateOrOverwrite"},
            headers=headers,
            files={"file": (pbix.name, pbix.read_bytes(), "application/octet-stream")},
        )
        _raise_for(response, "upload the .pbix")
        import_id = response.json()["id"]
        logger.info("Import %s started", import_id)

        waited = 0.0
        while True:
            status = http.get(f"{API}/groups/{workspace}/imports/{import_id}", headers=headers)
            _raise_for(status, "read the import status")
            body = status.json()
            state = body.get("importState")
            if state == "Succeeded":
                break
            if state == "Failed":
                raise PublishError(f"Power BI could not import the file: {body.get('error')}")
            if waited >= timeout_seconds:
                raise PublishError(f"Import {import_id} still '{state}' after {timeout_seconds}s.")
            sleep(poll_seconds)
            waited += poll_seconds

        datasets = body.get("datasets") or []
        reports = body.get("reports") or []
        dataset_id = datasets[0]["id"] if datasets else None
        rls = None
        if dataset_id:
            info = http.get(f"{API}/groups/{workspace}/datasets/{dataset_id}", headers=headers)
            _raise_for(info, "read the semantic model")
            rls = info.json().get("isEffectiveIdentityRolesRequired")
        return PublishResult(
            import_id=import_id,
            dataset_id=dataset_id,
            report_url=reports[0].get("webUrl") if reports else None,
            rls_roles_detected=rls,
        )
    finally:
        if client is None:
            http.close()


def _raise_for(response: httpx.Response, action: str) -> None:
    if response.status_code < 400:
        return
    hint = ""
    if response.status_code == 401:
        hint = " Sign-in worked but Power BI refused the token; check the app's API permissions."
    if response.status_code == 403:
        hint = (
            " You (or the service principal) need Member or Admin on the workspace, and "
            "service principals must be allowed in the tenant's admin settings."
        )
    if response.status_code == 404:
        hint = " Check PBI_WORKSPACE_ID."
    raise PublishError(
        f"Could not {action}: HTTP {response.status_code} {response.text[:300]}{hint}"
    )
