"""Extract translatable strings and compile a .mo file, without GNU gettext.

``makemessages``/``compilemessages`` need xgettext and msgfmt, which are not
installed on this machine. This script does the two jobs we actually need:

  extract  -- scan .py and .html for gettext calls and {% translate %} tags
  compile  -- write locale/<lang>/LC_MESSAGES/django.mo from the matching .po

The MO format is simple and documented, and Python's stdlib ``gettext`` reads
what we write here, so Arabic works with no external toolchain. Swap in real
gettext later and this script becomes unnecessary.

Usage:
    python tools/i18n.py extract
    python tools/i18n.py compile ar
"""

import re
import struct
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SCAN_ROOTS = [
    "accounts",
    "workouts",
    "nutrition",
    "progress",
    "subscriptions",
    "templates",
]

# gettext_lazy("..."), gettext("..."), _("...") with double quotes.
# The trailing group captures adjacent string literals, because Python joins
# implicitly concatenated literals and xgettext treats them as one msgid:
#     _("first part "
#       "second part")
PY_PATTERN = re.compile(
    r'(?:gettext_lazy|gettext|_)\(\s*'
    r'("(?:[^"\\]|\\.)*"(?:\s*"(?:[^"\\]|\\.)*")*)'
)
# {% translate "..." %} and {% trans "..." %}
TPL_PATTERN = re.compile(r'\{%\s*(?:translate|trans)\s+"((?:[^"\\]|\\.)*)"')
# {% blocktranslate %}body{% plural %}plural body{% endblocktranslate %}
# Captured separately so plural entries become msgid/msgid_plural pairs.
BLOCK_PATTERN = re.compile(
    r"\{%\s*blocktranslate[^%]*%\}(.*?)\{%\s*endblocktranslate\s*%\}",
    re.DOTALL,
)
PLURAL_SPLIT = re.compile(r"\{%\s*plural\s*%\}")
# Individual literals inside a concatenated run.
LITERAL_PATTERN = re.compile(r'"((?:[^"\\]|\\.)*)"')

#: Arabic has six plural categories; this is the standard CLDR/gettext rule.
PLURAL_FORMS = {
    "ar": (
        "nplurals=6; plural=(n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : "
        "n%100>=3 && n%100<=10 ? 3 : n%100>=11 ? 4 : 5);"
    ),
    "en": "nplurals=2; plural=(n != 1);",
}


def iter_source_files():
    for root in SCAN_ROOTS:
        root_path = BASE_DIR / root
        if not root_path.exists():
            continue
        for path in root_path.rglob("*"):
            if path.suffix not in {".py", ".html"}:
                continue
            if "migrations" in path.parts or "__pycache__" in path.parts:
                continue
            yield path


def extract():
    """Return {msgid: {"sources": [...], "plural": msgid_plural or None}}."""
    found = {}

    def record(msgid, plural, source):
        if not msgid or msgid.startswith("{{"):
            return
        entry = found.setdefault(msgid, {"sources": set(), "plural": None})
        entry["sources"].add(source)
        if plural:
            entry["plural"] = plural

    for path in iter_source_files():
        text = path.read_text(encoding="utf-8")
        source = str(path.relative_to(BASE_DIR)).replace("\\", "/")

        if path.suffix == ".py":
            for match in PY_PATTERN.findall(text):
                # Join implicitly concatenated literals into one msgid.
                record("".join(LITERAL_PATTERN.findall(match)), None, source)
        else:
            for match in TPL_PATTERN.findall(text):
                record(match, None, source)
            for body in BLOCK_PATTERN.findall(text):
                parts = PLURAL_SPLIT.split(body)
                singular = parts[0].strip()
                plural = parts[1].strip() if len(parts) > 1 else None
                record(singular, plural, source)

    return {
        key: {"sources": sorted(value["sources"]), "plural": value["plural"]}
        for key, value in sorted(found.items())
    }


def escape_po(value):
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )


def write_pot(strings, destination):
    lines = [
        'msgid ""',
        'msgstr ""',
        '"Content-Type: text/plain; charset=UTF-8\\n"',
        '"Content-Transfer-Encoding: 8bit\\n"',
        "",
    ]
    for msgid, meta in strings.items():
        for source in meta["sources"]:
            lines.append(f"#: {source}")
        lines.append(f'msgid "{escape_po(msgid)}"')
        if meta["plural"]:
            lines.append(f'msgid_plural "{escape_po(meta["plural"])}"')
            lines.append('msgstr[0] ""')
            lines.append('msgstr[1] ""')
        else:
            lines.append('msgstr ""')
        lines.append("")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(lines), encoding="utf-8")
    return len(strings)


def unescape_po(value):
    out = []
    index = 0
    while index < len(value):
        char = value[index]
        if char == "\\" and index + 1 < len(value):
            nxt = value[index + 1]
            out.append({"n": "\n", "t": "\t", '"': '"', "\\": "\\"}.get(nxt, nxt))
            index += 2
        else:
            out.append(char)
            index += 1
    return "".join(out)


def parse_po(path):
    """Minimal .po reader.

    Returns {msgid: msgstr} for singular entries and
    {msgid: {"plural": msgid_plural, "forms": [...]}} for plural ones. Handles
    continuation lines and msgstr[N] indices.
    """
    entries = {}
    state = {"msgid": None, "plural_id": None, "msgstr": "", "plurals": {}}
    target = None

    def flush():
        msgid = state["msgid"]
        if msgid is None:
            return
        if state["plural_id"] is not None and state["plurals"]:
            forms = [state["plurals"][key] for key in sorted(state["plurals"])]
            if any(forms):
                entries[msgid] = {"plural": state["plural_id"], "forms": forms}
        elif state["msgstr"]:
            entries[msgid] = state["msgstr"]

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("msgid_plural "):
            state["plural_id"] = unescape_po(
                line[len("msgid_plural ") :].strip().strip('"')
            )
            target = "plural_id"
        elif line.startswith("msgid "):
            flush()
            state = {
                "msgid": unescape_po(line[len("msgid ") :].strip().strip('"')),
                "plural_id": None,
                "msgstr": "",
                "plurals": {},
            }
            target = "id"
        elif line.startswith("msgstr["):
            index = int(line[line.index("[") + 1 : line.index("]")])
            rest = line[line.index("]") + 1 :].strip().strip('"')
            state["plurals"][index] = unescape_po(rest)
            target = ("plural", index)
        elif line.startswith("msgstr "):
            state["msgstr"] = unescape_po(line[len("msgstr ") :].strip().strip('"'))
            target = "str"
        elif line.startswith('"'):
            chunk = unescape_po(line.strip().strip('"'))
            if target == "id":
                state["msgid"] += chunk
            elif target == "plural_id":
                state["plural_id"] += chunk
            elif target == "str":
                state["msgstr"] += chunk
            elif isinstance(target, tuple):
                state["plurals"][target[1]] += chunk

    flush()
    return entries


def write_mo(entries, destination, language="ar"):
    """Write a binary .mo file.

    Layout: magic, revision, count, offset of key table, offset of value table,
    hash table size/offset (zero -- gettext falls back to binary search), then
    the length/offset pairs and the NUL-terminated strings themselves.

    Plurals are stored the way gettext expects: the key is
    "singular\\x00plural" and the value is all translated forms joined by NUL.
    The empty msgid carries the metadata header, which must include
    Plural-Forms or Django cannot pick the right form.
    """
    header = (
        "Content-Type: text/plain; charset=UTF-8\n"
        "Content-Transfer-Encoding: 8bit\n"
        f"Language: {language}\n"
        f"Plural-Forms: {PLURAL_FORMS.get(language, PLURAL_FORMS['en'])}\n"
    )

    pairs = {"": header}
    for msgid, value in entries.items():
        if msgid == "":
            # Ignore any header in the .po; we write a known-good one above.
            continue
        if isinstance(value, dict):
            # Plural entry: key is "singular\0plural", value is NUL-joined forms.
            pairs[f"{msgid}\x00{value['plural']}"] = "\x00".join(value["forms"])
        else:
            pairs[msgid] = value

    items = sorted(pairs.items(), key=lambda item: item[0].encode("utf-8"))
    keys = [key.encode("utf-8") for key, _ in items]
    values = [value.encode("utf-8") for _, value in items]

    count = len(items)
    key_table_offset = 7 * 4
    value_table_offset = key_table_offset + count * 8
    strings_offset = value_table_offset + count * 8

    key_descriptors = []
    offset = strings_offset
    for key in keys:
        key_descriptors.append((len(key), offset))
        offset += len(key) + 1

    value_descriptors = []
    for value in values:
        value_descriptors.append((len(value), offset))
        offset += len(value) + 1

    output = bytearray()
    output += struct.pack(
        "<7I",
        0x950412DE,  # little-endian magic
        0,  # revision
        count,
        key_table_offset,
        value_table_offset,
        0,  # hash table size
        0,  # hash table offset
    )
    for length, position in key_descriptors:
        output += struct.pack("<II", length, position)
    for length, position in value_descriptors:
        output += struct.pack("<II", length, position)
    for key in keys:
        output += key + b"\x00"
    for value in values:
        output += value + b"\x00"

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(bytes(output))
    return count


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else "extract"

    if command == "extract":
        strings = extract()
        pot = BASE_DIR / "locale" / "django.pot"
        total = write_pot(strings, pot)
        print(f"extracted {total} strings -> {pot}")
        return

    if command == "compile":
        languages = sys.argv[2:] or ["ar"]
        for language in languages:
            po = BASE_DIR / "locale" / language / "LC_MESSAGES" / "django.po"
            if not po.exists():
                print(f"skip {language}: {po} not found")
                continue
            entries = parse_po(po)
            mo = po.with_suffix(".mo")
            count = write_mo(entries, mo, language=language)
            print(f"compiled {count} translations -> {mo}")
        return

    if command == "check":
        # Report msgids present in source but missing from a catalogue.
        language = sys.argv[2] if len(sys.argv) > 2 else "ar"
        strings = extract()
        po = BASE_DIR / "locale" / language / "LC_MESSAGES" / "django.po"
        translated = parse_po(po) if po.exists() else {}
        missing = [key for key in strings if key not in translated]
        print(f"{len(strings) - len(missing)}/{len(strings)} translated for {language}")
        for key in missing:
            print(f"  MISSING: {key}")
        return

    raise SystemExit(f"unknown command: {command}")


if __name__ == "__main__":
    main()
