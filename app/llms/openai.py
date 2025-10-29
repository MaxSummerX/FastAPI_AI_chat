import asyncio
import json
import logging
import os
from typing import Any

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
            self.client = AsyncOpenAI(
                api_key=os.environ.get("OPENROUTER_API_KEY"),
                base_url=self.config.openrouter_base_url
                or os.getenv("OPENROUTER_BASE_URL")
                or "https://openrouter.ai/api/v1",
            )
        else:
            api_key = self.config.api_key or os.getenv("OPENAI_API_KEY")
            base_url = self.config.openai_base_url or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1"

            self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    def _parse_response(self, response: Any, tools: list[dict[str, Any]] | None) -> str | dict[str, Any]:
        """
        Обработка ответа с учетом того, использовались ли tools или нет.

        Args:
            response: Необработанный ответ от API.
            tools: Перечень tools, предоставленных в запросе.

        Returns:
            str or dict: Обработанный ответ.
        """
        if tools:
            processed_response = {
                "content": response.choices[0].message.content,
                "tool_calls": [],
            }

            if response.choices[0].message.tool_calls:
                for tool_call in response.choices[0].message.tool_calls:
                    processed_response["tool_calls"].append(
                        {
                            "name": tool_call.function.name,
                            "arguments": json.loads(extract_json(tool_call.function.arguments)),
                        }
                    )

            return processed_response
        else:
            # Возвращаем content из ответа модели
            content: str = response.choices[0].message.content or ""
            return content

    async def generate_response(
        self,
        messages: list[dict[str, str]],
        response_format: str | Any | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str = "auto",
        **kwargs: Any,
    ) -> str | dict[str, Any]:  # TODO: Переработать для сбора данных об ответе или разделить функциональность
        """
        Сгенерировать ответ JSON на основе предоставленных сообщений с помощью OpenAI.

        Args:
            messages (list): Список(list) содержащий словари(dict) 'role' и 'content'.
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
                "model": self.config.model,
                "messages": messages,
            }
        )

        if os.getenv("OPENROUTER_API_KEY"):
            openrouter_params = {}
            if self.config.models:
                openrouter_params["models"] = self.config.models
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
        if self.config.response_callback:
            try:
                if asyncio.iscoroutinefunction(self.config.response_callback):
                    await self.config.response_callback(self, response, params)
                else:
                    self.config.response_callback(self, response, params)
            except Exception as e:
                logging.error(f"Error due to callback: {e}")

        return parsed_response
