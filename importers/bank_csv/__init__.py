from pathlib import Path

from importers.common import IncomeDraft

from . import cathay, generic


SUPPORTED_BANKS = ("cathay", "esun", "twb", "wise", "generic")


def parse(path: str | Path, bank: str, **kwargs) -> list[IncomeDraft]:
    bank_key = str(bank).strip().lower()

    if bank_key == "cathay":
        return cathay.parse(path)
    if bank_key in {"esun", "twb", "wise", "generic"}:
        return generic.parse(path, **kwargs)

    supported = ", ".join(SUPPORTED_BANKS)
    raise ValueError(f"不支援的銀行代碼: {bank}. 支援: {supported}")
