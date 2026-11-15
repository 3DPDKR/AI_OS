"""Offline HMAC checkpoint file for an independently keyed journal snapshot.

This protects against *one-file* journal replacement/tampering while a trusted
anchor file and secret remain intact. It is not a monotonic hardware counter,
network authority, or defense against paired rollback of both files.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
import tempfile

from .consent import ConsentError


class AnchorMismatch(ConsentError):
    """Missing, invalid, or mismatched independently keyed snapshot."""


class JournalAnchor:
    """HMAC-SHA256 over a canonical journal snapshot, in a separate local file."""

    FORMAT = "nexion-journal-anchor-v1"

    def __init__(self, path: str | Path, key: bytes):
        self.path = Path(path)
        if not self.path.name or self.path.is_dir():
            raise ValueError("Anchor must be a regular file path")
        if not isinstance(key, bytes) or len(key) < 32:
            raise ValueError("Anchor key must be at least 32 secret bytes")
        self._key = key

    @staticmethod
    def _serialize(snapshot: dict) -> bytes:
        return json.dumps(snapshot, sort_keys=True, ensure_ascii=False,
                          separators=(",", ":")).encode("utf-8")

    def _signed(self, snapshot: dict) -> bytes:
        canonical = {"format": self.FORMAT, "state": snapshot}
        mac = hmac.new(self._key, self._serialize(canonical), hashlib.sha256).hexdigest()
        return self._serialize({**canonical, "mac": mac}) + b"\n"

    def _read(self) -> dict:
        try:
            with self.path.open("rb") as file:
                raw = file.read(8193)
            if len(raw) > 8192:
                raise AnchorMismatch("Anchor file exceeds size limit")
            document = json.loads(raw)
            if (not isinstance(document, dict)
                    or set(document) != {"format", "state", "mac"}
                    or document["format"] != self.FORMAT
                    or not isinstance(document["state"], dict)
                    or not isinstance(document["mac"], str)
                    or len(document["mac"]) != 64):
                raise AnchorMismatch("Malformed journal anchor")
            expected = self._signed(document["state"])
            mac_document = json.loads(expected)["mac"]
            if not hmac.compare_digest(mac_document, document["mac"]):
                raise AnchorMismatch("Journal anchor authentication failed")
            return document["state"]
        except (OSError, ValueError, TypeError, UnicodeError) as exc:
            raise AnchorMismatch("Journal anchor missing or unreadable") from exc

    def verify(self, snapshot: dict) -> None:
        if self._read() != snapshot:
            raise AnchorMismatch("Journal and independent anchor disagree; refuse operation")

    def initialize(self, snapshot: dict) -> None:
        """Exclusive first creation; never trust an existing file as new."""
        content = self._signed(snapshot)
        try:
            with self.path.open("xb") as file:
                file.write(content)
                file.flush()
                os.fsync(file.fileno())
            self._sync_directory()
        except FileExistsError as exc:
            raise AnchorMismatch("Existing anchor cannot initialize a new journal") from exc

    def record(self, snapshot: dict) -> None:
        """Crash-safe file replacement, following journal commit.

        If power fails between the two, subsequent operations MUST fail closed.
        Do not use this as a cross-file atomic transaction.
        """
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="wb", prefix=".nexion-anchor-",
                                             dir=self.path.parent, delete=False) as file:
                tmp_path = Path(file.name)
                file.write(self._signed(snapshot))
                file.flush()
                os.fsync(file.fileno())
            os.replace(tmp_path, self.path)
            tmp_path = None
            self._sync_directory()
        finally:
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)

    def _sync_directory(self) -> None:
        # POSIX directory fsync; on other platforms durability is best-effort.
        if hasattr(os, "O_DIRECTORY"):
            fd = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
