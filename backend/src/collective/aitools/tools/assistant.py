"""The "Assistant" tool: an agentic site chat assistant.

Unlike the other tools (which do one model call), the assistant runs a small
*tool-calling loop*: it hands the model the set of capabilities the current
user is allowed to use, runs whichever the model asks for, feeds the results
back, and repeats until the model produces a final answer.

The capability manifest is computed per request from the user's permissions and
each capability re-checks its own permission when run, so the loop can never
call something the user is not entitled to — even if the model asks for it.
"""

from collective.aitools import _
from collective.aitools import logger
from collective.aitools.capabilities import get_capability
from collective.aitools.capabilities import manifest_for
from collective.aitools.interfaces import DEFAULT_ASSISTANT_PROMPT
from collective.aitools.tools.base import AITool

import json


#: Upper bound on tool-calling rounds, to cap cost and prevent a runaway loop.
MAX_STEPS = 6


def _parse_arguments(raw):
    """Decode a tool call's ``arguments`` into a dict, tolerantly.

    The wire format is a JSON *string*, but some providers double-encode it (a
    JSON string containing JSON), so decode twice when the first pass yields a
    string. Anything that isn't a mapping in the end becomes ``{}``.
    """
    for _attempt in range(2):
        if isinstance(raw, dict):
            return raw
        if not isinstance(raw, str):
            return {}
        try:
            raw = json.loads(raw or "{}")
        except (TypeError, ValueError):
            return {}
    return raw if isinstance(raw, dict) else {}


def _coerce_arguments(capability, arguments):
    """Normalize model-supplied arguments into kwargs ``capability.run`` accepts.

    Models sometimes echo the schema instead of filling it — nesting the real
    values under a wrapper key such as ``parameters`` — or invent arguments that
    are not in the schema at all. Either one raises ``TypeError`` when splatted
    into :meth:`run`, which burns a step and tells the model nothing useful, so:
    unwrap a single nesting level when nothing at the top matches the schema,
    then keep only declared properties.

    Returns ``(kwargs, dropped)``, ``dropped`` being the discarded keys.
    """
    if not isinstance(arguments, dict):
        return {}, []

    properties = (getattr(capability, "parameters", None) or {}).get("properties")
    if not isinstance(properties, dict):
        # Schema does not enumerate its arguments; nothing to filter against.
        return dict(arguments), []
    declared = set(properties)

    # A lone unrecognized key holding a dict is a wrapper, not an argument.
    if declared and len(arguments) == 1 and not declared.intersection(arguments):
        (only,) = arguments.values()
        if isinstance(only, dict):
            arguments = only

    kwargs = {key: value for key, value in arguments.items() if key in declared}
    return kwargs, sorted(set(arguments) - declared)


class AssistantTool(AITool):
    """Answer a user's message, optionally calling capabilities to ground it."""

    name = "assistant"
    title = _("Assistant")
    description = _(
        "A site chat assistant that can search the site and guide editors, "
        "calling the enabled capabilities to ground its answers."
    )

    def get_prompt(self):
        prompt = (getattr(self.settings, "assistant_prompt", "") or "").strip()
        return prompt or DEFAULT_ASSISTANT_PROMPT

    def _run_capability(self, name, arguments, context, request):
        """Run capability ``name`` with ``arguments``, re-checking permission.

        Returns a JSON-serializable result dict; on any problem it returns an
        ``{"error": ...}`` payload (which is fed back to the model rather than
        raised, so the model can recover or explain)."""
        capability = get_capability(name)
        if capability is None:
            return {"error": f"unknown capability {name!r}"}
        # Defense in depth: never trust that the manifest alone gated this.
        if not capability.allowed_for(context):
            return {"error": f"not permitted to use {name!r}"}
        kwargs, dropped = _coerce_arguments(capability, arguments)
        if dropped:
            logger.info(
                "assistant: capability %r called with unknown arguments %s; ignored",
                name,
                dropped,
            )
        try:
            return capability.run(context, request, **kwargs)
        except Exception as exc:
            logger.exception("assistant: capability %r failed", name)
            return {"error": str(exc)}

    def run(self, context, messages=None, request=None):
        """Run the agent loop for a conversation.

        ``messages`` is the OpenAI-style history (a list of ``{"role",
        "content"}`` dicts, oldest first). Returns a dict with the assistant
        ``reply`` text and the list of ``steps`` (capabilities that were
        called), or ``None`` when the tool is disabled / no model is available.
        """
        if self._skip_if_disabled():
            return None

        convo = [{"role": "system", "content": self.get_prompt()}]
        convo.extend(messages or [])

        tools = manifest_for(context)
        steps = []
        proposals = []

        for _step in range(MAX_STEPS):
            message = self.service.tool_call(
                convo,
                tools=tools,
                model=self.get_model(),
                context=context,
            )
            if message is None:
                logger.info("assistant: no response from AI service.")
                return None

            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                return {
                    "reply": (message.get("content") or "").strip(),
                    "steps": steps,
                    "proposals": proposals,
                }

            # Record the assistant's tool-call turn, then answer each call.
            convo.append(message)
            for call in tool_calls:
                fn = call.get("function") or {}
                name = fn.get("name") or ""
                arguments = _parse_arguments(fn.get("arguments"))
                result = self._run_capability(name, arguments, context, request)
                steps.append({"capability": name, "arguments": arguments})
                # A capability may propose a user-confirmed write action; surface
                # it to the UI (the model still narrates it in its reply).
                if isinstance(result, dict) and result.get("proposal"):
                    proposals.append(result["proposal"])
                convo.append({
                    "role": "tool",
                    "tool_call_id": call.get("id"),
                    "content": json.dumps(result),
                })

        # Ran out of steps without a final answer.
        logger.info("assistant: reached MAX_STEPS without a final answer.")
        return {
            "reply": "",
            "steps": steps,
            "proposals": proposals,
            "error": "max_steps_reached",
        }
