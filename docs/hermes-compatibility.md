# Hermes version used for DevSentry

The project brief said Hermes Agent v0.23.0 was installed and that the version had not been verified. The tag does exist. This plugin was written against that release, not against a later `main` checkout.

| Item | Value |
| --- | --- |
| Product | Hermes Agent, "The Hearth Release" |
| Tag | `v0.23.0` |
| Tag object | `df1774294af26285ae758c6114f3f2f60e2a602d` |
| Commit the tag peels to | `2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19` |
| Tagger date | 2026-11-05T21:32:27Z |
| Release id recorded in the tag message | 435665175 |

Those values come from the GitHub Git data API:

- `GET /repos/NousResearch/hermes-agent/git/refs/tags/v0.23.0` returns an annotated tag object `df1774294af26285ae758c6114f3f2f60e2a602d`
- `GET /repos/NousResearch/hermes-agent/git/tags/df1774294af26285ae758c6114f3f2f60e2a602d` peels that object to commit `2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19`

The plugin sources that were read at that commit:

- `hermes_cli/plugins.py` — `PluginContext.register_tool(name, toolset, schema, handler, ...)`
- `hermes_cli/plugins_cmd.py` and `hermes_cli/plugins_cmd_install.py` — `hermes plugins` install, enable, and list
- `tools/registry.py` — `registry.dispatch(name, args)` returns the handler's string
- Developer guide: <https://hermes-agent.nousresearch.com/docs/developer-guide/plugins>

## Contract this plugin uses

`devsentry/plugin.yaml` is a v1 manifest. It sets `name`, `version`, `description`, `author`, and `provides_tools`. It does not set `manifest_version`, hooks, capabilities, or Python dependencies. Hermes documents that a manifest without `manifest_version` stays a supported v1 manifest.

`devsentry/__init__.py` defines `register(ctx)` and calls `ctx.register_tool` with:

- `name` equal to the schema name and to an entry in `provides_tools`
- `toolset="devsentry"`
- `schema` containing `name`, `description`, and `parameters`
- `handler` with the documented signature `(args, **kwargs) -> str`
- `description` set to the same string as `schema["description"]`

Handlers return a JSON object as a string on success and on failure. They catch their own errors.

Local install, as documented for a directory plugin, is a copy into `~/.hermes/plugins/devsentry` plus `hermes plugins enable devsentry`. `hermes plugins install` clones a Git URL or a catalog entry. A plain folder is not an install identifier. `file://` is accepted as a local Git URL and is warned as a local scheme. The integration check uses the directory copy and `hermes plugins enable`, which is the documented path for a plugin you have on disk.

`hermes plugins doctor <path> --ci` is the documented registration check. It parses the manifest, imports the package, calls `register(ctx)`, and compares declared tools with registered tools.

## What was executed here

On this Linux machine, after installing that commit with the official installer:

```text
hermes --version
Hermes Agent v0.23.0 (2026.9.24) · stable · local 2bd378ed1b8d
Install directory: the Hermes checkout for that machine (path omitted)
Install method: git
Python: 3.14.9
OpenAI SDK: 2.54.0
Up to date

git -C ~/.hermes/hermes-agent rev-parse HEAD
2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19

git -C ~/.hermes/hermes-agent describe --tags --exact-match HEAD
v0.23.0
```

`python3 scripts/hermes_integration.py --hermes ~/.local/bin/hermes` then did the rest against a temporary `HERMES_HOME` (so the real `~/.hermes/config.yaml` was not the home that got `devsentry` enabled). It exited 0. The saved report is `samples/hermes-integration.json`.

- `hermes plugins doctor <plugin> --ci` printed `manifest: devsentry 0.1.0 (standalone)`, `OK: runtime discovery, manifest parsing, import, and registration passed`, and `registrations: 3 tool(s), 0 hook(s)`.
- `hermes plugins validate <plugin> --json` returned `"ok": true` with no warnings. The checks that passed include `declared tools`, `capability probe` (`register() ran in isolation`), `security scan` (`safe`), and `no core override`.
- `hermes plugins enable devsentry` printed `Plugin devsentry enabled.`
- `hermes plugins list` showed `devsentry` as `enabled`, version `0.1.0`, source `user`.
- Hermes's `tools.registry.dispatch` then called all three tools. `inspect_project`, `diagnose_error`, and `review_changes` each returned `"ok": true`. The review's `index_sha256_unchanged` was true. `diagnose_error` included a source snippet from the temporary project and `certainty: "leads_only"`.

`python3 -m pytest -q` in this repository reported `22 passed`. Those tests do not import Hermes. `tests/test_plugin.py` calls `register` with a stand-in object. The doctor, validate, enable, list, and `registry.dispatch` results above are the plugin runtime. They are not a model choosing those tools.

## Model chat, separate from the plugin

The plugin does not select a model and does not contain a provider key. A model-driven chat is Hermes itself calling whatever provider is configured for that home.

Checked on this install, without reading or copying any other account's credentials:

- `hermes portal info` reported `Auth: not logged in`.
- `hermes auth list` printed nothing. `~/.hermes/auth.json` was absent.
- `~/.hermes/.env` had no provider API key set. `model.provider` in `config.yaml` is `auto`, `model.default` is `anthropic/claude-opus-4.6`, and `model.base_url` is `https://openrouter.ai/api/v1`.
- No Ollama, llama.cpp, vLLM, or other local inference process was running.

The one real chat command was:

```text
hermes chat --oneshot -Q -q "Reply with the single word pong." --max-turns 1 --ignore-rules
```

It exited 1 before any model request. Stderr, saved in `samples/hermes-chat-probe.txt`:

```text
Hermes is not connected to any AI provider yet. Run `hermes model` to pick one, type `/login` in chat, or add a key with `hermes auth add <provider>`. (Advanced: put an API key such as OPENROUTER_API_KEY in ~/.hermes/.env.)
```

There is no transcript of a model discovering or calling `inspect_project`, `diagnose_error`, or `review_changes`. Producing one without a provider would be a simulation. None was written.

To run that chat later, keep the plugin setup and add a provider this Hermes already supports. Plugin setup is still:

```bash
mkdir -p ~/.hermes/plugins/devsentry
cp -a devsentry/. ~/.hermes/plugins/devsentry/
hermes plugins enable devsentry
```

The tools register in toolset `devsentry`. After a provider is logged in, a one-shot chat is:

```bash
hermes chat --oneshot -q "Use the DevSentry tools on this project." -t devsentry
```

Provider setup, from this install's `hermes chat` error, `hermes portal info`, and the `model:` comments in its `config.yaml`:

- Nous Portal, the subscription path Hermes documents as its default: `hermes portal` or `hermes model`, then choose Nous Portal. That login is OAuth against an existing Nous subscription. This run did not start it and did not buy one.
- An API key in `~/.hermes/.env`, then `hermes model` or `model.provider` set to that provider. The config comments name `OPENROUTER_API_KEY` for `openrouter` (the current `base_url`), `NOUS_API_KEY` for `nous-api`, `ANTHROPIC_API_KEY` for `anthropic`, `OPENAI_API_KEY` for the OpenAI API, and the other keys listed beside `model.provider`. `hermes auth add <provider>` is the command the chat error names for the credential pool. `hermes auth add openrouter --type oauth` is the documented browser login for OpenRouter. Those are paid or account-backed calls. None was added here.
- A local OpenAI-compatible server that is already running, with no key: `model.provider: custom` (aliases `ollama`, `vllm`, `llamacpp`) and `model.base_url` such as `http://127.0.0.1:11434/v1`, or `provider: lmstudio` for LM Studio's default `http://127.0.0.1:1234/v1`. Nothing was listening, and no local runtime was installed for this check.

Until one of those is already authorized, Hermes will keep exiting with the message above. Do not point Hermes at another product's token to get past it.

The same commands were not run on Windows.

A separate check installed a temporary Git repository with `hermes plugins install "file://<repo>#devsentry" --no-enable`. Hermes warned that `file://` is an unreviewed local scheme, then installed the plugin and left it disabled. `hermes plugins remove devsentry` deleted that copy. The first attempt was blocked because the temporary commit contained `__pycache__` bytecode. A tree without bytecode installed. That scan result is why the source archive and git tree omit bytecode.
