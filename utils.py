import html
import re
from uuid import UUID
import streamlit as st
from typing import Dict, List, Literal, Any, Optional
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.documents import Document
from langchain_core.messages import BaseMessage
from pydantic import BaseModel, model_validator
from logger import logger
import json
import ast


class Tool(BaseModel):
    name: str
    arguments: dict | None = None
    output: Any | None = None


class Message(BaseMessage):
    pass


def format_message(text):
    """
    This function is used to format the messages in the chatbot UI.

    Parameters:
    text (str): The text to be formatted.
    """
    text_blocks = re.split(r"```[\s\S]*?```", text)

    text_blocks = [html.escape(block) for block in text_blocks]

    formatted_text = ""
    for i in range(len(text_blocks)):
        formatted_text += text_blocks[i].replace("\n", "<br>")

    return formatted_text


def get_message_html(message: Message):
    """
    This function is used to get the HTML for a message in the chatbot UI.
    """
    if message.type in ["human", "user"]:
        avatar_url = "https://avataaars.io/?avatarStyle=Transparent&topType=ShortHairShortFlat&accessoriesType=Prescription01&hairColor=Auburn&facialHairType=BeardLight&facialHairColor=Black&clotheType=Hoodie&clotheColor=PastelBlue&eyeType=Squint&eyebrowType=DefaultNatural&mouthType=Smile&skinColor=Tanned"
        message_alignment = "flex-end"
        message_bg_color = "linear-gradient(135deg, #00B2FF 0%, #006AFF 100%)"
        avatar_class = "user-avatar"
        return f"""
                <div style="display: flex; align-items: center; margin-bottom: 10px; justify-content: {message_alignment};">
                    <div style="background: {message_bg_color}; color: white; border-radius: 20px; padding: 10px; margin-right: 5px; max-width: 75%; font-size: 14px;">
                        {message.content} \n </div>
                    <img src="{avatar_url}" class="{avatar_class}" alt="avatar" style="width: 50px; height: 50px;" />
                </div>
                """
    else:
        avatar_url = "https://avataaars.io/?avatarStyle=Transparent&topType=WinterHat2&accessoriesType=Kurt&hatColor=Blue01&facialHairType=MoustacheMagnum&facialHairColor=Blonde&clotheType=Overall&clotheColor=Gray01&eyeType=WinkWacky&eyebrowType=SadConcernedNatural&mouthType=Sad&skinColor=Light"
        message_alignment = "flex-start"
        message_bg_color = "#71797E"
        avatar_class = "bot-avatar"

        text = format_message(message.content)

        return f"""
                <div style="display: flex; align-items: center; margin-bottom: 10px; justify-content: {message_alignment};">
                    <img src="{avatar_url}" class="{avatar_class}" alt="avatar" style="width: 50px; height: 50px;" />
                    <div style="background: {message_bg_color}; color: white; border-radius: 20px; padding: 10px; margin-right: 5px; max-width: 75%; font-size: 14px;">
                        {text} \n </div>
                </div>
                """


def display_message(message: Message):
    """Helper function for streamlit"""
    tool_log = ""
    if message.type == "tool":
        tool_log = f"(tool={message.additional_kwargs['name']})"
    # logger.info(
    #     '\t displaying message %s: "%s" %s',
    #     message.type,
    #     (
    #         str(message.content)[:500] + "..."
    #         if len(str(message.content)) > 500
    #         else str(message.content)
    #     ),
    #     tool_log,
    # )
    if message.type == "tool":
        expander = st.expander(
            f"Tool `{message.additional_kwargs['name']}` finished", expanded=False
        )
        display_tool_output(expander=expander, tool_output_py=message.content)
    elif message.type == "ai" and "tool_calls" in message.additional_kwargs:
        for tc in message.additional_kwargs["tool_calls"]:
            expander = st.expander(
                f"Running tool `{tc['function']['name']}`", expanded=False
            )
            display_tool_input(
                expander=expander, tool_input=tc["function"]["arguments"]
            )
    else:
        formatted = get_message_html(message)
        st.write(formatted, unsafe_allow_html=True)
    return


def display_tool_input(expander, tool_input):
    expander.write(f"Tool input: `{tool_input}`")


def format_tool_out_to_document(out: dict, idx: int) -> Document:
    # It's a langchain document
    # out = Document.parse_obj(out)
    # print("out.keys()", out.keys())
    if out.get("type") == "Document":
        out.pop("type")
    page_content = out.pop("page_content", None)
    if page_content is None:
        page_content = out.get("question") + " " + out.get("answer")
    metadata = out.pop("metadata", None)
    if metadata is None:
        metadata = {k: v for k, v in out.items()}
    out = Document(page_content=page_content, metadata=metadata)
    return out


def display_tool_output(expander, tool_output_py):
    # print("tool_output,py", type(tool_output_py), tool_output_py)
    if isinstance(tool_output_py, str) and tool_output_py[0] in ["[", "{"]:
        tool_output_py = ast.literal_eval(tool_output_py)

    if isinstance(tool_output_py, list):
        for idx, out in enumerate(tool_output_py):
            if isinstance(out, dict):
                # Start index at 1
                out = format_tool_out_to_document(out, idx=idx + 1)
                src = out.metadata["source"]
                if "page_number" in out:
                    src += f' (Page {out.metadata["page_number"]})'
                expander.markdown(
                    f"**{out.metadata['id']}: {src} - {out.metadata['full_section']}**"
                )
                expander.json(out.dict(), expanded=False)
            else:
                expander.write(out)
    else:
        expander.write(tool_output_py)


def get_bot_message_container(text):
    """Generate the bot's message container style for the given text."""
    avatar_url = "https://avataaars.io/?avatarStyle=Transparent&topType=WinterHat2&accessoriesType=Kurt&hatColor=Blue01&facialHairType=MoustacheMagnum&facialHairColor=Blonde&clotheType=Overall&clotheColor=Gray01&eyeType=WinkWacky&eyebrowType=SadConcernedNatural&mouthType=Sad&skinColor=Light"
    message_alignment = "flex-start"
    message_bg_color = "#71797E"
    avatar_class = "bot-avatar"
    formatted_text = format_message(text)
    container_content = f"""
        <div style="display: flex; align-items: center; margin-bottom: 10px; justify-content: {message_alignment};">
            <img src="{avatar_url}" class="{avatar_class}" alt="avatar" style="width: 50px; height: 50px;" />
            <div style="background: {message_bg_color}; color: white; border-radius: 20px; padding: 10px; margin-right: 5px; max-width: 75%; font-size: 14px;">
                {formatted_text} \n </div>
        </div>
    """
    return container_content


class StreamlitUICallbackHandler(BaseCallbackHandler):
    def __init__(self):
        # Buffer to accumulate tokens
        self.token_buffer = []
        self.placeholder = None
        self.has_streaming_ended = False

    def on_llm_new_token(self, token, run_id, parent_run_id=None, **kwargs):
        """
        Handle the new token from the model. Accumulate tokens in a buffer and update the Streamlit UI.
        """
        self.token_buffer.append(token)
        complete_message = "".join(self.token_buffer)
        if self.placeholder is None:
            container_content = get_bot_message_container(complete_message)
            self.placeholder = st.markdown(container_content, unsafe_allow_html=True)
        else:
            # Update the placeholder content
            container_content = get_bot_message_container(complete_message)
            self.placeholder.markdown(container_content, unsafe_allow_html=True)

    def on_llm_end(self, response, run_id, parent_run_id=None, **kwargs):
        """
        Reset the buffer when the LLM finishes running.
        """
        self.token_buffer = []  # Reset the buffer
        self.has_streaming_ended = True

    def __call__(self, *args, **kwargs):
        pass
