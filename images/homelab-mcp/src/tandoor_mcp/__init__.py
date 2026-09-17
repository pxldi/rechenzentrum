"""Tandoor Recipes as MCP tools: search, read, create and update recipes, and
read and extend the meal plan.

The Tandoor token lives here and nowhere else. ZeroClaw never sees it; it
only sees the tool names. Reads are safe to auto-approve; the three writes
(create_recipe, update_recipe, add_meal_plan) are meant to sit behind the
agent's approval prompt, which is configured on the ZeroClaw side.
"""
