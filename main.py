import warnings
import os
import asyncio
import json
from typing import List

import streamlit as st


import utils
import ast
from langserve import RemoteRunnable
from logger import logger

warnings.filterwarnings("ignore")


URL = os.environ.get("FAQ_BOT_SERVER_API", "http://localhost:8002")
SECRET_KEY = os.environ.get("SECRET_KEY", "123")
runner = RemoteRunnable(url=URL)
callback_handler = utils.StreamlitUICallbackHandler()

INITIAL_MESSAGE = [
    utils.Message(
        content="Hey there, I'm OneSpark-Bot! What OneSpark related info can I give you today?",
        type="ai",
    )
]

logger.info("\n\n\n\n\n")


def append_message(msg: utils.Message):
    st.session_state.chat_history.append(msg)


async def run_model(inp: dict, config: dict = {}):
    import requests

    if "configurable" not in config:
        config = {"configurable": config}
    logger.info("input %s", inp)
    logger.info("config %s", config["configurable"])

    # async for event in runner.astream_events(input=inp, config=config, version="v1"):
    headers = {"SECRETKEY": SECRET_KEY}
    response = requests.post(
        URL + "/chat/stream_events",
        json={"input": inp, "config": config},
        stream=True,
        headers=headers,
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


async def main():
    st.title("OneSpark FAQ Bot")
    # Add a reset button
    if st.button("Reset Chat", type="secondary"):
        for key in st.session_state.keys():
            del st.session_state[key]
        st.session_state["chat_history"] = INITIAL_MESSAGE

    ### Sidebar ###
    st.sidebar.markdown(
        "# FAQ bot\n\nThis FAQ bot is an intuitive and user-friendly application that allows you to interact with OneSpark's knowledge base using natural language queries."
    )
    st.sidebar.markdown("FAQ: https://www.onespark.co.za/faqs")
    st.sidebar.markdown("Product guides: https://www.onespark.co.za/legal")
    # Model parameters
    model_options = {
        "gpt-4-0125-preview": "GPT-4-turbo",
        "gpt-4": "GPT-4",
        "gpt-3.5-turbo": "GPT-3.5-turbo",
    }
    model = st.sidebar.selectbox(
        "Model name",
        options=list(model_options.keys()),
        format_func=lambda x: model_options[x],
        index=2,
    )
    temperature = st.sidebar.slider(
        "Model temperature (0-1)",
        min_value=0,
        max_value=1,
        value=0,
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
            append_message(utils.Message(content=example, type="human"))

    ### Sidebar ###

    ### Styles ###
    with open("ui/styles.md", "r") as styles_file:
        styles_content = styles_file.read()
        st.write(styles_content, unsafe_allow_html=True)

    ### Styles ###

    if "chat_history" not in st.session_state:
        st.session_state["chat_history"]: List[utils.Message] = INITIAL_MESSAGE

    if "model" not in st.session_state:
        st.session_state["model"] = model

    if "temperature" not in st.session_state:
        st.session_state["temperature"] = temperature

    if "prompt_disabled" not in st.session_state:
        st.session_state.prompt_disabled = False

    # Prompt for user input and save
    if prompt := st.chat_input(
        max_chars=250, disabled=st.session_state.prompt_disabled
    ):
        append_message(utils.Message(content=prompt, type="human"))
        st.session_state.prompt_disabled = True

    # Show conversation history
    for message in st.session_state.chat_history:
        utils.display_message(message)

    # set prompt disabled-ness
    st.session_state.prompt_disabled = not callback_handler.has_streaming_ended

    # get latest query (see if it's from the user)
    latest_msg: utils.Message = st.session_state.chat_history[-1]
    if latest_msg.type == "human":
        config = {
            # "llm": "fake_llm",
            "llm_model_name": model,
            "llm_temperature": temperature,
        }
        # Ignore last one as it's the query
        chat_history = [el.model_dump() for el in st.session_state["chat_history"][:-1]]
        inp = {"query": latest_msg.content, "chat_history": chat_history}
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
                message = f"Running tool `{tool_name}` with input: `{tool_input}`"
                append_message(
                    utils.Message(
                        content=message,
                        type="ai",
                        tool=utils.Tool(name=tool_name, arguments=tool_input),
                    )
                )
                # Display message
                utils.display_message(st.session_state.chat_history[-1])
            elif kind == "on_tool_end":
                logger.info("tool end \n```\n%s\n```\n", data)
                tool_name = " ".join(data["name"].split("_")).capitalize()
                tool_output = data["data"]["output"]
                tool_output_py = (
                    None if tool_output is None else ast.literal_eval(tool_output)
                )
                # Store message
                message = (
                    f"Tool `{tool_name}` finished with output: ```{tool_output_py}```"
                )
                append_message(
                    utils.Message(
                        content=message,
                        type="ai",
                        tool=utils.Tool(name=tool_name, output=tool_output_py),
                    )
                )
                # Display
                utils.display_message(st.session_state.chat_history[-1])
            # else:
            #     pass
        # Append final message
        final_message = "".join(callback_handler.token_buffer)
        append_message(utils.Message(content=final_message, type="ai"))
        # Reset handler
        callback_handler.on_llm_end(response=final_message, run_id=None)
    # Reset prompt availability
    st.session_state["prompt_disabled"] = False


asyncio.run(main())
