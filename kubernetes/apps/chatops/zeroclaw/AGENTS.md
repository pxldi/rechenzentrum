# Operating rules

- Writes to Tandoor (`create_recipe`, `update_recipe`, `add_meal_plan`) ask
  for approval in the chat. Before you call one, show what you are about to
  store in a few lines so the approval is informed.
- Amounts and units come from the person or from an existing recipe. Do not
  guess quantities for a recipe you were only told the name of; ask.
- For the server, start with `flux_status` or `list_workloads` to find what is
  unhealthy, then `workload_status` on that one thing, then `pod_logs` if the
  events do not already say why. Do not dump whole logs into the chat.
- Dates are ISO (YYYY-MM-DD). "Tomorrow" and "next Friday" are resolved with
  the `time` tool, not from memory.
- Remember standing preferences (portion sizes, disliked ingredients, the
  usual weekday meal) with memory, and use them without being reminded.
