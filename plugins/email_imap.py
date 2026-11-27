"""Email: unread mail from every connected mailbox (IMAP, read-only — nothing is
marked as read). Mailboxes are added in the app (Connections tab); passwords
live in Windows Credential Manager.
"""

import email
import email.header
import imaplib
import re
from concurrent.futures import ThreadPoolExecutor

import connections
from core import Ctx, skill

IMAP_HOSTS = {"gmail.com": "imap.gmail.com", "googlemail.com": "imap.gmail.com", "yandex.ru": "imap.yandex.ru",
              "ya.ru": "imap.yandex.ru", "mail.ru": "imap.mail.ru", "bk.ru": "imap.mail.ru", "inbox.ru": "imap.mail.ru",
              "list.ru": "imap.mail.ru", "outlook.com": "outlook.office365.com", "hotmail.com": "outlook.office365.com",
              "live.com": "outlook.office365.com", "icloud.com": "imap.mail.me.com", "yahoo.com": "imap.mail.yahoo.com"}


MX_PROVIDERS = [("google.com", "imap.gmail.com"), ("googlemail.com", "imap.gmail.com"),
                ("outlook.com", "outlook.office365.com"), ("yandex", "imap.yandex.ru"), ("mail.ru", "imap.mail.ru")]


def _mx(domain: str) -> str:
    """Mail servers of a domain (company / university addresses on Google Workspace, Microsoft 365…)."""
    import subprocess
    try:
        return subprocess.run(["nslookup", "-type=mx", domain], capture_output=True, text=True, timeout=6,
                              creationflags=subprocess.CREATE_NO_WINDOW).stdout.lower()
    except Exception:  # noqa: BLE001
        return ""


def guess_host(address: str) -> str:
    domain = address.split("@")[-1].lower()
    if domain in IMAP_HOSTS:
        return IMAP_HOSTS[domain]
    mx = _mx(domain)
    for marker, host in MX_PROVIDERS:
        if marker in mx:
            return host
    return "imap." + domain


def _decode(value: str) -> str:
    out = []
    for chunk, enc in email.header.decode_header(value or ""):
        try:
            out.append(chunk.decode(enc or "utf-8", errors="replace") if isinstance(chunk, bytes) else chunk)
        except LookupError:
            out.append(chunk.decode("utf-8", errors="replace"))
    return re.sub(r"\s+", " ", "".join(out)).strip()


def _sender(raw: str) -> str:
    name = _decode(raw)
    m = re.match(r'^"?([^"<]+?)"?\s*<', name)
    return m.group(1).strip() if m else name


def check_box(acc: dict, limit: int = 5) -> dict:
    """Return {"account", "unread", "items": [{"from", "subject"}], "error"}."""
    res = {"account": acc.get("name") or acc["address"], "address": acc["address"], "unread": 0, "items": [], "error": ""}
    pwd = connections.get_secret(f"email:{acc['address']}")
    if not pwd:
        res["error"] = "нет пароля"
        return res
    try:
        with imaplib.IMAP4_SSL(acc.get("imap_host") or guess_host(acc["address"]), timeout=15) as box:
            box.login(acc["address"], pwd)
            box.select("INBOX", readonly=True)
            _, data = box.search(None, "UNSEEN")
            ids = data[0].split()
            res["unread"] = len(ids)
            for mid in reversed(ids[-limit:]):
                _, msg = box.fetch(mid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT)])")
                hdr = email.message_from_bytes(msg[0][1])
                res["items"].append({"from": _sender(hdr.get("From", "")), "subject": _decode(hdr.get("Subject", ""))})
    except Exception as e:  # noqa: BLE001
        res["error"] = str(e)[:120]
    return res


def check_all(limit: int = 5) -> list[dict]:
    accounts = connections.load()["email"]
    if not accounts:
        return []
    with ThreadPoolExecutor(max_workers=len(accounts)) as ex:
        return list(ex.map(lambda a: check_box(a, limit), accounts))


def summary(lang: str, detailed: bool = True) -> str:
    boxes = check_all()
    if not boxes:
        return ""
    total = sum(b["unread"] for b in boxes)
    errors = [b for b in boxes if b["error"]]
    if total == 0:
        s = "Новых писем нет." if lang == "ru" else "Yangi xatlar yo'q."
    else:
        s = (f"Непрочитанных писем: {total}." if lang == "ru" else f"O'qilmagan xatlar: {total} ta.")
        if detailed:
            items = [f"{i['from']}: {i['subject'] or ('без темы' if lang == 'ru' else 'mavzusiz')}"
                     for b in boxes for i in b["items"]][:5]
            s += (" Последние: " if lang == "ru" else " Oxirgilari: ") + ". ".join(items) + "."
    if errors:
        s += (" Не удалось проверить: " if lang == "ru" else " Tekshirib bo'lmadi: ") + ", ".join(b["account"] for b in errors) + "."
    return s


@skill(
    "email.unread",
    title={"ru": "Прочитать новые письма (все ящики)", "uz": "Yangi xatlarni o'qish (barcha pochtalar)"},
    patterns={
        "ru": [r"(почт|письм|имейл|емейл|мейл|email|ящик)\w*.*(прочитай|сколько|проверь|есть|новые|новых|покажи|что|какие|непрочитан)",
               r"(прочитай|сколько|проверь|есть|новые|новых|покажи|что|какие|непрочитан)\w*.*(почт|письм|имейл|емейл|мейл|email|ящик)"],
        "uz": [r"(pochta|xat|email|imeyl|meyl)\w*.*(oqi|nechta|tekshir|bormi|yangi|korsat|qancha)",
               r"(yangi|nechta) (xat|email|imeyl)"],
    },
    examples={"ru": ["Прочитай почту", "Есть новые письма?"], "uz": ["Pochtani o'qi", "Yangi xatlar bormi?"]},
    priority=45,
)
def unread(ctx: Ctx) -> str:
    s = summary(ctx.lang)
    return s or ctx.t("Почта не подключена. Добавьте ящик в окне Джарвиса, вкладка «Подключения».",
                      "Pochta ulanmagan. Jarvis oynasidagi «Подключения» bo'limida pochtani qo'shing.")
