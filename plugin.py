__id__ = "ai-chat-summarizer"
__name__ = "AI Chat Summarizer & Fact Checker"
__author__ = "@edward_vishnevsky"
__version__ = "0.4.3"
__min_version__ = "0.0.1"
__description__ = "Собирает сообщения, отправляет в LLM, поддерживает разные API, персонажей стилизации и кастомный промпт персонажа."

import threading
import traceback
import requests
import urllib.parse

from base_plugin import BasePlugin, MenuItemData, MenuItemType
from ui.settings import Header, Divider, Input, EditText, Switch, Selector, Text
from client_utils import run_on_queue, send_text, send_request, RequestCallback
from android_utils import run_on_ui_thread, log
from java import jclass

Toast = jclass("android.widget.Toast")

_DEFAULT_URL = "http://192.168.1.100:11434/v1/chat/completions"
_DEFAULT_MODEL = "llama3.2"
_DEFAULT_LIMIT = "300"
_MAX_CHARS = 28000

CHARACTER_PRESETS = [
    {"emoji": "🚫", "name": "Стандартный", "prompt": ""},
    {"emoji": "😈", "name": "Игривая кокетка", "prompt": "Пиши как очень игривая, раскованная и слегка пошлая девушка, которая обожает флиртовать. Используй двусмысленные намёки, дерзкие шуточки, томные вздохи (ах~, ммм~) и горячие эмодзи (🫦, 🔥, 😉, 😈, 💦). Обращайся к читателю с лёгкой провокацией или ласково (например, «сладенький», «шалун», «красавчик», «котик»). Преврати скучную выжимку чата в пикантный рассказ: называй жаркие споры «ролевыми играми», а сухие факты — «нашими маленькими грязными секретами». При всей этой раскованной подаче ОБЯЗАТЕЛЬНО сохрани всю суть переписки, ключевые тезисы и результаты фактчекинга. Ответ должен быть невероятно горячим и дразнящим, но при этом оставаться точным по смыслу!"},
    {"emoji": "🌸 ", "name": "Кавайная тянка", "prompt": "Пиши как милая аниме-тяночка! Используй японские словечки (ня, кавай, семпай, десу, бака), много милых смайликов (🌸, 🎀, ✨), каомодзи (≧◡≦, (⁄ ⁄>⁄ ▽ ⁄<⁄ ⁄), ʕ- ᴥ- ʔ) и чрезмерно восторженную, эмоциональную подачу. Уменьшительно-ласкательные суффиксы приветствуются! При этом обязательно сохрани изначальный смысл переписки, просто оберни факты в очень милую и слегка наивную подачу."},
    {"emoji": "🧠", "name": "Человек после лоботомии", "prompt": "Пиши как человек, которому только что сделали лоботомию. Твои мысли путаются, ты постоянно отвлекаешься на случайные предметы, звуки или запахи. Используй рваные предложения, странные философские наблюдения на пустом месте, повторяй слова и забывай, о чём говорил секунду назад. Сохрани суть обсуждаемых в чате вопросов, но выдавай их как обрывочные, странные откровения, перемешанные с полным бредом."},
    {"emoji": "🪨", "name": "Пещерный человек", "prompt": "Пиши как первобытный пещерный человек, австралопитек. Используй очень простые слова, говори о себе в третьем лице или просто \"Я\". Никаких сложных терминов — заменяй их на примитивные аналоги (например, \"машина\" = \"железный зверь\", \"интернет\" = \"невидимая паутина\"). Речь должна быть рубленой, рычащей (Угх, аргх, уга-буга) и сфокусированной на базовых потребностях: еда, выживание, соплеменники. Смысл переписки передай через эту примитивную призму."},
    {"emoji": "🤠", "name": "Ковбой Дикого Запада", "prompt": "Пиши как суровый, прокуренный ковбой с Дикого Запада. Используй сленг вестернов (партнёр, салун, револьвер, шериф, лассо, прерии). Тон должен быть спокойным, слегка с ленцой, с характерным южным акцентом (вставляй словечки типа \"howdy\", \"yee-haw\"). Заменяй современные концепции на ковбойские аналоги, но строго сохраняй факты и суть переписки. Говори так, будто рассказываешь эту историю за стаканом виски в местном баре после долгой поездки на мустанге."},
    {"emoji": "✨", "name": "Милая девочка", "prompt": "Пиши как милая добрая девочка: используй нежные интонации, милые символы, каомодзи и очаровательные украшения умеренно. Сохраняй смысл, структуру и полезность ответа."},
    {"emoji": "⛪", "name": "Православный священник", "prompt": "Пиши как православный священник: спокойно, назидательно и мягко. Иногда уместно ссылайся на Библию, духовную мудрость и добродетели, но не искажай факты и не превращай ответ в сплошную проповедь."},
    {"emoji": "🥃", "name": "Матершинный гопник", "prompt": "Пиши как грубоватый дворовый гопник: разговорно, дерзко, с уличной подачей. Допускается умеренная обсценная лексика, но без перебора. Смысл, факты и структура должны сохраняться."},
    {"emoji": "🎩", "name": "Интеллигентный парень", "prompt": "Пиши как интеллигентный, образованный молодой человек: вежливо, ясно, остроумно и аккуратно. Используй чистый язык и хорошую структуру."},
    {"emoji": "🐱", "name": "Кошечка", "prompt": "Пиши как ласковая кошечка: мягко, игриво, с лёгкими мур-нотками и кошачьими интонациями, но не ломай логику ответа."},
    {"emoji": "🐶", "name": "Собачка", "prompt": "Пиши как дружелюбная собачка: бодро, позитивно, верно и энергично, с лёгкими собачьими словечками и добрым настроением."},
    {"emoji": "💼", "name": "Корпоративный клерк", "prompt": "Пиши в корпоративном стиле: как внутреннее резюме от офисного сотрудника, с деловой структурой, канцеляризмами, нейтральным тоном и бизнес-лексикой."},
    {"emoji": "🪷", "name": "Буддист", "prompt": "Пиши как буддист, познавший дзен: спокойно, созерцательно, с нотками осознанности, принятия и внутреннего равновесия, но не уходи от сути."},
    {"emoji": "💻", "name": "Заядлый программист", "prompt": "Пиши как опытный программист: используй айтишные аналогии, инженерный подход, техническую точность и местами профессиональный жаргон."},
    {"emoji": "🎮", "name": "Геймер", "prompt": "Пиши как увлечённый геймер: с игровыми аналогиями, мемным вайбом, упоминаниями каток, скилла, лута, квестов, патчей и нерфов, если это уместно."},
    {"emoji": "🧛", "name": "Готический вампир", "prompt": "Пиши как элегантный мрачный вампир: красиво, слегка театрально, с тёмной эстетикой и благородной манерой речи."},
    {"emoji": "🧠", "name": "Психолог", "prompt": "Пиши как спокойный и вдумчивый психолог: замечай эмоциональные паттерны, мягко объясняй динамику общения и структурируй переживания участников."},
    {"emoji": "🛠️", "name": "Свой персонаж", "prompt": ""}
]

CHARACTER_LABELS = [f"{c['emoji']} {c['name']}" for c in CHARACTER_PRESETS]
CUSTOM_CHARACTER_INDEX = len(CHARACTER_PRESETS) - 1

_PROMPT_FULL = """Ты — профессиональный аналитик текстовой переписки Telegram. Твоя задача — проанализировать предоставленный транскрипт чата.
Анализируй только текст сообщений, полностью игнорируй системные сообщения о добавлении картинок, файлов и других вложений.
ОБЯЗАТЕЛЬНО обращай внимание на контекст (личные сообщения, группа или канал) и имена авторов сообщений. Ты должен четко понимать, кто, кому и что именно говорит, кто выдвигает какие тезисы и как на них реагируют другие участники.

СТРУКТУРА ОТВЕТА:

## 📝 Краткое содержание
Опиши основную тему обсуждения, вектор развития разговора и к какому итогу пришли участники.

## 🎯 Ключевые тезисы
Сформируй структурированный маркерный (bullet) список главных утверждений, договорённостей, идей и решений. Обязательно указывай авторов, если в беседе участвует больше одного человека.

## 🔍 Проверка фактов
Найди в тексте утверждения, которые подаются как объективные факты. Для каждого проверяемого утверждения:
- Утверждение: \"...\"
- Статус: [Подтверждено в беседе / Сомнительно / Не подтверждено / Требует внешней проверки]
- Комментарий: кратко объясни причину такого статуса на основе текста.
Если проверяемых фактов в тексте нет — напиши об этом явно.

Отвечай на том же языке, на котором ведется переписка."""

_PROMPT_SUMMARY_ONLY = """Ты — профессиональный аналитик текстовой переписки Telegram. Твоя задача — сделать качественную выжимку предоставленного транскрипта чата.
Анализируй только текст сообщений, полностью игнорируй картинки, файлы и другие вложения.
Учитывай источник и имена авторов, чтобы правильно передать динамику диалога.

СТРУКТУРА ОТВЕТА:

## 📝 Краткое содержание
Опиши основную тему обсуждения, ход разговора и итоговый результат.

## 🎯 Ключевые тезисы
Сформируй маркерный список главных мыслей, аргументов, договорённостей и решений. Обязательно указывай авторов конкретных идей.

Отвечай на том же языке, на котором ведется переписка."""

_PROMPT_FACTCHECK_ONLY = """Ты — строгий и беспристрастный факт-чекер. Твоя задача — проанализировать предоставленный транскрипт Telegram-чата исключительно на предмет достоверности озвучиваемых данных.
Анализируй только текст сообщений, игнорируй вложения. НЕ делай общую суммаризацию разговора. Ищи только те утверждения, которые преподносятся как объективные факты.

Для каждого найденного утверждения выведи:
- Утверждение: \"...\" (с указанием автора)
- Статус: [Внутренне непротиворечиво / Сомнительно / Искажено / Требует фактчека в интернете]
- Комментарий: краткое обоснование статуса.

Если в тексте нет явных фактических утверждений — напиши об этом явно.
Отвечай на языке переписки."""

_DETAIL_LEVELS = [
    """
ИНСТРУКЦИЯ ПО ДЕТАЛИЗАЦИИ: [КРАТКО]
Сделай максимально сжатую и лаконичную выжимку. Умести смысл в 2-4 предложениях и 3-4 главных буллитах. Игнорируй второстепенные детали и оставь только суть и финальные итоги.""",
    """
ИНСТРУКЦИЯ ПО ДЕТАЛИЗАЦИИ: [НОРМАЛЬНО]
Сделай сбалансированную выжимку. Отрази контекст, основные темы, ключевые аргументы сторон и итог обсуждения. Убери информационный шум, но сохрани логику диалога.""",
    """
ИНСТРУКЦИЯ ПО ДЕТАЛИЗАЦИИ: [МАКСИМАЛЬНО ПОДРОБНО]
Сделай очень подробный анализ диалога. Сохрани все подтемы, аргументы, контраргументы, идеи, нюансы и эмоциональный фон. Ответ должен быть объёмным и исчерпывающим."""
]

class Plugin(BasePlugin):
    def on_plugin_load(self):
        self.add_menu_item(MenuItemData(
            menu_type=MenuItemType.MESSAGE_CONTEXT_MENU,
            text="Суммаризация / фактчек от этого сообщения",
            item_id="ollama_summarize_popup",
            icon="msg_search",
            subtext="AI Анализ",
            priority=90,
            on_click=self._on_menu_click,
        ))
        self._log_info("Plugin loaded")

    def on_plugin_unload(self):
        self._log_info("Plugin unloaded")

    def _fetch_models(self):
        try:
            api_type = int(self.get_setting("api_type", 0))
        except Exception:
            api_type = 0
        api_url = str(self.get_setting("api_url", _DEFAULT_URL)).strip()
        api_key = str(self.get_setting("api_key", "")).strip()
        fetched = []
        try:
            parsed = urllib.parse.urlparse(api_url)
            base_url = f"{parsed.scheme}://{parsed.netloc}"
            headers = {}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            if api_type == 0:
                models_url = api_url.replace("chat/completions", "models")
                r = requests.get(models_url, headers=headers, timeout=1.5)
                if r.ok:
                    data = r.json()
                    fetched = [str(m.get("id")) for m in data.get("data", []) if "id" in m]
            else:
                models_url = f"{base_url}/api/tags"
                r = requests.get(models_url, headers=headers, timeout=1.5)
                if r.ok:
                    data = r.json()
                    fetched = [str(m.get("name")) for m in data.get("models", []) if "name" in m]
        except Exception as e:
            self._log_error(f"[fetch models] {e}")
        return fetched

    def create_settings(self):
        old_cached_str = str(self.get_setting("cached_models", _DEFAULT_MODEL))
        old_cached = old_cached_str.split(",") if old_cached_str else [_DEFAULT_MODEL]
        try:
            old_idx = int(self.get_setting("model_index", 0))
        except Exception:
            old_idx = 0
        if old_idx >= len(old_cached):
            old_idx = 0
        old_model = old_cached[old_idx]
        fetched_models = self._fetch_models()
        if fetched_models:
            if old_model in fetched_models:
                self.set_setting("model_index", fetched_models.index(old_model))
            else:
                self.set_setting("model_index", 0)
            self.set_setting("cached_models", ",".join(fetched_models))
        else:
            fetched_models = old_cached
        models_status = "Модели успешно загружены с сервера." if (fetched_models != old_cached or len(fetched_models) > 1) else "Внимание: не удалось получить список моделей с сервера. Отображаются сохраненные."

        settings_list = [
            Header(text="Настройки API"),
            Selector(key="api_type", text="Тип API", default=0, items=["OpenAI-совместимый (OpenWebUI, v1)", "Ollama Native API (/api/chat)"]),
            Input(key="api_url", text="API URL", default=_DEFAULT_URL, subtext="OpenAI/OpenWebUI: http://.../v1/chat/completions\nOllama Native: http://.../api/chat"),
            Input(key="api_key", text="API Key / Bearer Token", default="", subtext="Токен для OpenAI/OpenWebUI. Для локальной Ollama оставьте пустым."),
            Divider(text="Выбор модели"),
            Selector(key="model_index", text="Выбрать модель", default=0, items=fetched_models),
            Text(text=models_status, accent=False),
            Divider(text="Параметры анализа"),
            Selector(key="detail_level", text="Подробность суммаризации", default=1, items=["Кратко (только суть)", "Нормально (сбалансированно)", "Подробно (сохранить все детали)"]),
            Selector(key="mode", text="Режим работы", default=0, items=["Суммаризация + проверка фактов", "Только суммаризация", "Только проверка фактов"]),
            Input(key="max_messages", text="Максимум сообщений", default=_DEFAULT_LIMIT, subtext="Ограничение на глубину сбора истории (10-2000)"),
            Switch(key="include_sender", text="Указывать имена отправителей", default=True, subtext="Добавлять имя автора к каждому сообщению"),
            Switch(key="include_datetime", text="Добавлять дату и время сообщений", default=False, subtext="Помогает модели ориентироваться во временных рамках переписки"),
            Divider(text="Стилизация"),
            Selector(key="character_index", text="Персонаж", default=0, items=CHARACTER_LABELS),
            
        ]

        current_character = self.get_setting("character_index", 0)
        if current_character == CUSTOM_CHARACTER_INDEX:
            settings_list.append(EditText(key="custom_character_prompt", hint="Свой персонаж: опишите стиль, лексику, настроение и манеру речи", default="", multiline=True, max_length=4000))
        return settings_list

    def _get_alert_builder(self):
        from ui.alert import AlertDialogBuilder
        return AlertDialogBuilder

    def _on_menu_click(self, ctx):
        try:
            message = ctx.get("message")
            dialog_id = ctx.get("dialog_id")
            account = ctx.get("account")
            fragment = ctx.get("fragment")
            if message is None or dialog_id is None or account is None:
                self._log_error(f"[menu] missing keys: {list(ctx.keys())}")
                return
            selected_id = self._msg_id(message)
            self._log_info(f"[menu] selected_id={selected_id} dialog={dialog_id}")
            spinner_ref = {"dialog": None}
            self._toast(fragment, "Начинаю сбор сообщений…")
            self._show_spinner(fragment, spinner_ref, "Анализирую историю…")
            run_on_queue(lambda: self._process(account=account, dialog_id=dialog_id, selected_id=selected_id, fragment=fragment, spinner_ref=spinner_ref))
        except Exception as e:
            self._log_error(f"[menu] error: {e}\n{traceback.format_exc()}")
            self._toast(ctx.get("fragment"), "Ошибка запуска плагина")

    def _process(self, account, dialog_id, selected_id, fragment, spinner_ref):
        try:
            api_url = self.get_setting("api_url", _DEFAULT_URL).strip()
            api_key = self.get_setting("api_key", "").strip()
            cached_str = str(self.get_setting("cached_models", _DEFAULT_MODEL))
            models_list = cached_str.split(",") if cached_str else [_DEFAULT_MODEL]
            try:
                model_idx = int(self.get_setting("model_index", 0))
            except Exception:
                model_idx = 0
            if model_idx >= len(models_list):
                model_idx = 0
            model = models_list[model_idx]
            try:
                api_type = int(self.get_setting("api_type", 0))
                mode = int(self.get_setting("mode", 0))
                detail_level = int(self.get_setting("detail_level", 1))
                character_index = int(self.get_setting("character_index", 0))
            except Exception:
                api_type = 0
                mode = 0
                detail_level = 1
                character_index = 0
            include_sender = self.get_setting("include_sender", True)
            include_datetime = self.get_setting("include_datetime", False)
            # custom_prompt = self.get_setting("system_prompt", "").strip()
            custom_character_prompt = self.get_setting("custom_character_prompt", "").strip()
            if character_index < 0 or character_index >= len(CHARACTER_PRESETS):
                character_index = 0
            character = CHARACTER_PRESETS[character_index]
            if character_index == CUSTOM_CHARACTER_INDEX:
                character_prompt = custom_character_prompt
            else:
                character_prompt = character.get("prompt", "").strip()
            try:
                max_msgs = max(10, min(2000, int(self.get_setting("max_messages", _DEFAULT_LIMIT))))
            except Exception:
                max_msgs = 300

            if mode == 1:
                sys_prompt = _PROMPT_SUMMARY_ONLY
            elif mode == 2:
                sys_prompt = _PROMPT_FACTCHECK_ONLY
            else:
                sys_prompt = _PROMPT_FULL
            if mode != 2:
                sys_prompt += f"\n\n{_DETAIL_LEVELS[detail_level]}"
            if character_prompt:
                sys_prompt += (
                    "\n\nСТИЛИЗАЦИЯ ОТВЕТА:\n"
                    f"Оформи итоговый ответ в образе персонажа {character['emoji']} {character['name']}.\n"
                    f"{character_prompt}\n"
                    "Сохраняй фактическое содержание, структуру Markdown, полезность и читабельность ответа."
                )
            # if custom_prompt:
            #     sys_prompt += f"\n\nДОПОЛНИТЕЛЬНЫЙ СИСТЕМНЫЙ ПРОМПТ ОТ ПОЛЬЗОВАТЕЛЯ:\n{custom_prompt}"

            self._update_spinner(spinner_ref, "Загружаю историю чата…")
            chat_type_ru, chat_title = self._get_chat_info(account, dialog_id)
            messages = self._collect_history(account=account, dialog_id=dialog_id, selected_id=selected_id, fragment=fragment, max_count=max_msgs)
            if not messages:
                self._dismiss_spinner(spinner_ref)
                self._log_error("[process] no messages")
                self._toast(fragment, "Не удалось собрать сообщения")
                self._show_error_dialog(fragment, "Не удалось собрать сообщения для анализа. Попробуйте подгрузить чат выше.")
                return

            transcript = self._build_transcript(messages, include_sender, include_datetime)
            truncated = False
            if len(transcript) > _MAX_CHARS:
                transcript = transcript[:_MAX_CHARS]
                truncated = True
            mode_label = ["Суммаризация + фактчек", "Суммаризация", "Проверка фактов"][mode]
            detail_label = ["Кратко", "Нормально", "Подробно"][detail_level]
            character_label = f"{character['emoji']} {character['name']}"
            context_block = f"КОНТЕКСТ ПЕРЕПИСКИ:\n- Источник: {chat_type_ru}\n- Название / Собеседник: {chat_title}\n\n--- ТЕКСТ СООБЩЕНИЙ ---\n"
            if mode == 1:
                base_req = f"Сделай суммаризацию только по тексту переписки ({len(messages)} сообщений). Игнорируй картинки и файлы.\n\n"
            elif mode == 2:
                base_req = f"Проверь факты только по тексту переписки ({len(messages)} сообщений). Игнорируй картинки и файлы.\n\n"
            else:
                base_req = f"Проанализируй только текст переписки ({len(messages)} сообщений, от старых к новым). Игнорируй картинки и файлы.\n\n"
            user_content = base_req + context_block + transcript
            self._update_spinner(spinner_ref, f"Ожидаю ответ от {model}…")
            llm_result = self._call_llm(api_type=api_type, url=api_url, api_key=api_key, model=model, system_prompt=sys_prompt, user_content=user_content)
            self._dismiss_spinner(spinner_ref)
            if truncated:
                llm_result = "[!] Транскрипт был обрезан из-за ограничения по длине.\n\n" + llm_result
            result_text = (
                f"[{mode_label} | {detail_label}]\n"
                f"Персонаж: {character_label}\n"
                f"Источник: {chat_type_ru} ({chat_title})\n"
                f"Сообщений: {len(messages)}\n"
                f"{'=' * 30}\n\n{llm_result}"
            )
            self._show_result_dialog(fragment, account, dialog_id, result_text)
        except Exception as e:
            self._dismiss_spinner(spinner_ref)
            self._log_error(f"[process] fatal: {e}\n{traceback.format_exc()}")
            self._show_error_dialog(fragment, str(e)[:1500])

    def _get_chat_info(self, account, dialog_id):
        try:
            from org.telegram.messenger import MessagesController
            mc = MessagesController.getInstance(account)
            did = int(dialog_id)
            if did > 0:
                return ("Личные сообщения", self._user_name(did))
            chat_id = abs(did)
            chat = mc.getChat(chat_id)
            title = getattr(chat, "title", str(chat_id)) if chat else str(chat_id)
            if chat:
                is_megagroup = getattr(chat, "megagroup", False)
                is_broadcast = getattr(chat, "broadcast", False)
                if is_broadcast and not is_megagroup:
                    return ("Канал", title)
            return ("Группа", title)
        except Exception as e:
            self._log_error(f"[chat_info] {e}")
            return ("Неизвестно", str(dialog_id))

    def _get_my_name(self, account):
        if hasattr(self, "_my_name_cache"):
            return self._my_name_cache
        try:
            from org.telegram.messenger import UserConfig
            user = UserConfig.getInstance(account).getCurrentUser()
            if user:
                fn = (getattr(user, "first_name", "") or "").strip()
                ln = (getattr(user, "last_name", "") or "").strip()
                self._my_name_cache = f"{fn} {ln}".strip() or getattr(user, "username", "Я")
                return self._my_name_cache
        except Exception:
            pass
        self._my_name_cache = "Я"
        return self._my_name_cache

    def _context_from_fragment(self, fragment):
        try:
            return fragment.getParentActivity() if fragment is not None else None
        except Exception:
            return None

    def _show_spinner(self, fragment, spinner_ref, title):
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
                self._log_error(f"[spinner show] {e}")
        run_on_ui_thread(_ui)

    def _update_spinner(self, spinner_ref, title):
        def _ui():
            try:
                bld = spinner_ref.get("dialog")
                if bld:
                    bld.set_title(title)
            except Exception as e:
                self._log_error(f"[spinner update] {e}")
        run_on_ui_thread(_ui)

    def _dismiss_spinner(self, spinner_ref):
        def _ui():
            try:
                bld = spinner_ref.get("dialog")
                if bld:
                    bld.dismiss()
                spinner_ref["dialog"] = None
            except Exception as e:
                self._log_error(f"[spinner dismiss] {e}")
        run_on_ui_thread(_ui)

    def _show_error_dialog(self, fragment, text):
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
                self._log_error(f"[error dialog] {e}")
        run_on_ui_thread(_ui)

    def _show_result_dialog(self, fragment, account, dialog_id, result_text):
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
                def on_send_chat(dialog, which):
                    try:
                        send_text(peer=dialog_id, text=result_text, account=account, parse_mode="Markdown")
                        self._toast(fragment, "Отправлено в чат")
                    except Exception as e:
                        self._log_error(f"[send chat] {e}")
                        self._toast(fragment, "Ошибка отправки в чат")
                    try:
                        dialog.dismiss()
                    except Exception:
                        pass
                def on_send_saved(dialog, which):
                    try:
                        saved_id = self._saved_messages_id(account, fallback=dialog_id)
                        send_text(peer=saved_id, text=result_text, account=account, parse_mode="Markdown")
                        self._toast(fragment, "Отправлено в Избранное")
                    except Exception as e:
                        self._log_error(f"[send saved] {e}")
                        self._toast(fragment, "Ошибка отправки в Избранное")
                    try:
                        dialog.dismiss()
                    except Exception:
                        pass
                bld.set_positive_button("В текущий чат", on_send_chat)
                bld.set_negative_button("В Избранное", on_send_saved)
                bld.set_neutral_button("Закрыть", lambda dialog, which: dialog.dismiss())
                bld.show()
            except Exception as e:
                self._log_error(f"[result dialog] {e}\n{traceback.format_exc()}")
                self._toast(fragment, "Ошибка показа результата")
        run_on_ui_thread(_ui)

    def _toast(self, fragment, text):
        def _ui():
            try:
                ctx = self._context_from_fragment(fragment)
                if ctx is not None:
                    Toast.makeText(ctx, text, Toast.LENGTH_SHORT).show()
            except Exception as e:
                self._log_error(f"[toast] {e}")
        run_on_ui_thread(_ui)

    def _log_info(self, text):
        try:
            self.log(text)
            log(text)
        except Exception:
            pass

    def _log_error(self, text):
        try:
            self.log(text)
            log(text)
        except Exception:
            pass

    def _collect_history(self, account, dialog_id, selected_id, fragment, max_count):
        api_msgs = self._from_tl_api(account, dialog_id, selected_id, max_count)
        if api_msgs:
            return api_msgs
        mem = self._from_fragment(account, dialog_id, fragment, selected_id, max_count)
        return mem or []

    def _from_fragment(self, account, dialog_id, fragment, selected_id, max_count):
        try:
            if fragment is None:
                return []
            msg_list = getattr(fragment, "messages", None)
            if msg_list is None:
                adapter = getattr(fragment, "chatAdapter", None)
                if adapter:
                    msg_list = getattr(adapter, "messages", None)
            if msg_list is None:
                return []
            result = []
            found_selected = False
            size = msg_list.size()
            for i in range(size):
                try:
                    mo = msg_list.get(i)
                    mid = self._msg_id(mo)
                    if mid == selected_id:
                        found_selected = True
                    if mid >= selected_id:
                        parsed = self._parse_mo(mo, account, dialog_id)
                        if parsed:
                            result.append(parsed)
                except Exception:
                    pass
            if not found_selected:
                return []
            result.sort(key=lambda x: x["id"])
            return result[:max_count]
        except Exception as e:
            self._log_error(f"[fragment] error: {e}\n{traceback.format_exc()}")
            return []

    def _from_tl_api(self, account, dialog_id, selected_id, max_count):
        try:
            from org.telegram.tgnet import TLRPC
            peer = self._resolve_input_peer(account, dialog_id)
            if peer is None:
                return []
            all_raw = []
            seen_ids = set()
            current_offset_id = int(selected_id)
            is_first_chunk = True
            fetches = 0
            step = 100
            while len(all_raw) < max_count and fetches < 80:
                fetches += 1
                limit = min(step, max_count - len(all_raw))
                req = TLRPC.TL_messages_getHistory()
                req.peer = peer
                req.offset_id = current_offset_id
                req.offset_date = 0
                req.add_offset = -(limit - 1) if is_first_chunk else -limit
                req.limit = limit
                req.max_id = 0
                req.min_id = int(selected_id) - 1
                req.hash = 0
                resp = self._sync_send(req, timeout=30)
                if resp is None:
                    break
                messages_array = getattr(resp, "messages", None)
                if messages_array is None:
                    break
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
                fresh = []
                for m in batch:
                    try:
                        mid = int(m.id)
                        if mid not in seen_ids and mid >= selected_id:
                            seen_ids.add(mid)
                            fresh.append(m)
                    except Exception:
                        pass
                if not fresh:
                    break
                all_raw.extend(fresh)
                ids = [int(m.id) for m in fresh if hasattr(m, "id")]
                if not ids:
                    break
                current_offset_id = min(ids)
                is_first_chunk = False
            result = []
            for raw in all_raw:
                try:
                    mid = int(raw.id)
                    if mid < selected_id:
                        continue
                    text = str(raw.message) if getattr(raw, "message", None) else ""
                    date = int(raw.date) if hasattr(raw, "date") else 0
                    author = self._author_from_raw(account, raw, dialog_id)
                    result.append({"id": mid, "date": date, "author": author, "text": text})
                except Exception:
                    pass
            result.sort(key=lambda x: x["id"])
            return result[:max_count]
        except Exception as e:
            self._log_error(f"[tl_api] error: {e}\n{traceback.format_exc()}")
            return []

    def _resolve_input_peer(self, account, dialog_id):
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
            self._log_error(f"[peer] resolve error: {e}")
            return None

    def _sync_send(self, request, timeout=30):
        event = threading.Event()
        holder = [None, None]
        def _cb(response, error, _h=holder, _e=event):
            _h[0] = response
            _h[1] = error
            _e.set()
        send_request(request, RequestCallback(_cb))
        event.wait(timeout=timeout)
        return holder[0]

    def _extract_text(self, mo):
        try:
            if hasattr(mo, "messageText") and mo.messageText is not None:
                return str(mo.messageText.toString())
        except Exception:
            pass
        try:
            if hasattr(mo, "caption") and mo.caption is not None:
                return str(mo.caption.toString())
        except Exception:
            pass
        try:
            if hasattr(mo, "messageOwner") and mo.messageOwner is not None and hasattr(mo.messageOwner, "message") and mo.messageOwner.message is not None:
                return str(mo.messageOwner.message)
        except Exception:
            pass
        return ""

    def _parse_mo(self, mo, account, dialog_id):
        try:
            mid = self._msg_id(mo)
            text = self._extract_text(mo)
            is_out = False
            try:
                if hasattr(mo, "isOut") and callable(mo.isOut):
                    is_out = mo.isOut()
                else:
                    owner = mo.getMessageOwner()
                    if owner and hasattr(owner, "out"):
                        is_out = owner.out
            except Exception:
                pass
            if is_out:
                author = self._get_my_name(account)
            else:
                author = None
                try:
                    owner = mo.getMessageOwner()
                    fid = getattr(owner, "from_id", None) if owner else None
                    if fid is not None:
                        if hasattr(fid, "user_id"):
                            author = self._user_name(int(fid.user_id))
                        elif hasattr(fid, "channel_id"):
                            author = "Канал"
                        elif hasattr(fid, "chat_id"):
                            author = "Группа"
                except Exception:
                    pass
                if not author:
                    author = "Админ / Канал" if int(dialog_id) < 0 else self._user_name(int(dialog_id))
            date = 0
            try:
                owner = mo.getMessageOwner()
                if owner:
                    date = int(getattr(owner, "date", 0) or 0)
            except Exception:
                pass
            return {"id": mid, "date": date, "author": author, "text": text}
        except Exception as e:
            self._log_error(f"[parse_mo] {e}")
            return None

    def _author_from_raw(self, account, raw, dialog_id):
        try:
            if getattr(raw, "out", False):
                return self._get_my_name(account)
            fid = getattr(raw, "from_id", None)
            if fid is not None:
                if hasattr(fid, "user_id"):
                    return self._user_name(int(fid.user_id))
                if hasattr(fid, "channel_id"):
                    return "Канал"
                if hasattr(fid, "chat_id"):
                    return "Группа"
            return "Админ / Канал" if int(dialog_id) < 0 else self._user_name(int(dialog_id))
        except Exception:
            return "Неизвестный"

    def _user_name(self, user_id):
        try:
            from org.telegram.messenger import MessagesController, UserConfig
            account = UserConfig.selectedAccount
            mc = MessagesController.getInstance(account)
            user = mc.getUser(user_id)
            if user:
                fn = (getattr(user, "first_name", "") or "").strip()
                ln = (getattr(user, "last_name", "") or "").strip()
                name = f"{fn} {ln}".strip() if ln else fn
                return name or getattr(user, "username", None) or f"Пользователь_{user_id}"
        except Exception:
            pass
        return f"Пользователь_{user_id}"

    def _msg_id(self, mo):
        for attr in ("getId", "get_id"):
            try:
                v = getattr(mo, attr, None)
                if v is not None:
                    return int(v() if callable(v) else v)
            except Exception:
                pass
        try:
            return int(mo.getMessageOwner().id)
        except Exception:
            return 0

    def _format_message_datetime(self, ts):
        try:
            import datetime
            if not ts:
                return ""
            return datetime.datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M")
        except Exception:
            return ""

    def _build_transcript(self, messages, include_sender, include_datetime=False):
        lines = []
        for m in messages:
            text = (m.get("text") or "").strip()
            if not text:
                continue
            prefix_parts = []
            if include_datetime:
                dt = self._format_message_datetime(m.get("date", 0))
                if dt:
                    prefix_parts.append(dt)
            if include_sender:
                prefix_parts.append(m['author'])
            if prefix_parts:
                lines.append(f"[{' | '.join(prefix_parts)}]: {text}")
            else:
                lines.append(text)
        return "\n".join(lines)

    def _call_llm(self, api_type, url, api_key, model, system_prompt, user_content):
        if api_type == 0:
            payload = {"model": model, "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_content}], "temperature": 0.15}
        else:
            payload = {"model": model, "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_content}], "stream": False, "options": {"temperature": 0.15, "num_predict": 2048}}
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        resp = requests.post(url, json=payload, headers=headers, timeout=180)
        if not resp.ok:
            raise RuntimeError(f"HTTP {resp.status_code} от LLM:\n{resp.text[:600]}")
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip() if api_type == 0 else data["message"]["content"].strip()

    def _saved_messages_id(self, account, fallback):
        try:
            from org.telegram.messenger import UserConfig
            uid = UserConfig.getInstance(account).getClientUserId()
            if uid and uid != 0:
                return int(uid)
        except Exception as e:
            self._log_error(f"[saved] {e}")
        return fallback
