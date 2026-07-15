Add an agentic chat "Assistant" for authenticated users. It runs a tool-calling
loop (via ``collective.aisettings``' ``IAIService.tool_call``) over a set of
*capabilities* — named ``IAIAssistantCapability`` utilities — that ground its
answers: "Search the site", "Where to add" (suggest folders for a content type)
and "Propose a draft" (generate a draft from a rough brief for the editor to
confirm). Capabilities are permission-gated per user, and any content creation
only happens after an explicit confirmation, re-validated server-side by the
``@aitools-assistant`` / ``@aitools-assistant-apply`` endpoints. Ships a
Classic UI floating chat widget (Markdown rendering, session persistence,
"start new chat"). Loose content-type names are accepted and add-ons can
contribute more via an ``IContentTypeSynonyms`` utility. @frapell
