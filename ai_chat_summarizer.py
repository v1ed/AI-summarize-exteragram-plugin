from typing import Any, List, Literal, Optional
from collections import defaultdict
import datetime
import requests
import urllib.parse

from base_plugin import BasePlugin, HookResult, HookStrategy
from ui.settings import Header, Divider, Input, EditText, Switch, Selector, Text

__id__ = "ai_chat_summarizer"
__name__ = "AI Chat Summarizer & Fact Checker"
__author__ = "@edward_vishnevsky"
__version__ = "0.5.0"
__description__ = "qweqweqweqweqweqweqweqweqwe qweqweqweqweqweqweqweqweqwe"

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
LOGS_ENABLED = True
DEFAULT_CHARACTERS_LINK = ""
DEFAULT_SYSTEM_PROMPTS_LINK = ""


class Character:
    def __init__(self, emoji: str, name: str, prompt: str):
        self.emoji = emoji
        self.name = name
        self.prompt = prompt


class Log:
    def __init__(self):
        self.logs = []
    
    def log(self, level: Literal["debug", "info", "warn", "error"], message: str, exc: Optional[Exception] = None):
        self.logs.append({
            'timestamp': datetime.datetime.now().isoformat(),
            'level': level,
            'message': message,
        })
    
    def clear(self):
        self.logs = []
    
    def get(self):
        return self.logs
    
    def __str__(self):
        s = ''
        for log in self.logs:
            s += f"{log['timestamp']}\t{log['level']}\t{log['message']}\n"
        return s

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
        fetched = []

        # parsed = urllib.parse.urlparse(api_url)
        # base_url = f"{parsed.scheme}://{parsed.netloc}"
        headers = {}
        headers["Authorization"] = f"Bearer {api_key}"
        if api_type == 0:
            models_url = f"{url}{'/' if not url.endswith('/') else ''}models"
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
        return fetched


class Plugin(BasePlugin):
    def log_debug(self, text):
        if LOG_LEVEL <= 0:
            self.log(f"[DEBUG]\t{text}")
            if LOGS_ENABLED:
                logger.log(
                    level='debug',
                    message=text,
                )

    def log_info(self, text):
        if LOG_LEVEL <= 1:
            self.log(f"[INFO]\t{text}")
            logger.log(
                level='info',
                message=text,
            )

    def log_warn(self, text):
        if LOG_LEVEL <= 2:
            self.log(f"[WARN]\t{text}")
            if LOGS_ENABLED:
                logger.log(
                level='warn',
                message=text,
            )
    
    def log_error(self, text):
        if LOG_LEVEL <= 3:
            self.log(f"[ERROR]\t{text}")
            if LOGS_ENABLED:
                logger.log(
                level='error',
                message=text,
            )

    def on_plugin_load(self):
        self.log_info("Plugin loading started")
        # Проверить настройки

        # Подгрузить список персонажей

        # Проверить доступность модели

        # Добавить пункт меню
        # self.add_menu_item(MenuItemData(
        #     menu_type=MenuItemType.MESSAGE_CONTEXT_MENU,
        #     text="Суммаризация / фактчек от этого сообщения",
        #     item_id="ollama_summarize_popup",
        #     icon="msg_search",
        #     subtext="AI Анализ",
        #     priority=90,
        #     on_click=self._on_menu_click,
        # ))
        self.log_info("Plugin loaded")

    def create_settings(self):
        self.log_debug("Building settings")
        '''
        ai                      Настройки ИИ
            ai_api_type:    str     Тип API
            ai_api_url:    str     Ссылка на API
            ai_api_key:     str     Ключ доступа API
            ai_mdl_idx:     int     Индекс модели
            cache:
                ai_cache_mdls:  list
        
        req                     Настройки запроса
            req_lod:        int     Уровень детализации (0 - оч. кратко; 2 - оч. подробно)
            req_mode:       int     Режим работы (Сум. + ф-ч.; сум.; ф-ч.)
            req_max_msg:    int     Максимальное кол-во сообщений для сбора
        
        chrctr                  Настройки персонажа
            chrctr_idx:     int             Индекс персонажа
            chrctr_prompt:  Optional[str]   Промпт персонажа (Если выбран кастомный)
        
        exp:                    Экспериментальные опции
            exp_enabled:    bool    Вкл./выкл.
            exp_sys_sumfch: str     Системный промпт суммаризации и факт-чекинга 
            exp_sys_sum:    str     Системный промпт суммаризации
            exp_sys_fch:    str     Системный промпт факт-чекинга
            exp_gh_chr_lnk: str     Ссылка на JSON с персонажами
            exp_dev_mode:   bool    Вкл./выкл. режим разработчика

        dev                     Режим разработчика
            dev_log_lvl:    int     Уровень логов
            dev_logs:       toggle  Выгрузка логов
            dev_clear:      toggle  Очистка логов
        '''
        ai_settings_list = [
            Header(text="Настройки API"),
            Selector(key="ai_api_type", text="Тип API", default=0, items=["OpenAI-совместимый", "Ollama Native API"]),
            Input(key="ai_api_url", text="API URL", default="", subtext="OpenAI: http://.../v1/\nOllama Native: http://.../api/"),
            Input(key="ai_api_key", text="API Key / Bearer Token", default="", subtext="Токен для OpenAI/OpenWebUI. Для локальной Ollama оставьте пустым.")
        ]
        cached_models = self.get_setting("ai_cache_mdls", [])
        cached_idx = int(self.get_setting("ai_mdl_idx", 0))

        if cached_idx >= len(cached_models):
            cached_idx = 0

        cached_selected_model = ''
        if cached_idx:
            cached_selected_model = cached_models[cached_idx]
        
        fetched_models = []
        try:
            api_type = int(self.get_setting("ai_api_type", ""))
            api_url = str(self.get_setting("ai_api_url", ""))
            api_key = str(self.get_setting("ai_api_key", ""))
            fetched_models = LLM.fetch_models(
                url=api_url,
                api_type=api_type,
                api_key=api_key
            )
        except Exception as e:
            self.log_error(f"{str(e)}")
        
        if fetched_models:
            if cached_selected_model in fetched_models:
                self.set_setting("ai_mdl_idx", fetched_models.index(cached_selected_model))
            else:
                self.set_setting("ai_mdl_idx", 0)
            self.set_setting("ai_cache_mdls", fetched_models)
            ai_settings_list.append(Selector(key="ai_mdl_idx", text="Выбрать модель", default=0, items=fetched_models))

        dev_settings_list = [
            EditText(
                key="dev_logs",
                hint="Логи",
                default=str(logger),
                multiline=True,
                max_length=12000
            )
        ]
        # ai_settings_list = [
        #     Header(text="Настройки API"),
        #     Selector(key="ai_api_type", text="Тип API", default=0, items=["OpenAI-совместимый", "Ollama Native API"]),
        #     Input(key="ai_api_url", text="API URL", default="", subtext="OpenAI: http://.../v1/\nOllama Native: http://.../api/"),
        #     Input(key="ai_api_key", text="API Key / Bearer Token", default="", subtext="Токен для OpenAI/OpenWebUI. Для локальной Ollama оставьте пустым."),
        #     Selector(key="ai_mdl_idx", text="Выбрать модель", default=0, items=fetched_models),
            
        #     # Divider(text="Параметры анализа"),
        #     # Selector(key="detail_level", text="Подробность суммаризации", default=1, items=["Кратко (только суть)", "Нормально (сбалансированно)", "Подробно (сохранить все детали)"]),
        #     # Selector(key="mode", text="Режим работы", default=0, items=["Суммаризация + проверка фактов", "Только суммаризация", "Только проверка фактов"]),
        #     # Input(key="max_messages", text="Максимум сообщений", default=_DEFAULT_LIMIT, subtext="Ограничение на глубину сбора истории (10-2000)"),
        #     # Switch(key="include_sender", text="Указывать имена отправителей", default=True, subtext="Добавлять имя автора к каждому сообщению"),
        #     # Switch(key="include_datetime", text="Добавлять дату и время сообщений", default=False, subtext="Помогает модели ориентироваться во временных рамках переписки"),
        #     # Divider(text="Стилизация"),
        #     # Selector(key="character_index", text="Персонаж", default=0, items=CHARACTER_LABELS),
        # ]
        settings_list = ai_settings_list + dev_settings_list
        return settings_list