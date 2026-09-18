"""
Отправка письма через классический Microsoft Outlook.

Открывает окно нового письма с заполненными темой, текстом
и прикреплёнными файлами. Получателя пользователь выбирает
в самом Outlook из адресной книги.
"""
from __future__ import annotations

import os


def send_via_outlook(subject: str, body: str,
                     attachments: list = None) -> tuple:
    """
    Возвращает (успех: bool, сообщение_об_ошибке: str).
    """
    attachments = attachments or []

    try:
        import win32com.client  # noqa
    except Exception:
        return False, (
            "Модуль pywin32 не установлен.\n\n"
            "Установи его командой:\n"
            "    pip install pywin32"
        )

    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
    except Exception as e:
        return False, (
            "Не удалось подключиться к Outlook.\n\n"
            "Возможные причины:\n"
            "  • Классический Outlook не установлен (нужен именно\n"
            "    из пакета Microsoft Office, а не «Почта Windows»).\n"
            "  • Outlook запущен в первый раз и не завершил настройку.\n"
            "  • Outlook повреждён (Помощь → Восстановление).\n\n"
            f"Техническое сообщение: {e}"
        )

    try:
        mail = outlook.CreateItem(0)   # 0 = MailItem
        mail.Subject = subject
        mail.Body = body

        attached = 0
        for path in attachments:
            if not path:
                continue
            if not os.path.exists(path):
                continue
            try:
                mail.Attachments.Add(os.path.abspath(path))
                attached += 1
            except Exception:
                pass

        mail.Display()
        return True, ""

    except Exception as e:
        return False, f"Ошибка при создании письма в Outlook: {e}"