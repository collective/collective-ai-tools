"""Module where all interfaces, events and exceptions live."""

from collective.aitools import _
from zope import schema
from zope.interface import Attribute
from zope.interface import Interface
from zope.publisher.interfaces.browser import IDefaultBrowserLayer


class IBrowserLayer(IDefaultBrowserLayer):
    """Marker interface that defines a browser layer."""


#: Default instruction sent to the vision model by the "Recognize image" tool.
#: The tool asks for a structured JSON result (title, description, tags), so the
#: prompt describes *what* each part should contain; the JSON shape itself is
#: enforced by the tool's ``output_type``.
DEFAULT_VISION_PROMPT = (
    "Analyze this image and return metadata for a content editor:\n"
    "- title: a short, descriptive title (a few words, no trailing period).\n"
    "- description: one or two sentences describing the image, accurate and "
    "concise, suitable for use as alternative text.\n"
    "- tags: between 5 and 10 short lowercase keywords or subjects that "
    "categorize the image (single words or short phrases).\n"
    "Base everything only on what is actually visible in the image."
)

#: Default system prompt for the "Summarize" tool (fills the Description).
DEFAULT_SUMMARIZE_PROMPT = (
    "You write concise summaries for a content management system. Given the "
    "text of a page, write a single-paragraph description of at most 300 "
    "characters that captures what the page is about. It doubles as the "
    "search-engine meta description, so make it clear and self-contained. "
    "Use the same language as the content. Return only the description text, "
    "with no preamble, quotes or labels."
)

#: Default system prompt for the "Suggest tags" tool. The set of tags already
#: in use on the site is appended at call time so the model can reuse them.
DEFAULT_SUGGEST_TAGS_PROMPT = (
    "You categorize content for a content management system. Given the text "
    "of a page, propose between 5 and 10 short keyword tags (single words or "
    "short phrases) that best classify it. Prefer reusing tags from the "
    "provided list of existing site tags whenever one fits, and only invent a "
    "new tag when nothing existing applies. Use the same language as the "
    "content."
)

#: Default system prompt for the "Assistant" tool (the site chat assistant).
#: The assistant is agentic: it may call the capabilities offered to it (site
#: search, "where should I add this", …) to ground its answers. The set of
#: capabilities it is actually allowed to use is computed per request from the
#: current user's permissions, so the prompt only describes the behaviour.
DEFAULT_ASSISTANT_PROMPT = (
    "You are a helpful assistant embedded in a Plone website, helping an "
    "editor manage and find content. You have tools available; use them to "
    "ground every answer in the real site rather than guessing. When you "
    "reference a page, include its URL so the user can open it. Never claim to "
    "have created, changed or deleted content: you can only *propose* such "
    "actions for the user to confirm. Answer in the same language as the user. "
    "Be concise."
)


class IAITool(Interface):
    """A single AI-powered tool for editors or visitors.

    Each tool is registered as a *named utility* providing this interface,
    where the utility name matches :attr:`name`::

        <utility
            factory=".recognize_image.RecognizeImageTool"
            provides="collective.aitools.interfaces.IAITool"
            name="recognize_image"
            />

    Tools read their own enable flag and optional model override from the
    "AI Tools" control panel (:class:`IAIToolsSettings`) and reach a model
    through the ``collective.aisettings`` ``IAIService`` utility — they never
    talk to an LLM SDK directly. When no model is configured the tool passes
    ``model=None`` so ``collective.aisettings`` resolves one by capability.

    How tools get *invoked* (event, action/menu item, async cron job, …) is
    intentionally left open; subclasses only implement :meth:`run`.
    """

    name = Attribute("Unique identifier; matches the utility registration name.")
    title = Attribute("Human-readable title (a translatable message).")
    description = Attribute("Human-readable description (a translatable message).")

    def is_enabled():
        """Return ``True`` when the tool is enabled in the control panel."""

    def get_model():
        """Return the configured model name, or ``None`` to let
        ``collective.aisettings`` choose a model by capability."""

    def available_for(context):
        """Return ``True`` when the tool may run against ``context``
        (enabled, and any tool-specific preconditions met)."""

    def run(context, **kwargs):
        """Execute the tool against ``context`` and return its result, or
        ``None`` when the tool is disabled / no model is available."""


class IAIAssistantCapability(Interface):
    """A single capability the chat "Assistant" may call (tool/function calling).

    Each capability is registered as a *named utility* providing this interface,
    where the utility name matches :attr:`name`::

        <utility
            factory=".search_site.SearchSiteCapability"
            provides="collective.aitools.interfaces.IAIAssistantCapability"
            name="search_site"
            />

    A capability is the assistant's equivalent of an :class:`IAITool`, but it is
    exposed *to the model* as a callable function. The assistant builds, per
    request, the list of capabilities the current user is allowed to use (each
    capability re-checks :attr:`permission` against the context in
    :meth:`allowed_for`, so filtering the list is not the only safeguard), hands
    their :meth:`tool_schema` to the model, and runs whichever ones the model
    asks for.

    Capabilities that only *read* are safe to run inside the agent loop.
    Anything that *writes* must not act here; it returns a proposal for the user
    to confirm through a separate, explicit endpoint.
    """

    name = Attribute("Unique identifier; matches the utility registration name.")
    description = Attribute("Plain-English description sent to the model.")
    parameters = Attribute(
        "JSON Schema (a dict) describing the call arguments, as expected by "
        "OpenAI-style function calling."
    )
    permission = Attribute(
        "Zope permission the current user must hold on the context for this "
        "capability to be offered and run. A permission *title* ('View', "
        "'Modify portal content'), not the dotted ZCML id: "
        "``checkPermission`` only understands titles."
    )

    def allowed_for(context):
        """Return ``True`` when the current user may use this capability against
        ``context`` (i.e. holds :attr:`permission`)."""

    def tool_schema():
        """Return the OpenAI-style ``{"type": "function", "function": {...}}``
        tool definition for this capability."""

    def run(context, request, **kwargs):
        """Execute the capability and return a JSON-serializable result (the
        payload fed back to the model as the tool result)."""


class IContentTypeSynonyms(Interface):
    """A provider of extra content-type name synonyms for the assistant.

    Add-ons that ship their own content types can teach the assistant friendly
    names for them by registering a *utility* (named or unnamed) providing this
    interface::

        <utility
            factory=".synonyms.MyProductSynonyms"
            provides="collective.aitools.interfaces.IContentTypeSynonyms"
            />

    The type resolver (:func:`collective.aitools.capabilities.types.
    resolve_portal_type`) merges every registered provider's mapping on top of
    the built-in synonyms, so no add-on has to modify this package. Later
    contributions win on key conflicts; targets that don't exist on the site
    are ignored.
    """

    def get_synonyms():
        """Return a ``{synonym: portal_type_id}`` mapping.

        Keys are matched case-insensitively (and whitespace-normalized)."""


class IAIToolsSettings(Interface):
    """Settings for the AI tools, edited in the "AI Tools" control panel.

    One enable flag plus an optional model override per tool. An empty model
    means "let ``collective.aisettings`` pick a model for the capability".
    Stored as flat registry records (no prefix), mirroring
    ``collective.aisettings``'s ``IAISettings``.
    """

    # -- Recognize image (vision) --
    recognize_image_enabled = schema.Bool(
        title=_('Enable "Recognize image"'),
        description=_(
            "Generate a textual description of an item's image using a "
            "vision-capable model."
        ),
        required=False,
        default=False,
    )
    recognize_image_model = schema.TextLine(
        title=_("Recognize image: model"),
        description=_(
            "Model name to use. Leave empty to let collective.aisettings pick "
            "a vision-capable model."
        ),
        required=False,
        default="",
    )
    recognize_image_prompt = schema.Text(
        title=_("Recognize image: prompt"),
        description=_("Instruction sent to the vision model."),
        required=False,
        default=DEFAULT_VISION_PROMPT,
    )

    # -- Help me write (completion) --
    help_me_write_enabled = schema.Bool(
        title=_('Enable "Help me write"'),
        description=_(
            "Offer editors drafting and rewriting assistance (start a draft, "
            "grammar check, change tone, …)."
        ),
        required=False,
        default=False,
    )
    help_me_write_model = schema.TextLine(
        title=_("Help me write: model"),
        description=_(
            "Model name to use. Leave empty to let collective.aisettings pick "
            "a completion-capable model."
        ),
        required=False,
        default="",
    )

    # -- Summarize (completion) --
    summarize_enabled = schema.Bool(
        title=_('Enable "Summarize"'),
        description=_(
            "Generate a concise description/summary of an item from its text "
            "content (also usable as the SEO meta description)."
        ),
        required=False,
        default=False,
    )
    summarize_model = schema.TextLine(
        title=_("Summarize: model"),
        description=_(
            "Model name to use. Leave empty to let collective.aisettings pick "
            "a completion-capable model."
        ),
        required=False,
        default="",
    )
    summarize_prompt = schema.Text(
        title=_("Summarize: prompt"),
        description=_("Instruction sent to the model."),
        required=False,
        default=DEFAULT_SUMMARIZE_PROMPT,
    )

    # -- Suggest tags (completion) --
    suggest_tags_enabled = schema.Bool(
        title=_('Enable "Suggest tags"'),
        description=_(
            "Suggest Subject keywords for an item from its text content, "
            "reusing tags already in use on the site where possible."
        ),
        required=False,
        default=False,
    )
    suggest_tags_model = schema.TextLine(
        title=_("Suggest tags: model"),
        description=_(
            "Model name to use. Leave empty to let collective.aisettings pick "
            "a completion-capable model."
        ),
        required=False,
        default="",
    )
    suggest_tags_prompt = schema.Text(
        title=_("Suggest tags: prompt"),
        description=_("Instruction sent to the model."),
        required=False,
        default=DEFAULT_SUGGEST_TAGS_PROMPT,
    )

    # -- Assistant (chat, tool-calling) --
    assistant_enabled = schema.Bool(
        title=_('Enable "Assistant"'),
        description=_(
            "Offer a site chat assistant that can search the site and guide "
            "editors, calling the enabled capabilities to ground its answers."
        ),
        required=False,
        default=False,
    )
    assistant_model = schema.TextLine(
        title=_("Assistant: model"),
        description=_(
            "Model name to use. Leave empty to let collective.aisettings pick "
            "a tool-calling-capable model."
        ),
        required=False,
        default="",
    )
    assistant_prompt = schema.Text(
        title=_("Assistant: prompt"),
        description=_("System prompt steering the assistant."),
        required=False,
        default=DEFAULT_ASSISTANT_PROMPT,
    )
