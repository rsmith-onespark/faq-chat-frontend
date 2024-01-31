import html
import re
from uuid import UUID
import streamlit as st
from typing import Dict, List, Literal, Any, Optional
from langchain_core.callbacks import BaseCallbackHandler
from pydantic import BaseModel, model_validator
from logger import logger


class Tool(BaseModel):
    name: str
    arguments: dict | None = None
    output: Any | None = None


class Message(BaseModel):
    content: str
    type: Literal["ai", "human"] = "ai"
    tool: Tool | None = None

    @model_validator(mode="after")
    def validate_is_tool(self):
        if self.tool is not None and self.type != "ai":
            raise ValueError("invalid is_tool")
        return self


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
    if message.type == "human":
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
    tool_log = "" if message.tool is None else f"tool={message.tool.name}"
    logger.info(
        '\t displaying message %s: "%s" (%s)',
        message.type,
        message.content,
        tool_log,
    )
    if message.tool is None:
        formatted = get_message_html(message)
        st.write(formatted, unsafe_allow_html=True)
    else:
        if message.tool.output is not None:
            expander = st.expander(
                "Tool `{message.tool.name}` finished", expanded=False
            )
            display_tool_output(expander=expander, tool_output_py=message.tool.output)
        else:
            expander = st.expander(
                f"Running tool `{message.tool.name}`", expanded=False
            )
            display_tool_input(expander=expander, tool_input=message.tool.arguments)
    return


def display_tool_input(expander, tool_input):
    expander.write(f"Tool input: `{tool_input}`")


def display_tool_output(expander, tool_output_py):
    expander.write("Output: ...")
    # Display message
    if isinstance(tool_output_py, list):
        for out in tool_output_py:
            if isinstance(out, dict):
                expander.json(out)
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
