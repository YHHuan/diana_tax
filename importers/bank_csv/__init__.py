from pathlib import Path

from importers.common import IncomeDraft

from . import cathay, esun, generic, twb, wise


SUPPORTED_BANKS = ("cathay", "esun", "richart", "twb", "wise", "generic")


def parse(path: str | Path, bank: str, **kwargs) -> list[IncomeDraft]:
    bank_key = str(bank).strip().lower()

    if bank_key == "cathay":
        return cathay.parse(path)
    if bank_key in {"esun", "richart"}:
        return esun.parse(path)
    if bank_key == "twb":
        return twb.parse(path)
    if bank_key == "wise":
        return wise.parse(path)
    if bank_key == "generic":
        return generic.parse(path, **kwargs)

    supported = ", ".join(SUPPORTED_BANKS)
    raise ValueError(f"不支援的銀行代碼: {bank}. 支援: {supported}")
