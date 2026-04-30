import string
from collections import Counter

def frequency_analysis(text):
    try:
        with open(text,'r',encoding='utf-8') as file:
            text = file.read()
        text = text.lower().translate(str.maketrans('','',string.punctuation))
        words = text.split()
        word_count = Counter(words)
        for word, count in word_count.items():
            print(f"{word}:{count}")
    except FileNotFoundError:
        print("Error: File not found.")
    except Exception as e:
        print(f"An error occurred: {e}")

frequency_analysis("input.txt")