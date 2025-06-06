import re
import os
timestamp = "2025-06-06_07-27-02"
filename = os.path.join("saved", f"elect_analysis_{timestamp}.txt")
with open(filename, 'r', encoding='utf-8', errors='ignore') as reader:
    analysis = reader.read()

lines = analysis.splitlines()
domain_pattern = re.compile(r"^(.*domain)\s*$", re.IGNORECASE)
indicator_pattern = re.compile(r"^INDICATOR[: ]+(.*)$", re.IGNORECASE)

current_domain = None
current_indicator = None
current_desc = []
observations = []  # This is the main output: list of dicts

for idx, line in enumerate(lines + [""]):  # Add an empty line to flush last obs
    line = line.strip()
    if not line:
        continue

    # Check for domain
    if domain_pattern.match(line):
        # Flush any ongoing indicator
        if current_indicator and current_domain:
            observations.append({
                "timestamp": timestamp,
                "domain": current_domain,
                "indicator": current_indicator,
                "description": " ".join(current_desc).strip()
            })
        current_domain = domain_pattern.match(line).group(1).lower().replace(" domain", "")
        current_indicator = None
        current_desc = []
        continue

    # Check for indicator
    indicator_match = indicator_pattern.match(line)
    if indicator_match:
        # Flush previous indicator, if any
        if current_indicator and current_domain:
            observations.append({
                "timestamp": timestamp,
                "domain": current_domain,
                "indicator": current_indicator,
                "description": " ".join(current_desc).strip()
            })
        current_indicator = indicator_match.group(1).strip()
        current_desc = []
        continue

    # If in an indicator, gather description lines
    if current_indicator:
        current_desc.append(line)

# If last indicator at EOF, flush it (only if not already flushed)
if current_indicator and current_domain and current_desc:
    observations.append({
        "timestamp": timestamp,
        "domain": current_domain,
        "indicator": current_indicator,
        "description": " ".join(current_desc).strip()
    })

# For domains with no indicators, store a "None" indicator and description as None
# (optional—depends if you want these rows in your table)
# See code above for how to collect these if desired.

# Output
print("Observations for DB insertion:")
for obs in observations:
    print(obs)

# If you want as list-of-tuples for direct SQL insert:
sql_rows = [(obs["timestamp"], obs["domain"], obs["indicator"], obs["description"]) for obs in observations]
