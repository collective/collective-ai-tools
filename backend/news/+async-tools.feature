Every tool endpoint can run as a polled task (`"async": true`), as the
assistant already does, so a slow model call no longer hits proxy timeouts. The
widgets always ask for one, polling `@aitools-task-status`, and fall back to a
synchronous call when a poll lands on a process without the task. @frapell
