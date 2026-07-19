
import logging
import ssl
from email.message import EmailMessage

import aiosmtplib

try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _SSL_CTX = ssl.create_default_context()

from ..config import settings

log = logging.getLogger("mailer")


STATUS_PHRASE = {
    "purchased":       "завершена покупка на аукционе.",
    "invoice_jp":      "выставлен счёт японской стороны.",
    "to_port":         "начата доставка в порт отправления.",
    "ship_assigned":   "назначено судно для морской перевозки.",
    "customs_invoice": "выставлен счёт за таможенную очистку.",
    "released":        "завершена таможенная очистка — автомобиль готов к выдаче.",
}


async def send_email(to: str, subject: str, html: str) -> bool:
    if not settings.smtp_host:
        log.warning("SMTP не настроен — письмо не отправлено (to=%s)", to)
        return False
    msg = EmailMessage()
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content("Письмо в формате HTML.")
    msg.add_alternative(html, subtype="html")
    kwargs = {"hostname": settings.smtp_host, "port": settings.smtp_port,
              "username": settings.smtp_user or None,
              "password": settings.smtp_password or None,
              "tls_context": _SSL_CTX}
    if settings.smtp_port == 465:
        kwargs["use_tls"] = True
    elif settings.smtp_port == 587:
        kwargs["start_tls"] = True
    try:
        await aiosmtplib.send(msg, **kwargs)
        log.info("Письмо отправлено: %s", to)
        return True
    except Exception as e:
        log.error("Ошибка отправки письма %s: %s", to, e)
        return False


def _status_html(full_name: str, car_label: str, status_label: str, phrase: str) -> str:
    lk_url = (settings.public_url or "https://lk.avto-hub.online").rstrip("/")
    return f"""<div style="font-family:Arial,sans-serif;max-width:520px;margin:auto">
      <div style="background:#c63e45;color:#fff;padding:18px 22px;border-radius:10px 10px 0 0;font-size:20px;font-weight:bold;font-style:italic">AVTO-hub</div>
      <div style="border:1px solid #e6e6e6;border-top:0;padding:24px 22px;border-radius:0 0 10px 10px">
        <p>Здравствуйте, {full_name or 'клиент'}!</p>
        <p>По вашему автомобилю <b>{car_label}</b> {phrase}</p>
        <p style="background:#f6f1ec;border-left:3px solid #c63e45;padding:10px 14px">Новый статус: <b>{status_label}</b></p>
        <p>Подробности — в <a href="{lk_url}" style="color:#c63e45;font-weight:bold">личном кабинете</a>.</p>
        <p style="color:#888;font-size:12px;margin-top:20px">Автоматическое уведомление, отвечать не нужно.</p>
      </div></div>"""


async def send_status_email(to_email: str, full_name: str, car_label: str,
                            status_value: str, status_label: str) -> bool:
    """Письмо клиенту при смене статуса авто. Вызывается из админ-роутера."""
    phrase = STATUS_PHRASE.get(status_value, "статус обновлён.")
    subject = f"AVTO-hub: {status_label} — {car_label}"
    html = _status_html(full_name, car_label, status_label, phrase)
    return await send_email(to_email, subject, html)


def _reset_html(full_name: str, link: str) -> str:
    return f"""<div style="font-family:Arial,sans-serif;max-width:520px;margin:auto">
      <div style="background:#c63e45;color:#fff;padding:18px 22px;border-radius:10px 10px 0 0;font-size:20px;font-weight:bold;font-style:italic">AVTO-hub</div>
      <div style="border:1px solid #e6e6e6;border-top:0;padding:24px 22px;border-radius:0 0 10px 10px">
        <p>Здравствуйте, {full_name or 'клиент'}!</p>
        <p>Вы запросили восстановление пароля в личном кабинете AVTO-hub. Чтобы задать новый пароль, нажмите на кнопку:</p>
        <p style="text-align:center;margin:24px 0"><a href="{link}" style="background:#c63e45;color:#fff;text-decoration:none;padding:12px 28px;border-radius:8px;font-weight:bold">Задать новый пароль</a></p>
        <p style="color:#666;font-size:13px">Ссылка действует 1 час. Если вы не запрашивали восстановление пароля — просто проигнорируйте это письмо, ваш пароль останется прежним.</p>
        <p style="color:#888;font-size:12px;margin-top:20px">Автоматическое уведомление, отвечать не нужно.</p>
      </div></div>"""


async def send_password_reset_email(to_email: str, full_name: str, link: str) -> bool:
    """Письмо со ссылкой для сброса пароля."""
    return await send_email(to_email, "AVTO-hub: восстановление пароля",
                            _reset_html(full_name, link))
