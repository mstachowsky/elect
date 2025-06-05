
with open("infant_toddler.txt",'r',encoding='utf-8',errors='ignore') as reader:
    backgrounds = reader.read().split("###")

print(backgrounds)
