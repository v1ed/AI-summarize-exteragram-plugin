__id__ = "ai-chat-summarizer"
__name__ = "AI Chat Summarizer & Fact Checker"
__author__ = "@edward_vishnevsky"
__version__ = "0.5.0"
__min_version__ = "0.0.1"
__description__ = "Собирает сообщения, отправляет в LLM, поддерживает разные API, персонажей стилизации (только с GitHub), экспериментальный режим и редактируемые промпты."

import json
import threading
import traceback
import requests
import urllib.parse
import datetime

from base_plugin import BasePlugin, MenuItemData, MenuItemType
from ui.settings import Header, Divider, Input, EditText, Switch, Selector, Text
from client_utils import run_on_queue, send_text, send_request, RequestCallback
from android_utils import run_on_ui_thread
from java import jclass

Toast = jclass("android.widget.Toast")
AndroidLog = jclass("android.util.Log")

_DEFAULT_URL = "http://192.168.1.100:11434/v1/chat/completions"
_DEFAULT_MODEL = "llama3.2"
_DEFAULT_LIMIT = "300"
_MAX_CHARS = 28000

_DEFAULT_CHARACTERS_GITHUB_URL = "https://raw.githubusercontent.com/v1ed/AI-summarize-exteragram-plugin/main/characters.json"

_DEFAULT_PROMPT_FULL = """Ты — профессиональный аналитик текстовой переписки Telegram. Твоя задача — проанализировать предоставленный транскрипт чата.
Анализируй только текст сообщений, полностью игнорируй системные сообщения о добавлении картинок, файлов и других вложений.
ОБЯЗАТЕЛЬНО обращай внимание на контекст (личные сообщения, группа или канал) и имена авторов сообщений. Ты должен четко понимать, кто, кому и что именно говорит, кто выдвигает какие тезисы и как на них реагируют другие участники.

СТРУКТУРА ОТВЕТА:

## 📝 Краткое содержание
Опиши основную тему обсуждения, вектор развития разговора и к какому итогу пришли участники.

## 🎯 Ключевые тезисы
Сформируй структурированный маркерный (bullet) список главных утверждений, договорённостей, идей и решений. Обязательно указывай авторов, если в беседе участвует больше одного человека.

## 🔍 Проверка фактов
Найди в тексте утверждения, которые подаются как объективные факты. Для каждого проверяемого утверждения:
- Утверждение: "..."
- Статус: [Подтверждено в беседе / Сомнительно / Не подтверждено / Требует внешней проверки]
- Комментарий: кратко объясни причину такого статуса на основе текста.
Если проверяемых фактов в тексте нет — напиши об этом явно.

Отвечай на том же языке, на котором ведется переписка."""

_DEFAULT_PROMPT_SUMMARY_ONLY = """Ты — профессиональный аналитик текстовой переписки Telegram. Твоя задача — сделать качественную выжимку предоставленного транскрипта чата.
Анализируй только текст сообщений, полностью игнорируй картинки, файлы и другие вложений.
Учитывай источник и имена авторов, чтобы правильно передать динамику диалога.

СТРУКТУРА ОТВЕТА:

## 📝 Краткое содержание
Опиши основную тему обсуждения, ход разговора и итоговый результат.

## 🎯 Ключевые тезисы
Сформируй маркерный список главных мыслей, аргументов, договорённостей и решений. Обязательно указывай авторов конкретных идей.

Отвечай на том же языке, на котором ведется переписка."""

_DEFAULT_PROMPT_FACTCHECK_ONLY = """Ты — строгий и беспристрастный факт-чекер. Твоя задача — проанализировать предоставленный транскрипт Telegram-чата исключительно на предмет достоверности озвучиваемых данных.
Анализируй только текст сообщений, игнорируй вложения. НЕ делай общую суммаризацию разговора. Ищи только те утверждения, которые преподносятся как объективные факты.

Для каждого найденного утверждения выведи:
- Утверждение: "..." (с указанием автора)
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
    def _log_debug(self, text):
        try:
            AndroidLog.d("AiChatSummarizer", str(text))
        except Exception:
            pass

    def _log_info(self, text):
        try:
            AndroidLog.i("AiChatSummarizer", str(text))
        except Exception:
            pass

    def _log_error(self, text):
        try:
            AndroidLog.e("AiChatSummarizer", str(text))
        except Exception:
            pass

    def on_plugin_load(self):
        self._log_info("=== Инициализация плагина (on_plugin_load) ===")
        try:
            self.add_menu_item(MenuItemData(
                menu_type=MenuItemType.MESSAGE_CONTEXT_MENU,
                text="Суммаризация / фактчек от этого сообщения",
                item_id="ollama_summarize_popup",
                icon="msg_search",
                subtext="AI Анализ",
                priority=90,
                on_click=self._on_menu_click,
            ))
            self._log_info("Пункт контекстного меню успешно добавлен.")
        except Exception as e:
            self._log_error(f"Не удалось добавить пункт меню: {e}\n{traceback.format_exc()}")
            
        self._user_cache = {}
        self._log_debug("Кэш пользователей инициализирован.")
        
        self._refresh_remote_characters(silent=True)
        self._log_info("=== Плагин успешно загружен ===")

    def on_plugin_unload(self):
        self._log_info("Плагин выгружен")

    def _normalize_character_item(self, item):
        self._log_debug(f"Нормализация персонажа: {item}")
        if not isinstance(item, dict):
            return None
        emoji = str(item.get("emoji", "🙂")).strip() or "🙂"
        name = str(item.get("name", "")).strip()
        prompt = str(item.get("prompt", "")).strip()
        if not name:
            self._log_debug("Персонаж пропущен из-за отсутствия имени.")
            return None
        return {"emoji": emoji, "name": name, "prompt": prompt}

    def _get_remote_characters(self):
        self._log_debug("Чтение персонажей из локального кэша (настройки плагина).")
        raw = str(self.get_setting("remote_characters_json", "")).strip()
        if not raw:
            self._log_debug("Кэш персонажей пуст.")
            return []
        try:
            data = json.loads(raw)
            if not isinstance(data, list):
                return []
            out = []
            for item in data:
                norm = self._normalize_character_item(item)
                if norm:
                    out.append(norm)
            self._log_debug(f"Успешно прочитано {len(out)} персонажей из локального кэша.")
            return out
        except Exception as e:
            self._log_error(f"[remote characters parse] Ошибка парсинга кэша: {e}")
            return []

    def _get_character_presets(self):
        remote_items = self._get_remote_characters()
        custom_item = None
        merged = []
        seen = set()

        for item in remote_items:
            normalized = self._normalize_character_item(item)
            if not normalized:
                continue

            is_custom = (
                normalized.get("prompt") == "__custom__"
                or normalized.get("name", "").strip().casefold() == "свой персонаж".casefold()
            )

            if is_custom:
                custom_item = {"emoji": normalized["emoji"], "name": normalized["name"], "prompt": "__custom__"}
                continue

            key = (normalized["name"].casefold(), normalized["prompt"])
            if key in seen:
                continue
            seen.add(key)
            merged.append(normalized)

        merged.sort(key=lambda x: x["name"].casefold())

        if custom_item is None:
            custom_item = {"emoji": "🛠️", "name": "Свой персонаж", "prompt": "__custom__"}

        merged.append(custom_item)
        self._log_debug(f"Сформирован итоговый список из {len(merged)} персонажей.")
        return merged

    def _get_character_labels(self):
        return [f"{c['emoji']} {c['name']}" for c in self._get_character_presets()]

    def _get_custom_character_index(self):
        chars = self._get_character_presets()
        for i, item in enumerate(chars):
            if item.get("prompt") == "__custom__":
                return i
        return max(0, len(chars) - 1)

    def _download_remote_characters(self, url):
        self._log_info(f"Начало загрузки персонажей с GitHub: {url}")
        url = str(url or "").strip()
        if not url:
            raise ValueError("Пустой URL персонажей")
        headers = {"Accept": "application/json, text/plain, */*"}
        r = requests.get(url, headers=headers, timeout=6)
        r.raise_for_status()
        data = r.json()
        self._log_debug(f"JSON получен, размер массива: {len(data) if isinstance(data, list) else 'не массив'}")
        
        if not isinstance(data, list):
            raise ValueError("Ожидался JSON-массив персонажей")
        out = []
        for item in data:
            norm = self._normalize_character_item(item)
            if norm:
                out.append(norm)
        if not out:
            raise ValueError("Не найдено ни одного корректного персонажа")
        self._log_info(f"Успешно обработано {len(out)} персонажей из сети.")
        return out

    def _on_refresh_characters_click(self, *args):
        self._log_info("Ручной клик по обновлению персонажей в настройках.")
        self._refresh_remote_characters(silent=False)

    def _refresh_remote_characters(self, silent=False):
        self._log_info(f"Вызов _refresh_remote_characters. silent={silent}")
        def _job():
            try:
                url = self.get_setting("characters_github_url", _DEFAULT_CHARACTERS_GITHUB_URL)
                items = self._download_remote_characters(url)
                self.set_setting("remote_characters_json", json.dumps(items, ensure_ascii=False))
                self._log_debug("Кэш персонажей обновлен в настройках.")
                
                if not silent:
                    self.set_setting("character_index", 0)
                    self._log_debug("Индекс персонажа сброшен на 0.")
                
                try:
                    nonce = int(self.get_setting("experimental_refresh_nonce", 0)) + 1
                    self.set_setting("experimental_refresh_nonce", nonce, reload_settings=True)
                except Exception:
                    self.set_setting("experimental_refresh_nonce", 1, reload_settings=True)
                
                self._log_info(f"=== Успешно загружено {len(items)} персонажей с GitHub ===")
                
                if not silent:
                    def _ui():
                        try:
                            Toast.makeText(jclass("com.exteragram.messenger.ApplicationLoader").applicationContext, f"Персонажи обновлены: {len(items)}", Toast.LENGTH_SHORT).show()
                        except Exception as e:
                            self._log_error(f"Не удалось показать toast: {e}")
                    run_on_ui_thread(_ui)
            except Exception as e:
                self._log_error(f"Ошибка загрузки списка персонажей: {e}\n{traceback.format_exc()}")
                if not silent:
                    def _ui():
                        try:
                            Toast.makeText(jclass("com.exteragram.messenger.ApplicationLoader").applicationContext, "Не удалось обновить персонажей", Toast.LENGTH_SHORT).show()
                        except Exception:
                            pass
                    run_on_ui_thread(_ui)

        run_on_queue(_job)

    def _sort_models(self, models):
        uniq = []
        seen = set()
        for m in models:
            name = str(m).strip()
            if not name:
                continue
            key = name.casefold()
            if key in seen:
                continue
            seen.add(key)
            uniq.append(name)
        uniq.sort(key=lambda x: x.casefold())
        return uniq

    def _get_models_cache(self):
        self._log_debug("Получение кэша моделей.")
        cached_raw = str(self.get_setting("cached_models", _DEFAULT_MODEL))
        parts = [x.strip() for x in cached_raw.split("\n") if x.strip()]
        return parts or [_DEFAULT_MODEL]

    def _fetch_models(self):
        self._log_info("Сбор списка моделей с сервера...")
        try:
            api_type = int(self.get_setting("api_type", 0))
        except Exception:
            api_type = 0

        api_url = str(self.get_setting("api_url", _DEFAULT_URL)).strip()
        api_key = str(self.get_setting("api_key", "")).strip()
        fetched = []
        
        self._log_debug(f"API type: {api_type}, URL: {api_url}")

        try:
            parsed = urllib.parse.urlparse(api_url)
            base_url = f"{parsed.scheme}://{parsed.netloc}"
            headers = {}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            if api_type == 0:
                if api_url.endswith("/v1/chat/completions"):
                    models_url = api_url[:-len("/chat/completions")] + "/models"
                elif "/chat/completions" in api_url:
                    models_url = api_url.replace("/chat/completions", "/models")
                else:
                    models_url = f"{base_url}/v1/models"
                
                self._log_debug(f"Запрашиваем модели по адресу (OpenAI): {models_url}")
                r = requests.get(models_url, headers=headers, timeout=2.5)
                if r.ok:
                    data = r.json()
                    fetched = [str(m.get("id")) for m in data.get("data", []) if "id" in m]
            else:
                models_url = f"{base_url}/api/tags"
                self._log_debug(f"Запрашиваем модели по адресу (Ollama): {models_url}")
                r = requests.get(models_url, headers=headers, timeout=2.5)
                if r.ok:
                    data = r.json()
                    fetched = [str(m.get("name")) for m in data.get("models", []) if "name" in m]
        except Exception as e:
            self._log_error(f"Не удалось стянуть модели: {e}")

        self._log_info(f"Получено {len(fetched)} моделей.")
        return self._sort_models(fetched)

    def _on_experimental_mode_changed(self, *args):
        value = bool(args[-1]) if args else False
        self._log_info(f"Смена режима экспериментов на: {value}")
        self.set_setting("experimental_mode", value, reload_settings=True)

    def _on_character_changed(self, *args):
        try:
            idx = int(args[-1]) if args else 0
        except Exception:
            idx = 0
        self._log_info(f"Пользователь выбрал персонажа под индексом: {idx}")
        self.set_setting("character_index", idx, reload_settings=True)

    def _get_mode_prompt(self, mode):
        self._log_debug(f"Получение промпта для режима {mode}")
        if mode == 1:
            prompt = str(self.get_setting("prompt_summary_only", _DEFAULT_PROMPT_SUMMARY_ONLY)).strip()
            return prompt or _DEFAULT_PROMPT_SUMMARY_ONLY
        if mode == 2:
            prompt = str(self.get_setting("prompt_factcheck_only", _DEFAULT_PROMPT_FACTCHECK_ONLY)).strip()
            return prompt or _DEFAULT_PROMPT_FACTCHECK_ONLY
        prompt = str(self.get_setting("prompt_full", _DEFAULT_PROMPT_FULL)).strip()
        return prompt or _DEFAULT_PROMPT_FULL

    def create_settings(self):
        self._log_info("Вызов create_settings() для построения UI настроек.")
        old_cached = self._get_models_cache()

        try:
            old_idx = int(self.get_setting("model_index", 0))
        except Exception:
            old_idx = 0

        if old_idx < 0 or old_idx >= len(old_cached):
            old_idx = 0

        old_model = old_cached[old_idx]
        self._log_debug(f"Старая выбранная модель: {old_model} (index {old_idx})")
        
        fetched_models = self._fetch_models()

        if fetched_models:
            if old_model in fetched_models:
                model_idx = fetched_models.index(old_model)
                self._log_debug(f"Найдена старая модель в новом списке, новый индекс: {model_idx}")
            else:
                model_idx = 0
                self._log_debug(f"Старая модель не найдена в новом списке, ставим индекс 0 ({fetched_models[0]})")

            self.set_setting("cached_models", "\n".join(fetched_models))
            self.set_setting("model_index", model_idx)
            models_status = "Модели успешно загружены и отсортированы по алфавиту."
        else:
            self._log_debug("Список моделей не обновился, используем старый кэш.")
            fetched_models = old_cached
            models_status = "Внимание: не удалось получить список моделей с сервера. Отображаются сохраненные."

        chars = self._get_character_presets()
        char_labels = [f"{c['emoji']} {c['name']}" for c in chars]
        custom_idx = self._get_custom_character_index()

        try:
            current_character = int(self.get_setting("character_index", 0))
        except Exception:
            current_character = 0

        if current_character < 0 or current_character >= len(chars):
            current_character = 0

        settings_list = [
            Header(text="Настройки API"),
            Selector(
                key="api_type",
                text="Тип API",
                default=0,
                items=["OpenAI-совместимый (OpenWebUI, v1)", "Ollama Native API (/api/chat)"]
            ),
            Input(
                key="api_url",
                text="API URL",
                default=_DEFAULT_URL,
                subtext="OpenAI/OpenWebUI: http://.../v1/chat/completions\nOllama Native: http://.../api/chat"
            ),
            Input(
                key="api_key",
                text="API Key / Bearer Token",
                default="",
                subtext="Токен для OpenAI/OpenWebUI. Для локальной Ollama оставьте пустым."
            ),
            Divider(text="Выбор модели"),
            Selector(key="model_index", text="Выбрать модель", default=0, items=fetched_models),
            Text(text=models_status, accent=False),

            Divider(text="Параметры анализа"),
            Selector(
                key="detail_level",
                text="Подробность суммаризации",
                default=1,
                items=["Кратко (только суть)", "Нормально (сбалансированно)", "Подробно (сохранить все детали)"]
            ),
            Selector(
                key="mode",
                text="Режим работы",
                default=0,
                items=["Суммаризация + проверка фактов", "Только суммаризация", "Только проверка фактов"]
            ),
            Input(
                key="max_messages",
                text="Максимум сообщений",
                default=_DEFAULT_LIMIT,
                subtext="Ограничение на глубину сбора истории (10-2000)"
            ),
            Switch(
                key="include_sender",
                text="Указывать имена отправителей",
                default=True,
                subtext="Добавлять имя автора к каждому сообщению"
            ),
            Switch(
                key="include_datetime",
                text="Добавлять дату и время сообщений",
                default=False,
                subtext="Помогает модели ориентироваться во временных рамках переписки"
            ),

            Divider(text="Стилизация"),
            Selector(
                key="character_index",
                text="Персонаж",
                default=0,
                items=char_labels,
                on_change=self._on_character_changed
            ),
        ]

        if current_character == custom_idx:
            settings_list.append(
                EditText(
                    key="custom_character_prompt",
                    hint="Свой персонаж: опишите стиль, лексику, настроение и манеру речи",
                    default="",
                    multiline=True,
                    max_length=4000
                )
            )

        settings_list.extend([
            Divider(text="Дополнительно"),
            Switch(
                key="experimental_mode",
                text="Режим экспериментов",
                default=False,
                subtext="Открывает редактирование промптов и настроек GitHub",
                on_change=self._on_experimental_mode_changed
            ),
        ])

        if bool(self.get_setting("experimental_mode", False)):
            settings_list.extend([
                Divider(text="Промпты"),
                EditText(
                    key="prompt_summary_only",
                    hint="Промпт для режима только суммаризации",
                    default=_DEFAULT_PROMPT_SUMMARY_ONLY,
                    multiline=True,
                    max_length=12000
                ),
                EditText(
                    key="prompt_factcheck_only",
                    hint="Промпт для режима только факт-чекинга",
                    default=_DEFAULT_PROMPT_FACTCHECK_ONLY,
                    multiline=True,
                    max_length=12000
                ),
                EditText(
                    key="prompt_full",
                    hint="Промпт для объединенного режима",
                    default=_DEFAULT_PROMPT_FULL,
                    multiline=True,
                    max_length=12000
                ),

                Divider(text="Персонажи GitHub"),
                Input(
                    key="characters_github_url",
                    text="Ссылка на персонажей",
                    default=_DEFAULT_CHARACTERS_GITHUB_URL,
                    subtext="Raw GitHub URL на JSON-файл со списком персонажей"
                ),
                Text(
                    text="Обновить персонажей (вручную)",
                    accent=True,
                    on_click=self._on_refresh_characters_click
                ),
            ])

        self._log_debug("Настройки успешно построены.")
        return settings_list

    def _get_alert_builder(self):
        from ui.alert import AlertDialogBuilder
        return AlertDialogBuilder

    def _on_menu_click(self, ctx):
        self._log_info("=== Вызван _on_menu_click ===")
        try:
            message = ctx.get("message")
            dialog_id = ctx.get("dialog_id")
            account = ctx.get("account")
            fragment = ctx.get("fragment")
            if message is None or dialog_id is None or account is None:
                self._log_error(f"Не хватает ключей контекста в меню: {list(ctx.keys())}")
                return
            
            selected_id = self._msg_id(message)
            self._log_info(f"Контекст: message_id={selected_id}, dialog_id={dialog_id}, account={account}")
            spinner_ref = {"dialog": None}
            self._toast(fragment, "Начинаю сбор сообщений…")
            self._show_spinner(fragment, spinner_ref, "Анализирую историю…")
            
            run_on_queue(lambda: self._process(account=account, dialog_id=dialog_id, selected_id=selected_id, fragment=fragment, spinner_ref=spinner_ref))
        except Exception as e:
            self._log_error(f"Сбой при обработке клика в меню: {e}\n{traceback.format_exc()}")
            self._toast(ctx.get("fragment"), "Ошибка запуска плагина")

    def _process(self, account, dialog_id, selected_id, fragment, spinner_ref):
        self._log_info("=== Запуск фонового процесса сбора сообщений ===")
        try:
            api_url = str(self.get_setting("api_url", _DEFAULT_URL)).strip()
            api_key = str(self.get_setting("api_key", "")).strip()

            cached_models = self._get_models_cache()
            try:
                model_idx = int(self.get_setting("model_index", 0))
            except Exception:
                model_idx = 0
            if model_idx < 0 or model_idx >= len(cached_models):
                model_idx = 0
            model = cached_models[model_idx]
            self._log_info(f"Используемая LLM модель: {model}")

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
            custom_character_prompt = self.get_setting("custom_character_prompt", "").strip()

            characters = self._get_character_presets()
            if character_index < 0 or character_index >= len(characters):
                character_index = 0
            character = characters[character_index]

            if character.get("prompt") == "__custom__":
                character_prompt = custom_character_prompt
            else:
                character_prompt = str(character.get("prompt", "")).strip()

            try:
                max_msgs = max(10, min(2000, int(str(self.get_setting("max_messages", _DEFAULT_LIMIT)).strip())))
            except Exception:
                max_msgs = 300

            sys_prompt = self._get_mode_prompt(mode)
            if mode != 2:
                sys_prompt += f"\n\n{_DETAIL_LEVELS[detail_level].strip()}"

            if character_prompt:
                sys_prompt += (
                    "\n\nСТИЛИЗАЦИЯ ОТВЕТА:\n"
                    f"Оформи итоговый ответ в образе персонажа {character['emoji']} {character['name']}.\n"
                    f"{character_prompt}\n"
                    "Сохраняй фактическое содержание, структуру Markdown, полезность и читабельность ответа."
                )

            self._log_debug(f"Настройки анализа: Режим={mode}, Макс сообщений={max_msgs}, Персонаж={character['name']}")
            self._update_spinner(spinner_ref, "Загружаю историю чата…")
            
            chat_type_ru, chat_title = self._get_chat_info(account, dialog_id)
            self._log_info(f"Чат определен как: {chat_type_ru} ({chat_title})")
            
            self._log_info("Вызов _collect_history...")
            messages = self._collect_history(account=account, dialog_id=dialog_id, selected_id=selected_id, fragment=fragment, max_count=max_msgs)
            
            if not messages:
                self._dismiss_spinner(spinner_ref)
                self._log_error("Не удалось найти ни одного сообщения. _collect_history вернул пустой список.")
                self._toast(fragment, "Не удалось собрать сообщения")
                self._show_error_dialog(fragment, "Не удалось собрать сообщения для анализа. Попробуйте подгрузить историю чата выше (проскролльте вверх).")
                return

            self._log_info(f"Успешно собрано {len(messages)} сообщений для анализа.")
            transcript = self._build_transcript(messages, include_sender, include_datetime)
            
            truncated = False
            if len(transcript) > _MAX_CHARS:
                self._log_info(f"Длина транскрипта ({len(transcript)}) превышает лимит ({_MAX_CHARS}), обрезаем...")
                transcript = transcript[:_MAX_CHARS]
                truncated = True

            mode_label = ["Суммаризация + фактчек", "Суммаризация", "Проверка фактов"][mode] if mode in (0, 1, 2) else "Анализ"
            detail_label = ["Кратко", "Нормально", "Подробно"][detail_level] if detail_level in (0, 1, 2) else "Нормально"
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
            self._log_info("Отправка запроса к LLM...")
            
            llm_result = self._call_llm(api_type=api_type, url=api_url, api_key=api_key, model=model, system_prompt=sys_prompt, user_content=user_content)
            
            self._log_info(f"Успешный ответ от нейросети получен, длина ответа: {len(llm_result)} символов.")
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
            
            self._log_info("Формирование и показ финального диалога...")
            self._show_result_dialog(fragment, account, dialog_id, result_text)
        except Exception as e:
            self._dismiss_spinner(spinner_ref)
            self._log_error(f"Критическая ошибка в _process: {e}\n{traceback.format_exc()}")
            self._show_error_dialog(fragment, str(e)[:1500])

    def _get_chat_info(self, account, dialog_id):
        try:
            if dialog_id is None:
                return "чат", "Неизвестный чат"
            did = int(dialog_id)
            
            from org.telegram.messenger import MessagesController
            mc = MessagesController.getInstance(account)
            
            if did > 0:
                if did == self._saved_messages_id(account, 0):
                    return "избранное", "Избранное"
                title = self._user_name(account, did)
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
            self._log_error(f"[_get_chat_info] Ошибка получения информации о чате: {e}")
        return "чат", "Неизвестный чат"

    def _get_my_name(self, account):
        return "Вы"

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
            self._log_debug(f"Ошибка получения контекста: {e}")
            return None

    def _show_spinner(self, fragment, spinner_ref, title):
        self._log_debug(f"Показ спиннера: {title}")
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
                self._log_error(f"[spinner show] Ошибка показа спиннера: {e}")
        run_on_ui_thread(_ui)

    def _update_spinner(self, spinner_ref, title):
        self._log_debug(f"Обновление спиннера: {title}")
        def _ui():
            try:
                bld = spinner_ref.get("dialog")
                if bld:
                    bld.set_title(title)
            except Exception as e:
                self._log_error(f"[spinner update] Ошибка: {e}")
        run_on_ui_thread(_ui)

    def _dismiss_spinner(self, spinner_ref):
        self._log_debug("Скрытие спиннера")
        def _ui():
            try:
                bld = spinner_ref.get("dialog")
                if bld:
                    bld.dismiss()
                spinner_ref["dialog"] = None
            except Exception as e:
                self._log_error(f"[spinner dismiss] Ошибка скрытия: {e}")
        run_on_ui_thread(_ui)

    def _show_error_dialog(self, fragment, text):
        self._log_debug(f"Показ окна ошибки: {text[:50]}...")
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
                self._log_error(f"[error dialog] Ошибка показа: {e}")
        run_on_ui_thread(_ui)

    def _show_result_dialog(self, fragment, account, dialog_id, result_text):
        self._log_info("Показ финального окна с результатом")
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
                    self._log_info("Отправка результата в текущий чат...")
                    try:
                        send_text(peer=dialog_id, text=result_text, account=account, parse_mode="Markdown")
                        self._toast(fragment, "Отправлено в чат")
                    except Exception as e:
                        self._log_error(f"[send chat] Ошибка отправки: {e}")
                        self._toast(fragment, "Ошибка отправки в чат")
                    try:
                        dialog.dismiss()
                    except Exception:
                        pass
                
                def on_send_saved(dialog, which):
                    self._log_info("Отправка результата в Избранное...")
                    try:
                        # Получаем реальный ID текущего пользователя (это и есть чат Избранное)
                        from org.telegram.messenger import UserConfig
                        saved_id = UserConfig.getInstance(account).getClientUserId()
                        
                        send_text(peer=saved_id, text=result_text, account=account, parse_mode="Markdown")
                        self._toast(fragment, "Отправлено в Избранное")
                    except Exception as e:
                        self._log_error(f"[send saved] Ошибка: {e}")
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
                self._log_error(f"[result dialog] Ошибка окна: {e}\n{traceback.format_exc()}")
                self._toast(fragment, "Ошибка показа результата")
        run_on_ui_thread(_ui)

    def _toast(self, fragment, text):
        def _ui():
            try:
                ctx = self._context_from_fragment(fragment)
                if ctx is not None:
                    Toast.makeText(ctx, str(text), Toast.LENGTH_SHORT).show()
            except Exception as e:
                self._log_error(f"[toast] Ошибка: {e}")
        run_on_ui_thread(_ui)

    def _collect_history(self, account, dialog_id, selected_id, fragment, max_count):
        self._log_info("Попытка сбора сообщений через _from_tl_api (API)...")
        api_msgs = self._from_tl_api(account, dialog_id, selected_id, max_count)
        if api_msgs:
            self._log_info(f"Успех (API): собрано {len(api_msgs)} сообщений.")
            return api_msgs
            
        self._log_info("TL_API вернул пустоту. Фолбек на считывание _from_fragment (UI)...")
        mem = self._from_fragment(account, dialog_id, fragment, selected_id, max_count)
        self._log_info(f"Успех (UI): собрано {len(mem) if mem else 0} сообщений.")
        return mem or []

    def _from_fragment(self, account, dialog_id, fragment, selected_id, max_count):
        try:
            if fragment is None:
                self._log_debug("[_from_fragment] fragment = None")
                return []
            msg_list = getattr(fragment, "messages", None)
            if msg_list is None:
                adapter = getattr(fragment, "chatAdapter", None)
                if adapter:
                    msg_list = getattr(adapter, "messages", None)
            if msg_list is None:
                self._log_debug("[_from_fragment] msg_list = None")
                return []
            
            result = []
            found_selected = False
            size = msg_list.size()
            self._log_debug(f"[_from_fragment] msg_list size: {size}")
            
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
                except Exception as ex_inner:
                    self._log_debug(f"[_from_fragment] Ошибка парсинга элемента {i}: {ex_inner}")
            
            if not found_selected:
                self._log_error(f"[_from_fragment] Стартовое сообщение {selected_id} не найдено в списке!")
                return []
                
            result.sort(key=lambda x: x["id"])
            return result[:max_count]
        except Exception as e:
            self._log_error(f"[_from_fragment] Критическая ошибка: {e}\n{traceback.format_exc()}")
            return []

    def _from_tl_api(self, account, dialog_id, selected_id, max_count):
        try:
            from org.telegram.tgnet import TLRPC
            peer = self._resolve_input_peer(account, dialog_id)
            if peer is None:
                self._log_error("[_from_tl_api] Не удалось разрешить peer!")
                return []
                
            self._log_debug(f"[_from_tl_api] Peer получен. Начинаем цикл стягивания, макс. кол-во: {max_count}")
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
                    self._log_debug(f"[_from_tl_api] Ответ пустой на шаге {fetches}")
                    break
                messages_array = getattr(resp, "messages", None)
                if messages_array is None:
                    self._log_debug(f"[_from_tl_api] Массив messages пуст на шаге {fetches}")
                    break
                    
                batch = []
                try:
                    if hasattr(messages_array, "size"):
                        for i in range(messages_array.size()):
                            batch.append(messages_array.get(i))
                    else:
                        batch = list(messages_array)
                except Exception as ex_arr:
                    self._log_debug(f"[_from_tl_api] Ошибка итерации массива: {ex_arr}")
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
                
            self._log_debug(f"[_from_tl_api] Сырых сообщений собрано: {len(all_raw)}")
            
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
                except Exception as ex_m:
                    self._log_debug(f"[_from_tl_api] Ошибка парсинга raw: {ex_m}")
                    pass
            result.sort(key=lambda x: x["id"])
            return result[:max_count]
        except Exception as e:
            self._log_error(f"[_from_tl_api] Ошибка: {e}\n{traceback.format_exc()}")
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

    def _extract_text(self, mo):
        if mo is None:
            return ""
        candidates = []
        for attr in ("messageText", "text", "caption", "message"):
            try:
                value = getattr(mo, attr, None)
                if isinstance(value, str) and value.strip():
                    candidates.append(value)
            except Exception:
                pass
        for meth in ("getMessageText", "getCaption", "getText"):
            try:
                fn = getattr(mo, meth, None)
                if callable(fn):
                    value = fn()
                    if isinstance(value, str) and value.strip():
                        candidates.append(value)
            except Exception:
                pass
        try:
            owner = getattr(mo, "messageOwner", None)
            if owner is not None:
                for attr in ("message", "messageText", "text", "caption"):
                    value = getattr(owner, attr, None)
                    if isinstance(value, str) and value.strip():
                        candidates.append(value)
        except Exception:
            pass
        for value in candidates:
            if value and value.strip():
                return value.strip()
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
                            author = self._user_name(account, int(fid.user_id))
                        elif hasattr(fid, "channel_id"):
                            author = "Канал"
                        elif hasattr(fid, "chat_id"):
                            author = "Группа"
                except Exception:
                    pass
                if not author:
                    author = "Админ / Канал" if int(dialog_id) < 0 else self._user_name(account, int(dialog_id))
                    
            date = 0
            try:
                owner = mo.getMessageOwner()
                if owner:
                    date = int(getattr(owner, "date", 0) or 0)
            except Exception:
                pass
                
            return {"id": mid, "date": date, "author": author, "text": text}
        except Exception as e:
            self._log_error(f"[parse_mo] Ошибка: {e}")
            return None

    def _author_from_raw(self, account, raw, dialog_id):
        if raw is None:
            return "Неизвестно"
        try:
            out = getattr(raw, "out", False)
            if out:
                return self._get_my_name(account)
        except Exception:
            pass
        user_id = None
        for attr in ("from_id", "user_id", "sender_id", "fromId"):
            try:
                value = getattr(raw, attr, None)
                if isinstance(value, int):
                    user_id = value
                    break
                if hasattr(value, "user_id"):
                    user_id = int(getattr(value, "user_id"))
                    break
                if hasattr(value, "channel_id"):
                    user_id = int(getattr(value, "channel_id"))
                    break
            except Exception:
                pass
        if user_id is not None:
            return self._user_name(account, user_id)
        return "Неизвестно"

    def _user_name(self, account, user_id):
        try:
            uid = int(user_id)
            if uid in self._user_cache:
                return self._user_cache[uid]
                
            from org.telegram.messenger import MessagesController
            mc = MessagesController.getInstance(account)
            user = mc.getUser(uid)
            if user:
                first = getattr(user, "first_name", "") or ""
                last = getattr(user, "last_name", "") or ""
                full_name = f"{first} {last}".strip()
                if not full_name:
                    full_name = getattr(user, "username", "") or ""
                if full_name:
                    self._user_cache[uid] = full_name
                    self._log_debug(f"[_user_name] Пользователь {uid} разрешен как {full_name}")
                    return full_name
        except Exception as e:
            self._log_error(f"[_user_name] Ошибка: {e}")
            
        return f"User {user_id}"

    def _msg_id(self, mo):
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

    def _format_message_datetime(self, ts):
        try:
            if not ts:
                return ""
            dt = datetime.datetime.fromtimestamp(int(ts))
            return dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return ""

    def _build_transcript(self, messages, include_sender, include_datetime=False):
        self._log_debug(f"Построение транскрипта из {len(messages)} сообщений...")
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
        self._log_debug(f"LLM API вызов: тип={api_type}, URL={url}")
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
            self._log_debug("Отправка POST запроса к OpenAI-совместимому API")
            r = requests.post(url, headers=headers, json=payload, timeout=120)
            self._log_debug(f"Код ответа: {r.status_code}")
            r.raise_for_status()
            data = r.json()
            choices = data.get("choices", [])
            if choices:
                msg = choices[0].get("message", {})
                content = msg.get("content")
                if isinstance(content, str):
                    return content.strip()
            if "text" in data and isinstance(data["text"], str):
                return data["text"].strip()
            raise RuntimeError("Пустой ответ от OpenAI-совместимого API")

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            "stream": False
        }
        self._log_debug("Отправка POST запроса к Ollama Native API")
        r = requests.post(url, headers=headers, json=payload, timeout=120)
        self._log_debug(f"Код ответа: {r.status_code}")
        r.raise_for_status()
        data = r.json()
        if isinstance(data.get("message"), dict):
            content = data["message"].get("content")
            if isinstance(content, str):
                return content.strip()
        if isinstance(data.get("response"), str):
            return data["response"].strip()
        raise RuntimeError("Пустой ответ от Ollama API")

    def _saved_messages_id(self, account, fallback):
        try:
            saved = int(self.get_setting("saved_messages_dialog_id", 0))
            if saved:
                return saved
        except Exception:
            pass
        return fallback