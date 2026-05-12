# SPDX-FileCopyrightText: 2026 4113Eng-wfs
# SPDX-License-Identifier: GPL-3.0-or-later
"""
cs_api_client.py – Pure-Python client for the OGC Connected Systems API.

Target server: https://cs.ogc.secd.eu/api/1.0
Spec:          https://cs.ogc.secd.eu/api-docs.html

Only stdlib dependencies (urllib, json) — works inside QGIS Python env
without any additional pip packages.

Usage::

    from .cs_api_client import CSAPIClient

    client = CSAPIClient('https://cs.ogc.secd.eu/api/1.0', token='...')

    # Register a drone system
    system = client.post('/systems', {
        'uid': 'urn:drone:dji:mavic3-001',
        'name': 'DJI Mavic 3 – Unit 001',
        'type': 'drone',
        'status': 'inactive',
        'properties': {'make': 'DJI', 'model': 'Mavic 3'},
    })

    # Create a deployment (mission)
    dep = client.post('/deployments', {
        'uid': 'urn:deployment:mission-01',
        'name': 'Survey Mission 01',
        'systemId': system['id'],
        'timeStart': '2026-05-07T08:00:00Z',
        'timeEnd':   '2026-05-07T09:30:00Z',
        'geometry': {'type': 'Point', 'coordinates': [12.5, 41.9]},
        'properties': {},
    })
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional


# ── Default endpoint ──────────────────────────────────────────────────────────
DEFAULT_BASE_URL = "https://cs.ogc.secd.eu/api/1.0"
_USER_AGENT = "QGIS-GeneralRasterImporter/2.0 (OGC-CS-Client)"


class CSAPIError(Exception):
    """Raised when the CS API returns an error response."""

    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail
        super().__init__(f"CS API {status}: {detail}")


class CSAPIClient:
    """
    Minimal REST client for the OGC Connected Systems API.

    All methods return parsed JSON as plain dicts/lists.
    Raises :class:`CSAPIError` on HTTP ≥ 400 responses.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        token: Optional[str] = None,
        timeout: int = 20,
    ):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Low-level helpers
    # ------------------------------------------------------------------

    def _headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        h = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": _USER_AGENT,
        }
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        if extra:
            h.update(extra)
        return h

    def _url(self, path: str, params: Optional[Dict[str, Any]] = None) -> str:
        url = self.base_url + path
        if params:
            clean = {k: str(v) for k, v in params.items() if v is not None}
            url += "?" + urllib.parse.urlencode(clean)
        return url

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        body: Optional[Any] = None,
    ) -> Any:
        url = self._url(path, params)
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(
            url,
            data=data,
            headers=self._headers(),
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                pass
            raise CSAPIError(exc.code, detail) from exc
        except urllib.error.URLError as exc:
            raise CSAPIError(0, str(exc.reason)) from exc

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        return self._request("GET", path, params=params)

    def post(self, path: str, body: Any) -> Any:
        return self._request("POST", path, body=body)

    def put(self, path: str, body: Any) -> Any:
        return self._request("PUT", path, body=body)

    def delete(self, path: str) -> None:
        self._request("DELETE", path)

    def patch(self, path: str, body: Any) -> Any:
        return self._request("PATCH", path, body=body)

    # ------------------------------------------------------------------
    # Systems (Part 1)
    # ------------------------------------------------------------------

    def list_systems(
        self,
        uid: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[dict]:
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if uid:
            params["uid"] = uid
        resp = self.get("/systems", params)
        return (
            resp.get("features")
            or resp.get("systems")
            or resp.get("items")
            or (resp if isinstance(resp, list) else [])
        )

    def register_system(self, body: dict) -> dict:
        return self.post("/systems", body)

    def get_system(self, system_id: str) -> dict:
        return self.get(f"/systems/{system_id}")

    def update_system(self, system_id: str, body: dict) -> dict:
        return self.put(f"/systems/{system_id}", body)

    def delete_system(self, system_id: str) -> None:
        self.delete(f"/systems/{system_id}")

    # ------------------------------------------------------------------
    # Deployments (Part 1)
    # ------------------------------------------------------------------

    def list_deployments(
        self,
        system_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[dict]:
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if system_id:
            params["systemId"] = system_id
        resp = self.get("/deployments", params)
        return (
            resp.get("features")
            or resp.get("deployments")
            or resp.get("items")
            or (resp if isinstance(resp, list) else [])
        )

    def create_deployment(self, body: dict) -> dict:
        return self.post("/deployments", body)

    def get_deployment(self, dep_id: str) -> dict:
        return self.get(f"/deployments/{dep_id}")

    def update_deployment(self, dep_id: str, body: dict) -> dict:
        return self.put(f"/deployments/{dep_id}", body)

    def delete_deployment(self, dep_id: str) -> None:
        self.delete(f"/deployments/{dep_id}")

    # ------------------------------------------------------------------
    # Datastreams (Part 2)
    # ------------------------------------------------------------------

    def list_datastreams(self, limit: int = 50) -> List[dict]:
        resp = self.get("/datastreams", {"limit": limit})
        return (
            resp.get("datastreams")
            or resp.get("items")
            or (resp if isinstance(resp, list) else [])
        )

    def get_datastream_observations(
        self,
        datastream_id: str,
        limit: int = 200,
        since: Optional[str] = None,
    ) -> List[dict]:
        params: Dict[str, Any] = {"limit": limit}
        if since:
            params["phenomenonTime"] = since
        resp = self.get(f"/datastreams/{datastream_id}/observations", params)
        return (
            resp.get("observations")
            or resp.get("items")
            or (resp if isinstance(resp, list) else [])
        )

    # ------------------------------------------------------------------
    # Observations (Part 2)
    # ------------------------------------------------------------------

    def post_observation(self, body: dict) -> dict:
        return self.post("/observations", body)

    # ------------------------------------------------------------------
    # Spatial extensions
    # ------------------------------------------------------------------

    def get_active_drones(self) -> List[dict]:
        resp = self.get("/spatial/drones/active")
        return (
            resp.get("features")
            or resp.get("drones")
            or (resp if isinstance(resp, list) else [])
        )

    def get_flight_path(self, system_id: str) -> Optional[dict]:
        """Return GeoJSON LineString for the system's reconstructed flight path."""
        try:
            return self.get(f"/spatial/flightpath/{system_id}")
        except CSAPIError:
            return None

    def get_observations_within(
        self,
        bbox: Optional[List[float]] = None,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        radius_m: Optional[float] = None,
        limit: int = 200,
    ) -> List[dict]:
        params: Dict[str, Any] = {"limit": limit}
        if bbox and len(bbox) == 4:
            params["bbox"] = ",".join(str(v) for v in bbox)
        elif lat is not None and lon is not None:
            params["lat"] = lat
            params["lon"] = lon
            if radius_m is not None:
                params["radius"] = radius_m
        resp = self.get("/spatial/observations/within", params)
        return (
            resp.get("observations")
            or resp.get("items")
            or resp.get("features")
            or (resp if isinstance(resp, list) else [])
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def find_or_register_system(self, uid: str, name: str, properties: dict) -> str:
        """
        Look up a system by *uid*.  If found return its ``id``.
        If not found, register it and return the new ``id``.

        Raises :class:`CSAPIError` on unexpected failures.
        """
        existing = self.list_systems(uid=uid, limit=1)
        if existing:
            item = existing[0]
            return str(
                item.get("id")
                or item.get("properties", {}).get("id", "")
            )
        body = {
            "uid": uid,
            "name": name,
            "type": "drone",
            "status": "inactive",
            "properties": properties,
        }
        created = self.register_system(body)
        return str(
            created.get("id")
            or created.get("properties", {}).get("id", "")
        )

    def push_dji_mission(
        self,
        mission_name: str,
        drone_uid: str,
        drone_name: str,
        drone_properties: dict,
        time_start: str,
        time_end: str,
        flight_path_geojson: Optional[dict] = None,
        extra_properties: Optional[dict] = None,
    ) -> dict:
        """
        One-shot helper: find/register the system, then create a deployment.

        Returns the created deployment dict with an additional
        ``_system_id`` key carrying the resolved CS system UUID.
        """
        import uuid as _uuid

        system_id = self.find_or_register_system(
            uid=drone_uid,
            name=drone_name,
            properties=drone_properties,
        )

        dep_props: dict = dict(extra_properties or {})
        if flight_path_geojson:
            dep_props["flightPath"] = flight_path_geojson

        dep_uid = f"urn:deployment:{drone_uid}:{time_start[:10]}-{_uuid.uuid4().hex[:6]}"

        dep_body: dict = {
            "uid": dep_uid,
            "name": mission_name,
            "systemId": system_id,
            "timeStart": time_start,
            "timeEnd": time_end,
            "properties": dep_props,
        }
        deployment = self.create_deployment(dep_body)
        deployment["_system_id"] = system_id
        return deployment
