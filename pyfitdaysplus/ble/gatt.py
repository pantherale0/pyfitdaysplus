"""GATT discovery helpers for the ICOMON FFB0 service."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from uuid import UUID

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.service import BleakGATTService, BleakGATTServiceCollection
from bleak.uuids import normalize_uuid_str

from ..exceptions import ProtocolError
from ..protocol.constants import (
    CHAR_FILE_WRITE_UUID,
    CHAR_NOTIFY_UUID,
    CHAR_WRITE_UUID,
    SERVICE_UUID,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ScaleCharacteristics:
    """Resolved FFB0 characteristic UUIDs and write modes."""

    write_uuid: str
    notify_uuid: str
    file_write_uuid: str | None
    write_with_response: bool
    file_write_with_response: bool


def discover_scale_characteristics(
    services: BleakGATTServiceCollection,
) -> ScaleCharacteristics:
    """Find FFB1 / FFB2 (and optional FFB4) on a connected scale."""
    _log_gatt_table(services)
    service = _find_service(services, SERVICE_UUID)
    if service is None:
        found = _format_uuids(svc.uuid for svc in services) or "none"
        msg = f"service {SERVICE_UUID} not found (found: {found})"
        raise ProtocolError(msg)

    write = _find_characteristic(service, services, CHAR_WRITE_UUID)
    notify = _find_characteristic(service, services, CHAR_NOTIFY_UUID)
    file_write = _find_characteristic(service, services, CHAR_FILE_WRITE_UUID)
    if write is None or notify is None:
        missing: list[str] = []
        if write is None:
            missing.append(f"FFB1 ({CHAR_WRITE_UUID})")
        if notify is None:
            missing.append(f"FFB2 ({CHAR_NOTIFY_UUID})")
        found = (
            _format_uuids(
                char.uuid for char in _iter_characteristics(service, services)
            )
            or "none"
        )
        msg = (
            "required FFB0 service characteristics not found: "
            f"missing {', '.join(missing)} (found: {found})"
        )
        raise ProtocolError(msg)

    if file_write is None:
        _LOGGER.debug(
            "FFB0 write=%s notify=%s file=absent write_with_response=%s",
            write.uuid,
            notify.uuid,
            _att_write_response(write),
        )
        return ScaleCharacteristics(
            write_uuid=write.uuid,
            notify_uuid=notify.uuid,
            file_write_uuid=None,
            write_with_response=_att_write_response(write),
            file_write_with_response=False,
        )

    _LOGGER.debug(
        "FFB0 write=%s notify=%s file=%s write_with_response=%s",
        write.uuid,
        notify.uuid,
        file_write.uuid,
        _att_write_response(write),
    )
    return ScaleCharacteristics(
        write_uuid=write.uuid,
        notify_uuid=notify.uuid,
        file_write_uuid=file_write.uuid,
        write_with_response=_att_write_response(write),
        file_write_with_response=_att_write_response(file_write),
    )


def gatt_has_uuid(
    client: BleakClient,
    uuid: UUID,
    *,
    chars: bool,
) -> bool:
    """Return whether ``uuid`` is present as a service or characteristic."""
    key = _uuid_key(uuid)
    for service in client.services:
        if not chars and _uuid_key(service.uuid) == key:
            return True
        if chars:
            for characteristic in service.characteristics:
                if _uuid_key(characteristic.uuid) == key:
                    return True
    return False


def att_mtu(client: BleakClient) -> int:
    """Negotiated ATT MTU, or 23 when the backend has not reported one."""
    size = getattr(client, "mtu_size", None)
    if isinstance(size, int) and size >= 23:
        return size
    return 23


async def refresh_att_mtu(client: BleakClient) -> None:
    """Copy BlueZ's negotiated GATT MTU onto the Bleak client when possible."""
    backend = getattr(client, "_backend", None)
    if backend is None:
        return
    mtu = await _bluez_gatt_mtu(backend)
    if mtu is None or mtu < 23:
        return
    backend._mtu_size = mtu
    _LOGGER.debug("BlueZ GATT MTU=%s", mtu)


def _uuid_equal(left: str | UUID, right: str | UUID) -> bool:
    return normalize_uuid_str(str(left)) == normalize_uuid_str(str(right))


def _find_service(
    services: BleakGATTServiceCollection,
    uuid: UUID,
) -> BleakGATTService | None:
    for service in services:
        if _uuid_equal(service.uuid, uuid):
            return service
    return None


def _find_characteristic(
    service: BleakGATTService,
    services: BleakGATTServiceCollection,
    uuid: UUID,
) -> BleakGATTCharacteristic | None:
    for characteristic in _iter_characteristics(service, services):
        if _uuid_equal(characteristic.uuid, uuid):
            return characteristic
    return None


def _iter_characteristics(
    service: BleakGATTService,
    services: BleakGATTServiceCollection,
) -> list[BleakGATTCharacteristic]:
    found: list[BleakGATTCharacteristic] = list(service.characteristics)
    seen = {_uuid_key(char.uuid) for char in found}
    for characteristic in services.characteristics.values():
        key = _uuid_key(characteristic.uuid)
        if key in seen:
            continue
        seen.add(key)
        found.append(characteristic)
    return found


def _uuid_key(uuid: str | UUID) -> str:
    return normalize_uuid_str(str(uuid))


def _format_uuids(uuids: Iterable[str]) -> str:
    return ", ".join(sorted(set(uuids)))


def _att_write_response(characteristic: BleakGATTCharacteristic) -> bool:
    properties = {prop.lower() for prop in characteristic.properties}
    if "write-without-response" in properties:
        return False
    return "write" in properties


def _log_gatt_table(services: BleakGATTServiceCollection) -> None:
    if not _LOGGER.isEnabledFor(logging.DEBUG):
        return
    for service in services:
        _LOGGER.debug("GATT service %s", service.uuid)
        for characteristic in service.characteristics:
            properties = ",".join(characteristic.properties) or "none"
            _LOGGER.debug(
                "  char %s properties=%s",
                characteristic.uuid,
                properties,
            )


async def _bluez_gatt_mtu(backend: object) -> int | None:
    try:
        from bleak.backends.bluezdbus import defs
        from bleak.backends.bluezdbus.manager import get_global_bluez_manager
    except ImportError:
        return None
    device_path = getattr(backend, "_device_path", None)
    if not isinstance(device_path, str) or not device_path:
        return None
    try:
        manager = await get_global_bluez_manager()
        properties = getattr(manager, "_properties", {})
        for path, ifaces in properties.items():
            if not str(path).startswith(device_path):
                continue
            gatt = ifaces.get(defs.GATT_CHARACTERISTIC_INTERFACE)
            if not isinstance(gatt, dict):
                continue
            mtu = gatt.get("MTU")
            if isinstance(mtu, int) and mtu >= 23:
                return mtu
    except Exception:
        _LOGGER.debug("BlueZ MTU lookup failed", exc_info=True)
    return None
