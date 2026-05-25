"""Arbiter virtual ledger for ESCROW balance management."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fp.core.base import EntityUid

if TYPE_CHECKING:
    from .models import LedgerSnapshot


class InsufficientBalance(Exception):
    def __init__(self, entity_uid: EntityUid, required: float, available: float) -> None:
        super().__init__(
            f"{entity_uid}: need {required}, have {available}"
        )


class Ledger:
    """In-memory virtual balance ledger managed by Arbiter."""

    def __init__(self) -> None:
        self._balances: dict[EntityUid, float] = {}
        self._frozen: dict[EntityUid, float] = {}

    def to_snapshot(self) -> LedgerSnapshot:
        from .models import LedgerSnapshot
        return LedgerSnapshot(
            balances=dict(self._balances),
            frozen=dict(self._frozen),
        )

    @classmethod
    def from_snapshot(cls, snapshot: LedgerSnapshot) -> Ledger:
        ledger = cls()
        ledger._balances = dict(snapshot.balances)
        ledger._frozen = dict(snapshot.frozen)
        return ledger

    def balance(self, entity_uid: EntityUid) -> float:
        return self._balances.get(entity_uid, 0.0)

    def available(self, entity_uid: EntityUid) -> float:
        return self.balance(entity_uid) - self._frozen.get(entity_uid, 0.0)

    def deposit(self, entity_uid: EntityUid, amount: float) -> None:
        """Credit an entity's account."""
        self._balances[entity_uid] = self.balance(entity_uid) + amount

    def _check_available(self, entity_uid: EntityUid, amount: float) -> None:
        avail = self.available(entity_uid)
        if avail < amount:
            raise InsufficientBalance(entity_uid, amount, avail)

    def freeze(self, entity_uid: EntityUid, amount: float) -> None:
        """Reserve funds for an ESCROW contract."""
        self._check_available(entity_uid, amount)
        self._frozen[entity_uid] = self._frozen.get(entity_uid, 0.0) + amount

    def unfreeze(self, entity_uid: EntityUid, amount: float) -> None:
        """Release frozen funds (contract cancelled)."""
        self._frozen[entity_uid] = max(0.0, self._frozen.get(entity_uid, 0.0) - amount)

    def transfer(self, from_uid: EntityUid, to_uid: EntityUid, amount: float) -> None:
        """Transfer from one entity to another. Unfreezes if frozen."""
        self._check_available(from_uid, amount)
        self._balances[from_uid] = self.balance(from_uid) - amount
        self._balances[to_uid] = self.balance(to_uid) + amount
        frozen = self._frozen.get(from_uid, 0.0)
        if frozen > 0:
            self._frozen[from_uid] = max(0.0, frozen - amount)

    def escrow_transfer(self, from_uid: EntityUid, to_uid: EntityUid, amount: float) -> None:
        """Transfer frozen ESCROW funds. Deducts from frozen first."""
        frozen = self._frozen.get(from_uid, 0.0)
        if frozen < amount:
            raise InsufficientBalance(from_uid, amount, frozen)
        self._frozen[from_uid] = frozen - amount
        self._balances[from_uid] = self.balance(from_uid) - amount
        self._balances[to_uid] = self.balance(to_uid) + amount
