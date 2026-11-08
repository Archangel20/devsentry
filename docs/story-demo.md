# Story demo

The film at `devsentry-demo.mp4` is a debugging story, not an install checklist.

A sample call divides by zero. `inspect_project` names the tree. `diagnose_error` places the real traceback on the cited line and labels the result a lead, not a confirmed cause. The developer, not the plugin, changes `ratio(1, 0)` to `ratio(1, 2)` and reruns the sample. `review_changes` then separates a staged README note from that unstaged edit and reports that the Git index did not change.

Title cards and the top line are editorial captions. The terminal pictures are a screen recording of a real PTY: the sample command, `sed`, `git diff`, the rerun, and `scripts/story_demo.py`. That helper calls Hermes `tools.registry.dispatch`. It is not a `hermes` subcommand, and no model is called. The closing card summarizes the traceback, the unstaged edit, and the untouched index.

Reproduce the capture from the repository root:

```bash
bash scripts/record_story_demo.sh
```

That script expects a prepared sample checkout, `HERMES_HOME` with DevSentry enabled, and `/tmp/ds-story/launch.py` from the Hermes runtime. The commands actually shown are the sample run, the three registry calls, and the developer edit.
