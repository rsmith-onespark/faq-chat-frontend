import warnings
import os
import asyncio
import json
from typing import List, Dict
import uuid

import streamlit as st


import utils
import ast
from langserve import RemoteRunnable
from logger import logger
import requests

warnings.filterwarnings("ignore")

URL = os.environ.get("FAQ_BOT_SERVER_API", "http://localhost:8002")
SECRET_KEY = os.environ.get("SECRET_KEY", "123")
HEADERS = {"SECRETKEY": SECRET_KEY}
runner = RemoteRunnable(url=URL)
callback_handler = utils.StreamlitUICallbackHandler()

INITIAL_MESSAGE = utils.Message(
    content="Hey there, I'm OneSpark-Bot! What OneSpark related info can I give you today?",
    type="ai",
)

logger.info("\n\n\n\n\n")


async def run_model(inp: dict, config: dict = {}):
    if "configurable" not in config:
        config = {"configurable": config}
    logger.info("input %s", inp)
    logger.info("config %s", config["configurable"])

    # async for event in runner.astream_events(input=inp, config=config, version="v1"):
    response = requests.post(
        URL + "/chat/stream_events",
        json={"input": inp, "config": config},
        stream=True,
        headers=HEADERS,
    )
    logger.info("post response %s", response)
    if response.status_code != 200:
        yield {"event": "error", "data": response.text}
    else:
        chunks = []
        semi_chunk = b""
        for chunk in response.iter_lines(
            chunk_size=1024, delimiter="\r\n\r\n", decode_unicode=True
        ):
            if chunk:
                # logger.info("-------")
                c_str: str = chunk
                # logger.info("\t %s", c_str)
                if c_str.startswith("event: end"):
                    # Ignore
                    pass
                elif c_str.startswith("event: "):
                    # Set starting string
                    semi_chunk = chunk
                else:
                    # Add to existing string
                    semi_chunk += chunk
                try:
                    semi_chunk_processed = (
                        "{"
                        + semi_chunk.replace(
                            "event: data\r\ndata:", '"event": "data",\r\n"data":'
                        )
                        .replace("event: end", '"event": "end"')
                        .replace("event: error\r\n", '"event": "error",\r\n')
                        + "}"
                    )
                    event_json = json.loads(semi_chunk_processed)
                    # Only append if decoded properly
                    chunks.append(event_json)

                    yield event_json
                except json.JSONDecodeError as e:
                    logger.error(
                        "Error: could not decode semi_chunk %s %s", semi_chunk, e
                    )


def update_chat_history():
    response = requests.get(
        URL + f"/chat/get_chat_history/{st.session_state.session_id}",
        headers=HEADERS,
    ).json()
    # print("get response", response)
    msgs = [] if response is None else response["messages"]
    msgs = [utils.Message(**el) for el in msgs]
    for msg in msgs:
        if msg not in st.session_state.chat_history:
            st.session_state.chat_history.append(msg)


async def main():
    st.title("OneSpark FAQ Bot")
    # Add a reset button
    if st.button("Reset Chat", type="secondary"):
        for key in st.session_state.keys():
            del st.session_state[key]
        st.session_state.chat_history = [INITIAL_MESSAGE]

    ### Sidebar ###
    st.sidebar.markdown(
        "# FAQ bot\n\nThis FAQ bot is an intuitive and user-friendly application that allows you to interact with OneSpark's knowledge base using natural language queries."
    )
    st.sidebar.markdown("FAQ: https://www.onespark.co.za/faqs")
    st.sidebar.markdown("Product guides: https://www.onespark.co.za/legal")
    # Model parameters
    model_options = {
        "gpt-4-0125-preview": "GPT-4-turbo",
        # "gpt-4": "GPT-4",
        "gpt-3.5-turbo": "GPT-3.5-turbo",
    }
    model = st.sidebar.selectbox(
        "Model name",
        options=list(model_options.keys()),
        format_func=lambda x: model_options[x],
        index=0,
    )
    temperature = st.sidebar.slider(
        "Model's randomness (Default = 0 i.e. same output given the same input)",
        min_value=0.0,
        max_value=1.0,
        step=0.1,
        value=0.0,
    )
    st.session_state["model"] = model
    st.session_state["temperature"] = temperature
    # # More text
    # st.sidebar.markdown(
    #     """## Features
    # - **Conversational AI**: Harnesses ChatGPT to handle natural language
    # - **Intelligent document search**: Uses Embeddings technology to find information similar to your query
    # - **Conversational Memory**: Retains context for interactive, dynamic responses.
    # - **Tells jokes**: Ask it to tell you a joke
    # - **Interactive User Interface**: Transforms data querying into an engaging conversation, complete with a chat reset option."""
    # )

    st.sidebar.markdown("## Here are some example queries you can try:")
    for example in [
        "Who is OneSpark?",
        "How can I make a claim?",
        "Tell me about your funeral product",
        "How many people can I add to my funeral plan",
        "why do I need life cover?",
        "tell me a joke",
    ]:
        if st.sidebar.button(label=example):
            st.session_state.latest_prompt = example

    ### Sidebar ###

    ### Styles ###
    with open("ui/styles.md", "r") as styles_file:
        styles_content = styles_file.read()
        st.write(styles_content, unsafe_allow_html=True)

    ### Styles ###

    ### Session state ###

    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())
        print("session_id", st.session_state.session_id)

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = [INITIAL_MESSAGE]

    if "model" not in st.session_state:
        st.session_state["model"] = model

    if "temperature" not in st.session_state:
        st.session_state["temperature"] = temperature

    if "latest_prompt" not in st.session_state:
        st.session_state.latest_prompt: str = ""

    if "prompt_disabled" not in st.session_state:
        st.session_state.prompt_disabled = False

    ### Session state ###

    # Update chat history
    update_chat_history()

    # Prompt for user input and save
    if prompt := st.chat_input(
        max_chars=250, disabled=st.session_state.prompt_disabled
    ):
        st.session_state.latest_prompt = prompt
        st.session_state.prompt_disabled = True

    # Show conversation history
    for message in st.session_state.chat_history:
        utils.display_message(message)

    # set prompt disabled-ness
    st.session_state.prompt_disabled = not callback_handler.has_streaming_ended

    # get latest query (see if it's from the user)
    latest_msg = st.session_state.latest_prompt
    if len(latest_msg.strip()) > 0:
        # Display
        utils.display_message(
            utils.Message(
                content=latest_msg,
                type="human",
            )
        )

        config = {
            # "llm": "fake_llm",
            "llm_model_name": model,
            "llm_temperature": temperature,
        }
        # Ignore last one as it's the query
        inp = {
            "query": latest_msg,
            "session_id": st.session_state.session_id,
        }
        results = []
        async for event in run_model(inp=inp, config=config):
            results.append(event)
            data = event.get("data", {})
            if event["event"] == "error":
                logger.error("Error %s", data)
                callback_handler.on_llm_new_token(token=data, run_id=None)
                break
            kind = data.get("event")
            if kind == "on_chat_model_stream":
                token = data["data"]["chunk"]["content"]
                if len(token) > 0:
                    callback_handler.on_llm_new_token(token=token, run_id=None)
            elif kind == "on_tool_start":
                logger.info("invoking tool %s", data)
                tool_name = " ".join(data["name"].split("_")).capitalize()
                tool_input = data["data"]["input"]
                if isinstance(tool_input, dict) and len(tool_input) == 0:
                    tool_input = None
                # Store message
                # message = f"Running tool `{tool_name}` with input: `{tool_input}`"
                msg = utils.Message(
                    content="",
                    type="ai",
                    additional_kwargs={
                        "tool_calls": [
                            {"function": {"name": tool_name, "arguments": tool_input}}
                        ]
                    },
                )
                # Display message
                utils.display_message(msg)
            elif kind == "on_tool_end":
                logger.info("tool end \n```\n%s\n```\n", data)
                tool_name = " ".join(data["name"].split("_")).capitalize()
                tool_output = data["data"]["output"]
                # Store message
                msg = utils.Message(
                    content=tool_output,
                    type="tool",
                    additional_kwargs={"name": tool_name},
                )
                # Display
                utils.display_message(msg)
            # else:
            #     pass
        # Append final message
        final_message = "".join(callback_handler.token_buffer)
        # Reset handler
        callback_handler.on_llm_end(response=final_message, run_id=None)
        st.session_state.latest_prompt = ""

    # Reset prompt availability
    st.session_state["prompt_disabled"] = False


asyncio.run(main())
