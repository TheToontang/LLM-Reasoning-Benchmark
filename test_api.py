import csv
from dotenv import load_dotenv
from google import genai

# Load API key from .env
load_dotenv()

# Connect to Gemini
client = genai.Client()

# Read the first question from CSV
with open("questions.csv", "r", encoding="utf-8-sig", newline="") as file:
    reader = csv.DictReader(file)
    questions = list(reader)

question = questions[0]

# Prepare the prompt
prompt = question["question"] + "\n\n"
prompt += "A. " + question["choice_A"] + "\n"
prompt += "B. " + question["choice_B"] + "\n"
prompt += "C. " + question["choice_C"] + "\n"
prompt += "D. " + question["choice_D"] + "\n"
prompt += "\nAnswer with only A, B, C, or D."

# Send one question to Gemini
# Send one question to Gemini
response = client.models.generate_content(
    model="gemini-3.8-flash", 
    contents=prompt
)

print("Question ID:", question["id"])
print("Gold answer:", question["gold_answer"])
print("Gemini answer:", response.text)
