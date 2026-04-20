from typing import Any, List, Literal, Optional
from collections import defaultdict
import datetime

from base_plugin import BasePlugin, HookResult, HookStrategy
from ui.settings import Header, Input, Text
__requirements__ = ["pydantic"]

__id__ = "ai_chat_summarizer"
__name__ = "AI Chat Summarizer & Fact Checker"
__author__ = "@edward_vishnevsky"
__version__ = "0.5.0"
__min_version__ = "0.0.1"
__description__ = "тест"

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
    DISABLED: -1
    DEBUG:    0
    INFO:     1
    WARNING:  2
    ERROR:    3
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
    
    def log(self, level: Literal["debug", "info", "warn", "error"], message: str, exc: Optional[Exception]):
        self.logs.append({
            'timestamp': datetime.datetime.now().isoformat(),
            'level': level,
            'message': message,
        })
    
    def clear(self):
        self.logs = []


logger = Log()


class Plugin(BasePlugin):
    def log_debug(self, text):
        if LOG_LEVEL >= 0:
            self.log(f"[DEBUG]\t{text}")
            logger.log(
                level='debug',
                message=text,
            )

    def log_info(self, text):
        if LOG_LEVEL >= 1:
            self.log(f"[INFO]\t{text}")
            logger.log(
                level='info',
                message=text,
            )

    def log_warn(self, text):
        if LOG_LEVEL >= 2:
            self.log(f"[WARN]\t{text}")
            logger.log(
                level='warn',
                message=text,
            )
    
    def log_error(self, text):
        if LOG_LEVEL >= 3:
            self.log(f"[ERROR]\t{text}")
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

        return super().on_plugin_load()

    def create_settings(self):
        self.log_debug("Building settings")
        '''
        ai                      Настройки ИИ
            ai_api_type:    str     Тип API
            ai_api_link:    str     Ссылка на API
            ai_api_key:     str     Ключ доступа API
            ai_mdl_idx:     int     Индекс модели
        
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
        pass