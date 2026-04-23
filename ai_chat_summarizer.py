from typing import Literal, Optional, Callable
import datetime
import requests
import traceback
import json
import threading
import re

from base_plugin import BasePlugin, MenuItemData, MenuItemType
from ui.settings import Header, Divider, Input, EditText, Switch, Selector, Text, Custom, SimpleSettingFactory
from client_utils import run_on_queue, send_text, send_request, RequestCallback
from android_utils import run_on_ui_thread
from pydantic import BaseModel, Field
from pydantic import validator as field_validator
import emoji as emojilib

__id__ = "ai_chat_summarizer"
__name__ = "AI Chat Summarizer & Fact Checker"
__author__ = "@edward_vishnevsky"
__version__ = "0.6.0"
__description__ = "qweqweqweqweqweqweqweqweqwe qweqweqweqweqweqweqweqweqwe"
__requirements__ = ['pydantic==1.10.15', 'emoji']


'''
TODO: 
- AI API
    - Подключение к API по ключу
    - Парсинг моделей с API
    - Сортировка списка моделей по алфавиту после парсинга
    - Сохранение выбранной модели
- Request
    - Выбор сообщений, где есть текст. Где текста нет - сбрасывать
    - Получение промптов с облака
    - Настройка детализации с помощью промпта
- Character
    - Получение JSON с персонажами с GitHub
    - Парсинг полученного JSON и валидация всех строк
    - Запись в отдельный класс
'''

'''
LOGGING LEVELS
    DEBUG:    0
    INFO:     1
    WARNING:  2
    ERROR:    3
    DISABLED: -1
'''
LOG_LEVEL = 0
BLOCK_HEIGHT_DP = 300
LOGS_ENABLED = True
DEFAULT_SYSTEM_PROMPTS_LINK = ""
DEFAULT_REQ_MAX_MSG = 300
DEFAULT_CHARACTERS_URL = "https://raw.githubusercontent.com/v1ed/AI-summarize-exteragram-plugin/main/characters.json"
SUMMARY_FACTCHECK_PROMPT = """
Ты — профессиональный аналитик текстовой переписки Telegram.

ЗАДАЧА:
Проанализировать транскрипт чата и выдать структурированный результат с кратким содержанием, ключевыми тезисами и проверкой фактов.

ОГРАНИЧЕНИЯ:
- Анализируй ТОЛЬКО текст сообщений.
- Полностью игнорируй системные сообщения и любые упоминания вложений (файлы, фото, стикеры и т.д.).
- НЕ додумывай факты, которых нет в тексте.
- НЕ используй внешние знания при проверке фактов — опирайся только на содержимое переписки.
- Если данных недостаточно — явно укажи это.
- Учитывай контекст (личный чат, группа, канал).
- Обязательно отслеживай авторов сообщений и связи "кто → кому → что".

ФОРМАТ ОТВЕТА (строго соблюдай):

*Краткое содержание*
Кратко опиши:
- основную тему
- развитие диалога
- итог (если есть)

*Ключевые тезисы*
- Указывай ключевые мысли, решения и аргументы
- Для каждого пункта указывай автора (если их несколько)
- Формат строго через "-" (без нумерации)

*Проверка фактов*
Найди утверждения, которые подаются как факты.

Для каждого:
- Утверждение: "..."
- Статус: Подтверждено в беседе / Сомнительно / Не подтверждено / Требует внешней проверки
- Комментарий: краткое объяснение, строго на основе текста

Если фактов нет:
- Явных фактических утверждений не обнаружено

ЯЗЫК:
- Используй тот же язык, что и в переписке

ФОРМАТИРОВАНИЕ TELEGRAM:
- Используй только допустимую разметку Telegram:
  *жирный*, _курсив_, `моноширинный`
- Заголовки оформляй через *жирный текст*, НЕ используй "#"
- Списки только через "-"
"""
SUMMARY_PROMPT = """
Ты — профессиональный аналитик текстовой переписки Telegram.

ЗАДАЧА:
Сделать точную и сжатую выжимку предоставленного транскрипта чата.

ОГРАНИЧЕНИЯ:
- Анализируй только текст сообщений
- Игнорируй вложения и системные события
- Не добавляй информацию, которой нет в переписке
- Учитывай авторов и структуру диалога
- Передавай причинно-следственные связи и реакцию участников

ФОРМАТ ОТВЕТА:

*Краткое содержание*
- Основная тема
- Ход обсуждения
- Итог

*Ключевые тезисы*
- Основные идеи, аргументы и решения
- Указывай авторов
- Используй только "-" для списка

ЯЗЫК:
- Совпадает с языком переписки

ФОРМАТ TELEGRAM:
- Только допустимая разметка:
  *жирный*, _курсив_, `моноширинный`
- Заголовки через *жирный*
- Без "#", без HTML
"""
FACTCHECK_PROMPT = """
Ты — строгий и беспристрастный факт-чекер Telegram-переписки.

ЗАДАЧА:
Выделить и оценить достоверность фактических утверждений в чате.

ОГРАНИЧЕНИЯ:
- НЕ делай суммаризацию
- Анализируй только текст сообщений
- Игнорируй вложения и системные события
- НЕ используй внешние знания
- Оценивай только внутреннюю логичность и подтверждение в рамках переписки
- Не интерпретируй мнения как факты

ЧТО СЧИТАТЬ ФАКТОМ:
- Утверждения о событиях, данных, числах, причинно-следственных связях
- НЕ учитывать мнения, предположения, эмоции

ФОРМАТ ОТВЕТА:

Для каждого утверждения:
- Утверждение: "..." (автор: ...)
- Статус: Внутренне непротиворечиво / Сомнительно / Искажено / Требует проверки вне чата
- Комментарий: краткое обоснование

Если фактов нет:
- Явных фактических утверждений не обнаружено

ЯЗЫК:
- Совпадает с языком переписки

ФОРМАТ TELEGRAM:
- Используй только:
  *жирный*, _курсив_, `моноширинный`
- Заголовки через *жирный*
- Списки через "-"
"""
_DETAIL_LEVELS = [
    """
ИНСТРУКЦИЯ ПО ДЕТАЛИЗАЦИИ: [КРАТКО]

ЗАДАЧА:
Сформировать максимально сжатую выжимку без потери ключевого смысла.

ТРЕБОВАНИЯ:
- Итог: 2–4 предложения в блоке "Краткое содержание"
- 3–4 пункта в "Ключевые тезисы"
- Только основные идеи, решения и итог
- Полностью убрать детали, примеры, уточнения и повторения
- Игнорировать второстепенные реплики и ответвления диалога
- Не описывать процесс обсуждения — только результат и суть

ОГРАНИЧЕНИЯ:
- Не добавляй новую информацию
- Не интерпретируй сверх текста
- Если итог неочевиден — прямо укажи это

ФОРМАТ:
- Строго соблюдать структуру основного промпта
- Списки только через "-"
- Без нумерации

ФОРМАТ TELEGRAM:
- Только допустимая разметка:
  *жирный*, _курсив_, `моноширинный`
- Заголовки через *жирный*
""",

    """
ИНСТРУКЦИЯ ПО ДЕТАЛИЗАЦИИ: [НОРМАЛЬНО]

ЗАДАЧА:
Сделать сбалансированную выжимку с сохранением логики диалога.

ТРЕБОВАНИЯ:
- Отразить:
  - контекст общения
  - ключевые темы
  - аргументы участников
  - развитие обсуждения
  - итог (если есть)
- Сохранять причинно-следственные связи
- Указывать авторов ключевых тезисов
- Удалять шум (повторы, оффтоп, несущественные детали)

ОГРАНИЧЕНИЯ:
- Не добавляй факты вне текста
- Не делай избыточных обобщений
- Не теряй важные смысловые переходы

ФОРМАТ:
- Чёткая структура (как в основном промпте)
- Логически сгруппированные буллиты
- Списки через "-"

ФОРМАТ TELEGRAM:
- Только:
  *жирный*, _курсив_, `моноширинный`
- Заголовки через *жирный*
""",

    """
ИНСТРУКЦИЯ ПО ДЕТАЛИЗАЦИИ: [МАКСИМАЛЬНО ПОДРОБНО]

ЗАДАЧА:
Сделать полный и детализированный анализ диалога.

ТРЕБОВАНИЯ:
- Сохранить:
  - все значимые подтемы
  - аргументы и контраргументы
  - развитие дискуссии по шагам
  - позиции участников
  - изменения мнений (если есть)
  - важные уточнения и нюансы
- Передать структуру обсуждения (кто, что, в ответ на что)
- Отразить эмоциональный фон (если он влияет на смысл)

ДОПОЛНИТЕЛЬНО:
- Можно группировать тезисы по подтемам
- Можно выделять противоречия и согласия
- Можно кратко пояснять неявные связи (ТОЛЬКО если они очевидны из текста)

ОГРАНИЧЕНИЯ:
- Не добавляй внешние знания
- Не искажай формулировки
- Не превращай ответ в поток текста — сохраняй структуру

ФОРМАТ:
- Строго следовать структуре основного промпта
- Расширенные списки через "-"
- Допускается вложенная логика (но без нумерации)

ФОРМАТ TELEGRAM:
- Только:
  *жирный*, _курсив_, `моноширинный`
- Заголовки через *жирный*
"""
]

class Character(BaseModel):
    emoji: str
    name: str = Field(..., max_length=32)
    prompt: str = Field(..., max_length=1024)

    @field_validator('emoji', allow_reuse=True)
    def validate_reaction_emoji(cls, v: str) -> str:
        if not emojilib.is_emoji(v):
            raise ValueError('emoji field is incorrect!')
        return v
    # def __init__(self, emoji: str, name: str, prompt: str):
    #     self.emoji = emoji
    #     self.name = name
    #     self.prompt = prompt


class Log:
    def __init__(self):
        self.logs = []
        self.logger_func = None
        self.log_level = LOG_LEVEL
    
    def set_log_func(self, func: Callable):
        self.logger_func = func

    def set_log_level(self, level: int):
        if level not in range(0, 4):
            raise ValueError("Log level should be 0 to 3")    
        self.log_level = level

    def log(self, level: Literal["debug", "info", "warn", "error"], message: str, exc: Optional[Exception] = None):
        if self.logger_func:
            splitted_message = message.split("\n")
            for line in splitted_message:
                self.logger_func(f"[{level}]\t{line}")
        if LOGS_ENABLED:
            self.logs.append({
                'timestamp': datetime.datetime.now().isoformat(),
                'level': level,
                'message': message,
            })
    
    def debug(self, message: str):
        if self.log_level <= 0:
            self.log(level="debug", message=message)
    
    def info(self, message: str):
        if self.log_level <= 1:
            self.log(level="info", message=message)
    
    def warn(self, message: str):
        if self.log_level <= 2:
            self.log(level="warn", message=message)
    
    def error(self, message: str):
        if self.log_level <= 3:
            self.log(level="error", message=message)
    
    def clear(self):
        self.logs = []
        self.debug(f"{len(self.logs)}")
    
    def get(self):
        return self.logs
    
    def __str__(self):
        s = ''
        for log in self.logs:
            s += f"{log['timestamp']} {log['level']} {log['message']}\n"
        return s
    
    def __len__(self):
        return len(self.logs)

logger = Log()

class LLM:
    @classmethod
    def fetch_models(cls, url: str, api_type: int, api_key: str): 
        '''
        url:        str     Ссылка на API: http(s)://HOST:PORT/api
        api_type:   int     Тип API: 0 - OpenAI, 1 - Ollama
        api_key:    str     Ключ API
        '''
        if api_type not in (0, 1):
            raise ValueError("Wrong API type")
        if not url:
            raise ValueError("URL is empty!")
        fetched = []

        # parsed = urllib.parse.urlparse(api_url)
        # base_url = f"{parsed.scheme}://{parsed.netloc}"
        headers = {}
        headers["Authorization"] = f"Bearer {api_key}"
        if api_type == 0:
            r = requests.get(f"{url.rstrip('/')}/models", headers=headers, timeout=1.5)
            if r.ok:
                data = r.json()
                fetched = [str(m.get("id")) for m in data.get("data", []) if "id" in m]
        else:
            r = requests.get(f"{url.rstrip('/')}/tags", headers=headers, timeout=1.5)
            if r.ok:
                data = r.json()
                fetched = [str(m.get("name")) for m in data.get("models", []) if "name" in m]
        return fetched
    
    @classmethod
    def strip_reasoning(cls, text: str) -> str:
        if not text:
            return text

        patterns = [
            # базовые
            r"<think.*?>.*?</think>",
            r"<thought.*?>.*?</thought>",
            r"<thinking.*?>.*?</thinking>",
            r"<reasoning.*?>.*?</reasoning>",
            r"<analysis.*?>.*?</analysis>",
            r"<reflection.*?>.*?</reflection>",
            r"<scratchpad.*?>.*?</scratchpad>",
            r"<deliberation.*?>.*?</deliberation>",

            # иногда встречаются кастомные
            r"<internal.*?>.*?</internal>",
            r"<chain[-_ ]?of[-_ ]?thought.*?>.*?</chain[-_ ]?of[-_ ]?thought>",
            r"<cot.*?>.*?</cot>",
            r"<hidden.*?>.*?</hidden>",
            r"<private.*?>.*?</private>",
        ]

        cleaned = text
        for pattern in patterns:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE | re.DOTALL)

        return cleaned.strip()

    @classmethod
    def call_llm(cls, api_type, url, api_key, model, system_prompt, user_content, logger):
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        if api_type == 0:
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                "temperature": 0.2
            }
            r = requests.post(f"{url.rstrip('/')}/chat/completions", headers=headers, json=payload, timeout=120)
            if not r.ok:
                raise ValueError(f"{r.status_code} {' '.join(r.text.split())}")
            r.raise_for_status()
            data = r.json()
            logger.debug(f"{data}")
            choices = data.get("choices", [])
            if choices:
                msg = choices[0].get("message", {})
                content = msg.get("content")
                if isinstance(content, str):
                    return cls.strip_reasoning(content.strip())
            if "text" in data and isinstance(data["text"], str):
                return cls.strip_reasoning(data["text"].strip())
            raise RuntimeError("Пустой ответ от OpenAI-совместимого API")

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            "stream": False
        }
        r = requests.post(f"{url.rstrip('/')}/chat", headers=headers, json=payload, timeout=120)
        r.raise_for_status()
        data = r.json()

        if isinstance(data.get("message"), dict):
            content = data["message"].get("content")
            if isinstance(content, str):
                return cls.strip_reasoning(content.strip())
        if isinstance(data.get("response"), str):
            return cls.strip_reasoning(data["response"].strip())
        raise RuntimeError("Пустой ответ от Ollama API")


class Plugin(BasePlugin):
    # Методы UI
    # ──────────────────────────────────────────────
    # View builders
    # ──────────────────────────────────────────────

    def _build_scroll_container(self):
        """Собирает FrameLayout(ScrollView(TextView)) с фиксированной высотой."""
        from android.widget import FrameLayout, ScrollView
        from android.view import ViewGroup
        from org.telegram.messenger import AndroidUtilities, ApplicationLoader

        ctx = ApplicationLoader.applicationContext

        tv     = self._build_text_view(ctx)
        scroll = self._build_scroll_view(ctx, tv)

        self._log_text_view = tv

        container = FrameLayout(ctx)
        container.addView(
            scroll,
            ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                AndroidUtilities.dp(BLOCK_HEIGHT_DP),
            )
        )
        return container

    def _build_text_view(self, ctx):
        """Создаёт readonly TextView с заданным текстом."""
        from android.widget import TextView
        from org.telegram.messenger import AndroidUtilities

        tv = TextView(ctx)
        tv.setText(str(logger))
        tv.setTextSize(14)
        tv.setPadding(
            AndroidUtilities.dp(16),
            AndroidUtilities.dp(12),
            AndroidUtilities.dp(16),
            AndroidUtilities.dp(12),
        )
        tv.setSingleLine(False)
        tv.setMaxLines(1000)
        tv.setFocusable(False)
        tv.setFocusableInTouchMode(False)
        tv.setClickable(False)
        tv.setLongClickable(False)
        tv.setCursorVisible(False)
        return tv

    def _build_scroll_view(self, ctx, child):
        """Оборачивает child в ScrollView с правильным touch-листенером."""
        from android.widget import ScrollView
        from android.view import ViewGroup

        scroll = ScrollView(ctx)
        scroll.setFillViewport(True)
        scroll.addView(
            child,
            ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT,
            )
        )
        scroll.setOnTouchListener(self._make_touch_listener())
        return scroll

    # ──────────────────────────────────────────────
    # Touch listener (fix nested scroll conflict)
    # ──────────────────────────────────────────────

    def _make_touch_listener(self):
        """Возвращает OnTouchListener, который запрещает RecyclerView
        перехватывать события пока палец внутри ScrollView."""
        from android.view import MotionEvent, View
        from java import dynamic_proxy

        class ScrollTouchListener(dynamic_proxy(View.OnTouchListener)):
            def onTouch(self, view, event):
                action = event.getAction()
                if action == MotionEvent.ACTION_DOWN or action == MotionEvent.ACTION_MOVE:
                    view.getParent().requestDisallowInterceptTouchEvent(True)
                elif action == MotionEvent.ACTION_UP or action == MotionEvent.ACTION_CANCEL:
                    view.getParent().requestDisallowInterceptTouchEvent(False)
                return False

        return ScrollTouchListener()

    # ──────────────────────────────────────────────
    # Actions
    # ──────────────────────────────────────────────

    def _refresh_log_view(self):
        """Обновляет текст в живом TextView на UI-потоке."""
        if self._log_text_view is None:
            return
        try:
            from org.telegram.messenger import AndroidUtilities
            tv = self._log_text_view
            new_text = str(logger)
            # setText должен вызываться на главном UI-потоке
            run_on_ui_thread(lambda: tv.setText(new_text))

        except Exception as e:
            logger.error(f"refresh FAIL: {e}")

    def _on_clear_logs(self, view=None):
        logger.clear()
        self._refresh_log_view()
        logger.info("logs cleared and view updated")
    
    def _on_log_level_change(self, view=None):
        logger.set_log_level(int(self.get_setting('dev_log_lvl', LOG_LEVEL)))

    def _copy_to_clipboard(self, view):
        """Копирует DISPLAY_TEXT в системный буфер обмена."""
        try:
            from android.content import ClipData
            from org.telegram.messenger import ApplicationLoader
            from ui.bulletin import BulletinHelper

            clipboard = ApplicationLoader.applicationContext.getSystemService("clipboard")
            clipboard.setPrimaryClip(ClipData.newPlainText("plugin_text", str(logger)))
            BulletinHelper.show_info("Скопировано в буфер обмена")
            logger.debug("[ST] copied to clipboard OK")
        except Exception as e:
            logger.debug(f"[ST] clipboard FAIL: {e}")

    def _get_alert_builder(self):
        from ui.alert import AlertDialogBuilder
        return AlertDialogBuilder
    
    def _context_from_fragment(self, fragment):
        try:
            if fragment is None:
                return None
            for attr in ("getContext", "getParentActivity", "getActivity", "getParentFragment"):
                obj = getattr(fragment, attr, None)
                if callable(obj):
                    ctx = obj()
                    if ctx is not None:
                        return ctx
            return fragment
        except Exception as e:
            logger.debug(f"Ошибка получения контекста: {e}")
            return None

    def _show_spinner(self, fragment, spinner_ref, title):
        logger.debug(f"Показ спиннера: {title}")
        def _ui():
            try:
                ctx = self._context_from_fragment(fragment)
                if ctx is None:
                    return
                AlertDialogBuilder = self._get_alert_builder()
                bld = AlertDialogBuilder(ctx, AlertDialogBuilder.ALERT_TYPE_SPINNER)
                bld.set_title(title)
                bld.show()
                bld.set_cancelable(False)
                spinner_ref["dialog"] = bld
            except Exception as e:
                logger.error(f"[spinner show] Ошибка показа спиннера: {e}")
        run_on_ui_thread(_ui)
    
    def _update_spinner(self, spinner_ref, title):
        logger.debug(f"Обновление спиннера: {title}")
        def _ui():
            try:
                bld = spinner_ref.get("dialog")
                if bld:
                    bld.set_title(title)
            except Exception as e:
                logger.error(f"[spinner update] Ошибка: {e}")
        run_on_ui_thread(_ui)

    def _dismiss_spinner(self, spinner_ref):
        logger.debug("Скрытие спиннера")
        def _ui():
            try:
                bld = spinner_ref.get("dialog")
                if bld:
                    bld.dismiss()
                spinner_ref["dialog"] = None
            except Exception as e:
                logger.error(f"[spinner dismiss] Ошибка скрытия: {e}")
        run_on_ui_thread(_ui)
    
    def _show_error_dialog(self, fragment, text):
        logger.debug(f"Показ окна ошибки: {text[:50]}...")
        def _ui():
            try:
                ctx = self._context_from_fragment(fragment)
                if ctx is None:
                    return
                AlertDialogBuilder = self._get_alert_builder()
                bld = AlertDialogBuilder(ctx)
                bld.set_title("Ошибка")
                bld.set_message(text)
                bld.set_positive_button("OK", lambda dialog, which: dialog.dismiss())
                bld.show()
            except Exception as e:
                logger.error(f"[error dialog] Ошибка показа: {e}")
        run_on_ui_thread(_ui)

    def _show_result_dialog(self, fragment, account, dialog_id, result_text):
        logger.info("Показ финального окна с результатом")
        def _ui():
            try:
                ctx = self._context_from_fragment(fragment)
                if ctx is None:
                    return
                AlertDialogBuilder = self._get_alert_builder()
                bld = AlertDialogBuilder(ctx)
                bld.set_title("Результат анализа")
                bld.set_message(result_text)
                bld.set_message_text_view_clickable(True)
                
                # Перенести в TelegramAPI
                def on_send_chat(dialog, which):
                    logger.info("Отправка результата в текущий чат...")
                    try:
                        send_text(peer=dialog_id, text=result_text, account=account, parse_mode="Markdown")
                    except Exception as e:
                        logger.error(f"[send chat] Ошибка отправки: {e}")
                    try:
                        dialog.dismiss()
                    except Exception:
                        pass
                
                # Перенести в TelegramAPI
                def on_send_saved(dialog, which):
                    logger.info("Отправка результата в Избранное...")
                    try:
                        # Получаем реальный ID текущего пользователя (это и есть чат Избранное)
                        from org.telegram.messenger import UserConfig
                        saved_id = UserConfig.getInstance(account).getClientUserId()
                        
                        send_text(peer=saved_id, text=result_text, account=account, parse_mode="Markdown")
                        # self._toast(fragment, "Отправлено в Избранное")
                    except Exception as e:
                        logger.error(f"[send saved] Ошибка: {e}")
                        # self._toast(fragment, "Ошибка отправки в Избранное")
                    try:
                        dialog.dismiss()
                    except Exception:
                        pass
                        
                bld.set_positive_button("В текущий чат", on_send_chat)
                bld.set_negative_button("В Избранное", on_send_saved)
                bld.set_neutral_button("Закрыть", lambda dialog, which: dialog.dismiss())
                bld.show()
            except Exception as e:
                logger.error(f"[result dialog] Ошибка окна: {e}\n{traceback.format_exc()}")
                # self._toast(fragment, "Ошибка показа результата")
        run_on_ui_thread(_ui)

    # Методы персонажей
    def fetch_characters(self, url: str):
        logger.info(f"Started fetching characters from {url}")
        headers = {"Accept": "application/json, text/plain, */*"}
        logger.debug(url)
        r = requests.get(url, headers=headers, timeout=6)
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, list):
            raise ValueError("Received JSON is not a list")
        out = []
        for character in data:
            try:
                parsed = Character(**character)
                out.append(parsed)
            except Exception as e:
                logger.error(f"{str(e)}")
                logger.debug(f"Error with character: {character}")
                logger.debug(f"{traceback.format_exc()}")
        return out
    
    def get_characters(self):
        cached_characters = self.get_setting("chrctr_cache_list", '[]')
        cached_characters = [Character(**c) for c in json.loads(cached_characters)]
        logger.debug(f"len(cached_characters): {len(cached_characters)}")

        fetched_characters = []
        if not cached_characters:
            try:
                char_url = str(self.get_setting("exp_chr_lnk", DEFAULT_CHARACTERS_URL))
                logger.info(f"Trying to fetch from: {char_url}")
                fetched_characters = self.fetch_characters(
                    url=char_url
                )
                logger.debug(f"Fetched {len(fetched_characters)} characters:")
            except Exception as e:
                logger.error(f"{str(e)}")
                logger.debug(f"{traceback.format_exc()}")
        
            fetched_characters = [Character(emoji="🚫", name="Стандартный", prompt=""), *fetched_characters, Character(emoji="🔧", name="Кастомный", prompt="")]
            logger.debug(f"Caching fetched characters...")
            self.set_setting("chrctr_cache_list", json.dumps([c.dict() for c in fetched_characters]))
        else:
            fetched_characters = cached_characters
        return fetched_characters

    def msg_id(self, mo):
        for obj in (mo, getattr(mo, "messageOwner", None)):
            if obj is None:
                continue
            for attr in ("id", "messageId", "msg_id"):
                try:
                    value = getattr(obj, attr, None)
                    if value is not None:
                        return int(value)
                except Exception:
                    pass
        return 0
    
    def compile_sys_prompt(self, mode: int, lod: int, character: Character):
        out = ""
        logger.debug(f"Using mode {mode}")
        if mode == 0:
            out += self.get_setting("exp_sys_sumfch", SUMMARY_FACTCHECK_PROMPT)
        elif mode == 1:
            out += self.get_setting("exp_sys_sum", SUMMARY_PROMPT)
        elif mode == 2:
            out += self.get_setting("exp_sys_fch", FACTCHECK_PROMPT)
        else:
            raise ValueError("Mode should be in range 0-2")
        

        logger.debug(f"Using LOD {lod}")
        if lod not in range(0, 3):
            raise ValueError("Level of details should be in range 0-2")
        out += f"\n\n{_DETAIL_LEVELS[lod].strip()}"

        logger.debug(f"Using character {character.name}")
        if character:
            out += (
                "\n\nСТИЛИЗАЦИЯ ОТВЕТА:\n"
                f"Оформи итоговый ответ в образе персонажа {character.emoji} {character.name}.\n"
                f"{character.prompt}\n"
                "Сохраняй фактическое содержание, структуру Markdown, полезность и читабельность ответа."
            )
        return out


    def resolve_input_peer(self, account, dialog_id):
        try:
            from org.telegram.messenger import MessagesController
            mc = MessagesController.getInstance(account)
            did = int(dialog_id)
            if did > 0:
                user = mc.getUser(did)
                return mc.getInputPeer(user) if user else None
            chat_id = abs(did)
            chat = mc.getChat(chat_id)
            return mc.getInputPeer(chat) if chat else None
        except Exception as e:
            logger.error(f"[peer] resolve error: {e}")
            return None


    def sync_send(self, request, timeout=30):
        holder = {"response": None, "error": None}
        event = threading.Event()
        def _cb(response, error, _h=holder, _e=event):
            _h["response"] = response
            _h["error"] = error
            _e.set()
        try:
            send_request(request, RequestCallback(_cb))
            event.wait(timeout)
        except Exception as e:
            holder["error"] = e
        if holder["error"] is not None:
            raise RuntimeError(str(holder["error"]))
        return holder["response"]

    def get_chat_info(self, account, dialog_id):
        try:
            if dialog_id is None:
                return "чат", "Неизвестный чат"
            did = int(dialog_id)
            
            from org.telegram.messenger import MessagesController
            mc = MessagesController.getInstance(account)
            
            if did > 0:
                if did == self.saved_messages_id(account, 0):
                    return "избранное", "Избранное"
                title = self.user_name(account, did)
                if title.startswith("User "):
                    title = f"Пользователь {did}"
                return "личные сообщения", title
            
            if did < 0:
                chat_id = abs(did)
                chat = mc.getChat(chat_id)
                title = f"ID {did}"
                if chat:
                    c_title = getattr(chat, "title", "") or ""
                    if c_title:
                        title = c_title
                return "группа/канал", title
        except Exception as e:
            logger.error(f"[get_chat_info] Ошибка получения информации о чате: {e}")
        return "чат", "Неизвестный чат"

    def from_tl_api(self, account, dialog_id, selected_id, max_count):
        try:
            from org.telegram.tgnet import TLRPC
            import datetime

            peer = self.resolve_input_peer(account, dialog_id)
            if peer is None:
                logger.error("[from_tl_api] Не удалось разрешить peer!")
                return []

            all_messages = []
            seen_ids = set()
            current_offset_id = int(selected_id)
            offset = 0
            fetches = 0
            step = 100

            while len(all_messages) < max_count and fetches < 80:
                fetches += 1
                limit = min(step, max_count - len(all_messages))

                req = TLRPC.TL_messages_getHistory()
                req.peer = peer
                # req.offset_id = current_offset_id
                req.offset_id = 0
                req.offset_date = 0
                req.add_offset = offset
                req.limit = limit
                req.max_id = 0
                req.min_id = current_offset_id-1

                req.hash = 0

                resp = self.sync_send(req, timeout=30)
                if resp is None:
                    break
                
                messages_array = getattr(resp, "messages", None)
                if not messages_array:
                    break

                # --- преобразуем в список ---
                batch = []
                try:
                    if hasattr(messages_array, "size"):
                        for i in range(messages_array.size()):
                            batch.append(messages_array.get(i))
                    else:
                        batch = list(messages_array)
                except Exception:
                    break

                if not batch:
                    break

                # --- собираем пользователей ---
                users_dict = {}
                users = resp.users

                try:
                    for i in range(users.size()):
                        u = users.get(i)
                        users_dict[u.id] = u
                        logger.debug(f"{u.id} {u.access_hash}")
                except Exception as e:
                    logger.error(f"{e}")
                
                # Собираем каналы
                chats_dict = {}
                chats = resp.chats

                try:
                    for i in range(chats.size()):
                        c = chats.get(i)
                        chats_dict[c.id] = c
                except Exception as e:
                    logger.error(f"{e}")

                fresh = []

                for m in batch:
                    try:
                        mid = int(m.id)
                        
                        # --- защита от дублей ---
                        if mid in seen_ids:
                            continue
                            
                        # --- фильтр по id ---
                        if mid <= 0:
                            continue

                        # --- фильтр "непустых" сообщений ---
                        text = getattr(m, "message", None)
                        has_text = text and text.strip()
                        has_media = getattr(m, "media", None) is not None

                        if not has_text and not has_media:
                            continue

                        seen_ids.add(mid)

                        # --- получаем имя автора ---
                        name = "Unknown"

                        if hasattr(m, "from_id") and m.from_id:
                            uid = getattr(m.from_id, "user_id", None) or getattr(m.from_id, "channel_id", None)
                            user = users_dict.get(uid)
                            if user:
                                first = getattr(user, "first_name", "") or ""
                                last = getattr(user, "last_name", "") or ""
                                name = (first + " " + last).strip() or "Unknown"
                        
                        # для каналов
                        if getattr(m, "post", False):
                            if getattr(m, "post_author", None):
                                name = m.post_author
                            else:
                                # fallback — имя канала
                                cid = None
                                if hasattr(m.peer_id, "channel_id"):
                                    cid = m.peer_id.channel_id

                                chat = chats_dict.get(cid)
                                if chat:
                                    name = getattr(chat, "title", "Channel")
                        # --- дата ---
                        dt = None
                        if hasattr(m, "date"):
                            dt = datetime.datetime.fromtimestamp(m.date)

                        fresh.append({
                            "name": name,
                            "text": text if has_text else "[media]",
                            "datetime": dt
                        })

                    except Exception:
                        continue

                if not fresh:
                    break

                all_messages.extend(fresh)

                # обновляем offset (идём к более старым)
                ids = [int(m.id) for m in batch if hasattr(m, "id")]
                if not ids:
                    break

                # current_offset_id = min(ids)
                offset += len(batch)
                
            all_messages.sort(key=lambda x: x["datetime"])
            logger.debug(f"{all_messages[1]}, {all_messages[-1]}")
            return all_messages
            

        except Exception as e:
            logger.error(f"[from_tl_api] Ошибка: {e}")
            return []

    def collect_history(self, account, dialog_id, selected_id, fragment, max_count):
        logger.info("Попытка сбора сообщений через _from_tl_api (API)...")
        logger.debug(f"Max messages: {max_count}")
        api_msgs = self.from_tl_api(account, dialog_id, selected_id, max_count)
        if api_msgs:
            logger.info(f"Успех (API): собрано {len(api_msgs)} сообщений.")
            return api_msgs
            
        logger.error("TL_API вернул пустоту. Фолбек на считывание _from_fragment (UI)...")
        return []

    def build_transcript(self, messages):
        logger.debug(f"Построение транскрипта из {len(messages)} сообщений...")
        lines = []
        for m in messages:
            text = f"{m.get('name')} | {m.get('datetime').isoformat()} | {m.get('text')}"
            lines.append(text)
        return "\n".join(lines)

    def on_menu_click(self, ctx):
        logger.debug(f"Menu button was called")
        message = ctx.get("message")
        dialog_id = ctx.get("dialog_id")
        account = ctx.get("account")
        fragment = ctx.get("fragment")
        logger.debug(f"message={message} dialog_id={dialog_id} account={account} fragment={fragment}")

        selected_id = self.msg_id(message)
        spinner_ref = {"dialog": None}
        self._show_spinner(fragment, spinner_ref, "Анализирую историю…")

        run_on_queue(lambda: self.process(account=account, dialog_id=dialog_id, selected_id=selected_id, fragment=fragment, spinner_ref=spinner_ref, logger=logger))
        # self.process(account=account, dialog_id=dialog_id, selected_id=selected_id, fragment=fragment, spinner_ref=spinner_ref)

    def process(self, account, dialog_id, selected_id, fragment, spinner_ref, logger):
        try:
            # Проверяем ключ и ссылку на API
            logger.debug("Checking for ai_api_url and ai_api_key")
            api_url = str(self.get_setting("ai_api_url", "")).strip()
            api_key = str(self.get_setting("ai_api_key", "")).strip()
            if not api_url:
                raise ValueError("API URL not set! Check plugin settings")
            if not api_key:
                raise ValueError("API Key not set! Check plugin settings")
            logger.debug(f"ai_api_url={api_url} ai_api_key={api_key}")
            
            # Получаем модель
            cached_models = self.get_setting("ai_cache_mdls", [])
            model_idx = int(self.get_setting("ai_mdl_idx", 0))
            model = cached_models[model_idx]
            logger.info(f"Using LLM: {model}")

            api_type = int(self.get_setting("ai_api_type", 0))
            mode = int(self.get_setting("req_mode", 0))
            detail_level = int(self.get_setting("req_lod", 1))
            character_index = int(self.get_setting("chrctr_idx", 0))
            logger.debug(f"api_type={api_type} mode={mode} detail_level={detail_level} character_index={character_index}")

            characters = self.get_characters()
            if character_index < 0 or character_index >= len(characters):
                character_index = 0
            character = characters[character_index]
            logger.debug(f"character={str(character)[:50]}")
            
            max_msgs = max(10, min(2000, int(str(self.get_setting("req_max_msg", DEFAULT_REQ_MAX_MSG)).strip())))

            sys_prompt = self.compile_sys_prompt(mode=mode, lod=detail_level, character=character)
            logger.debug(f"sys_prompt={sys_prompt[:50]}")

            messages = self.collect_history(account=account, dialog_id=dialog_id, selected_id=selected_id, fragment=fragment, max_count=max_msgs)
            if not messages:
                raise ValueError("Error while collecting messages. Please, try again later.")
            logger.debug(f"messages={str(messages)[:50]}...")
            transcripted = self.build_transcript(messages)
            logger.debug(f"transcripted={transcripted[:50]}...")
            
            chat_type_ru, chat_title = self.get_chat_info(account, dialog_id)
            logger.debug(f"chat_type_ru={chat_type_ru} chat_title={chat_title}")

            context_block = f"КОНТЕКСТ ПЕРЕПИСКИ:\n- Источник: {chat_type_ru}\n- Название / Собеседник: {chat_title}\n\n--- ТЕКСТ СООБЩЕНИЙ ---\n"

            if mode == 1:
                base_req = f"Сделай суммаризацию только по тексту переписки ({len(messages)} сообщений).\n\n"
            elif mode == 2:
                base_req = f"Проверь факты только по тексту переписки ({len(messages)} сообщений).\n\n"
            else:
                base_req = f"Проанализируй только текст переписки ({len(messages)} сообщений, от старых к новым).\n\n"

            user_content = base_req + context_block + transcripted
            self._update_spinner(spinner_ref, f"Ожидаю ответ от {model}…")

            llm_result = LLM.call_llm(
                api_type=api_type,
                url=api_url,
                api_key=api_key,
                model=model,
                system_prompt=sys_prompt,
                user_content=user_content,
                logger=logger
            )
            logger.debug(f"llm_result={llm_result[:50]}")
            self._dismiss_spinner(spinner_ref)

            self._show_result_dialog(fragment, account, dialog_id, llm_result)
            
        except Exception as e:
            self._dismiss_spinner(spinner_ref)
            logger.error(str(e))
            logger.debug(traceback.format_exc())
            self._show_error_dialog(fragment, str(e)[:1500])

    def on_plugin_load(self):
        logger.clear()
        logger.set_log_func(func=self.log)
        logger.set_log_level(level=int(self.get_setting("dev_log_lvl", LOG_LEVEL)))
        logger.error("-"*30)
        logger.info("Plugin loading started")
        logger.debug(f"len(logger.get())={len(logger.get())}")
        logger.debug("Logger setted!")
        self._log_text_view = None
        # Проверить настройки

        # Подгрузить список персонажей

        # Проверить доступность модели

        # Добавить пункт меню
        self.add_menu_item(MenuItemData(
            menu_type=MenuItemType.MESSAGE_CONTEXT_MENU,
            text="Суммаризация / фактчек от этого сообщения",
            item_id="ollama_summarize_popup",
            icon="msg_search",
            subtext="AI Анализ",
            priority=90,
            on_click=self.on_menu_click,
        ))
        logger.info("Plugin loaded")

    def create_settings(self):
        logger.debug("Building settings...")
        '''
        cache: COMPLETE
            ai_cache_mdls:      list    
            chrctr_cache_list:  list

        ai                      Настройки ИИ    COMPLETE
            ai_api_type:    str     Тип API
            ai_api_url:     str     Ссылка на API
            ai_api_key:     str     Ключ доступа API
            ai_mdl_idx:     int     Индекс модели
        
        req                     Настройки запроса   COMPLETE
            req_lod:        int     Уровень детализации (0 - оч. кратко; 2 - оч. подробно)
            req_mode:       int     Режим работы (Сум. + ф-ч.; сум.; ф-ч.)
            req_max_msg:    int     Максимальное кол-во сообщений для сбора
        
        chrctr                  Настройки персонажа COMPLETE
            chrctr_idx:     int             Индекс персонажа
            chrctr_prompt:  Optional[str]   Промпт персонажа (Если выбран кастомный)
        
        exp:                    Экспериментальные опции
            exp_enabled:    bool    Вкл./выкл.
            exp_sys_sumfch: str     Системный промпт суммаризации и факт-чекинга 
            exp_sys_sum:    str     Системный промпт суммаризации
            exp_sys_fch:    str     Системный промпт факт-чекинга
            exp_chr_lnk:    str     Ссылка на JSON с персонажами
            exp_dev_mode:   bool    Вкл./выкл. режим разработчика

        dev                     Режим разработчика  COMPLETE
            dev_enabled:    bool    Включены параметры разработчика
            dev_log_lvl:    int     Уровень логов
            dev_logs:       toggle  Выгрузка логов
            dev_logs_copy:  button  Копирование логов в буфер
            dev_logs_clear: toggle  Очистка логов
        '''

        # Настройки модели
        logger.info("Building AI settings...")
        ai_settings_list = [
            Header(text="Настройки API"),
            Selector(key="ai_api_type", text="Тип API", default=0, items=["OpenAI-совместимый", "Ollama Native API"]),
            Input(key="ai_api_url", text="API URL", default="", subtext="OpenAI: http://.../v1/\nOllama Native: http://.../api/"),
            Input(key="ai_api_key", text="API Key", default="", subtext="Токен для OpenAI/OpenWebUI. Для локальной Ollama оставьте пустым.")
        ]
        logger.info("Getting models from cache...")
        cached_models = self.get_setting("ai_cache_mdls", [])
        cached_model_idx = int(self.get_setting("ai_mdl_idx", 0))
        logger.debug(f"cached_model_idx={cached_model_idx}, len(cached_models)={len(cached_models)}")
        if cached_model_idx >= len(cached_models):
            logger.debug("cached_model_idx >= len(cached_models)... Resetting cached_model_idx")
            cached_model_idx = 0

        cached_selected_model = ''
        if cached_model_idx:
            cached_selected_model = cached_models[cached_model_idx]
        
        fetched_models = []
        logger.info(f"Trying to fetch models...")
        try:
            api_type = int(self.get_setting("ai_api_type", 0))
            api_url = str(self.get_setting("ai_api_url", ""))
            api_key = str(self.get_setting("ai_api_key", ""))
            fetched_models = LLM.fetch_models(
                url=api_url,
                api_type=api_type,
                api_key=api_key
            )
            logger.info(f"Fetched {len(fetched_models)} models!")
        except Exception as e:
            logger.error(f"An error occured while fetching models: {str(e)}")
            logger.debug(f"{traceback.format_exc()}")
        
        if fetched_models:
            logger.debug(f"cached_selected_model in fetched_models: {cached_selected_model in fetched_models}")
            if cached_selected_model in fetched_models:
                self.set_setting("ai_mdl_idx", fetched_models.index(cached_selected_model))
            else:
                self.set_setting("ai_mdl_idx", 0)
            logger.info(f"Updating cached models")
            self.set_setting("ai_cache_mdls", fetched_models)
            ai_settings_list.append(Selector(key="ai_mdl_idx", text="Выбрать модель", default=0, items=fetched_models))

        logger.info("AI settings builded successfully!")

        # Настройки запроса к модели
        logger.info("Building request settings...")
        request_settings_list = [
            Divider(text="Параметры анализа"),
            Selector(key="req_lod", text="Подробность суммаризации", default=1, items=["Кратко (только суть)", "Нормально (сбалансированно)", "Подробно (сохранить все детали)"]),
            Selector(key="req_mode", text="Режим работы", default=0, items=["Суммаризация + проверка фактов", "Только суммаризация", "Только проверка фактов"]),
            Input(key="req_max_msg", text="Максимум сообщений", default=DEFAULT_REQ_MAX_MSG, subtext="Ограничение на глубину сбора истории (10-2000)"),
        ]

        # Настройки персонажа
        logger.info("Building character settings...")
        chrctr_settings_list = [
            Divider(text="Персонаж")
        ]

        try:
            logger.info(f"Trying to get characters...")
            fetched_characters = self.get_characters()
            cached_character_idx = self.get_setting("chrctr_idx", 0)

            logger.info(f"cached_character_idx={cached_character_idx}, len(fetched_characters)={len(fetched_characters)}")
            if cached_character_idx >= len(fetched_characters):
                logger.debug("cached_character_idx >= len(fetched_characters)... Resetting cached_character_idx")
                cached_character_idx = 0
            
            cached_selected_character = None
            if cached_character_idx:
                cached_selected_character = fetched_characters[cached_character_idx]
            
            if fetched_characters:
                if cached_selected_character in fetched_characters:
                    self.set_setting("chrctr_idx", fetched_characters.index(cached_selected_character))
                else:
                    self.set_setting("chrctr_idx", 0)

            chrctr_settings_list.append(Selector(key="chrctr_idx", text="Выбрать персонажа", default=0, items=[f"{c.emoji} {c.name}" for c in fetched_characters]))

            if cached_character_idx == len(fetched_characters) - 1:
                logger.info(f"Custom character was set!")
                chrctr_settings_list.append(
                    EditText(
                        key="chrctr_prompt",
                        hint="Свой персонаж: опишите стиль, лексику, настроение и манеру речи. Не более 1024 символов",
                        default="",
                        multiline=True,
                        max_length=1024
                    )
                )
                chrctr_settings_list[-1].prompt = self.get_setting("chrctr_prompt", "")
        except Exception as e:
            logger.error(str(e))
            logger.debug(traceback.format_exc())
        
        logger.info("Character settings builded successfully!")

        logger.info("Building experimental settings...")
        exp_settings_list = [
            Divider(text="Экспериментальные опции"),
            Switch(key="exp_enabled", text="Включить экспериментальные опции", default=False)
        ]
        if self.get_setting("exp_enabled", False):
            exp_settings_list += [
            #     exp_sys_sumfch: str     Системный промпт суммаризации и факт-чекинга 
            # exp_sys_sum:    str     Системный промпт суммаризации
            # exp_sys_fch:    str     Системный промпт факт-чекинга
            # exp_chr_lnk:    str     Ссылка на JSON с персонажами
                Divider(text="Свой системный промпт для суммаризации и факт-чекинга"),
                EditText(
                    key="exp_sys_sumfch",
                    hint="Свой системный промпт для суммаризации и факт-чекинга",
                    default=SUMMARY_FACTCHECK_PROMPT,
                    multiline=True,
                    max_length=10000
                ),
                Divider(text="Свой системный промпт для суммаризации"),
                EditText(
                    key="exp_sys_sum",
                    hint="Свой системный промпт для суммаризации",
                    default=SUMMARY_PROMPT,
                    multiline=True,
                    max_length=10000
                ),
                Divider(text="Свой системный промпт для факт-чекинга"),
                EditText(
                    key="exp_sys_fch",
                    hint="Свой системный промпт для факт-чекинга",
                    default=FACTCHECK_PROMPT,
                    multiline=True,
                    max_length=10000
                ),
                Divider(text="Ссылка на JSON файл с персонажами"),
                EditText(
                    key="exp_chr_lnk",
                    hint="Ссылка на JSON файл с персонажами",
                    default=DEFAULT_CHARACTERS_URL,
                )
            ]

        logger.info("Experimental settings builded successfully!")

        dev_settings_list = [
            Divider(text="Параметры разработчика"),
            Switch(key="dev_enabled", text="Включить параметры разработчика", default=False)
        ]
        if self.get_setting("dev_enabled", False):
            dev_settings_list.append(
                Selector(key="dev_log_lvl", text="Уровень логов", default=LOG_LEVEL, items=["DEBUG", "INFO", "WARN", "ERROR"], on_change=self._on_log_level_change)
            )
        
            try:
                container = self._build_scroll_container()
            except Exception as e:
                logger.error(f"An error occured while building dev settings {e}")
                logger.debug(traceback.format_exc())
                dev_settings_list += [Header(text="Ошибка загрузки блока"), Divider()]

            dev_settings_list += [
                Custom(view=container),
                Text(
                    text="Копировать текст",
                    icon="msg_copy",
                    accent=True,
                    on_click=self._copy_to_clipboard,
                ),
                Divider(),
            ]

            dev_settings_list.append(
                Text(
                    text="Очистить логи",
                    icon="msg_cancel",
                    red=True,
                    on_click=self._on_clear_logs,
                ),
            )

        settings_list = ai_settings_list + request_settings_list + chrctr_settings_list + exp_settings_list + dev_settings_list
        return settings_list
