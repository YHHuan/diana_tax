import csv
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path


ENCODINGS = ("utf-8-sig", "utf-8", "cp950", "big5", "big5hkscs")


def load_csv_rows(path: str | Path) -> tuple[list[str], list[dict[str, str]]]:
    csv_path = Path(path)
    last_error: UnicodeDecodeError | None = None

    for encoding in ENCODINGS:
        try:
            with csv_path.open("r", encoding=encoding, newline="") as handle:
                reader = csv.DictReader(handle)
                fieldnames = list(reader.fieldnames or [])
                if not fieldnames:
                    return [], []
                rows = [normalize_row(row, fieldnames) for row in reader]
                return fieldnames, rows
        except UnicodeDecodeError as exc:
            last_error = exc

    if last_error is not None:
        raise last_error

    return [], []


def normalize_row(row: dict[str | None, str | None], fieldnames: list[str]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for fieldname in fieldnames:
        value = row.get(fieldname, "")
        normalized[fieldname] = str(value or "").strip()
    return normalized


def normalize_header(value: str) -> str:
    return "".join(str(value or "").strip().lower().split())


def detect_column(fieldnames: list[str], aliases: tuple[str, ...]) -> str | None:
    alias_map = {normalize_header(name): name for name in fieldnames}
    for alias in aliases:
        match = alias_map.get(normalize_header(alias))
        if match:
            return match
    return None


def pick_column(
    fieldnames: list[str],
    aliases: tuple[str, ...],
    explicit_name: str | None = None,
) -> str | None:
    if explicit_name:
        for fieldname in fieldnames:
            if fieldname == explicit_name:
                return fieldname
        raise ValueError(f"CSV 欄位不存在: {explicit_name}")
    return detect_column(fieldnames, aliases)


def parse_decimal(value: str | None) -> Decimal | None:
    raw = str(value or "").strip()
    if not raw:
        return None

    negative = False
    if raw.startswith("(") and raw.endswith(")"):
        negative = True
        raw = raw[1:-1]

    cleaned = (
        raw.replace(",", "")
        .replace("NT$", "")
        .replace("NTD", "")
        .replace("$", "")
        .replace("+", "")
        .strip()
    )
    if not cleaned:
        return None

    try:
        amount = Decimal(cleaned)
    except InvalidOperation:
        return None

    return -amount if negative else amount


def parse_date(value: str | None) -> date:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("缺少日期")

    candidates = (
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y.%m.%d",
        "%Y%m%d",
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M",
    )
    for fmt in candidates:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass

    if "/" in raw:
        parts = raw.split("/")
        if len(parts) == 3 and parts[0].isdigit():
            year = int(parts[0])
            if year < 1911:
                roc_date = f"{year + 1911}/{parts[1]}/{parts[2]}"
                return datetime.strptime(roc_date, "%Y/%m/%d").date()

    raise ValueError(f"無法解析日期: {raw}")


def compact_join(*values: str | None) -> str:
    parts: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        parts.append(text)
        seen.add(text)
    return " | ".join(parts)

