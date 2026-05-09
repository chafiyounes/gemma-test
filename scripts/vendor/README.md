# Vendor files for vLLM

`tool_chat_template_gemma4.jinja` is downloaded automatically by `scripts/start_vllm.sh`
when you start **gemma4** (unless `VLLM_GEMMA4_TOOLING=0`).

Source: [vLLM examples](https://github.com/vllm-project/vllm/blob/main/examples/tool_chat_template_gemma4.jinja) (Apache-2.0).

Manual fetch:

```bash
curl -fsSL -o scripts/vendor/tool_chat_template_gemma4.jinja \
  https://raw.githubusercontent.com/vllm-project/vllm/main/examples/tool_chat_template_gemma4.jinja
```
