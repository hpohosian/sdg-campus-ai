from api.llm.mistral import MistralLLM


def main():
    llm = MistralLLM()

    messages = [
        {"role": "system", "content": "You are a useful AI assistant."},
        {"role": "user", "content": "Explain what Python is in two sentences."}
    ]

    response = llm.generate(
        messages,
        temperature=0.7
    )

    print("Model response:\n")
    print(response)


if __name__ == "__main__":
    main()
    