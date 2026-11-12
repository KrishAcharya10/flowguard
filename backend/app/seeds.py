"""Seed namespaces (spec 4.2). Pure functions, no imports from the app.

Prediction seeds and simulator-truth seeds live in separate namespaces so the
predictor can never reproduce the hidden outcome by accident.
The built-in Python hashing function is salted per process, so seeds use zlib.crc32.
"""
import zlib


def _crc(text: str) -> int:
    return zlib.crc32(text.encode("utf-8")) & 0xFFFFFFFF


def seed_pred(global_seed: int, shipment_id: str) -> int:
    return _crc(f"{global_seed}|pred|{shipment_id}")


def seed_truth(global_seed: int, shipment_id: str, route_id: str, lot_type: str) -> int:
    return _crc(f"{global_seed}|truth|{shipment_id}|{route_id}|{lot_type}")


def seed_truth_disruption(global_seed: int, disruption_id: str) -> int:
    return _crc(f"{global_seed}|truth|disruption|{disruption_id}")


def name_key(name: str) -> int:
    return _crc(name)
