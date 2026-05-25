"""Mailbox for entity - local message storage and management."""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from .mail import Mail

if TYPE_CHECKING:
    from .core import MailStatus


class Mailbox:
    """Local mailbox for storing and managing entity messages."""

    def __init__(self, entity_uid: str, mailbox_path: Path):
        self.entity_uid = entity_uid
        self.mailbox_path = mailbox_path
        self.mailbox_path.parent.mkdir(parents=True, exist_ok=True)

    def _iter_entries(self) -> Iterator[dict[str, Any]]:
        """Iterate over all JSONL entries in the mailbox file."""
        if not self.mailbox_path.exists():
            return
        with open(self.mailbox_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    yield json.loads(line.strip())
                except json.JSONDecodeError:
                    continue

    def _rewrite_entries(self, match_fn: Callable[[dict], bool], **updates: Any) -> bool:
        """Rewrite mailbox file, applying updates to entries that match."""
        if not self.mailbox_path.exists():
            return False

        temp_path = self.mailbox_path.with_suffix(".tmp")
        updated = False

        with open(self.mailbox_path, "r", encoding="utf-8") as f_in:
            with open(temp_path, "w", encoding="utf-8") as f_out:
                for line in f_in:
                    try:
                        entry = json.loads(line.strip())
                        if match_fn(entry):
                            entry["metadata"].update(updates)
                            updated = True
                        f_out.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    except json.JSONDecodeError:
                        f_out.write(line)

        if updated:
            temp_path.replace(self.mailbox_path)
        else:
            temp_path.unlink()

        return updated

    def _mail_exists(self, mail_id: str, direction: str) -> bool:
        """Check if mail_id already exists in mailbox for the given direction."""
        return any(
            e.get("mail", {}).get("mail_id") == mail_id
            and e.get("metadata", {}).get("direction") == direction
            for e in self._iter_entries()
        )

    def _append_mail(self, mail: Mail, direction: str) -> None:
        """Append mail to JSONL file with deduplication."""
        from .core import MailStatus

        mail_id = mail.mail_id if hasattr(mail, 'mail_id') else None
        if mail_id and self._mail_exists(mail_id, direction):
            logger.warning(f"[Mailbox {self.entity_uid}] 跳过重复邮件 mail_id={mail_id}")
            return

        mail_entry = {
            "mail": mail.to_dict(),
            "metadata": {
                "direction": direction,
                "is_read": False,
                "is_handled": False,
                "timestamp": datetime.utcnow().isoformat(),
                "status": mail.status.value if hasattr(mail, 'status') else MailStatus.RECEIVED.value,
            }
        }

        with open(self.mailbox_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(mail_entry, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())

        logger.debug(f"[Mailbox {self.entity_uid}] {'发件箱' if direction == 'outbound' else '收件箱'} mail_id={mail_id}")

    def save_inbound(self, mail: Mail) -> None:
        """Save received mail."""
        self._append_mail(mail, "inbound")

    def save_outbound(self, mail: Mail) -> None:
        """Save sent mail."""
        self._append_mail(mail, "outbound")

    def list_mails(
        self,
        is_read: bool | None = None,
        is_handled: bool | None = None,
        direction: str | None = None,
    ) -> list[dict[str, Any]]:
        """List mails with optional filters."""
        mails = []
        for entry in self._iter_entries():
            metadata = entry.get("metadata", {})
            if is_read is not None and metadata.get("is_read") != is_read:
                continue
            if is_handled is not None and metadata.get("is_handled") != is_handled:
                continue
            if direction is not None and metadata.get("direction") != direction:
                continue
            mails.append(entry)
        return mails

    def get_mail(self, mail_id: str) -> dict[str, Any] | None:
        """Get single mail by message_id."""
        for entry in self._iter_entries():
            message = entry.get("mail", {}).get("message", {})
            if isinstance(message, dict) and message.get("message_id") == mail_id:
                return entry
        return None

    def _update_mail_status(self, mail_id: str, **updates: Any) -> bool:
        """Update mail metadata by message_id."""
        def match(entry: dict) -> bool:
            message = entry.get("mail", {}).get("message", {})
            return isinstance(message, dict) and message.get("message_id") == mail_id
        return self._rewrite_entries(match, **updates)

    def _update_mail_status_by_mail_id(self, mail_id_value: str, **updates: Any) -> bool:
        """Update mail metadata by mail_id (envelope ID)."""
        def match(entry: dict) -> bool:
            return entry.get("mail", {}).get("mail_id") == mail_id_value
        return self._rewrite_entries(match, **updates)

    def mark_mail_status(self, mail_id: str, status: MailStatus) -> bool:
        """Update mail status by message_id."""
        return self._update_mail_status(mail_id, status=status.value)

    def mark_mail_status_by_mail_id(self, mail_id_value: str, status: MailStatus) -> bool:
        """Update mail status by mail_id (envelope ID)."""
        return self._update_mail_status_by_mail_id(mail_id_value, status=status.value)

    def mark_as_read(self, mail_id: str) -> bool:
        """Mark mail as read by message_id."""
        from .core import MailStatus
        return self._update_mail_status(mail_id, is_read=True, status=MailStatus.PROCESSING.value)

    def mark_as_handled(self, mail_id: str) -> bool:
        """Mark mail as handled by message_id."""
        from .core import MailStatus
        return self._update_mail_status(mail_id, is_handled=True, status=MailStatus.DONE.value)

    def mark_as_handled_by_mail_id(self, mail_id_value: str) -> bool:
        """Mark mail as handled by mail_id (envelope ID)."""
        from .core import MailStatus
        return self._update_mail_status_by_mail_id(mail_id_value, is_handled=True, status=MailStatus.DONE.value)
