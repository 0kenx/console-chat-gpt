import json

import anthropic
import openai
from mistralai.client import MistralClient
from mistralai.models.chat_completion import ChatMessage

from console_gpt.custom_stdout import custom_print
from console_gpt.menus.combined_menu import AssistantObject, ChatObject
from console_gpt.menus.command_handler import command_handler
from console_gpt.prompts.assistant_prompt import assistance_reply
from console_gpt.prompts.save_chat_prompt import save_chat
from console_gpt.prompts.user_prompt import chat_user_prompt


def mistral_messages(message_dicts):
    return [ChatMessage(role=msg["role"], content=msg["content"]) for msg in message_dicts]


def chat(console, data) -> None:
    # Assign all variables at once via the Object returned by the menu
    (
        api_key,
        api_usage,
        model_input_pricing_per_1k,
        model_max_tokens,
        model_name,
        model_output_pricing_per_1k,
        model_title,
    ) = data.model.values()

    # Initiate API
    if model_title == "mistral":
        client = MistralClient(api_key=api_key)
    elif model_title == "anthropic":
        client = anthropic.Anthropic(api_key=api_key)
        role = data.conversation[0]["content"]
    else:
        client = openai.OpenAI(api_key=api_key)

    # Set defaults
    if model_title == "mistral":
        conversation = [message for message in data.conversation if message["role"] != "system"]
    elif model_title == "anthropic":
        conversation = []
    else:
        conversation = data.conversation
    temperature = data.temperature

    # Inner Loop
    while True:
        response = ""  # Adding this to satisfy the IDE
        error_appeared = False  # Used when the API returns an exception
        user_input = chat_user_prompt()
        if not user_input:  # Used to catch SIGINT
            save_chat(conversation, ask=True)
        # Command Handler
        handled_user_input = command_handler(model_title, model_name, user_input["content"], conversation)
        match handled_user_input:
            case "continue" | None:
                continue
            case "break":
                break
            case _:
                user_input["content"] = handled_user_input

        # Add user's input to the overall conversation
        conversation.append(user_input)

        # Start the loading bar until API response is returned
        with console.status("[bold green]Generating a response...", spinner="aesthetic"):
            try:
                if model_title == "mistral":
                    response = client.chat(
                        model=model_name,
                        temperature=float(temperature) / 2,
                        messages=mistral_messages(conversation),
                    )
                elif model_title == "anthropic":
                    # headers = {
                    #     "x-api-key": api_key,
                    #     "anthropic-version": "2023-06-01",
                    #     "content-type": "application/json",
                    # }
                    # payload = {
                    #     "model": model_name,
                    #     "max_tokens": model_max_tokens,
                    #     "temperature": (float(temperature) / 2),
                    #     "system": role,
                    #     "messages": conversation,
                    # }
                    # response = requests.post(
                    #     "https://api.anthropic.com/v1/messages", json=payload, headers=headers
                    # ).json()
                    response = client.messages.create(
                        model=model_name,
                        max_tokens=model_max_tokens,
                        temperature=float(temperature) / 2,
                        system=role,
                        messages=conversation,
                    ).model_dump_json()
                else:
                    # response = client.chat.completions.create(
                    #     model=model_name,
                    #     temperature=temperature,
                    #     messages=conversation,
                    #     max_tokens=model_max_tokens,
                    # )
                    response = client.chat.completions.create(
                        model=model_name,
                        temperature=temperature,
                        messages=conversation,
                    )
            # TODO: Handle mistralai.exceptions.MistralAPIException
            except openai.APIConnectionError or anthropic.APIConnectionError as e:
                error_appeared = True
                print("The server could not be reached")
                print(e.__cause__)
            except openai.RateLimitError or anthropic.RateLimitError as e:
                error_appeared = True
                print(f"A 429 status code was received; we should back off a bit. - {e}")
            except openai.APIStatusError or anthropic.APIStatusError as e:
                error_appeared = True
                print("Another non-200-range status code was received")
                print(e.status_code)
                print(e.response)
            except KeyboardInterrupt:
                # Notifying the user about the interrupt but continues normally.
                custom_print("info", "Interrupted the request. Continue normally.")
                conversation.pop(-1)
                continue
        if error_appeared:
            custom_print(
                "warn",
                "Exception was raised. Decided whether to continue. Your last message is lost as well",
            )
            # Removes the last user input in order to avoid issues if the conversation continues
            conversation.pop(-1)
            continue
        if model_title == "anthropic":
            response = json.loads(response)
            response = response["content"][0]["text"]
        else:
            response = response.choices[0].message.content
        assistant_response = dict(role="assistant", content=response)
        conversation.append(assistant_response)
        assistance_reply(response)
