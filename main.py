import csv

# Open the dataset
with open("questions.csv", "r", encoding="utf-8-sig", newline="") as file:
    reader = csv.DictReader(file)

    questions = list(reader)

# Display dataset information
print("Total questions:", len(questions))

# Display the first question
print("\nFirst question:")
print(questions[0])

# Display all question IDs and variants

for question in questions:
    print(question["id"], "-", question["variant"])


# Count each variant

original_count = 0
paraphrased_count = 0
typo_count = 0

for question in questions:
    if question["variant"] == "original":
        original_count += 1

    elif question["variant"] == "paraphrased":
        paraphrased_count += 1

    elif question["variant"] == "typo":
        typo_count += 1

print("Original:", original_count)
print("Paraphrased:", paraphrased_count)
print("Typo:", typo_count)


# Count questions by category

logical_count = 0
deductive_count = 0
constraint_count = 0

for question in questions:
    if question["category"] == "logical":
        logical_count += 1

    elif question["category"] == "deductive":
        deductive_count += 1

    elif question["category"] == "constraint":
        constraint_count += 1

print("\nQuestions by category:")
print("Logical:", logical_count)
print("Deductive:", deductive_count)
print("Constraint:", constraint_count)


# Prepare the first question as a prompt

question = questions[0]

prompt = question["question"] + "\n\n"

prompt += "A. " + question["choice_A"] + "\n"
prompt += "B. " + question["choice_B"] + "\n"
prompt += "C. " + question["choice_C"] + "\n"
prompt += "D. " + question["choice_D"] + "\n"

prompt += "\nAnswer with only A, B, C, or D."

print("\nExample prompt:")
print(prompt)