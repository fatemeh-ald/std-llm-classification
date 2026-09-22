# Security Technical Debt Classification Prompt

This repository provides the prompt used in experiments for detecting and classifying Security Technical Debt (STD) in software issue comments using Large Language Models (LLMs).

## Prompt

The complete prompt used in the experiments is available in the following file:

`prompt.txt`

The prompt was designed to classify issue comments into:

- **Security Technical Debt**
- **Not Security Technical Debt**

For comments classified as Security Technical Debt, the prompt also asks the model to identify the relevant **Common Weakness Enumeration (CWE)** when sufficient evidence is available.

## Models

The prompt was used with multiple Large Language Models, including:

- Claude
- GPT
- DeepSeek
