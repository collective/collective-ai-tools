Support collective.aisettings' shared task store: the assistant's turns record
their owner, answer `503` while the instance is shutting down, and the chat
widget retries a turn interrupted by a restart once, silently. The assistant
endpoints are now `Cache-Control: no-store`, so no proxy can serve a stale
poll. @frapell
