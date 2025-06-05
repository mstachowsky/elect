import ollama
import re

def parse_llm_output(text):
    # Step 1: Remove anything within <think>...</think>
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)

    # Step 2: Split on <indicator>
    parts = text.split("<indicator>")
    results = []

    for part in parts[1:]:  # First part before the first <indicator> is irrelevant
        # Step 3a: Extract title (ends at </indicator>)
        title_match = re.match(r"(.*?)</indicator>", part, re.DOTALL)
        if not title_match:
            continue
        title = title_match.group(1).strip()

        # Step 3b: Check if <applicable> is present
        if "<applicable>" not in part:
            continue

        # Step 3c: Extract explanation
        explanation_match = re.search(r"<explanation>(.*?)</explanation>", part, re.DOTALL)
        explanation = explanation_match.group(1).strip() if explanation_match else ""

        results.append({
            "title": title,
            "explanation": explanation
        })

    return results

# Set up the client to connect to your remote host
client = ollama.Client(host='http://ece-nebula16:11434')

with open("infant_toddler_short.txt",'r',encoding='utf-8',errors='ignore') as reader:
    backgrounds = reader.read().split("###")

print(backgrounds)


story = """
- used the hand sign for "milk"
- Led grandmother to fridge
"""

domains = ["Physical Domain","Social Domain","Emotional Domain","Communication, Language, and Literacy Domain","Cognitive Domain"]

for i,background in enumerate(backgrounds[1:]):
    
    print(f"=================={domains[i]}+++++++++++++")
    system = f"""
    You are helping to analyze developmental observations for a toddler, L. The toddler is 15 months old. You will be provided a point form set of observations and background from a document that explains various developmental indicators in various domains. You must consider all indicators in the background. The indicators are labeled according to the string INDICATOR, then a short description, then a colon, and then a long description. Here is an example:
    
    INDICATOR: Sensory-Motor Integration: Coordinates senses with actions (e.g., looks at a toy and then reaches for it; hears a sound and crawls toward it)
    
    For each indicator:
        
        1. Repeat the indicator's short description verbatim within <indicator> and </indicator> xml tags
        2. Output <applicable> if the indicator is applicable to the observations, otherwise output <not applicable>
        3. If the indicator is applicable, provide a brief explanation for why, within <explanation> and </explanation> XML tags.
        4. If the indicator is not applicable, move on without any explanation. Produce no other output for that indicator.

    It is critical that you stick only to the facts and background, and do a thorough job. You must not make anything up! Here is the background:
        
    {background}


    and here is the point form observations:
        
    {story}

    """

    # Make a non-streaming query
    response = client.chat(
        model='cogito:70b',
        messages=[{'role':'system','content': 'Enable deep thinking subroutine.'},{'role': 'user', 'content': system}],
        stream=False
    )

    #print(response['message']['content'])
    
    content = response['message']['content']
    indicators = parse_llm_output(content)
    
    # Display results or store for later processing
    for item in indicators:
        print(f"Title: {item['title']}")
        print(f"Explanation: {item['explanation']}\n")
