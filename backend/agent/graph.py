from __future__ import annotations
import os
from typing import Annotated, Sequence
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_groq import ChatGroq
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from typing_extensions import TypedDict
from config import settings
from agent.tools import ALL_TOOLS
os.environ.setdefault('LANGCHAIN_API_KEY', settings.LANGCHAIN_API_KEY)
os.environ.setdefault('LANGCHAIN_TRACING_V2', settings.LANGCHAIN_TRACING_V2)
os.environ.setdefault('LANGCHAIN_PROJECT', settings.LANGCHAIN_PROJECT)

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    system_prompt: str

_groq_key = settings.GROQ_API_KEY if settings.GROQ_API_KEY else "gsk_dummy"
_llm = ChatGroq(model='llama-3.3-70b-versatile', api_key=_groq_key, temperature=0.3)
_llm_with_tools = _llm.bind_tools(ALL_TOOLS)

def _agent_node(state: AgentState) -> dict:
    system_prompt = state.get('system_prompt', 'You are a clinical scheduling assistant.')
    messages = list(state['messages'])
    full_messages = [SystemMessage(content=system_prompt)] + messages
    response: AIMessage = _llm_with_tools.invoke(full_messages)
    return {'messages': [response]}
_tools_node = ToolNode(ALL_TOOLS)

def _should_continue(state: AgentState) -> str:
    last = state['messages'][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return 'tools'
    return 'end'
_workflow = StateGraph(AgentState)
_workflow.add_node('agent', _agent_node)
_workflow.add_node('tools', _tools_node)
_workflow.set_entry_point('agent')
_workflow.add_conditional_edges('agent', _should_continue, {'tools': 'tools', 'end': END})
_workflow.add_edge('tools', 'agent')
agent = _workflow.compile()