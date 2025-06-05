BACKGROUND_FILE_PATH = "toddler.txt"
with open(BACKGROUND_FILE_PATH,'r',encoding='utf-8',errors='ignore') as reader:
	BACKGROUNDS = reader.read().split("###")
#BACKGROUNDS = BACKGROUND_FILE.read_text(encoding="utf-8", errors="ignore").split("###")
DOMAINS = [
    "Physical Domain",
    "Social Domain",
    "Emotional Domain",
    "Communication, Language, and Literacy Domain",
    "Cognitive Domain",
]
print(BACKGROUNDS)
