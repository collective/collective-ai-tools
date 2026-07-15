Add an "AI Tools" control panel and a tools framework (named ``IAITool``
utilities), with two initial Classic UI tools: "Recognize image" (vision)
and "Help me write" (drafting/rewriting). "Help me write" adds a button to
TinyMCE rich-text fields on edit/add forms, backed by the
``@aitools-help-me-write`` REST endpoint. Tools reach a model through
``collective.aisettings``. @frapell
