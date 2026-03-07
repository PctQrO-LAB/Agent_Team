import re

with open('src/tools/generate_tools.py', 'r', encoding='utf-8') as f:
    text = f.read()

# We'll just look at generate_tools first to see its current implementation before making any concrete change plan
print(text[:500])
