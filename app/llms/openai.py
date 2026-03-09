import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator, Awaitable
from typing import Any

from loguru import logger
from openai import AsyncOpenAI

from app.configs.llms.base import BaseLlmConfig
from app.configs.llms.openai import OpenAIConfig
from app.llms.base import LLMBase
from app.utils.utils import extract_json


class AsyncOpenAILLM(LLMBase):
    def __init__(self, config: BaseLlmConfig | OpenAIConfig | dict | None = None):
        # При необходимости конвертирует в OpenAIConfig
        if config is None:
            config = OpenAIConfig()
        elif isinstance(config, dict):
            config = OpenAIConfig(**config)
        elif isinstance(config, BaseLlmConfig) and not isinstance(config, OpenAIConfig):
            # Конвертирование BaseLlmConfig в OpenAIConfig
            config = OpenAIConfig(
                model=config.model,
                temperature=config.temperature,
                api_key=config.api_key,
                max_tokens=config.max_tokens,
                top_p=config.top_p,
                top_k=config.top_k,
            )

        super().__init__(config)

        if not self.config.model:
            self.config.model = "gpt-5-nano"

        if os.environ.get("OPENROUTER_API_KEY"):  # Использование OpenRouter
            base_url: str = "https://openrouter.ai/api/v1"
            if isinstance(self.config, OpenAIConfig) and self.config.openrouter_base_url:
                base_url = self.config.openrouter_base_url
            elif os.getenv("OPENROUTER_BASE_URL"):
                env_url = os.getenv("OPENROUTER_BASE_URL")
                if env_url:
                    base_url = env_url

            self.client = AsyncOpenAI(api_key=os.environ.get("OPENROUTER_API_KEY"), base_url=base_url)
        else:
            api_key = self.config.api_key or os.getenv("OPENAI_API_KEY")
            openai_base_url: str = "https://api.openai.com/v1"
            if isinstance(self.config, OpenAIConfig) and self.config.openai_base_url:
                openai_base_url = self.config.openai_base_url
            elif os.getenv("OPENAI_BASE_URL"):
                env_url = os.getenv("OPENAI_BASE_URL")
                if env_url:
                    openai_base_url = env_url

            self.client = AsyncOpenAI(api_key=api_key, base_url=openai_base_url)

    @staticmethod
    def _parse_response(response: Any, tools: list[dict[str, Any]] | None) -> str | dict[str, Any]:
        """
        Обработка ответа с учетом того, использовались ли tools или нет.

        Args:
            response: Необработанный ответ от API.
            tools: Перечень tools, предоставленных в запросе.

        Returns:
            str or dict: Обработанный ответ.
        """
        if response is None:
            raise ValueError("Received None response from LLM API")

        if not hasattr(response, "choices") or not response.choices:
            raise ValueError("LM response missing 'choices' or empty choices list")

        first_choice = response.choices[0]

        if not hasattr(first_choice, "message") or first_choice.message is None:
            raise ValueError("LLM response first choice missing 'message'")

        if tools:
            processed_response: dict[str, Any] = {
                "content": response.choices[0].message.content or "",
                "tool_calls": [],
            }

            if hasattr(first_choice.message, "tool_calls") and first_choice.message.tool_calls:
                for tool_call in first_choice.message.tool_calls:
                    processed_response["tool_calls"].append(
                        {
                            "id": tool_call.id,
                            "function": {
                                "name": tool_call.function.name,
                                "arguments": json.loads(extract_json(tool_call.function.arguments)),
                            },
                        }
                    )

            return processed_response
        else:
            # Возвращаем content из ответа модели
            content: str = first_choice.message.content or ""
            return content

    async def generate_response(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        response_format: str | Any | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str = "auto",
        **kwargs: Any,
    ) -> str | dict[str, Any]:
        """
        Сгенерировать ответ JSON на основе предоставленных сообщений с помощью OpenAI.

        Args:
            messages (list): Список(list) содержащий словари(dict) 'role' и 'content'.
            model (str, optional): Модель LLM. Если None - используется self.config.model.
            response_format (str or object, optional): Формат ответа. По умолчанию — «None».
            tools (list, optional): Список(list) tools что модель может вызвать. По умолчанию — None.
            tool_choice (str, optional): Метод выбора tools. По умолчанию — "auto".
            **kwargs: Дополнительные параметры, специфичные для OpenAI.

        Returns:
            json: Сгенерированный ответ.
        """
        params = self._get_supported_params(messages=messages, **kwargs)

        params.update(
            {
                "model": model or self.config.model,
                "messages": messages,
            }
        )

        if os.getenv("OPENROUTER_API_KEY"):
            openrouter_params: dict[str, Any] = {}
            if isinstance(self.config, OpenAIConfig):
                if self.config.models:
                    openrouter_params["models"] = self.config.models
                    if self.config.route:
                        openrouter_params["route"] = self.config.route
                    params.pop("model")

                if self.config.site_url and self.config.app_name:
                    extra_headers = {
                        "HTTP-Referer": self.config.site_url,
                        "X-Title": self.config.app_name,
                    }
                    openrouter_params["extra_headers"] = extra_headers

            params.update(**openrouter_params)

        else:
            openai_specific_generation_params = ["store"]
            for param in openai_specific_generation_params:
                if hasattr(self.config, param):
                    params[param] = getattr(self.config, param)

        if response_format:
            params["response_format"] = response_format
        if tools:
            params["tools"] = tools
            params["tool_choice"] = tool_choice

        response = await self.client.chat.completions.create(**params)

        parsed_response = self._parse_response(response, tools)
        if isinstance(self.config, OpenAIConfig) and self.config.response_callback:
            try:
                if asyncio.iscoroutinefunction(self.config.response_callback):
                    await self.config.response_callback(self, response, params)
                else:
                    self.config.response_callback(self, response, params)
            except Exception as e:
                logging.error(f"Error due to callback: {e}")

        return parsed_response

    async def generate_stream_response(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str = "auto",
        **kwargs: Any,
    ) -> tuple[AsyncIterator[str], Awaitable[dict[str, Any]]]:
        """
        Сгенерировать ответ JSON на основе предоставленных сообщений с помощью OpenAI.

        Args:
            messages (list): Список(list) содержащий словари(dict) 'role' и 'content'.
            model (str, optional): Модель LLM. Если None - используется self.config.model.
            tools (list, optional): Список(list) tools что модель может вызвать. По умолчанию — None.
            tool_choice (str, optional): Метод выбора tools. По умолчанию — "auto".
            **kwargs: Дополнительные параметры, специфичные для OpenAI.

        Returns:
            json: Сгенерированный ответ.
        """
        params = self._get_supported_params(messages=messages, **kwargs)

        params.update(
            {
                "model": model or self.config.model,
                "messages": messages,
                "stream": True,
            }
        )

        if os.getenv("OPENROUTER_API_KEY"):
            openrouter_params: dict[str, Any] = {}
            if isinstance(self.config, OpenAIConfig):
                if self.config.models:
                    openrouter_params["models"] = self.config.models
                    if self.config.route:
                        openrouter_params["route"] = self.config.route
                    params.pop("model")

                if self.config.site_url and self.config.app_name:
                    extra_headers = {
                        "HTTP-Referer": self.config.site_url,
                        "X-Title": self.config.app_name,
                    }
                    openrouter_params["extra_headers"] = extra_headers

            params.update(**openrouter_params)

        else:
            openai_specific_generation_params = ["store"]
            for param in openai_specific_generation_params:
                if hasattr(self.config, param):
                    params[param] = getattr(self.config, param)

        if tools:
            params["tools"] = tools
            params["tool_choice"] = tool_choice

        response = await self.client.chat.completions.create(**params)

        chunks: list[str] = []
        tool_calls_buffer: dict[int, dict[str, Any]] = {}  # index -> {id, function: {name, arguments}}
        stream_completed = asyncio.Event()

        async def stream_generator() -> AsyncIterator[str]:
            """
            Генератор для стрима, собирает chunks и устанавливает флаг завершения.
            """
            try:
                async for chunk in response:
                    # Пропускаем chunks без choices (финальные, служебные)
                    if not chunk.choices:
                        continue

                    # Текстовый контент
                    if chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        chunks.append(content)
                        yield content

                    # Tool calls (приходят кусками)
                    if hasattr(chunk.choices[0].delta, "tool_calls") and chunk.choices[0].delta.tool_calls:
                        for tool_call_chunk in chunk.choices[0].delta.tool_calls:
                            idx = tool_call_chunk.index

                            # Инициализация при первом появлении
                            if idx not in tool_calls_buffer:
                                tool_calls_buffer[idx] = {
                                    "id": tool_call_chunk.id or "",
                                    "function": {"name": "", "arguments": ""},
                                }

                            # Накопление данных
                            if tool_call_chunk.id:
                                tool_calls_buffer[idx]["id"] = tool_call_chunk.id
                            if hasattr(tool_call_chunk, "function") and tool_call_chunk.function:
                                if tool_call_chunk.function.name:
                                    tool_calls_buffer[idx]["function"]["name"] = tool_call_chunk.function.name
                                if tool_call_chunk.function.arguments:
                                    tool_calls_buffer[idx]["function"]["arguments"] += (
                                        tool_call_chunk.function.arguments
                                    )
            finally:
                stream_completed.set()

        async def get_result() -> dict[str, Any]:
            """
            Ожидает завершения стрима и возвращает полный ответ.
            Returns:
                dict: {"content": str, "tool_calls": list[dict]}
            """
            await stream_completed.wait()

            result: dict[str, Any] = {"content": "".join(chunks), "tool_calls": []}

            # Конвертируем накопленные tool_calls в нужный формат
            for idx in sorted(tool_calls_buffer.keys()):
                tc = tool_calls_buffer[idx]
                args_str = tc["function"]["arguments"]

                # Парсим JSON с обработкой ошибок (некоторые модели генерируют невалидный JSON)
                try:
                    args = json.loads(args_str) if args_str else {}
                except json.JSONDecodeError as e:
                    logger.warning(f"Invalid JSON in tool call arguments: {e}, args: {args_str[:100]}...")
                    # Попытка исправить обрезанный JSON - добавляем закрывающие скобки
                    try:
                        # Если строка обрезана внутри строки, закрываем её и объект
                        if args_str.count('"') % 2 == 1:  # Нечётное количество кавычек
                            # Находим последний незакрытый ключ
                            last_quote = args_str.rfind('"')
                            if last_quote != -1:
                                # Пытаемся закрыть значение и объект
                                fixed = args_str + '"}'
                                try:
                                    args = json.loads(fixed)
                                    logger.info("Fixed JSON by adding closing quote/brace")
                                except (json.JSONDecodeError, ValueError, TypeError):
                                    args = {}
                            else:
                                args = {}
                        else:
                            args = {}
                    except (json.JSONDecodeError, ValueError, TypeError):
                        args = {}

                result["tool_calls"].append(
                    {"id": tc["id"], "function": {"name": tc["function"]["name"], "arguments": args}}
                )

            return result

        return stream_generator(), get_result()
