# todo project tasks

- [ ] Sync the 7 most important open todos to Home Assistant helpers `input_text.epaper_todo_1` … `input_text.epaper_todo_7` via the HA REST API so the e-paper display stays current
	- [ ] Decide where and how to trigger the sync (e.g. cron job, `todo get` post-hook, HA automation calling a script, or a new `todo sync-ha` subcommand)
